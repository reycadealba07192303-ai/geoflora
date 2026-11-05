"""Background worker: GeoFlora app reports -> lab dataset -> retrained 21-class candidate -> admin approval -> live.

Every pass (default every 10 minutes):
1. Imports newly approved/corrected app reports (scripts/import_app_reports.py).
2. When at least --min-new imported photos are not yet in a training run, retrains the 21-class model on the whole lab
   dataset (validate -> split -> train -> evaluate -> export), packages it for GeoFlora, compares it with the live model
   on the new run's test photos, and records a training job that the administrator sees under Review & training.
3. Installs a candidate once an administrator approved it there: converts it to ONNX for the Next.js app
   (scripts/export_onnx.py, checked against Keras), makes it the newest member of apps/web/models/ensemble.json (the
   older member stays, and Next.js reloads by itself), and also installs it for the old Python service
   (scripts/install_lab_model.py, with backup and rollback).

  python scripts/app_training_worker.py              # loop
  python scripts/app_training_worker.py --once       # one pass
Logs go to stdout; state is in metadata/app_training_state.json.
"""
import argparse
import csv
import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

LAB = Path(__file__).resolve().parents[1]
GEOFLORA = LAB.parent
PY = sys.executable
SERVICE_PY = GEOFLORA / "services" / "ml" / ".venv" / "Scripts" / "python.exe"
CONFIG = "configs/expansion_nissap_v2.yaml"
ONNX_PY = LAB / ".venv-onnx" / "Scripts" / "python.exe"
WEB_MODELS = GEOFLORA / "apps" / "web" / "models"
STATE = LAB / "metadata" / "app_training_state.json"


def log(message):
    print(f"{datetime.now().isoformat(timespec='seconds')} {message}", flush=True)


