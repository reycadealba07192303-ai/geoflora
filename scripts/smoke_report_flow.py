"""Real HTTP/PDF/approval/training checks, isolated from live reports and models."""
import csv
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
URI = os.environ.get("GEOFLORA_MONGODB_URI", "mongodb://127.0.0.1:27017/geoflora_report_flow_validation")
if not URI.startswith("mongodb://127.0.0.1:27017/geoflora_report_flow_validation"):
    raise ValueError("Use only an isolated report-flow validation database")


def main():
    admin, user, other = requests.Session(), requests.Session(), requests.Session()
    setup = admin.get(BASE + "/api/auth", timeout=15).json()["setupRequired"]
    response = admin.post(BASE + "/api/auth", json={"action": "setup" if setup else "login", "username": "fixture_admin", "password": "GeoFlora-Smoke-Only-2026"}, timeout=15)
    assert response.status_code == 200, response.text
    for session in (user, other):
        response = session.post(BASE + "/api/auth", json={"action": "register", "username": "flow_" + uuid.uuid4().hex[:12], "password": secrets.token_urlsafe(20)}, timeout=15)
        assert response.status_code == 200, response.text
    rows = list(csv.DictReader((ROOT / "storage/datasets/curated/v3/manifest.csv").open(encoding="utf-8")))
    photos = {name: (ROOT / "storage/datasets" / next(row["local_path"] for row in rows if row["species_id"] == name and row["split"] == "test")).read_bytes() for name in ("chromolaena_odorata", "pontederia_crassipes")}

    def identify(photo, session=user):
        response = session.post(BASE + "/api/identify", files={"image": ("plant.jpg", photo, "image/jpeg")}, timeout=70)
        assert response.status_code == 200, response.text
        return response.json()

    def submit(photo, identification=None, description="", training=False, **changes):
        fields = {"requestId": str(uuid.uuid4()), "species": "unknown", "plantDescription": description, "latitude": "14.5995", "longitude": "120.9842", "locationMethod": "gps", "accuracy": "12", "placeName": "Isolated Manila test location", "observedAt": datetime.now(timezone.utc).isoformat(), "consent": "yes"}
        if identification: fields["identificationId"] = identification["identification_id"]
        if training: fields["trainingConsent"] = "yes"
        fields.update(changes)
        return user.post(BASE + "/api/sightings", data=fields, files={"image": ("plant.jpg", photo, "image/jpeg")}, timeout=20)

    known = identify(photos["chromolaena_odorata"])
    assert known["status"] == "identified" and known["information"]["source"]["url"].startswith("https://")
    response = submit(photos["chromolaena_odorata"], known, species="Forged client species")
    assert response.status_code == 201, response.text
    saved = response.json()
    assert saved["species"] == "Chromolaena odorata" and saved["description"] == known["information"]["description"]
    assert saved["citations"] == [known["information"]["source"]["url"]]
    assert saved["latitude"] == 14.5995 and saved["longitude"] == 120.9842 and saved["submittedAt"] and saved["observedAt"]
    report_url = BASE + "/api/sightings/" + saved["id"]
    assert user.get(report_url, timeout=15).json() == saved
    assert requests.get(report_url, timeout=15).status_code == 401
    assert other.get(report_url, timeout=15).status_code == 404
    assert other.get(report_url + "/pdf", timeout=15).status_code == 404
    response = user.get(report_url + "/pdf", timeout=40)
    assert response.status_code == 200, response.text
    assert response.headers["Content-Type"] == "application/pdf" and "attachment" in response.headers["Content-Disposition"]
    assert response.content.startswith(b"%PDF-")
    pdf_path = ROOT / "storage/logs/report-flow-validation.pdf"
    pdf_path.write_bytes(response.content)
    subprocess.run(["node", str(ROOT / "scripts/inspect_report_pdf.cjs"), str(pdf_path)], cwd=ROOT, check=True, timeout=20)
    assert submit(photos["pontederia_crassipes"], known, "Different image").status_code == 409
    unknown = identify(photos["pontederia_crassipes"])
    assert unknown["status"] == "uncertain", unknown
    assert submit(photos["pontederia_crassipes"], unknown).status_code == 400
    response = submit(photos["pontederia_crassipes"], unknown, "Floating plant with glossy rounded leaves and spongy stalks.")
    assert response.status_code == 201, response.text
    unknown_report = response.json()
    assert unknown_report["labelReviewStatus"] == "pending" and unknown_report["trainingConsent"] is False
    assert any(row["id"] == unknown_report["id"] for row in admin.get(BASE + "/api/admin/review").json()["reports"])
    review = {"id": unknown_report["id"], "action": "approve", "speciesId": "pontederia_crassipes", "confirmed": True, "rationale": "Isolated verification of a correctly labeled existing water-hyacinth photo", "description": "Water hyacinth is a floating freshwater plant with glossy rounded leaves and spongy stalks.", "citation": "https://www.iucngisd.org/gisd/species.php?sc=70"}
    response = admin.patch(BASE + "/api/admin/review", json=review)
    assert response.status_code == 200, response.text
    reviewed = user.get(BASE + "/api/sightings/" + unknown_report["id"]).json()
    assert reviewed["species"] == "Pontederia crassipes" and reviewed["labelSource"] == "admin_review"
    matched = identify(photos["pontederia_crassipes"])
    assert matched["method"] == "verified_reference" and matched["confidence"] is None and matched["species"]["id"] == "pontederia_crassipes"
    assert identify(photos["pontederia_crassipes"], other)["method"] == "model"  # No training consent: reference stays private.
    jpeg = user.get(BASE + "/api/sightings/" + unknown_report["id"] + "/photo").content
    assert identify(jpeg)["method"] == "verified_reference"

    # New-class eligibility and cumulative training use synthetic images in this DB only.
    with MongoClient(URI, serverSelectionTimeoutMS=3000) as connection:
        db = connection.get_default_database()
        assert db.trainingjobs.count_documents({}) == 0
        active = ROOT / "storage/models/mobilenetv2.keras"
        active_before = hashlib.sha256(active.read_bytes()).hexdigest()
        environment = {**os.environ, "GEOFLORA_MONGODB_URI": URI, "GEOFLORA_MIN_TRAINING_REPORTS": "1"}
        def worker():
            subprocess.run([str(ROOT / "services/ml/.venv/Scripts/python.exe"), str(ROOT / "scripts/auto_training_worker.py"), "--once"], cwd=ROOT, env=environment, timeout=180, check=True)
        synthetic_ids = []
        for index in range(3):
            stream = io.BytesIO()
            Image.fromarray(np.random.default_rng(int(uuid.uuid4().hex[:8], 16)).integers(0, 255, (128, 128, 3), dtype=np.uint8)).save(stream, format="JPEG")
            response = submit(stream.getvalue(), description="Synthetic fixture only, not a botanical observation or real invasive species.", training=True)
            assert response.status_code == 201, response.text
            row = response.json(); synthetic_ids.append(row["id"])
            response = admin.patch(BASE + "/api/admin/review", json={"id": row["id"], "action": "approve", "speciesId": "new_species", "scientificName": "Fixturea imaginaria", "commonName": "Synthetic test class", "description": "Synthetic fixture class for isolated pipeline verification, not real flora.", "citation": "https://example.org/synthetic-validation-only", "confirmed": True, "rationale": "Synthetic isolated pipeline test only; never activate this model"})
            assert response.status_code == 200, response.text
            if index == 0:
                worker()
                assert db.trainingjobs.find_one(sort=[("createdAt", -1)])["status"] == "waiting_for_data"
        worker()
        job = db.trainingjobs.find_one(sort=[("createdAt", -1)])
        assert job["status"] == "completed", job
        evaluation = json.loads((ROOT / job["candidatePath"] / "evaluation.json").read_text())
        assert "fixturea_imaginaria" in evaluation["class_order"]
        assert evaluation["dataset"]["images"] == 224  # Original 221 + all three synthetic contributions.
        assert hashlib.sha256(active.read_bytes()).hexdigest() == active_before and job["metrics"]["activated"] is False
        evidence = {"passed": True, "database": db.name, "synthetic_training_only": True, "checks": ["server-bound identification, description and citation", "report includes location and two timestamps", "actual PDF with photo, map and required text", "report/PDF owner authorization", "different-photo identification reuse rejected", "unknown description required", "review without training consent", "approved exact-photo lookup with no fabricated confidence", "private reference not shared without consent", "normalized-photo lookup", "new species waits for independent groups", "third independent sample triggers real seven-class training", "cumulative contributions retained", "active model unchanged"], "known_report_id": saved["id"], "reviewed_report_id": reviewed["id"], "synthetic_report_ids": synthetic_ids, "training_job_id": str(job["_id"]), "candidate_path": job["candidatePath"]}
        (ROOT / "docs/report-flow-smoke.json").write_text(json.dumps(evidence, indent=2))
        print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
