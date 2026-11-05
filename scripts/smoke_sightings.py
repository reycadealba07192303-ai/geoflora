"""HTTP + MongoDB integration check against the isolated validation server.

Start web on 5174 with GEOFLORA_MONGODB_URI pointing to the local
geoflora_sightings_validation database. Fixture records are retained there.
"""
import io
import json
import uuid
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
from PIL import Image
from pymongo import MongoClient

URL = "http://127.0.0.1:5174/api/sightings"
http = requests.Session()


def main():
    auth_url = URL.rsplit("/", 1)[0] + "/auth"
    setup = http.get(auth_url, timeout=15).json().get("setupRequired", False)
    auth = http.post(auth_url, json={"action": "setup" if setup else "login", "username": "fixture_admin", "password": "GeoFlora-Smoke-Only-2026"}, timeout=15)
    assert auth.status_code == 200, auth.text
    image = io.BytesIO()
    Image.new("RGB", (128, 96), "green").save(image, format="PNG")
    body = {"requestId": str(uuid.uuid4()), "species": "unknown", "placeName": "Manila validation fixture", "notes": "GeoFlora automated isolated smoke fixture",
            "plantDescription": "Heart-shaped green leaves with red and white spots", "suggestedSpecies": "Caladium bicolor", "trainingConsent": "yes", "trainingCandidateStatus": "approved",
            "latitude": "14.5995", "longitude": "120.9842", "locationMethod": "manual", "consent": "yes",
            "observedAt": datetime.now(timezone.utc).isoformat()}

    def post(data, payload=None, mime="image/png", origin=None):
        return http.post(URL, data=data, files={"image": ("fixture.png", image.getvalue() if payload is None else payload, mime)},
                             headers={"Origin": origin or "http://127.0.0.1:5174"}, timeout=15)

    with MongoClient("mongodb://127.0.0.1:27017", serverSelectionTimeoutMS=2000) as client:
        collection = client.geoflora_sightings_validation.sightings
        response = post(body)
        assert response.status_code == 201, response.text
        created = response.json()
        assert created["plantDescription"] == body["plantDescription"] and created["suggestedSpecies"] == "Caladium bicolor"
        assert created["trainingConsent"] is True and created["trainingCandidateStatus"] == "pending_review"
        assert created["species"] == "unknown"  # User text must not become a verified/model label.
        candidates = http.get(URL + "?trainingCandidates=1", timeout=15).json()["reports"]
        assert any(row["id"] == created["id"] for row in candidates)
        assert all(row["trainingConsent"] and row["trainingCandidateStatus"] == "pending_review" for row in candidates)
        opted_out = {k: v for k, v in body.items() if k != "trainingConsent"}
        opted_out["requestId"] = str(uuid.uuid4())
        opted_out_response = post(opted_out)
        assert opted_out_response.status_code == 201, opted_out_response.text
        assert opted_out_response.json()["trainingConsent"] is False
        assert opted_out_response.json()["trainingCandidateStatus"] == "not_requested"
        assert not any(row["id"] == opted_out_response.json()["id"] for row in http.get(URL + "?trainingCandidates=1", timeout=15).json()["reports"])
        assert post({**body, "suggestedSpecies": "Changed suggestion"}).status_code == 409
        assert post({**body, "plantDescription": "x" * 2001}).status_code == 400
        assert post({**body, "trainingConsent": "false"}).status_code == 400
        photo_url = f"{URL}/{created['id']}/photo"
        full_photo = http.get(photo_url, timeout=15)
        assert full_photo.status_code == 200, full_photo.text
        assert full_photo.headers["Content-Type"] == "image/jpeg"
        with Image.open(io.BytesIO(full_photo.content)) as decoded:
            assert decoded.size == (128, 96)
        thumb = http.get(photo_url + "?thumbnail=1", timeout=15)
        assert thumb.status_code == 200, thumb.text
        with Image.open(io.BytesIO(thumb.content)) as decoded:
            assert decoded.size == (120, 120)
        assert http.get(photo_url, headers={"Origin": "http://foreign.example"}, timeout=15).status_code == 403
        assert http.get(f"{URL}/invalid/photo", timeout=15).status_code == 400
        assert http.get(f"{URL}/000000000000000000000000/photo", timeout=15).status_code == 404
        assert created["placeName"] == body["placeName"] and created["submittedAt"] and created["observedAt"]
        listing = http.get(URL, timeout=15)
        assert listing.status_code == 200, listing.text
        report = next(row for row in listing.json()["reports"] if row["id"] == created["id"])
        assert report == created
        assert report["latitude"] == 14.5995 and report["longitude"] == 120.9842
        assert not {"photo", "payloadHash", "requestId"}.intersection(report)
        assert http.get(URL, headers={"Origin": "http://foreign.example"}, timeout=15).status_code == 403
        saved = collection.find_one({"requestId": body["requestId"]})
        assert saved and saved["status"] == "pending" and saved["prediction"] is None
        assert saved["location"] == {"type": "Point", "coordinates": [120.9842, 14.5995]}
        assert saved["observedAt"] != saved["submittedAt"] and saved["photo"][:2] == b'\xff\xd8'
        assert collection.find_one({"_id": saved["_id"]})["notes"] == body["notes"]
        assert post(body).status_code == 200
        assert post(body).json()["submittedAt"] == created["submittedAt"]
        assert post({**body, "placeName": "Different location description"}).status_code == 409
        assert post({**body, "placeName": "x" * 201}).status_code == 400
        assert collection.count_documents({"requestId": body["requestId"]}) == 1
        assert post({**body, "notes": "different payload"}).status_code == 409
        for changes in [{"latitude": ""}, {"longitude": "181"}, {"consent": "no"}, {"observedAt": "2030-01-01T00:00:00Z"}, {"accuracy": "-1"}]:
            assert post({**body, **changes}).status_code == 400, changes
        assert post(body, b'not-an-image').status_code == 422
        assert post(body, b'text', "text/plain").status_code == 415
        assert post(body, origin="http://foreign.example").status_code == 403
        concurrent = {**body, "requestId": str(uuid.uuid4())}
        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(lambda _: post(concurrent).status_code, range(2)))
        assert sorted(statuses) == [200, 201], statuses
        assert collection.count_documents({"requestId": concurrent["requestId"]}) == 1
    result = {"status": "passed", "database": "geoflora_sightings_validation", "checks": ["persistent pending report and normalized photo", "GeoJSON longitude/latitude order", "separate observation/submission time", "identical retry and concurrent retry saved once", "changed-payload conflict", "invalid coordinates/consent/time/accuracy/image rejected", "foreign-origin write rejected", "map listing returns saved place, dates and coordinates without photo/internal fields", "listing rejects foreign origin", "retry retains original report creation time", "place-name validation and conflict"], "fixture_request_ids": [body["requestId"], concurrent["requestId"]]}
    result["photo_checks"] = ["saved report photo returns JPEG with expected dimensions", "map thumbnail is 120x120 JPEG", "foreign origin rejected", "invalid ID rejected", "missing photo returns 404"]
    result["training_feedback_checks"] = ["description and suggestion persisted separately from unknown label", "explicit opt-in creates only pending candidate", "omitted consent excludes report from training queue", "client cannot approve training status", "invalid feedback rejected", "changed suggestion produces retry conflict"]
    Path("docs/sightings-smoke-evidence.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
