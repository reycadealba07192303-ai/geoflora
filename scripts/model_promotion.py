"""Evaluate experimental candidates, promote only with recorded admin approval, and preserve rollback artifacts.

A candidate replaces the live model only when all of these hold:
  * it passed the training quality targets (checked by the caller),
  * it supports every species the live model supports,
  * on the fixed benchmark it is at least as accurate as the live model, with macro recall at least as high.

The fixed comparison benchmark is the frozen v5 test split restricted to the live model's species. Automatic training
jobs never train on any curated historical test hash or observation group (see auto_training_worker.freeze_job).
The live v3 model may have seen some promotion-benchmark photos during its own training, which favours keeping it,
so promotion remains conservative rather than optimistic.

A promoted model carries its served-species list (species.yaml beside the model, with each species' role: "invasive" or
"lookalike"), so species it learned that were not served before, such as a non-invasive look-alike group, become
servable with it. Its quality gate already required at least 80% recall for every one of its classes.
"""
import csv
import json
import os
import shutil
import urllib.request

import yaml
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "storage/datasets/curated/v5_part2_final_five_classes"
LIVE = ROOT / "storage/models"
LIVE_FILES = ("mobilenetv2.keras", "class_mapping.json", "active_model.json", "species.yaml", "evaluation.json")
PACKAGED_SPECIES = ROOT / "services/ml/src/geoflora_ml/species.yaml"
INFERENCE = os.environ.get("GEOFLORA_ML_API_URL", "http://127.0.0.1:8000")


def benchmark_rows():
    with (BENCHMARK / "manifest.csv").open(encoding="utf-8", newline="") as stream:
        return [row for row in csv.DictReader(stream) if row["split"] == "test"]


def historical_test_rows():
    """Rows from every immutable curated test partition, used only to guard future training data."""
    rows = []
    for manifest in sorted((ROOT / "storage/datasets/curated").rglob("manifest.csv")):
        try:
            with manifest.open(encoding="utf-8-sig", newline="") as stream:
                rows.extend(row for row in csv.DictReader(stream) if row.get("split") == "test")
        except (OSError, UnicodeError, csv.Error):
            continue
    return rows


def _observation_keys(row):
    """Normalize dataset-specific class prefixes while retaining provider observation identity."""
    keys = set()
    for field in ("group_id", "observation_id"):
        value = str(row.get(field) or "").strip()
        if not value:
            continue
        keys.add(value)
        parts = value.split(":")
        for index in range(1, len(parts)):
            keys.add(":".join(parts[index:]))
        keys.add(parts[-1])
    return keys


def benchmark_hashes():
    """Exact files and observation groups held out from all automatic candidate training."""
    rows = historical_test_rows()
    held_hashes = {str(row.get("sha256")) for row in rows if row.get("sha256")}
    held_groups = set().union(*(_observation_keys(row) for row in rows)) if rows else set()
    # Perceptual groups are recomputed for each version, so the worker applies pHash
    # matching across historical test images instead of comparing version-local IDs.
    return held_hashes, held_groups


def candidate_promotion_decision(quality_passed: bool, comparison: dict | None = None):
    """Automated checks may label a candidate eligible, but never authorize activation."""
    if not quality_passed:
        return {"status": "not_eligible", "eligible": False, "reason": "Candidate quality gates failed"}
    if not comparison or comparison.get("promote") is not True:
        return {"status": "not_eligible", "eligible": False, "reason": (comparison or {}).get("reason", "Candidate comparison is missing")}
    return {"status": "awaiting_approval", "eligible": True}


def score(predictor, rows):
    correct, per_class = 0, {}
    for row in rows:
        result = predictor.predict((ROOT / row["local_path"]).read_bytes())
        top = result.candidates[0]["species"]["id"]
        hit = top == row["species_id"]
        correct += hit
        seen = per_class.setdefault(row["species_id"], [0, 0])
        seen[0] += hit
        seen[1] += 1
    recalls = {species: hits / total for species, (hits, total) in per_class.items()}
    return {"images": len(rows), "accuracy": correct / len(rows) if rows else 0.0, "macroRecall": sum(recalls.values()) / len(recalls) if recalls else 0.0, "recall": recalls}


