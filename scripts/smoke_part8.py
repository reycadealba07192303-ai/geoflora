"""Part 8 sighting checks through real HTTP on an isolated database (build apps/web first; inference on 8000).

Starts a temporary `next start` on 5174 against geoflora_part8_validation. Covers the stored
identification snapshot and record fields, map-pin locations, owner corrections with edit history,
withdrawal with immediate photo/location deletion, and ownership/review boundaries. Live data is untouched.
"""
import csv
import io
import json
import os
import secrets
import subprocess
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import requests
from bson import ObjectId
from PIL import Image
from pymongo import MongoClient
from smoke_auth_fixture import account as fixture_account

ROOT = Path(__file__).resolve().parents[1]
URI = "mongodb://127.0.0.1:27017/geoflora_part8_validation"
BASE = "http://127.0.0.1:5174"
OUTPUT = ROOT / "docs/part-8-sightings-smoke.json"
checks = []


def check(condition, message):
    assert condition, message
    checks.append(message)
    print("PASS", message)


def status(response, expected, message):
    check(response.status_code == expected, message if response.status_code == expected else f"{message}: expected {expected}, got {response.status_code} {response.text[:200]}")


def account(action, username):
    return fixture_account(URI, username, "admin" if action == "setup" else "user")


def noise():
    buffer = io.BytesIO()
    Image.fromarray(np.random.default_rng().integers(0, 256, (160, 160, 3), dtype=np.uint8)).save(buffer, format="PNG")
    return buffer.getvalue()


def submit(session, photo, content_type="image/png", **changes):
    fields = {"requestId": str(uuid.uuid4()), "species": "unknown", "plantDescription": "Climbing vine with heart-shaped leaves.",
              "latitude": "10.3157", "longitude": "123.8854", "locationMethod": "map_pin", "placeName": "Pinned test site",
              "observedAt": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(), "consent": "yes", **changes}
    return session.post(BASE + "/api/sightings", data=fields, files={"image": ("plant", photo, content_type)}, timeout=30), fields


