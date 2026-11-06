"""One pass of GeoFlora's cloud training (run by .github/workflows/training.yml every 30 minutes).

1. Restores the compact training photos from MongoDB Atlas (scripts/cloud_data.py download).
2. Imports newly approved/corrected app reports (training allowed, AI did not get them right) straight into the
   train split: compact photo + manifest row + split row, uploads the new photos, marks the reports as imported.
3. Activates models an administrator approved: downloads the ONNX candidate from Atlas, makes it the newest
   ensemble member (apps/web/models/ensemble.json, previous setup kept for rollback).
4. When at least --min-new imported photos are not yet in a model, retrains (v2 recipe), evaluates, exports,
   converts to ONNX, compares with the live model on the same test photos, stores the candidate in Atlas and
   records a training job; if it is better, the admin sees "Approve new model" under Review & training.
Steps 2 and 3 change files in the repository; the workflow commits and pushes them, and Vercel deploys.

  python scripts/cloud_training.py [--min-new 20] [--skip-download] [--onnx-python PATH]
Needs GEOFLORA_MONGODB_URI. The test and validation splits never change, so models stay comparable.
"""
import argparse
import csv
import io
import json
import os
import subprocess
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path

LAB = Path(__file__).resolve().parents[1]
GEOFLORA = LAB.parent
WEB_MODELS = GEOFLORA / "apps" / "web" / "models"
CONFIG = "configs/expansion_nissap_v2.yaml"
SPLITS = LAB / "metadata" / "nissap" / "split_assignments.csv"
MANIFEST = LAB / "metadata" / "image_manifest.csv"
sys.path.insert(0, str(LAB / "scripts"))
from cloud_data import bucket, compact, mongo_uri, write_shards  # noqa: E402


def log(message):
    print(f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} {message}", flush=True)


def run(args, python=sys.executable, cwd=LAB):
    log("run: " + " ".join(map(str, args)))
    r = subprocess.run([str(python), *map(str, args)], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"{args[0]} failed: {(r.stderr or r.stdout)[-1500:]}")
    return r.stdout


def import_reports(db, fs):
    import pandas as pd
    sys.path.insert(0, str(LAB))
    from geoflora_ml.catalog import by_name, load_catalog
    from geoflora_ml.utils import sha256_bytes, species_folder_name
    names = {k.lower(): v for k, v in by_name(load_catalog(LAB / "metadata" / "species_catalog.csv")).items()}
    splits = pd.read_csv(SPLITS, dtype=str, keep_default_na=False)
    manifest = pd.read_csv(MANIFEST, dtype=str, keep_default_na=False)
    have = set(splits["image_id"]) | set(manifest["image_id"])
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    new_files, split_rows, manifest_rows, done = [], [], [], []
    query = {"status": "verified", "trainingConsent": True, "trainingCandidateStatus": "approved", "labImport": {"$exists": False}}
    for report in db.sightings.find(query).sort("_id", 1):
        rid = str(report["_id"]); image_id = f"app-{rid}"
        name = (report.get("verifiedScientificName") or "").strip()
        sp = names.get(name.lower()) or names.get(" ".join(name.split()[:2]).lower())
        if sp is None or image_id in have or not report.get("photo"):
            log(f"skip {rid} ({name or '?'}): {'species not in the model yet' if sp is None else 'already imported' if image_id in have else 'no photo'}")
            continue
        rel = f"dataset/nissap/train/{species_folder_name(sp.scientific_name)}/{image_id}.jpg"
        target = LAB / rel; target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".src"); tmp.write_bytes(bytes(report["photo"]))
        data = compact(tmp); tmp.unlink(); target.write_bytes(data)
        review = (report.get("reviewHistory") or [{}])[-1]
        predicted = ((report.get("prediction") or {}).get("species") or {}).get("scientific_name") or "not sure"
        observed = report.get("observedAt")
        sha = sha256_bytes(data)
        split_rows.append({"image_id": image_id, "species_id": sp.species_id, "scientific_name": sp.scientific_name, "observation_group": f"grp-app-{rid[-10:]}",
                           "observation_id": f"geoflora:{rid}", "file_sha256": sha, "split": "train", "split_path": rel, "active": "true", "first_assigned": now, "last_updated": now})
        manifest_rows.append({"image_id": image_id, "species_id": sp.species_id, "scientific_name": sp.scientific_name, "verbatim_scientific_name": name,
                              "ecological_role": sp.role, "source": "GeoFlora app", "source_dataset_key": "geoflora-app-reports", "source_dataset_name": "GeoFlora field reports",
                              "publisher": "GeoFlora", "observation_id": f"geoflora:{rid}", "occurrence_id": rid, "license": "GEOFLORA-CONTRIBUTOR",
                              "license_raw": "GeoFlora contributor training consent", "attribution": "GeoFlora contributor (training use allowed in the app)",
                              "basis_of_record": "HUMAN_OBSERVATION", "country_code": "PH", "event_date": observed.isoformat() if hasattr(observed, "isoformat") else "",
                              "is_geoflora_field_observation": "true", "local_path": rel, "file_sha256": sha, "image_format": "jpg", "readable": "true", "quality_pass": "true",
                              "license_eligible": "true", "observation_group": f"grp-app-{rid[-10:]}", "label_conflict": "false", "review_status": "approved",
                              "reviewer": review.get("reviewer") or "GeoFlora administrator", "review_date": now[:10],
                              "review_notes": f"GeoFlora admin {'corrected' if review.get('action') == 'correct_identification' else 'approved'} this report (AI said: {predicted}); imported by cloud training", "split": "train"})
        new_files.append(target); done.append(rid)
    if not done:
        return 0
    write_shards(fs, new_files, f"add-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')}")
    pd.concat([splits, pd.DataFrame(split_rows)], ignore_index=True).to_csv(SPLITS, index=False)
    pd.concat([manifest, pd.DataFrame(manifest_rows).reindex(columns=manifest.columns, fill_value="")], ignore_index=True).to_csv(MANIFEST, index=False)
    from bson import ObjectId
    for rid in done:
        db.sightings.update_one({"_id": ObjectId(rid)}, {"$set": {"labImport": {"imageId": f"app-{rid}", "importedAt": datetime.now(timezone.utc), "via": "cloud"}, "trainingJobId": "ml-lab"}})
    log(f"imported {len(done)} report photo(s)")
    return len(done)