def served_species(candidate_dir: Path):
    """Write the candidate's served-species list: what is served now, plus the candidate's classes and their roles."""
    current = LIVE / "species.yaml" if (LIVE / "species.yaml").exists() else PACKAGED_SPECIES
    served = {entry["id"]: {"role": "invasive", **entry} for entry in yaml.safe_load(current.read_text(encoding="utf-8"))["species"]}
    for entry in json.loads((candidate_dir / "class_mapping.json").read_text())["classes"]:
        served[entry["id"]] = {"id": entry["id"], "scientific_name": entry["scientific_name"], "common_name": entry["common_name"], "role": entry.get("role", "invasive")}
    (candidate_dir / "species.yaml").write_text(yaml.safe_dump({"species": list(served.values())}, sort_keys=False, allow_unicode=True), encoding="utf-8")


def compare(candidate_dir: Path):
    from geoflora_ml.inference.predictor import PlantPredictor

    served_species(candidate_dir)

    live = PlantPredictor(model_path=LIVE / "mobilenetv2.keras", class_mapping_path=LIVE / "class_mapping.json")
    candidate = PlantPredictor(model_path=candidate_dir / "mobilenetv2.keras", class_mapping_path=candidate_dir / "class_mapping.json", confidence_threshold=live.confidence_threshold)
    if not live.ready:
        return {"promote": False, "reason": f"Live model is not loadable: {live.unavailable_reason}"}
    if not candidate.ready:
        return {"promote": False, "reason": f"Candidate cannot be served: {candidate.unavailable_reason}"}
    live_ids = {entry["id"] for entry in json.loads((LIVE / "class_mapping.json").read_text())["classes"]}
    candidate_ids = {entry["id"] for entry in json.loads((candidate_dir / "class_mapping.json").read_text())["classes"]}
    if not live_ids <= candidate_ids:
        return {"promote": False, "reason": f"Candidate drops live species: {sorted(live_ids - candidate_ids)}"}
    rows = [row for row in benchmark_rows() if row["species_id"] in live_ids]
    live_score, candidate_score = score(live, rows), score(candidate, rows)
    better = candidate_score["accuracy"] >= live_score["accuracy"] and candidate_score["macroRecall"] >= live_score["macroRecall"]
    reason = "Candidate matches or beats the live model on the fixed benchmark" if better else "Candidate is less accurate than the live model on the fixed benchmark"
    return {"promote": better, "reason": reason, "live": live_score, "candidate": candidate_score, "threshold": live.confidence_threshold}


def _reload():
    """Tells the classifier service to load the installed model: the local one, or the Hugging Face Space when
    GEOFLORA_ML_API_URL points there (the Space then downloads the model just published)."""
    headers = {name: value for name, value in (("X-GeoFlora-Key", os.environ.get("GEOFLORA_ML_API_KEY")), ("X-GeoFlora-Reload", os.environ.get("GEOFLORA_ML_RELOAD_TOKEN"))) if value}
    request = urllib.request.Request(f"{os.environ.get('GEOFLORA_ML_API_URL', INFERENCE).rstrip('/')}/reload", method="POST", headers=headers)
    with urllib.request.urlopen(request, timeout=300) as response:
        return json.loads(response.read())


def publish(message="Update served model"):
    """Uploads the live model files to the Hugging Face model repository the hosted service downloads from.

    Does nothing unless GEOFLORA_MODEL_REPO is set. The repository is created private; the Space reads it with its own
    HF_TOKEN secret. A file missing locally (species.yaml after a rollback to an older model) is removed there too.
    """
    repo = os.environ.get("GEOFLORA_MODEL_REPO")
    if not repo:
        return False
    from huggingface_hub import HfApi

    api = HfApi(token=os.environ.get("HF_TOKEN") or None)
    api.create_repo(repo, repo_type="model", private=True, exist_ok=True)
    api.upload_folder(repo_id=repo, repo_type="model", folder_path=LIVE, allow_patterns=list(LIVE_FILES), delete_patterns=list(LIVE_FILES), commit_message=message)
    return True


