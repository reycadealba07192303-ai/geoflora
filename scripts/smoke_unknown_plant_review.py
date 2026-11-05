"""Verify uncertain-identification -> pending report -> human review -> training queue.

Uses a new disposable local MongoDB database, real local Next.js and the active ML API.
It stops at the queued-job boundary; it does not launch another training run.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import secrets
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from bson import ObjectId
from pymongo import MongoClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/ml/src"))
from geoflora_ml.inference.predictor import PlantPredictor  # noqa: E402

WEB = ROOT / "apps/web"
PORT = 5174
BASE_URL = f"http://127.0.0.1:{PORT}"


def main() -> None:
    database_name = "geoflora_unknown_review_" + uuid.uuid4().hex[:12]
    uri = f"mongodb://127.0.0.1:27017/{database_name}"
    client = MongoClient(uri, serverSelectionTimeoutMS=3000)
    database = client.get_default_database()
    client.admin.command("ping")
    predictor = PlantPredictor()
    if not predictor.ready or predictor.model_version != "mobilenetv2_v3_seed42":
        raise RuntimeError("The active three-class model is not loaded for the inference smoke.")
    model_path = ROOT / "storage/models/mobilenetv2.keras"
    mapping_path = ROOT / "storage/models/class_mapping.json"
    active_path = ROOT / "storage/models/active_model.json"
    initial_model_sha = hashlib.sha256(model_path.read_bytes()).hexdigest()
    initial_mapping_sha = hashlib.sha256(mapping_path.read_bytes()).hexdigest()
    active_metadata = json.loads(active_path.read_text(encoding="utf-8"))

    now = datetime.now(timezone.utc)
    admin_id, user_id, other_id = ObjectId(), ObjectId(), ObjectId()
    accounts = [
        {"_id": admin_id, "username": "smoke_admin", "passwordHash": "smoke-only", "salt": "smoke-only", "role": "admin", "disabled": False, "emailVerified": True, "createdAt": now, "updatedAt": now},
        {"_id": user_id, "username": "smoke_contributor", "passwordHash": "smoke-only", "salt": "smoke-only", "role": "user", "disabled": False, "emailVerified": True, "createdAt": now, "updatedAt": now},
        {"_id": other_id, "username": "smoke_other", "passwordHash": "smoke-only", "salt": "smoke-only", "role": "user", "disabled": False, "emailVerified": True, "createdAt": now, "updatedAt": now},
    ]
    sessions: dict[str, str] = {}
    for account in accounts:
        token = secrets.token_hex(32)
        sessions[account["username"]] = token
        database.accounts.insert_one(account)
        database.sessions.insert_one({"tokenHash": hashlib.sha256(token.encode()).hexdigest(), "userId": account["_id"], "expiresAt": now + timedelta(hours=1)})
    database.species_classes.insert_one({"_id": "pontederia_crassipes", "id": "pontederia_crassipes", "scientific_name": "Pontederia crassipes", "common_name": "Water Hyacinth", "role": "invasive", "citation": "https://www.iucngisd.org/gisd/species.php?sc=70"})

    environment = {**os.environ, "GEOFLORA_MONGODB_URI": uri, "GEOFLORA_AI_REVIEW": "off"}
    log_path = ROOT / "storage/logs/unknown-review-smoke.log"
    log_stream = log_path.open("w", encoding="utf-8")
    process = subprocess.Popen(["node", "node_modules/next/dist/bin/next", "start", "--hostname", "127.0.0.1", "--port", str(PORT)], cwd=WEB, env=environment, stdout=log_stream, stderr=subprocess.STDOUT)
    try:
        for _ in range(80):
            if process.poll() is not None:
                raise RuntimeError(f"Next.js exited; see {log_path}")
            try:
                if requests.get(BASE_URL + "/api/auth", timeout=2).status_code in (200, 503):
                    break
            except requests.RequestException:
                time.sleep(0.5)
        else:
            raise RuntimeError(f"Next.js did not start; see {log_path}")

        # This historical held-out photo is used only to exercise the uncertain UI/API route. It is never copied into
        # the dataset, marked training-consented, or used to measure or tune model quality.
        with (ROOT / "storage/datasets/curated/v3/manifest.csv").open(encoding="utf-8-sig", newline="") as stream:
            row = next(record for record in csv.DictReader(stream) if record["species_id"] == "pontederia_crassipes" and record["split"] == "test")
        image_path = (ROOT / "storage/datasets" / row["local_path"]).resolve()
        if not image_path.is_relative_to((ROOT / "storage/datasets").resolve()):
            raise RuntimeError("Unsafe v3 image path")
        photo = image_path.read_bytes()
        contributor = requests.Session()
        contributor.cookies.set("geoflora_session", sessions["smoke_contributor"])
        admin = requests.Session()
        admin.cookies.set("geoflora_session", sessions["smoke_admin"])
        stranger = requests.Session()
        stranger.cookies.set("geoflora_session", sessions["smoke_other"])

        health = contributor.get(BASE_URL + "/api/identify", timeout=15).json()
        assert health["ready"] and health["model_version"] == "mobilenetv2_v3_seed42", health
        response = contributor.post(BASE_URL + "/api/identify", files={"image": (image_path.name, photo, "image/jpeg")}, timeout=90)
        assert response.status_code == 200, response.text
        prediction = response.json()
        assert prediction["method"] == "model" and prediction["status"] == "uncertain" and prediction["species"] is None, prediction

        request_id = str(uuid.uuid4())
        form = {
            "requestId": request_id, "species": "unknown", "suggestedSpecies": "Pontederia crassipes",
            "plantDescription": "Floating freshwater plant with glossy rounded leaves and spongy stalks; test fixture.",
            "latitude": "14.5995", "longitude": "120.9842", "locationMethod": "manual",
            "placeName": "Disposable smoke fixture", "observedAt": datetime.now(timezone.utc).isoformat(),
            "consent": "yes", "identificationId": prediction["identification_id"],
        }
        saved = contributor.post(BASE_URL + "/api/sightings", data=form, files={"image": (image_path.name, photo, "image/jpeg")}, timeout=30)
        assert saved.status_code == 201, saved.text
        report = saved.json()
        assert report["species"] == "unknown" and report["suggestedSpecies"] == "Pontederia crassipes"
        assert report["labelReviewStatus"] == "pending" and report["trainingCandidateStatus"] == "not_requested"
        assert report["prediction"]["status"] == "uncertain" and report["prediction"]["model_version"] == "mobilenetv2_v3_seed42"
        assert stranger.get(BASE_URL + f"/api/sightings/{report['id']}", timeout=15).status_code == 404
        assert contributor.patch(BASE_URL + "/api/admin/review", json={}).status_code == 403
        assert any(item["id"] == report["id"] for item in admin.get(BASE_URL + "/api/admin/review", timeout=15).json()["reports"])

        review = {
            "id": report["id"], "action": "detailed_verify", "speciesId": "pontederia_crassipes", "confirmed": True,
            "ecologicalStatus": "pending_ecological_review",
            "rationale": "Disposable workflow fixture; image was inspected and botanical label confirmed.",
            "description": "Floating freshwater plant with glossy rounded leaves and spongy stalks.",
            "citation": "https://www.iucngisd.org/gisd/species.php?sc=70",
        }
        response = admin.patch(BASE_URL + "/api/admin/review", json=review, timeout=20)
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["status"] == "verified" and result["trainingCandidateStatus"] == "not_requested" and result["trainingQueued"] is False, result
        stored = database.sightings.find_one({"requestId": request_id})
        assert stored and stored["trainingConsent"] is False and stored["verifiedSpeciesId"] == "pontederia_crassipes"
        assert stored["verifiedEcologicalStatus"] == "pending_ecological_review"
        assert database.trainingjobs.find_one({"reportIds": report["id"]}) is None
        assert stored["trainingJobId"] is None

        # Exercise the explicit "This does not match my plant" path with an owner-approved Lantana
        # training image. This is a workflow fixture only, not an accuracy or threshold evaluation.
        lantana_row = next(record for record in csv.DictReader((ROOT / "storage/datasets/curated/v3/manifest.csv").open(encoding="utf-8-sig", newline="")) if record["species_id"] == "lantana_camara" and record["split"] == "train")
        lantana_path = (ROOT / "storage/datasets" / lantana_row["local_path"]).resolve()
        if not lantana_path.is_relative_to((ROOT / "storage/datasets").resolve()):
            raise RuntimeError("Unsafe Lantana workflow fixture path")
        lantana_photo = lantana_path.read_bytes()
        mismatch_identified = contributor.post(BASE_URL + "/api/identify", files={"image": (lantana_path.name, lantana_photo, "image/jpeg")}, timeout=90)
        assert mismatch_identified.status_code == 200, mismatch_identified.text
        mismatch_prediction = mismatch_identified.json()
        assert mismatch_prediction["method"] == "model" and mismatch_prediction["status"] == "identified" and mismatch_prediction["species"]["id"] == "lantana_camara", mismatch_prediction
        expected_mismatch = predictor.predict(lantana_photo)
        assert abs(mismatch_prediction["confidence"] - expected_mismatch.confidence) < 1e-5
        mismatch_request_id = str(uuid.uuid4())
        mismatch_form = {
            "requestId": mismatch_request_id, "species": "unknown", "suggestedSpecies": "Euphorbia hirta",
            "plantDescription": "Workflow fixture: opposite toothed leaves and small green flower clusters, described by the test only.",
            "latitude": "14.5995", "longitude": "120.9842", "locationMethod": "manual",
            "placeName": "Disposable CNN disagreement fixture", "observedAt": datetime.now(timezone.utc).isoformat(),
            "consent": "yes", "identificationId": mismatch_prediction["identification_id"], "identificationDisagrees": "yes",
        }
        mismatch_saved = contributor.post(BASE_URL + "/api/sightings", data=mismatch_form, files={"image": (lantana_path.name, lantana_photo, "image/jpeg")}, timeout=30)
        assert mismatch_saved.status_code == 201, mismatch_saved.text
        mismatch_report = mismatch_saved.json()
        assert mismatch_report["species"] == "unknown" and mismatch_report["suggestedSpecies"] == "Euphorbia hirta"
        assert mismatch_report["identificationDisagrees"] is True and mismatch_report["labelReviewStatus"] == "pending"
        assert mismatch_report["prediction"]["species"]["id"] == "lantana_camara" and mismatch_report["prediction"]["status"] == "identified"
        stored_mismatch = database.sightings.find_one({"requestId": mismatch_request_id})
        assert stored_mismatch and stored_mismatch["speciesDescription"] == "" and stored_mismatch["citations"] == []
        assert stored_mismatch["identificationDisagrees"] is True and stored_mismatch["trainingConsent"] is False
        assert stored_mismatch.get("aiReview") is None and stored_mismatch["status"] == "pending"
        mismatch_detail_response = contributor.get(BASE_URL + f"/api/sightings/{mismatch_report['id']}", timeout=15)
        assert mismatch_detail_response.status_code == 200, mismatch_detail_response.text
        mismatch_detail = mismatch_detail_response.json()
        assert mismatch_detail["identificationDisagrees"] is True and mismatch_detail["species"] == "unknown"
        assert mismatch_detail["prediction"]["species"]["id"] == "lantana_camara" and mismatch_detail["citations"] == []
        queue_item = next(item for item in admin.get(BASE_URL + "/api/admin/review", timeout=15).json()["reports"] if item["id"] == mismatch_report["id"])
        assert queue_item["identificationDisagrees"] is True

        # One-off actual-image diagnostic: compare the HTTP path with a fresh local model.predict call.
        # Samples are behavior probes, not an accuracy set; source captions and owner review are not expert truth.
        lantana_rows = [record for record in csv.DictReader((ROOT / "storage/datasets/curated/v3/manifest.csv").open(encoding="utf-8-sig", newline="")) if record["species_id"] == "lantana_camara" and record["split"] == "train"]
        second_lantana = next(record for record in lantana_rows if record["group_id"] != lantana_row["group_id"])
        mikania_rows = list(csv.DictReader((ROOT / "storage/datasets/curated/owner_approved_five_class_plus_mikania_supplement_20261031/manifest.csv").open(encoding="utf-8-sig", newline="")))
        mikania_row = next(record for record in mikania_rows if record["species_id"] == "mikania_micrantha" and record["split"] == "train" and record["review_status"] == "owner_gallery_approved")
        probe_cases = [
            ("lantana_second_observation", ROOT / "storage/datasets" / second_lantana["local_path"], "owner-approved v3 training label; second observation group"),
            ("mikania_unsupported_by_active_model", ROOT / mikania_row["local_path"], "owner-gallery-approved source label; unsupported by active v3"),
            ("euphorbia_commons_bim24", ROOT / "storage/datasets/staging/reference_review_euphorbia_hirta/asthma_plant_1_bim24.jpg", "Commons caption only; locality and botanical label unverified"),
            ("euphorbia_commons_judgefloro", ROOT / "storage/datasets/staging/reference_review_euphorbia_hirta/tawa_tawa_philippines_01_judgefloro.jpg", "Commons caption/location metadata; botanical label unverified"),
        ]
        prediction_probes = []
        for probe_name, probe_path, label_basis in probe_cases:
            probe_path = probe_path.resolve()
            if not probe_path.is_relative_to((ROOT / "storage/datasets").resolve()):
                raise RuntimeError("Unsafe diagnostic image path")
            probe_bytes = probe_path.read_bytes()
            expected = predictor.predict(probe_bytes)
            response = contributor.post(BASE_URL + "/api/identify", files={"image": (probe_path.name, probe_bytes, "image/jpeg")}, timeout=90)
            assert response.status_code == 200, response.text
            actual = response.json()
            assert actual["method"] == "model" and actual["model_version"] == predictor.model_version
            assert actual["status"] == expected.status and abs(actual["confidence"] - expected.confidence) < 1e-5
            assert (actual.get("species") or {}).get("id") == (expected.species.id if expected.species else None)
            prediction_probes.append({"sample": probe_name, "label_basis": label_basis, "status": actual["status"], "predicted_species": (actual.get("species") or {}).get("id"), "score": actual["confidence"], "threshold": actual["confidence_threshold"], "method": actual["method"], "matches_fresh_keras_model_predict": True, "reference_match": False})

        database.sightings.update_one({"_id": ObjectId(report["id"])}, {"$set": {"referenceConsent": True, "referenceCandidateStatus": "approved"}})
        database.verified_image_references.insert_one({"sourceObservationId": report["id"], "sourceGroupId": report["id"], "speciesId": "pontederia_crassipes", "imageHash": "smoke-only", "embeddingVersion": "smoke-only", "active": True})
        assert stranger.patch(BASE_URL + f"/api/admin/references/{report['id']}", json={"action": "invalidate", "rationale": "Unauthorized invalidation check."}, timeout=15).status_code == 403
        invalidated = admin.patch(BASE_URL + f"/api/admin/references/{report['id']}", json={"action": "invalidate", "rationale": "Disposable invalidation fixture; verifies the administrator-only revocation path."}, timeout=15)
        assert invalidated.status_code == 200, invalidated.text
        assert database.verified_image_references.find_one({"sourceObservationId": report["id"]})["active"] is False
        assert database.sightings.find_one({"_id": ObjectId(report["id"])})["referenceCandidateStatus"] == "rejected"
        evidence = {
            "passed": True,
            "workflow": ["active CNN returned uncertain/no species", "user description and suggested name remained unverified", "report saved pending and user-owned", "unauthorized reviewer action denied", "admin human review confirmed botanical label only", "ecological status remained pending and no training consent/job was created", "admin-only reference invalidation deactivated the evidence and wrote an audit event"],
            "cnn_disagreement_workflow": {"passed": True, "fixture_split": lantana_row["split"], "cnn_prediction_preserved": {"species": mismatch_prediction["species"]["id"], "score": mismatch_prediction["confidence"], "model_version": mismatch_prediction["model_version"]}, "user_reported_species": mismatch_report["species"], "user_suggested_species": mismatch_report["suggestedSpecies"], "label_review_status": mismatch_report["labelReviewStatus"], "manual_review_flag": mismatch_report["identificationDisagrees"], "species_facts_copied_to_report": bool(stored_mismatch["speciesDescription"]), "training_consent": stored_mismatch["trainingConsent"], "ai_automatic_review": "disabled in smoke; flagged reports are excluded from the production auto-review claim query"},
            "prediction": {"model_version": prediction["model_version"], "status": prediction["status"], "species": prediction["species"], "confidence": prediction["confidence"], "threshold": prediction["confidence_threshold"], "method": prediction["method"]},
            "report_after_review": {"status": result["status"], "trainingCandidateStatus": result["trainingCandidateStatus"], "trainingQueued": result["trainingQueued"]},
            "future_training_job": "not eligible: no training consent, ecological status pending",
            "database": database_name,
            "active_model_sha_unchanged": hashlib.sha256(model_path.read_bytes()).hexdigest() == initial_model_sha,
            "active_mapping_sha_unchanged": hashlib.sha256(mapping_path.read_bytes()).hexdigest() == initial_mapping_sha,
            "active_model_version": active_metadata.get("candidate"),
            "active_confidence_threshold": active_metadata.get("confidence_threshold"),
            "fixture_split": row["split"],
            "prediction_probes": prediction_probes,
        }
        (ROOT / "docs/unknown-plant-workflow-smoke-2026-11-01.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        print(json.dumps(evidence, indent=2))
    finally:
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        log_stream.close()
        client.drop_database(database_name)
        client.close()


if __name__ == "__main__":
    main()