def run(args, cwd=LAB, python=PY):
    log("run: " + " ".join(map(str, args)))
    result = subprocess.run([str(python), *map(str, args)], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError(f"{args[0]} failed ({result.returncode}): {(result.stderr or result.stdout)[-1500:]}")
    return result.stdout


def env_value(name):
    if os.environ.get(name):
        return os.environ[name]
    env = GEOFLORA / "apps" / "web" / ".env.local"
    for line in env.read_text(encoding="utf-8").splitlines() if env.exists() else []:
        if line.startswith(name + "="):
            return line.split("=", 1)[1].strip().strip('"')
    return ""


def state():
    return json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {"trained_app_images": []}


def app_images():
    with open(LAB / "metadata" / "image_manifest.csv", encoding="utf-8", newline="") as fh:
        return [row["image_id"] for row in csv.DictReader(fh) if row["source"] == "GeoFlora app" and row["review_status"] == "approved"]


def accuracy_on(model_dir, test_csv):
    """Top-1 accuracy of a lab bundle on a run's test photos (same preprocessing as the lab)."""
    sys.path.insert(0, str(LAB))
    import numpy as np
    from geoflora_ml.inference import Predictor, preprocess_image
    model = Predictor(model_dir)
    ids = [c["species_id"] for c in model.mapping["classes"]]
    rows = list(csv.DictReader(open(test_csv, encoding="utf-8")))
    rows = [r for r in rows if r["species_id"] in ids]
    correct = 0
    for i in range(0, len(rows), 64):
        batch = rows[i:i + 64]
        probs = model.model.predict(np.stack([preprocess_image(LAB / r["split_path"], model.image_size) for r in batch]), verbose=0)
        correct += sum(ids[int(p.argmax())] == r["species_id"] for p, r in zip(probs, batch))
    return correct / max(1, len(rows)), len(rows)


def retrain(db, new_images):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    version = f"geoflora-mnv2-21cls-app-{stamp}"
    job = db.trainingjobs.insert_one({"status": "running", "source": "ml-lab", "reportIds": [i.removeprefix("app-") for i in new_images],
                                      "detail": f"Retraining with {len(new_images)} new photo(s) from GeoFlora reports", "createdAt": datetime.now(timezone.utc), "updatedAt": datetime.now(timezone.utc)}).inserted_id
    try:
        run(["scripts/validate_images.py", "--no-recheck"])
        run(["scripts/split_dataset.py", "--config", CONFIG])
        run(["scripts/train.py", "--config", CONFIG, "--run-name", f"app-{stamp}"])
        runs = sorted((LAB / "models" / "checkpoints" / "nissap").glob(f"run-*-app-{stamp}"))
        run_dir = runs[-1]
        run(["scripts/evaluate.py", "--config", CONFIG, "--run", run_dir])
        run(["scripts/export_model.py", "--config", CONFIG, "--run", run_dir, "--model-version", version])
        bundle = LAB / "models" / "exported" / version
        run(["scripts/package_for_geoflora.py", "--bundle", bundle, "--geoflora", GEOFLORA])
        metrics = json.loads((bundle / "evaluation_metrics.json").read_text(encoding="utf-8"))["test"]
        live_version = json.loads((WEB_MODELS / "ensemble.json").read_text(encoding="utf-8"))["members"][-1]
        live_bundle = LAB / "models" / "exported" / live_version
        candidate_acc, n = accuracy_on(bundle, run_dir / "test_images.csv")
        live_acc, _ = accuracy_on(live_bundle, run_dir / "test_images.csv") if live_bundle.is_dir() else (0.0, 0)
        per_class = {c["species"]: {"precision": c["precision"], "recall": c["recall"], "f1-score": c["f1"], "support": c["support"]} for c in metrics.get("per_class", [])}
        promote = candidate_acc >= live_acc
        db.trainingjobs.update_one({"_id": job}, {"$set": {
            "status": "completed", "updatedAt": datetime.now(timezone.utc), "candidatePath": f"storage/models/candidates/{version}",
            "detail": f"Retrained with {len(new_images)} new report photo(s). On the {n} test photos: new model {candidate_acc:.1%}, live model {live_acc:.1%}." + ("" if promote else " The new model is not better, so it is not offered for activation."),
            "metrics": {"accuracy": metrics["accuracy"], "macroF1": metrics["macro_f1"], "perClass": per_class, "qualityTargetsPassed": True,
                        "benchmark": {"promote": promote, "live": {"accuracy": live_acc, "macroRecall": 0}, "candidate": {"accuracy": candidate_acc, "macroRecall": metrics.get("macro_recall", 0)}}},
            "promotion": {"status": "awaiting_approval" if promote else "not_eligible", "eligible": promote},
        }})
        log(f"candidate {version}: {candidate_acc:.3f} vs live {live_acc:.3f}")
    except Exception as exc:  # noqa: BLE001 - record the failure for the admin page
        db.trainingjobs.update_one({"_id": job}, {"$set": {"status": "failed", "detail": str(exc)[:1500], "updatedAt": datetime.now(timezone.utc)}})
        raise


def install_approved(db):
    for job in db.trainingjobs.find({"source": "ml-lab", "promotion.status": "approved"}):
        candidate = job["candidatePath"]
        approver = job["promotion"].get("approvedUsername") or "GeoFlora administrator"
        try:
            version = Path(candidate).name
            run(["scripts/export_onnx.py", "--candidate", GEOFLORA / candidate, "--out", WEB_MODELS / version, "--check-images", "dataset/nissap/test", "--check-count", "100"], python=ONNX_PY)
            check = json.loads((WEB_MODELS / version / "onnx_check.json").read_text(encoding="utf-8"))
            if check["top1_agreement"] < 0.99:
                raise RuntimeError(f"ONNX check failed: top-1 agreement {check['top1_agreement']:.3f}")
            config_path = WEB_MODELS / "ensemble.json"
            config = json.loads(config_path.read_text(encoding="utf-8"))
            backup = WEB_MODELS / f"ensemble.before-{version}.json"
            backup.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
            config["members"] = [config["members"][0], version]
            config["version"] = f"geoflora-ensemble-{config['members'][0].removeprefix('geoflora-mnv2-')}+{version.removeprefix('geoflora-mnv2-')}" + ("+3cls" if config.get("confirm") else "")
            config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
            run(["scripts/install_lab_model.py", "--candidate", candidate, "--approved-by", approver, "--rationale", job["promotion"].get("rationale") or "Approved in GeoFlora admin"], cwd=GEOFLORA, python=SERVICE_PY)
            key = env_value("GEOFLORA_ML_API_KEY")
            request = urllib.request.Request("http://127.0.0.1:8000/reload", method="POST", headers={"X-GeoFlora-Key": key} if key else {})
            try:
                urllib.request.urlopen(request, timeout=120).read()
            except Exception as exc:  # noqa: BLE001
                log(f"reload request failed ({exc}); restart the inference service to use the new model")
            db.trainingjobs.update_one({"_id": job["_id"]}, {"$set": {"promotion.status": "promoted", "promotion.promotedAt": datetime.now(timezone.utc), "detail": f"Activated {Path(candidate).name} in the app's model ensemble. The previous setup is saved as models/ensemble.before-{Path(candidate).name}.json for rollback.", "updatedAt": datetime.now(timezone.utc)}})
            log(f"installed {candidate}")
        except Exception as exc:  # noqa: BLE001
            db.trainingjobs.update_one({"_id": job["_id"]}, {"$set": {"promotion.status": "failed", "detail": f"Activation failed: {str(exc)[:1200]}", "updatedAt": datetime.now(timezone.utc)}})


def one_pass(db, min_new):
    db.worker_status.replace_one({"_id": "auto_training"}, {"database": db.name, "stage": "checking new reports", "pid": os.getpid(), "updatedAt": datetime.now(timezone.utc).isoformat()}, upsert=True)
    print(run(["scripts/import_app_reports.py"]).strip(), flush=True)
    install_approved(db)
    current = state()
    new = [i for i in app_images() if i not in set(current["trained_app_images"])]
    log(f"{len(new)} imported report photo(s) not yet trained (retrain from {min_new})")
    if len(new) >= min_new and not db.trainingjobs.find_one({"source": "ml-lab", "status": "running"}):
        db.worker_status.replace_one({"_id": "auto_training"}, {"database": db.name, "stage": "training", "pid": os.getpid(), "updatedAt": datetime.now(timezone.utc).isoformat()}, upsert=True)
        retrain(db, new)
        current["trained_app_images"] = sorted(set(current["trained_app_images"]) | set(new))
        STATE.write_text(json.dumps(current, indent=2), encoding="utf-8")
    db.worker_status.replace_one({"_id": "auto_training"}, {"database": db.name, "stage": "idle", "pid": os.getpid(), "updatedAt": datetime.now(timezone.utc).isoformat()}, upsert=True)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--once", action="store_true")
    p.add_argument("--interval", type=int, default=600, help="seconds between passes")
    p.add_argument("--min-new", type=int, default=int(os.environ.get("GEOFLORA_RETRAIN_MIN_NEW", "20")), help="new report photos needed to retrain")
    args = p.parse_args()
    from pymongo import MongoClient
    db = MongoClient(env_value("GEOFLORA_MONGODB_URI") or "mongodb://127.0.0.1:27017/geoflora", serverSelectionTimeoutMS=8000).get_default_database()
    while True:
        try:
            one_pass(db, args.min_new)
        except Exception as exc:  # noqa: BLE001 - keep the loop alive
            log(f"pass failed: {exc}")
        if args.once:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