def file_sha256(path: Path):
    import hashlib
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def promote(candidate_dir: Path, job_id: str, metrics: dict, comparison: dict, approval: dict):
    """Install an admin-approved candidate, keeping a complete pre-promotion backup."""
    if approval.get("status") != "approved" or not approval.get("approvedBy") or not approval.get("rationale"):
        raise ValueError("Promotion requires a recorded administrator approval and rationale")
    if metrics.get("qualityTargetsPassed") is not True or comparison.get("promote") is not True:
        raise ValueError("Candidate must pass evaluation and live-model comparison gates before promotion")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = LIVE / "previous" / stamp
    backup.mkdir(parents=True)
    for name in LIVE_FILES:
        if (LIVE / name).exists():
            shutil.copy2(LIVE / name, backup / name)
    try:
        shutil.copy2(candidate_dir / "mobilenetv2.keras", LIVE / "mobilenetv2.keras")
        shutil.copy2(candidate_dir / "class_mapping.json", LIVE / "class_mapping.json")
        shutil.copy2(candidate_dir / "species.yaml", LIVE / "species.yaml")
        evaluation_path = candidate_dir / "evaluation.json"
        if not evaluation_path.is_file():
            raise FileNotFoundError("Candidate evaluation.json is required for promotion")
        shutil.copy2(evaluation_path, LIVE / "evaluation.json")
        evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
        evaluation_report = evaluation["classification_report"]
        evaluation_passed = evaluation["accuracy"] >= .85 and evaluation_report["macro avg"]["f1-score"] >= .85 and all(evaluation_report[name]["recall"] >= .80 for name in evaluation["class_order"])
        if not evaluation_passed or evaluation["accuracy"] != metrics.get("accuracy") or evaluation_report["macro avg"]["f1-score"] != metrics.get("macroF1"):
            raise ValueError("Candidate evaluation record does not match the approved metrics or quality gates")
        (LIVE / "active_model.json").write_text(json.dumps({
            "candidate": candidate_dir.name,
            "model_version": candidate_dir.name,
            "scope": "administrator-approved promotion after candidate evaluation",
            "activated_at": datetime.now(timezone.utc).isoformat(),
            "training_job": job_id,
            "classes": len(json.loads((candidate_dir / "class_mapping.json").read_text())["classes"]),
            "test_accuracy": metrics.get("accuracy"),
            "macro_f1": metrics.get("macroF1"),
            "evaluation_record": (LIVE / "evaluation.json").relative_to(ROOT).as_posix(),
            "candidate_evaluation_record": evaluation_path.relative_to(ROOT).as_posix(),
            "evaluation_sha256": file_sha256(evaluation_path),
            "model_sha256": file_sha256(candidate_dir / "mobilenetv2.keras"),
            "class_mapping_sha256": file_sha256(candidate_dir / "class_mapping.json"),
            "promotion_approval": {key: approval.get(key) for key in ("approvedBy", "approvedUsername", "approvedAt", "rationale")},
            "benchmark": comparison,
            "confidence_threshold": comparison["threshold"],
            "threshold_basis": "Inherited from the previous live model; not re-tuned for this candidate.",
            "previous": backup.relative_to(ROOT).as_posix(),
        }, indent=2), encoding="utf-8")
        publish(f"Promote {candidate_dir.name} (training job {job_id})")
        reloaded = _reload()
        return {"activated": True, "modelVersion": reloaded.get("model_version"), "backup": backup.relative_to(ROOT).as_posix()}
    except Exception as error:
        for name in LIVE_FILES:
            if (backup / name).exists():
                shutil.copy2(backup / name, LIVE / name)
            elif name in {"species.yaml", "evaluation.json"}:
                (LIVE / name).unlink(missing_ok=True)
        try:
            publish(f"Roll back to {backup.name}")
            _reload()
        except Exception:
            pass  # The service still holds the previous model in memory if the reload failed.
        return {"activated": False, "error": f"Promotion rolled back: {error}"[:500], "backup": backup.relative_to(ROOT).as_posix()}