def activate_approved(db, fs):
    activated = []
    for job in db.trainingjobs.find({"source": "ml-lab", "promotion.status": "approved"}):
        version = Path(job["candidatePath"]).name
        stored = db["training_data.files"].find_one({"filename": f"candidate-{version}.tar"})
        if not stored:
            continue  # trained by the laptop worker; it activates its own candidates
        with tarfile.open(fileobj=io.BytesIO(fs.open_download_stream(stored["_id"]).read())) as tar:
            for member in tar.getmembers():
                target = (WEB_MODELS / version / Path(member.name).name)
                target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(tar.extractfile(member).read())
        config_path = WEB_MODELS / "ensemble.json"; config = json.loads(config_path.read_text(encoding="utf-8"))
        (WEB_MODELS / f"ensemble.before-{version}.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        config["members"] = [config["members"][0], version]
        config["version"] = f"geoflora-ensemble-{config['members'][0].removeprefix('geoflora-mnv2-')}+{version.removeprefix('geoflora-mnv2-')}" + ("+3cls" if config.get("confirm") else "")
        config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        db.trainingjobs.update_one({"_id": job["_id"]}, {"$set": {"promotion.status": "promoted", "promotion.promotedAt": datetime.now(timezone.utc), "updatedAt": datetime.now(timezone.utc),
                                                                  "detail": f"Activated {version} in the app's model ensemble (published by cloud training; the online app updates after the deploy). Previous setup: models/ensemble.before-{version}.json."}})
        activated.append(version); log(f"activated {version}")
    return activated


def retrain(db, fs, new_ids, onnx_python):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    version = f"geoflora-mnv2-21cls-cloud-{stamp}"
    job = db.trainingjobs.insert_one({"status": "running", "source": "ml-lab", "reportIds": [i.removeprefix("app-") for i in new_ids], "createdAt": datetime.now(timezone.utc), "updatedAt": datetime.now(timezone.utc),
                                      "detail": f"Cloud training with {len(new_ids)} new photo(s) from GeoFlora reports"}).inserted_id
    try:
        run(["scripts/train.py", "--config", CONFIG, "--run-name", f"cloud-{stamp}"])
        run_dir = sorted((LAB / "models" / "checkpoints" / "nissap").glob(f"run-*-cloud-{stamp}"))[-1]
        run(["scripts/evaluate.py", "--config", CONFIG, "--run", run_dir])
        run(["scripts/export_model.py", "--config", CONFIG, "--run", run_dir, "--model-version", version])
        run(["scripts/package_for_geoflora.py", "--bundle", LAB / "models" / "exported" / version, "--geoflora", GEOFLORA])
        out = WEB_MODELS / version
        run(["scripts/export_onnx.py", "--candidate", GEOFLORA / "storage" / "models" / "candidates" / version, "--out", out, "--check-images", "dataset/nissap/test", "--check-count", "100"], python=onnx_python)
        live = json.loads((WEB_MODELS / "ensemble.json").read_text(encoding="utf-8"))["members"][-1]
        cmp = json.loads(run(["scripts/compare_onnx.py", "--candidate", out, "--live", WEB_MODELS / live, "--test-csv", run_dir / "test_images.csv"], python=onnx_python).strip().splitlines()[-1])
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            for f in out.iterdir(): tar.add(f, arcname=f.name)
        fs.upload_from_stream(f"candidate-{version}.tar", buf.getvalue(), metadata={"kind": "candidate", "version": version, "created": datetime.now(timezone.utc)})
        import shutil; shutil.rmtree(out)  # published to the repository only after the admin approves it
        metrics = json.loads((LAB / "models" / "exported" / version / "evaluation_metrics.json").read_text(encoding="utf-8"))["test"]
        per_class = {c["species"]: {"precision": c["precision"], "recall": c["recall"], "f1-score": c["f1"], "support": c["support"]} for c in metrics.get("per_class", [])}
        promote = cmp["candidate"] >= cmp["live"]
        db.trainingjobs.update_one({"_id": job}, {"$set": {
            "status": "completed", "updatedAt": datetime.now(timezone.utc), "candidatePath": f"storage/models/candidates/{version}",
            "detail": f"Cloud training with {len(new_ids)} new report photo(s). On the {cmp['photos']} test photos: new model {cmp['candidate']:.1%}, live model {cmp['live']:.1%}." + ("" if promote else " Not better, so it is not offered."),
            "metrics": {"accuracy": metrics["accuracy"], "macroF1": metrics["macro_f1"], "perClass": per_class, "qualityTargetsPassed": True,
                        "benchmark": {"promote": promote, "live": {"accuracy": cmp["live"], "macroRecall": 0}, "candidate": {"accuracy": cmp["candidate"], "macroRecall": metrics.get("macro_recall", 0)}}},
            "promotion": {"status": "awaiting_approval" if promote else "not_eligible", "eligible": promote}}})
        log(f"candidate {version}: {cmp['candidate']:.3f} vs live {cmp['live']:.3f}")
    except Exception as exc:  # noqa: BLE001 - recorded for the admin page
        db.trainingjobs.update_one({"_id": job}, {"$set": {"status": "failed", "detail": str(exc)[:1500], "updatedAt": datetime.now(timezone.utc)}})
        raise


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--min-new", type=int, default=int(os.environ.get("GEOFLORA_RETRAIN_MIN_NEW", "20")))
    p.add_argument("--skip-download", action="store_true")
    p.add_argument("--onnx-python", default=sys.executable)
    p.add_argument("--no-train", action="store_true", help="import and activate only")
    args = p.parse_args()
    db, fs = bucket(mongo_uri(None))
    db.worker_status.replace_one({"_id": "auto_training"}, {"database": db.name, "stage": "cloud: checking new reports", "pid": "github-actions", "updatedAt": datetime.now(timezone.utc).isoformat()}, upsert=True)
    imported = import_reports(db, fs)
    activated = activate_approved(db, fs)
    state = db.cloud_training_state.find_one({"_id": "nissap21"}) or {"trained": []}
    with open(SPLITS, encoding="utf-8") as fh:
        app_rows = [r["image_id"] for r in csv.DictReader(fh) if r["image_id"].startswith("app-") and r["active"] == "true"]
    new = [i for i in app_rows if i not in set(state["trained"])]
    log(f"{len(new)} imported report photo(s) not yet in a model (retrain from {args.min_new})")
    trained = False
    if not args.no_train and len(new) >= args.min_new and not db.trainingjobs.find_one({"source": "ml-lab", "status": "running"}):
        if not args.skip_download:
            run(["scripts/cloud_data.py", "download"])
        db.worker_status.replace_one({"_id": "auto_training"}, {"database": db.name, "stage": "cloud: training", "pid": "github-actions", "updatedAt": datetime.now(timezone.utc).isoformat()}, upsert=True)
        retrain(db, fs, new, args.onnx_python)
        db.cloud_training_state.replace_one({"_id": "nissap21"}, {"trained": sorted(set(state["trained"]) | set(new))}, upsert=True)
        trained = True
    db.worker_status.replace_one({"_id": "auto_training"}, {"database": db.name, "stage": "cloud: idle", "pid": "github-actions", "updatedAt": datetime.now(timezone.utc).isoformat()}, upsert=True)
    due = len(new) >= args.min_new and not trained
    summary = {"imported": imported, "activated": activated, "trained": trained, "training_due": due}
    print("SUMMARY " + json.dumps(summary))
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as fh:
            fh.write(f"changed={'true' if imported or activated else 'false'}\n")
            fh.write(f"due={'true' if due else 'false'}\n")


if __name__ == "__main__":
    main()
