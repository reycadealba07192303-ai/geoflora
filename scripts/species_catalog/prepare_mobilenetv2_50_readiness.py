from __future__ import annotations

"""Freeze a safe folder-based baseline and 50-slot research readiness inventory.

Only copies reviewed v3 baseline images after all historical-test protections.
Research candidates are reported, never promoted into training labels.
"""

import argparse
import csv
import hashlib
import json
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DATASETS = ROOT / "storage/datasets"
OUT = DATASETS / "experiments/geoflora_mobilenetv2_up_to_50_20261101"
V3 = DATASETS / "curated/v3"
MODEL_MAPPING = ROOT / "storage/models/candidates/mobilenetv2_v3_seed42/class_mapping.json"
QUEUE = ROOT / "docs/species_100_research_queue.csv"
LEDGER = ROOT / "docs/species_100_verification_ledger.csv"
READINESS = ROOT / "storage/species_catalog/exports/image_dataset_readiness.json"
sys.path.insert(0, str(ROOT / "services/ml/src"))
sys.path.insert(0, str(ROOT / "scripts"))

from geoflora_ml.collection.licensing import training_license_eligible  # noqa: E402
from auto_training_worker import benchmark_lookalike_filter  # noqa: E402
from model_promotion import _observation_keys, benchmark_hashes  # noqa: E402


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(row[key], ensure_ascii=False) if isinstance(row.get(key), (dict, list)) else row.get(key, "") for key in fields})


def inventory_baseline(out: Path, write_files: bool = True) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    metadata = read_json(V3 / "dataset_metadata.json")
    manifest_path = V3 / "manifest.csv"
    if digest(manifest_path) != metadata.get("manifest_sha256"):
        raise ValueError("Frozen v3 manifest checksum mismatch")
    mapping = read_json(MODEL_MAPPING)
    rows = read_csv(manifest_path)
    if any(row.get("review_status") != "approved" for row in rows):
        raise ValueError("v3 baseline contains records without explicit approved review status")
    if any(not training_license_eligible(row.get("license"), row.get("attribution")) for row in rows):
        raise ValueError("v3 baseline contains a photo outside the current strict training-license allowlist")

    held_hashes, held_groups = benchmark_hashes()
    near_test, save_hashes = benchmark_lookalike_filter()
    manifest_rows: list[dict[str, Any]] = []
    split_counts: dict[str, Counter[str]] = {key: Counter() for key in ("train", "val", "test")}
    excluded_rows = []
    class_ids = {item["id"] for item in mapping["classes"]}

    for row in rows:
        species_id = row["species_id"]
        if species_id not in class_ids:
            raise ValueError(f"Baseline row is not present in class_mapping.json: {species_id}")
        original_split = row["split"]
        target_split = "val" if original_split == "validation" else original_split
        source_path = (DATASETS / row["local_path"]).resolve()
        if not source_path.is_relative_to(DATASETS.resolve()) or not source_path.is_file() or digest(source_path) != row["sha256"]:
            raise ValueError(f"Baseline image path/checksum mismatch: {row['local_path']}")

        reason = ""
        if target_split in {"train", "val"}:
            if row["sha256"] in held_hashes:
                reason = "exact_historical_test_hash"
            elif _observation_keys(row) & held_groups:
                reason = "historical_test_observation_group"
            elif near_test(row["sha256"], source_path):
                reason = "perceptual_near_duplicate_of_historical_test"
        destination = ""
        if not reason and target_split != "test":
            suffix = source_path.suffix.lower() or ".jpg"
            relative = Path(target_split) / species_id / f"{row['sha256']}{suffix}"
            destination = relative.as_posix()
            if write_files:
                target_path = out / relative
                target_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_path, target_path)
                if digest(target_path) != row["sha256"]:
                    raise ValueError(f"Copied image checksum mismatch: {target_path}")
            split_counts[target_split][species_id] += 1
        elif target_split == "test":
            # Historical tests stay in their original immutable dataset. The
            # prepared expansion's test folders remain empty until new blind data exists.
            reason = "historical_test_reserved_not_copied_to_expansion"

        manifest_rows.append({**row, "prepared_split": target_split if not reason else "excluded", "prepared_path": destination, "excluded_reason": reason})
        if reason:
            excluded_rows.append({**row, "excluded_reason": reason})

    if write_files:
        save_hashes()
    if write_files:
        for split in ("train", "val", "test"):
            for species in mapping["classes"]:
                (out / split / species["id"]).mkdir(parents=True, exist_ok=True)
    if set(split_counts["train"]) != class_ids:
        raise ValueError("The safe prepared training folder lost an existing baseline class")

    summary = {
        "source_dataset": "storage/datasets/curated/v3",
        "source_manifest_sha256": digest(manifest_path),
        "source_images": len(rows),
        "source_split_counts": {key: dict(Counter(row["species_id"] for row in rows if row["split"] == ("validation" if key == "val" else key))) for key in ("train", "val", "test")},
        "prepared_safe_training_images": sum(split_counts["train"].values()),
        "prepared_safe_validation_images": sum(split_counts["val"].values()),
        "prepared_test_images": 0,
        "prepared_per_class": {species["id"]: {split: split_counts[split][species["id"]] for split in ("train", "val", "test")} for species in mapping["classes"]},
        "excluded_reason_counts": dict(Counter(row["excluded_reason"] for row in excluded_rows)),
        "class_mapping": mapping,
        "historical_test_hashes_held_out": len(held_hashes),
        "historical_test_group_keys_held_out": len(held_groups),
    }
    if write_files:
        write_csv(out / "source_manifest.csv", manifest_rows, list(rows[0].keys()) + ["prepared_split", "prepared_path", "excluded_reason"])
        write_csv(out / "excluded_from_development.csv", excluded_rows, list(rows[0].keys()) + ["excluded_reason"])
        (out / "class_mapping.json").write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary, rows