def main():
    MongoClient(URI).drop_database("geoflora_part8_validation")
    database = MongoClient(URI).get_default_database()
    env = {**os.environ, "GEOFLORA_MONGODB_URI": URI, "GEOFLORA_ML_API_URL": "http://127.0.0.1:8000"}
    log = (ROOT / "storage/logs/part8-smoke-web.log").open("w", encoding="utf-8")
    web = subprocess.Popen(["node", "node_modules/next/dist/bin/next", "start", "--hostname", "127.0.0.1", "--port", "5174"], cwd=ROOT / "apps/web", env=env, stdout=log, stderr=subprocess.STDOUT)
    try:
        for _ in range(60):
            try:
                requests.get(BASE + "/api/auth", timeout=3); break
            except requests.ConnectionError:
                time.sleep(0.5)
        admin, _ = account("setup", "fixture_admin")
        alice, alice_id = account("register", "alice_field")
        bob, _ = account("register", "bob_field")
        rita, rita_id = account("register", "rita_review")
        admin.patch(BASE + "/api/accounts", json={"id": rita_id, "action": "set-role", "role": "reviewer"}, timeout=15)

        # 1. Identification snapshot and record fields saved together.
        rows = [r for r in csv.DictReader((ROOT / "storage/datasets/curated/v3/manifest.csv").open(encoding="utf-8")) if r["split"] == "test" and r["species_id"] == "chromolaena_odorata"]
        photo = (ROOT / "storage/datasets" / rows[0]["local_path"]).read_bytes()
        identified = alice.post(BASE + "/api/identify", files={"image": ("plant.jpg", photo, "image/jpeg")}, timeout=90).json()
        check(identified["status"] == "identified", "real model identification for the report photo")
        response, fields = submit(alice, photo, "image/jpeg", identificationId=identified["identification_id"], species="Chromolaena odorata", trainingConsent="yes")
        status(response, 201, "report with identification and map-pin location is saved")
        report = response.json()["id"]
        stored = database.sightings.find_one({"_id": ObjectId(report)})
        check(stored["ownerId"] == alice_id and stored["status"] == "pending" and len(stored["photo"]) > 1000, "record stores owner, pending status and photo bytes")
        check(stored["prediction"]["confidence"] == identified["confidence"] and stored["prediction"]["model_version"] == "mobilenetv2_v3_seed42" and stored["prediction"]["confidence_threshold"] == 0.8, "record stores model score, threshold and model version from the server-side identification")
        check(stored["reportedSpecies"] == "Chromolaena odorata" and stored["locationMethod"] == "map_pin" and stored["locationAccuracy"] is None, "record stores species suggestion and map-pin location method without GPS accuracy")
        check(stored["location"]["coordinates"] == [123.8854, 10.3157], "GeoJSON coordinates are longitude, latitude")
        check(stored["observedAt"].replace(tzinfo=timezone.utc) < stored["submittedAt"].replace(tzinfo=timezone.utc), "observation time is stored separately from submission time")
        detail = alice.get(BASE + f"/api/sightings/{report}", timeout=15).json()
        check(detail["editable"] is True and detail["prediction"]["model_version"] == "mobilenetv2_v3_seed42", "owner sees the report as editable with its identification record")
        check(admin.get(BASE + f"/api/sightings/{report}", timeout=15).json()["editable"] is False, "an administrator viewing the report is not offered owner edits")
        pdf = alice.get(BASE + f"/api/sightings/{report}/pdf", timeout=60)
        check(pdf.status_code == 200 and pdf.content.startswith(b"%PDF-"), "the report PDF still generates with the identification record")
        status(submit(alice, noise(), locationMethod="satellite")[0], 400, "unknown location methods are rejected")

        # 2. Owner corrections with history; the photo and identification stay as submitted.
        new_time = (datetime.now(timezone.utc) - timedelta(days=1)).replace(microsecond=0).isoformat()
        patch = lambda session, rid, body: session.patch(BASE + f"/api/sightings/{rid}", json=body, timeout=15)
        response = patch(alice, report, {"placeName": "Corrected creek bank", "observedAt": new_time, "latitude": 10.32, "longitude": 123.9, "locationMethod": "map_pin", "notes": "Second visit"})
        status(response, 200, "owner corrects place, time, location and notes")
        check(response.json()["placeName"] == "Corrected creek bank" and response.json()["latitude"] == 10.32 and response.json()["lastEditedAt"], "corrected values are returned with the last-corrected time")
        stored = database.sightings.find_one({"_id": ObjectId(report)})
        edit = stored["editHistory"][-1]
        check(edit["editedBy"] == "alice_field" and edit["changes"]["placeName"]["from"] == "Pinned test site" and edit["changes"]["location"]["from"]["latitude"] == 10.3157, "edit history records who changed what, including the previous location")
        check(stored["prediction"]["confidence"] == identified["confidence"] and stored["reportedSpecies"] == "Chromolaena odorata", "corrections do not alter the model identification or its species")
        response = patch(alice, report, {"status": "verified", "trainingCandidateStatus": "approved", "verifiedSpeciesId": "lantana_camara", "photo": "x"})
        stored = database.sightings.find_one({"_id": ObjectId(report)})
        check(response.status_code == 200 and stored["status"] == "pending" and stored["trainingCandidateStatus"] == "pending_review" and stored["verifiedSpeciesId"] is None, "server-owned fields cannot be set through corrections")
        status(patch(alice, report, {"observedAt": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()}), 400, "future observation times are rejected")
        status(patch(alice, report, {"latitude": 95, "longitude": 120}), 400, "out-of-range corrected coordinates are rejected")
        status(patch(bob, report, {"placeName": "Hijacked"}), 404, "another contributor cannot correct the report")
        status(patch(rita, report, {"placeName": "Reviewer edit"}), 404, "reviewers cannot use owner corrections")
        status(requests.patch(BASE + f"/api/sightings/{report}", json={"placeName": "x"}, timeout=15), 401, "signed-out corrections are refused")

        # 3. Pending-identification reports keep a required description; reviewed reports lock.
        response, _ = submit(alice, noise(), suggestedSpecies="Mikania micrantha")
        unknown = response.json()["id"]
        status(patch(alice, unknown, {"plantDescription": ""}), 400, "a report awaiting identification cannot drop its description")
        response = patch(alice, unknown, {"suggestedSpecies": "Merremia peltata"})
        check(response.status_code == 200 and response.json()["species"] == "Merremia peltata", "changing the suggestion updates the reported species when no model label exists")
        rita.patch(BASE + "/api/admin/review", json={"id": unknown, "action": "reject", "rationale": "Not enough detail to identify."}, timeout=15)
        status(patch(alice, unknown, {"placeName": "Late edit"}), 409, "a reviewed report can no longer be corrected")
        status(alice.delete(BASE + f"/api/sightings/{unknown}", timeout=15), 409, "a reviewed report can no longer be withdrawn by its contributor")

        # 4. Withdrawal deletes photo, location and content immediately; a tombstone remains.
        status(bob.delete(BASE + f"/api/sightings/{report}", timeout=15), 404, "another contributor cannot withdraw the report")
        check(any(row["id"] == report for row in admin.get(BASE + "/api/sightings?trainingCandidates=1", timeout=15).json()["reports"]), "consented report is a training candidate before withdrawal")
        response = alice.delete(BASE + f"/api/sightings/{report}", timeout=15)
        check(response.status_code == 200 and response.json()["status"] == "withdrawn", "owner withdraws a pending report")
        stored = database.sightings.find_one({"_id": ObjectId(report)})
        removed = ["photo", "location", "placeName", "notes", "plantDescription", "suggestedSpecies", "prediction", "photoHash", "sourcePhotoHash", "identificationId", "editHistory"]
        check(not any(field in stored for field in removed), "withdrawal deletes the photo, coordinates, descriptions, identification and edit history")
        check(stored["status"] == "withdrawn" and stored["withdrawnAt"] and stored["submittedAt"] and stored["ownerId"] == alice_id and stored["trainingConsent"] is False, "a minimal tombstone keeps owner, submission and withdrawal times only")
        status(alice.get(BASE + f"/api/sightings/{report}", timeout=15), 410, "the withdrawn report reads as gone")
        status(alice.get(BASE + f"/api/sightings/{report}/photo", timeout=15), 404, "the withdrawn photo is unavailable")
        status(alice.get(BASE + f"/api/sightings/{report}/pdf", timeout=15), 404, "the withdrawn PDF is unavailable")
        check(all(row["id"] != report for row in alice.get(BASE + "/api/sightings", timeout=15).json()["reports"]), "withdrawn report leaves the contributor's map listing")
        check(all(row["id"] != report for row in admin.get(BASE + "/api/admin/review", timeout=15).json()["reports"]), "withdrawn report leaves the review queue")
        check(all(row["id"] != report for row in admin.get(BASE + "/api/sightings?trainingCandidates=1", timeout=15).json()["reports"]), "withdrawn report leaves the training candidates")
        status(alice.delete(BASE + f"/api/sightings/{report}", timeout=15), 409, "a report cannot be withdrawn twice")
        status(patch(alice, report, {"placeName": "After withdrawal"}), 409, "a withdrawn report cannot be corrected")
        retry = alice.post(BASE + "/api/sightings", data=fields, files={"image": ("plant", photo, "image/jpeg")}, timeout=30)
        status(retry, 409, "retrying the original submission does not resurrect a withdrawn report")
    finally:
        web.kill()
    OUTPUT.write_text(json.dumps({"checkedAt": datetime.now(timezone.utc).isoformat(), "database": URI, "checks": checks}, indent=2), encoding="utf-8")
    print(f"{len(checks)} checks passed")


if __name__ == "__main__":
    main()
