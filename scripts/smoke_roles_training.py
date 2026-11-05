"""Validate RBAC and an actual automatic-training job in an isolated local DB.

Start web on 5174 with GEOFLORA_MONGODB_URI=mongodb://127.0.0.1:27017/geoflora_roles_validation
and GEOFLORA_MIN_TRAINING_REPORTS=3. Synthetic fixture images never reach the live dataset/model.
"""
import hashlib
import io
import json
import os
import secrets
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import requests
from PIL import Image
from pymongo import MongoClient

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:5174"
URI = "mongodb://127.0.0.1:27017/geoflora_roles_validation"


def main():
    client = MongoClient(URI, serverSelectionTimeoutMS=3000)
    db = client.get_default_database()
    admin = requests.Session()
    setup = admin.get(BASE + "/api/auth").json()["setupRequired"]
    result = admin.post(BASE + "/api/auth", json={"action": "setup" if setup else "login", "username": "fixture_admin", "password": "GeoFlora-Smoke-Only-2026"})
    assert result.status_code == 200, result.text
    assert result.json()["user"]["role"] == "admin"
    assert "HttpOnly" in result.headers["Set-Cookie"] and "SameSite=strict" in result.headers["Set-Cookie"]
    assert admin.post(BASE + "/api/auth", json={"action": "setup", "username": "second_admin", "password": "Not-A-Real-Password-Only-Testing"}).status_code == 409
    user = requests.Session(); other = requests.Session()
    for session in (user, other):
        response = session.post(BASE + "/api/auth", json={"action": "register", "username": "fixture_" + uuid.uuid4().hex[:12], "password": secrets.token_urlsafe(24), "role": "admin"})
        assert response.status_code == 200, response.text
        assert response.json()["user"]["role"] == "user"
    assert requests.get(BASE + "/api/admin/review").status_code == 401
    assert requests.get(BASE + "/api/sightings").status_code == 401
    assert user.get(BASE + "/api/admin/review").status_code == 403
    assert user.get(BASE + "/api/sightings?trainingCandidates=1").status_code == 403
    assert user.patch(BASE + "/api/admin/review", json={}).status_code == 403
    ids = []
    for index in range(3):
        image = io.BytesIO()
        Image.fromarray(np.random.default_rng(int(uuid.uuid4().hex[:8], 16)).integers(0, 255, (128, 128, 3), dtype=np.uint8)).save(image, format="PNG")
        fields = {"requestId": str(uuid.uuid4()), "species": "unknown", "suggestedSpecies": "Chromolaena odorata", "plantDescription": "Synthetic isolated photo for access-control and pipeline tests only.", "latitude": "14.5995", "longitude": "120.9842", "locationMethod": "manual", "observedAt": datetime.now(timezone.utc).isoformat(), "consent": "yes", "trainingConsent": "yes", "trainingCandidateStatus": "approved", "ownerId": "forged", "notes": "Synthetic isolated RBAC/training fixture; not a botanical observation"}
        response = user.post(BASE + "/api/sightings", data=fields, files={"image": ("fixture.png", image.getvalue(), "image/png")})
        assert response.status_code == 201, response.text
        report = response.json(); ids.append(report["id"])
        assert report["trainingCandidateStatus"] == "pending_review"
        assert user.get(f"{BASE}/api/sightings/{report['id']}/photo").status_code == 200
        assert other.get(f"{BASE}/api/sightings/{report['id']}/photo").status_code == 404
        assert not any(row["id"] == report["id"] for row in other.get(BASE + "/api/sightings").json()["reports"])
        assert admin.get(f"{BASE}/api/sightings/{report['id']}/photo").status_code == 200
        approval = {"id": report["id"], "action": "approve", "speciesId": "chromolaena_odorata", "confirmed": True, "rationale": "Synthetic fixture approval for isolated pipeline test only"}
        assert admin.patch(BASE + "/api/admin/review", json={**approval, "confirmed": False}).status_code == 400
        response = admin.patch(BASE + "/api/admin/review", json=approval)
        assert response.status_code == 200, response.text
        assert admin.patch(BASE + "/api/admin/review", json=approval).status_code == 409
    queued = db.trainingjobs.find_one({"status": "queued"}, sort=[("createdAt", -1)])
    assert queued and set(ids).issubset(queued["reportIds"])
    active = ROOT / "storage/models/mobilenetv2.keras"
    before = hashlib.sha256(active.read_bytes()).hexdigest()
    environment = {**os.environ, "GEOFLORA_MONGODB_URI": URI, "GEOFLORA_MIN_TRAINING_REPORTS": "3"}
    process = subprocess.run([str(ROOT / "services/ml/.venv/Scripts/python.exe"), str(ROOT / "scripts/auto_training_worker.py"), "--once"], cwd=ROOT, env=environment, timeout=180)
    assert process.returncode == 0
    job = db.trainingjobs.find_one({"_id": queued["_id"]})
    assert job["status"] == "completed", job.get("detail")
    assert job["metrics"]["activated"] is False
    assert (ROOT / job["candidatePath"] / "mobilenetv2.keras").is_file()
    assert hashlib.sha256(active.read_bytes()).hexdigest() == before
    assert user.delete(BASE + "/api/auth").status_code == 200
    assert user.get(BASE + "/api/sightings").status_code == 401
    evidence = {"passed": True, "database": "geoflora_roles_validation", "synthetic_fixtures_only": True, "checks": ["first-admin setup cannot be repeated", "registration cannot self-elevate", "session cookie flags", "anonymous and user admin access denied", "user report/photo ownership enforced", "client owner/approval fields ignored", "admin approval requires confirmation", "review cannot be replayed", "approved threshold creates a job", "real worker exported data, trained and evaluated a candidate", "active model preserved", "logout invalidates session"], "job_id": str(job["_id"]), "job_status": job["status"], "candidate_path": job["candidatePath"]}
    (ROOT / "docs/roles-training-smoke.json").write_text(json.dumps(evidence, indent=2))
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
