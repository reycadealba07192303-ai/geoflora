"""Facilitator dry run of the usability tasks T1-T8 against a prepared study workspace. Records no study session.

Run against a pilot copy, not the real study database:
    services/ml/.venv/Scripts/python.exe scripts/prepare_usability_study.py --database geoflora_study_pilot --reset
    services/ml/.venv/Scripts/python.exe scripts/pilot_usability_study.py
Starts a temporary `next start` on 5174 (build apps/web first; inference on 8000) and checks that each task's
success condition is reachable with the practice data and the facilitator answer key.
"""
import json
import os
import secrets
import subprocess
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
DATABASE = "geoflora_study_pilot"
BASE = "http://127.0.0.1:5174"
setup = json.loads((ROOT / "storage/study/materials/study-setup.json").read_text(encoding="utf-8"))
checks = []


def check(condition, message):
    assert condition, message
    checks.append(message)
    print("PASS", message)


def main():
    if setup["database"] != DATABASE:
        raise SystemExit("Prepare the pilot copy first (see the module docstring).")
    env = {**os.environ, "GEOFLORA_MONGODB_URI": f"mongodb://127.0.0.1:27017/{DATABASE}", "GEOFLORA_ML_API_URL": "http://127.0.0.1:8000"}
    web = subprocess.Popen(["node", "node_modules/next/dist/bin/next", "start", "--hostname", "127.0.0.1", "--port", "5174"], cwd=ROOT / "apps/web", env=env,
                           stdout=(ROOT / "storage/logs/study-pilot-web.log").open("w", encoding="utf-8"), stderr=subprocess.STDOUT)
    try:
        for _ in range(60):
            try:
                requests.get(BASE + "/api/auth", timeout=3); break
            except requests.ConnectionError:
                time.sleep(0.5)
        login = lambda action, name: (lambda s: (s, s.post(BASE + "/api/auth", json={"action": action, "username": name, "password": secrets.token_urlsafe(18)}, timeout=15)))(requests.Session())
        facilitator, _ = login("setup", "pilot_facilitator")
        participant, response = login("register", "pilot_participant")
        check(response.status_code == 200 and response.json()["user"]["role"] == "user", "T1 a participant can create an account and is signed in")
        reviewer, response = login("register", "pilot_reviewer")
        facilitator.patch(BASE + "/api/accounts", json={"id": response.json()["user"]["id"], "action": "set-role", "role": "reviewer"}, timeout=15)

        photo = (ROOT / setup["t2Photo"]).read_bytes()
        result = participant.post(BASE + "/api/identify", files={"image": ("plant.jpg", photo, "image/jpeg")}, timeout=90).json()
        check(result["status"] == "identified" and result["species"]["scientific_name"] == "Lantana camara", "T2 the study photo is identified as Lantana camara")
        fields = {"requestId": str(uuid.uuid4()), "species": "Lantana camara", "identificationId": result["identification_id"], "plantDescription": "Shrub with orange and pink flower clusters.",
                  "latitude": "14.6362", "longitude": "121.0965", "locationMethod": "manual", "placeName": "Marikina Rivr Park", "observedAt": (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat(), "consent": "yes"}
        response = participant.post(BASE + "/api/sightings", data=fields, files={"image": ("plant.jpg", photo, "image/jpeg")}, timeout=30)
        check(response.status_code == 201, "T3 the sighting saves with location and observation time")
        report = response.json()["id"]
        check(any(p["id"] == report for p in participant.get(BASE + "/api/occurrences?layer=all", timeout=15).json()["points"]), "T4 the new report appears on the participant's map (unverified layer)")
        response = participant.patch(BASE + f"/api/sightings/{report}", json={"placeName": "Marikina River Park"}, timeout=15)
        check(response.status_code == 200 and response.json()["placeName"] == "Marikina River Park", "T5 the participant can correct the place name")
        queue = reviewer.get(BASE + "/api/admin/review", timeout=15).json()["reports"]
        practice = [row for row in queue if row.get("notes", "").startswith("Practice data")]
        check(len(practice) == 3 and any(row["id"] == report for row in queue), "T6 the reviewer queue holds the 3 practice sightings plus new reports")
        response = reviewer.patch(BASE + "/api/admin/review", json={"id": practice[0]["id"], "action": "request_correction", "rationale": "Pilot: please add the barangay."}, timeout=15)
        check(response.status_code == 200 and response.json()["status"] == "correction_requested", "T6 a reviewer decision with a reason saves")
        lantana = participant.get(BASE + "/api/catalog?q=lantana%20camara", timeout=30).json()["species"][0]
        check(lantana["activeModel"] is True and "supported" in setup["facilitatorAnswerKey"]["T7"], "T7 the catalog shows Lantana camara as supported by the live model")
        key = setup["facilitatorAnswerKey"]["T8"]
        for name, expected in key.items():
            months = participant.get(BASE + f"/api/analytics?species={name.lower().replace(' ', '%20')}", timeout=15).json()["byMonth"]
            check(months[-1] == {"month": "2026-10", "reports": expected}, f"T8 verified {name} reports in the latest month match the answer key ({expected})")
    finally:
        web.kill()
    (ROOT / "storage/study/materials/pilot-dry-run.json").write_text(json.dumps({"checkedAt": datetime.now(timezone.utc).isoformat(), "database": DATABASE, "checks": checks, "note": "Facilitator dry run only; not a participant session."}, indent=2), encoding="utf-8")
    print(f"{len(checks)} checks passed")


if __name__ == "__main__":
    main()