def proposed_roster(mapping: dict[str, Any], readiness: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    queue = read_csv(QUEUE)
    ledger = {row["source_taxon_id"]: row for row in read_csv(LEDGER)}
    baseline_names = {item["scientific_name"].casefold() for item in mapping["classes"]}
    # The current Water Hyacinth taxon appears under the synonym Eichhornia crassipes
    # in the old research queue; never create a duplicate class for it.
    baseline_names.add("eichhornia crassipes")
    stage_index = {key.casefold(): value for key, value in readiness["staging"]["species"].items()}

    baseline = []
    for order, species in enumerate(mapping["classes"], 1):
        baseline.append({
            "slot": order,
            "scientific_name": species["scientific_name"],
            "class_id": species["id"],
            "role": "existing_invasive_baseline",
            "source_evidence": "existing curated v3 owner-attested labels; ecological source records retained in v3",
            "ecological_approval": "existing_baseline_only_not_independent_expert_certification",
            "stage_candidate_records": 0,
            "stage_unique_images": 0,
            "stage_observation_groups": 0,
            "stage_license_eligible_after_holdout": 0,
            "training_ready_addition": False,
        })

    candidates = []
    for row in queue:
        name = row["search_name_candidate"].strip()
        if name.casefold() in baseline_names:
            continue
        evidence = ledger.get(row["source_taxon_id"], {})
        screen = evidence.get("ecology_screen_status", "unresolved")
        bucket = row.get("evidence_bucket", "")
        botanical_context = str(evidence.get("cdfp_annotations", "")).casefold()
        ambiguous_status = screen in {"native_status_conflict_hold", "origin_uncertain_hold", "exact_record_unresolved"} or any(term in botanical_context for term in ("cryptogenic", "native status conflict", "uncertain origin"))
        # Avoid native/origin conflicts and unresolved exact names in this proposed
        # roster. They remain in the full source queue, not in a target model plan.
        if ambiguous_status:
            continue
        if bucket == "source_flagged_invasive":
            priority = 0
            role = "source_flagged_invasive_pending_ecological_approval"
        else:
            priority = 1
            role = "introduced_species_invasive_status_unverified"
        image = stage_index.get(name.casefold(), {})
        candidates.append({
            "scientific_name": name,
            "class_id": "",
            "role": role,
            "source_taxon_id": row.get("source_taxon_id"),
            "source_url": row.get("source_url"),
            "source_doi": row.get("source_doi"),
            "source_license": row.get("source_license"),
            "source_evidence_bucket": bucket,
            "ecology_screen_status": screen,
            "ecological_approval": evidence.get("ecological_approval", "not_granted"),
            "candidate_records": image.get("candidate_records", 0),
            "unique_exact_images": image.get("unique_exact_images", 0),
            "unique_observation_groups": image.get("unique_observation_groups", 0),
            "license_eligible_excluding_historical_test": image.get("license_eligible_unique_images_excluding_historical_test", 0),
            "explicit_human_approved_images": image.get("explicit_human_approved_images_with_reviewer_and_rationale", 0),
            "training_ready_addition": False,
            "next_action": evidence.get("next_action", "verify_taxonomy_ecology_and_images"),
            "selection_priority": priority,
        })
    candidates.sort(key=lambda item: (item["selection_priority"], -int(item["license_eligible_excluding_historical_test"]), -int(item["unique_observation_groups"]), item["scientific_name"].casefold()))
    chosen = candidates[:47]
    proposed = baseline + [{"slot": index + 4, **item} for index, item in enumerate(chosen)]
    return proposed, {"available_research_candidates_after_conflict_holds": len(candidates), "proposed_new_class_slots": len(chosen), "unfilled_slots_under_50": 50 - len(proposed)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUT)
    parser.add_argument("--check-only", action="store_true", help="Compute readiness without creating the folder dataset")
    args = parser.parse_args()
    out = args.output.resolve()
    if not out.is_relative_to((DATASETS / "experiments").resolve()) or (out.exists() and not args.check_only):
        raise ValueError("Choose a new output directory under storage/datasets/experiments")
    if not args.check_only:
        out.mkdir(parents=True)
    mapping = read_json(MODEL_MAPPING)
    image_readiness = read_json(READINESS)
    baseline, _ = inventory_baseline(out, write_files=not args.check_only)
    roster, roster_counts = proposed_roster(mapping, image_readiness)
    if args.check_only:
        print(json.dumps({"baseline": baseline, "roster": roster_counts, "selected_new_candidates": [item["scientific_name"] for item in roster if item.get("slot", 0) > 3]}, ensure_ascii=False, indent=2))
        return 0
    roster_fields = list(dict.fromkeys(key for item in roster for key in item))
    write_csv(out / "proposed_50_species_roster.csv", roster, roster_fields)

    eligible_new_classes = sum(1 for item in roster if item.get("training_ready_addition"))
    train_config = {
        "version": "geoflora_mobilenetv2_up_to_50_20261101",
        "maximum_classes": 50,
        "actual_class_count_in_mapping": len(mapping["classes"]),
        "actual_class_ids_in_mapping": [item["id"] for item in mapping["classes"]],
        "eligible_new_classes": eligible_new_classes,
        "training_enabled": False,
        "not_started_reason": "No additional candidate has project ecological approval and explicit label/license review; the strictly holdout-filtered baseline validation split lacks Pontederia; no untouched independent test set is available.",
        "architecture": {
            "backbone": "ImageNet-pretrained MobileNetV2",
            "input_shape": [224, 224, 3],
            "preprocessing": "geoflora_ml.inference.preprocess.preprocess_rgb_batch",
            "classification_head": "Dropout(0.2) + Dense(num_classes, softmax)",
            "num_classes_rule": "len(class_mapping.classes); never fixed to maximum_classes",
        },
        "training_recipe_from_existing_pipeline": {
            "entry_point": "scripts/train_expanded.py --frozen-dataset <new reviewed curated dataset> --output <new candidate>",
            "batch_size": 16,
            "max_epochs": 60,
            "optimizer": "Adam, learning rate 0.001 for a new head",
            "class_balance": "inverse-frequency sample weights from train split",
            "augmentation": "TRAIN_ONLY_AUGMENTATION, train split only",
            "checkpoint_selection": "minimum validation cross-entropy",
            "early_stopping_patience": 8,
            "backbone_fine_tuning": "optional only after validation evidence; retain only if validation loss improves",
            "random_seed": 42,
        },
        "split_policy": {
            "train_val": "observation/group-aware existing v3 partitions, then exclude every exact hash, normalized group, or perceptual near-match to all historical test partitions",
            "test": "empty pending new independently sourced, human-reviewed Philippine field observations; do not reuse historical v3/v5/11-class tests for model selection",
            "lookalikes": "separate role and evidence; not included in the invasive baseline class map",
        },
        "baseline_safe_split_counts": baseline,
        "research_roster_counts": roster_counts,
        "active_model": "mobilenetv2_v3_seed42 remains unchanged",
    }
    (out / "training_config.json").write_text(json.dumps(train_config, ensure_ascii=False, indent=2), encoding="utf-8")
    readme = """# GeoFlora MobileNetV2 up-to-50 readiness dataset\n\nThis is a preparation snapshot, not a trainable expanded model. `train/` and `val/` contain only v3 baseline images that pass the current strict license/review checks and have no exact, observation-group, or perceptual overlap with any curated historical test partition. `test/` is deliberately empty: a fresh blind test set is required.\n\n`source_manifest.csv` preserves the original v3 records and marks excluded rows. `proposed_50_species_roster.csv` is a research shortlist; the 47 candidate additions are not verified target classes and are not in `class_mapping.json`. Use `training_config.json`; it records the existing MobileNetV2 recipe and why training is currently disabled. Never point training at `excluded_from_development.csv` or the historical test manifests.\n"""
    (out / "README.md").write_text(readme, encoding="utf-8")
    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "output": str(out.relative_to(ROOT)),
        "folder_counts": {split: {species["id"]: sum(1 for _ in (out / split / species["id"]).glob("*.*")) for species in mapping["classes"]} for split in ("train", "val", "test")},
        "training_enabled": False,
        "baseline": baseline,
        "roster": roster_counts,
        "limitations": ["No candidate addition has ecological approval in the research ledger.", "All source-batch image labels remain pending; source research grade is not independent botanical verification.", "A fresh blind test set is not available.", "Strict historical-test filtering leaves no Pontederia validation images in the baseline folder export."],
    }
    (out / "dataset_readiness.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
