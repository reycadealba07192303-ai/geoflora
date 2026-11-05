"""One isolated Next.js -> FastAPI -> review -> occurrence analytics smoke.

Uses one CC0 Nymphaea herbarium image as an unsupported/uncertain software
fixture. It is not an accuracy or field-photo evaluation. The disposable DB
is dropped in finally; no training consent/job is created.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import secrets
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests
from bson import ObjectId
from pymongo import MongoClient

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "apps/web"
PORT = 5176
BASE = f"http://127.0.0.1:{PORT}"
MODEL = ROOT / "storage/models/mobilenetv2.keras"
MAPPING = ROOT / "storage/models/class_mapping.json"
ACTIVE = ROOT / "storage/models/active_model.json"
SOURCE_FOLDER = ROOT / "storage/datasets/staging/lookalike_nymphaea_ph"
QUEUE = SOURCE_FOLDER / "review_queue.csv"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_fixture():
    with QUEUE.open(encoding="utf-8-sig", newline="") as f:
        rows = csv.DictReader(f)
        row = next(r for r in rows if r["source"] == "gbif" and r["license"] == "cc0" and "2571495242" in r["source_id"])
    path = (SOURCE_FOLDER / row["local_path"]).resolve()
    if not path.is_relative_to(SOURCE_FOLDER.resolve()):
        raise ValueError("Fixture path escapes the Nymphaea review pool")
    return row, path, path.read_bytes()


def ensure_not_historical_test(fixture_sha: str) -> bool:
    for manifest in (ROOT / "storage/datasets/curated").rglob("manifest.csv"):
        with manifest.open(encoding="utf-8-sig", newline="") as f:
            if any(r.get("split") == "test" and r.get("sha256") == fixture_sha for r in csv.DictReader(f)):
                return False
    return True


def main():
    fixture, image_path, photo = load_fixture()
    fixture_sha = sha(image_path)
    if fixture_sha != fixture["sha256"]:
        raise ValueError("CC0 fixture checksum does not match its review record")
    if not ensure_not_historical_test(fixture_sha):
        raise ValueError("Selected demo photo is present in a historical test split")
    model_before, mapping_before, active_before = sha(MODEL), sha(MAPPING), sha(ACTIVE)
    metadata = json.loads(ACTIVE.read_text(encoding="utf-8"))

    database_name = "geoflora_client_demo_" + uuid.uuid4().hex[:12]
    uri = f"mongodb://127.0.0.1:27017/{database_name}"
    client = MongoClient(uri, serverSelectionTimeoutMS=3000)
    db = client.get_default_database()
    client.admin.command("ping")
    now = datetime.now(timezone.utc)
    sessions = {}
    for username, role in (("demo_contributor", "user"), ("demo_admin", "admin")):
        token = secrets.token_hex(32)
        account_id = ObjectId()
        db.accounts.insert_one({"_id": account_id, "username": username, "passwordHash": "smoke-only", "salt": "smoke-only", "role": role, "disabled": False, "emailVerified": True, "createdAt": now, "updatedAt": now})
        db.sessions.insert_one({"tokenHash": hashlib.sha256(token.encode()).hexdigest(), "userId": account_id, "expiresAt": now.replace(year=now.year + 1)})
        sessions[username] = token

    env = {**os.environ, "GEOFLORA_MONGODB_URI": uri, "GEOFLORA_ML_API_URL": "http://127.0.0.1:8000", "GEOFLORA_AI_REVIEW": "off"}
    log_path = ROOT / "storage/logs/client-demo-e2e-web.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = log_path.open("w", encoding="utf-8")
    web = subprocess.Popen(["node", "node_modules/next/dist/bin/next", "start", "--hostname", "127.0.0.1", "--port", str(PORT)], cwd=WEB, env=env, stdout=log, stderr=subprocess.STDOUT)
    evidence = {"passed": False, "database": database_name, "fixture": {"sha256": fixture_sha, "source_url": fixture["source_url"], "license": fixture["license"], "training_or_evaluation_use": False}, "steps": []}
    try:
        for _ in range(90):
            if web.poll() is not None:
                raise RuntimeError(f"Next.js exited; see {log_path}")
            try:
                if requests.get(BASE + "/api/auth", timeout=2).status_code in (200, 503):
                    break
            except requests.RequestException:
                time.sleep(0.5)
        else:
            raise RuntimeError(f"Next.js failed to start; see {log_path}")

        user = requests.Session(); user.cookies.set("geoflora_session", sessions["demo_contributor"])
        admin = requests.Session(); admin.cookies.set("geoflora_session", sessions["demo_admin"])
        health = user.get(BASE + "/api/identify", timeout=15).json()
        assert health["ready"] and health["model_version"] == "mobilenetv2_v3_seed42", health
        evidence["steps"].append("Next.js health proxy reports the active three-class model ready")

        pred_response = user.post(BASE + "/api/identify", files={"image": (image_path.name, photo, "image/jpeg")}, timeout=90)
        assert pred_response.status_code == 200, pred_response.text
        prediction = pred_response.json()
        assert prediction["method"] == "model" and prediction["status"] == "uncertain" and prediction["species"] is None, prediction
        assert prediction["model_version"] == "mobilenetv2_v3_seed42" and prediction["confidence_threshold"] == metadata["confidence_threshold"] == 0.8, prediction
        evidence["prediction"] = {k: prediction.get(k) for k in ("method", "status", "species", "confidence", "confidence_threshold", "model_version")}
        evidence["steps"].append("uploaded CC0 unsupported-plant photo passed Next.js to real FastAPI/Keras and returned uncertain/no species")

        request_id = str(uuid.uuid4())
        description = "Floating water lily with rounded leaves and a visible flower; contributor-supplied and unverified."
        form = {"requestId": request_id, "species": "unknown", "suggestedSpecies": "Water lily (Nymphaea)", "plantDescription": description, "latitude": "14.5995", "longitude": "120.9842", "locationMethod": "map_pin", "placeName": "Disposable demo site", "observedAt": datetime.now(timezone.utc).isoformat(), "consent": "yes", "identificationId": prediction["identification_id"]}
        saved_response = user.post(BASE + "/api/sightings", data=form, files={"image": (image_path.name, photo, "image/jpeg")}, timeout=30)
        assert saved_response.status_code == 201, saved_response.text
        saved = saved_response.json()
        assert saved["species"] == "unknown" and saved["suggestedSpecies"] == "Water lily (Nymphaea)" and saved["plantDescription"] == description
        assert saved["status"] == "pending" and saved["labelReviewStatus"] == "pending" and saved["trainingConsent"] is False and saved["trainingCandidateStatus"] == "not_requested"
        assert saved["prediction"]["status"] == "uncertain" and saved["prediction"]["species"] is None
        evidence["pending_report"] = {k: saved.get(k) for k in ("id", "species", "suggestedSpecies", "status", "labelReviewStatus", "trainingConsent", "trainingCandidateStatus", "locationMethod", "latitude", "longitude")}
        evidence["steps"].append("user-provided plant information and map-pin coordinates saved as pending, unverified report")

        contributor_map = user.get(BASE + "/api/occurrences", timeout=15).json()
        assert contributor_map["points"] == [], contributor_map
        admin_all = admin.get(BASE + "/api/occurrences?layer=all", timeout=15).json()
        assert any(p["id"] == saved["id"] and p["status"] == "pending" for p in admin_all["points"]), admin_all
        pending_analytics = admin.get(BASE + "/api/analytics", timeout=15).json()
        assert pending_analytics["total"] == 0, pending_analytics
        assert user.patch(BASE + "/api/admin/review", json={}).status_code == 403
        queue = admin.get(BASE + "/api/admin/review", timeout=15).json()
        item = next((r for r in queue["reports"] if r["id"] == saved["id"]), None)
        assert item is not None and item["prediction"]["status"] == "uncertain" and item["labelReviewStatus"] == "pending", queue
        evidence["steps"].append("unverified report is absent from verified map/analytics and visible only in authorized review/pending layer")

        review = {"id": saved["id"], "action": "approve", "speciesId": "nymphaea_pubescens", "scientificName": "Nymphaea pubescens", "commonName": "Water lily", "notInvasive": True, "confirmed": True, "rationale": "Isolated smoke fixture only; reviewer explicitly classifies this as a non-invasive look-alike.", "description": "Aquatic water lily with rounded floating leaves and a prominent flower.", "citation": "https://powo.science.kew.org/results?q=Nymphaea%20pubescens"}
        reviewed_response = admin.patch(BASE + "/api/admin/review", json=review, timeout=20)
        assert reviewed_response.status_code == 200, reviewed_response.text
        reviewed = reviewed_response.json()
        stored = db.sightings.find_one({"requestId": request_id})
        assert reviewed["status"] == "verified" and reviewed["trainingQueued"] is False
        assert stored and stored["verifiedRole"] == "lookalike" and stored["verifiedSpeciesId"] == "nymphaea_pubescens"
        assert stored["trainingConsent"] is False and stored["trainingCandidateStatus"] == "not_requested" and stored["trainingJobId"] is None
        assert stored["prediction"]["status"] == "uncertain" and stored["prediction"]["species"] is None
        assert db.trainingjobs.count_documents({}) == 0
        evidence["review"] = {"status": reviewed["status"], "verified_species_id": stored["verifiedSpeciesId"], "verified_role": stored["verifiedRole"], "training_queued": reviewed["trainingQueued"], "job_count": db.trainingjobs.count_documents({}), "original_prediction_preserved": stored["prediction"]["status"] == "uncertain"}
        evidence["steps"].append("administrator verified fixture as a look-alike; original CNN uncertainty preserved; no training job created")

        points = admin.get(BASE + "/api/occurrences", timeout=15).json()["points"]
        point = next(p for p in points if p["id"] == saved["id"])
        analytics = admin.get(BASE + "/api/analytics", timeout=15).json()
        assert point["status"] == "verified" and point["species"] == "Nymphaea pubescens" and point["latitude"] == 14.5995 and point["longitude"] == 120.9842
        assert analytics["total"] == 1 and analytics["bySpecies"] == [{"species": "Nymphaea pubescens", "reports": 1}]
        assert analytics["byStatus"] == {"verified": 1} and analytics["method"]["meaning"].startswith("Counts are submitted reports")
        evidence["map_analytics"] = {"point": point, "total": analytics["total"], "bySpecies": analytics["bySpecies"], "byStatus": analytics["byStatus"], "interpretation": analytics["method"]["meaning"]}
        evidence["steps"].append("admin map and analytics show the human-confirmed look-alike report and geotag")
        assert sha(MODEL) == model_before and sha(MAPPING) == mapping_before and sha(ACTIVE) == active_before
        evidence["steps"].append("active model, mapping, and activation metadata hashes unchanged")
        evidence["passed"] = True
        evidence["active_model"] = {"version": metadata["candidate"], "threshold": metadata["confidence_threshold"], "model_sha256": model_before, "mapping_sha256": mapping_before, "active_metadata_sha256": active_before}
        evidence["historical_test_photo"] = False
        evidence["training_worker_started"] = False
        evidence["ai_review"] = "off in isolated test; admin approval was explicit"
    finally:
        web.terminate()
        try:
            web.wait(timeout=8)
        except subprocess.TimeoutExpired:
            web.kill(); web.wait(timeout=5)
        log.close()
        client.drop_database(database_name)
        client.close()
        (ROOT / "docs/client-demo-e2e-smoke-2026-11-01.json").write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(evidence, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