def rollback(backup_dir: Path, reason: str):
    """Restore a preserved model snapshot; keep the outgoing version and record a rollback audit trail."""
    if not reason or not reason.strip():
        raise ValueError("A rollback reason is required")
    previous_root = (LIVE / "previous").resolve()
    source = backup_dir.resolve()
    if previous_root not in source.parents:
        raise ValueError("Rollback source must be a saved model snapshot under storage/models/previous")
    required = ("mobilenetv2.keras", "class_mapping.json", "active_model.json")
    if not source.is_dir() or any(not (source / name).is_file() for name in required):
        raise ValueError("Rollback snapshot is incomplete")
    snapshot_metadata = json.loads((source / "active_model.json").read_text(encoding="utf-8"))
    for metadata_key, filename in (("model_sha256", "mobilenetv2.keras"), ("class_mapping_sha256", "class_mapping.json"), ("evaluation_sha256", "evaluation.json")):
        expected = snapshot_metadata.get(metadata_key)
        if expected and (not (source / filename).is_file() or file_sha256(source / filename) != expected):
            raise ValueError(f"Rollback snapshot failed its {metadata_key} integrity check")
    snapshot_time = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    outgoing = LIVE / "previous" / f"pre_rollback_{snapshot_time}"
    outgoing.mkdir(parents=True, exist_ok=False)
    for name in LIVE_FILES:
        if (LIVE / name).is_file():
            shutil.copy2(LIVE / name, outgoing / name)
    current = json.loads((LIVE / "active_model.json").read_text(encoding="utf-8"))
    try:
        for name in required:
            shutil.copy2(source / name, LIVE / name)
        for name in ("species.yaml", "evaluation.json"):
            if (source / name).exists():
                shutil.copy2(source / name, LIVE / name)
            else:
                (LIVE / name).unlink(missing_ok=True)
        restored = json.loads((LIVE / "active_model.json").read_text(encoding="utf-8"))
        restored["rollback"] = {
            "performed_at": datetime.now(timezone.utc).isoformat(),
            "reason": reason.strip()[:1000],
            "from_model_version": current.get("model_version") or current.get("candidate"),
            "to_model_version": restored.get("model_version") or restored.get("candidate"),
            "restored_snapshot": source.relative_to(ROOT).as_posix(),
            "outgoing_snapshot": outgoing.relative_to(ROOT).as_posix(),
        }
        restored["previous"] = outgoing.relative_to(ROOT).as_posix()
        (LIVE / "active_model.json").write_text(json.dumps(restored, indent=2), encoding="utf-8")
        publish(f"Rollback to {restored.get('model_version') or restored.get('candidate')}")
        reloaded = _reload()
        return {"rolled_back": True, "modelVersion": reloaded.get("model_version"), "outgoingBackup": outgoing.relative_to(ROOT).as_posix(), "restoredSnapshot": source.relative_to(ROOT).as_posix()}
    except Exception as error:
        for name in LIVE_FILES:
            if (outgoing / name).is_file():
                shutil.copy2(outgoing / name, LIVE / name)
            elif name in {"species.yaml", "evaluation.json"}:
                (LIVE / name).unlink(missing_ok=True)
        try:
            publish(f"Restore {current.get('model_version') or current.get('candidate')} after rollback failure")
            _reload()
        except Exception:
            pass
        return {"rolled_back": False, "error": f"Rollback failed; outgoing model restored: {error}"[:1000], "outgoingBackup": outgoing.relative_to(ROOT).as_posix()}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Safely restore a previously promoted GeoFlora model snapshot")
    parser.add_argument("--rollback-to", required=True, help="Saved snapshot under storage/models/previous")
    parser.add_argument("--reason", required=True, help="Reason recorded in active_model.json")
    args = parser.parse_args()
    target = Path(args.rollback_to)
    if not target.is_absolute():
        target = ROOT / target
    result = rollback(target, args.reason)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result.get("rolled_back") else 1)
