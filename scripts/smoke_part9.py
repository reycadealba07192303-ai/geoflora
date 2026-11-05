"""Part 9 checks through real HTTP on an isolated database (build apps/web first; inference on 8000).

Starts a temporary `next start` on 5174 against geoflora_part9_validation, seeded with a read-only copy of
a few catalog/staging records from the live database. Covers the sighting verification queue (approve,
reject, request correction), the original prediction kept separate from the confirmed species, the audit
history, catalog browsing indicators and live overview counts. Live data is only read.
"""
import csv
import io
import json
import os
import re
import secrets
import subprocess
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import requests
from PIL import Image
from pymongo import MongoClient
from smoke_auth_fixture import account as fixture_account

ROOT = Path(__file__).resolve().parents[1]
URI = "mongodb://127.0.0.1:27017/geoflora_part9_validation"
BASE = "http://127.0.0.1:5174"
OUTPUT = ROOT / "docs/part-9-review-catalog-smoke.json"
SEED = ["Chromolaena odorata", "Lantana camara", "Pontederia crassipes", "Mikania micrantha", "Pistia stratiotes", "Leucaena leucocephala", "Mimosa pudica", "Cryptostylis acutata"]
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
    fields = {"requestId": str(uuid.uuid4()), "species": "unknown", "plantDescription": "Shrub with clustered small flowers.", "latitude": "14.65", "longitude": "121.05",
              "locationMethod": "gps", "accuracy": "8", "placeName": "Part 9 test site", "observedAt": (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat(), "consent": "yes", "trainingConsent": "yes", **changes}
    response = session.post(BASE + "/api/sightings", data=fields, files={"image": ("plant", photo, content_type)}, timeout=30)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def seed():
    live, test = MongoClient("mongodb://127.0.0.1:27017").geoflora, MongoClient(URI).get_default_database()
    test.species_classes.insert_many([
        {"_id": "chromolaena_odorata", "scientific_name": "Chromolaena odorata", "common_name": "Hagonoy", "role": "invasive"},
        {"_id": "lantana_camara", "scientific_name": "Lantana camara", "common_name": "Lantana", "role": "invasive"},
        {"_id": "pontederia_crassipes", "scientific_name": "Pontederia crassipes", "common_name": "Water Hyacinth", "role": "invasive"},
    ])
    names = "|".join(re.escape(name) for name in SEED)
    catalog = list(live.species_catalog.find({"acceptedScientificName": {"$regex": f"^({names})( |$)"}}))
    staging = list(live.species_catalog_staging.find({"scientific_name": {"$regex": f"^({names})( |$)"}, "source_key": {"$not": re.compile("^gbif-download:")}}))
    test.species_catalog.insert_many(catalog)
    if staging:
        test.species_catalog_staging.insert_many(staging)
    return len(catalog), live.species_catalog.estimated_document_count()


def main():
    MongoClient(URI).drop_database("geoflora_part9_validation")
    seeded, live_before = seed()
    database = MongoClient(URI).get_default_database()
    env = {**os.environ, "GEOFLORA_MONGODB_URI": URI, "GEOFLORA_ML_API_URL": "http://127.0.0.1:8000"}
    log = (ROOT / "storage/logs/part9-smoke-web.log").open("w", encoding="utf-8")
    web = subprocess.Popen(["node", "node_modules/next/dist/bin/next", "start", "--hostname", "127.0.0.1", "--port", "5174"], cwd=ROOT / "apps/web", env=env, stdout=log, stderr=subprocess.STDOUT)
    try:
        for _ in range(60):
            try:
                requests.get(BASE + "/api/auth", timeout=3); break
            except requests.ConnectionError:
                time.sleep(0.5)
        admin, _ = account("setup", "fixture_admin")
        alice, _ = account("register", "alice_field")
        rita, rita_id = account("register", "rita_review")
        admin.patch(BASE + "/api/accounts", json={"id": rita_id, "action": "set-role", "role": "reviewer"}, timeout=15)

        rows = [r for r in csv.DictReader((ROOT / "storage/datasets/curated/v3/manifest.csv").open(encoding="utf-8")) if r["split"] == "test" and r["species_id"] == "chromolaena_odorata"]
        photo = (ROOT / "storage/datasets" / rows[0]["local_path"]).read_bytes()
        identified = alice.post(BASE + "/api/identify", files={"image": ("plant.jpg", photo, "image/jpeg")}, timeout=90).json()
        if identified.get("method") != "model" or identified.get("status") != "identified" or not identified.get("species", {}).get("id"):
            raise AssertionError("Quick Verify smoke fixture must produce an identified real CNN model prediction")
        predicted_name = identified["species"]["scientific_name"]
        report_quick = submit(alice, photo, "image/jpeg", identificationId=identified["identification_id"], suggestedSpecies=predicted_name, trainingConsent="yes")
        report_a = submit(alice, photo, "image/jpeg", identificationId=identified["identification_id"], species="Chromolaena odorata", trainingConsent="yes")
        report_b = submit(alice, noise(), suggestedSpecies="Mikania micrantha")
        report_c = submit(alice, noise())

        # 1. Every submitted report enters the verification queue with its evidence.
        status(alice.get(BASE + "/api/admin/review", timeout=15), 403, "contributors cannot open the verification queue")
        queue = rita.get(BASE + "/api/admin/review", timeout=15).json()
        ids = [row["id"] for row in queue["reports"]]
        check({report_a, report_b, report_c, report_quick} <= set(ids) and ids.index(report_a) < ids.index(report_c), "queue lists every awaiting report, oldest first, including model-identified ones")
        row_a = next(row for row in queue["reports"] if row["id"] == report_a)
        check(row_a["prediction"]["model_version"] == "mobilenetv2_v3_seed42" and row_a["prediction"]["confidence"] == identified["confidence"] and row_a["prediction"]["candidates"], "queue shows the original model prediction with score, version and candidates")
        check(row_a["locationMethod"] == "gps" and row_a["locationAccuracy"] == 8 and row_a["observedAt"] and row_a["submittedAt"] and row_a["placeName"] == "Part 9 test site", "queue shows location method, accuracy, place and both times")
        status(rita.get(BASE + f"/api/sightings/{report_b}/photo", timeout=15), 200, "reviewer can open the submitted photo")

        review = lambda rid, **body: rita.patch(BASE + "/api/admin/review", json={"id": rid, **body}, timeout=15)
        # 2. Quick Verify requires human confirmation and rationale; training consent alone does not approve or queue the photo.
        status(review(report_quick, action="quick_verify", speciesId=identified["species"]["id"], rationale="Visible leaf arrangement and clustered flowers match the reference.", confirmed=False), 400, "Quick Verify requires explicit human confirmation")
        status(review(report_quick, action="quick_verify", speciesId=identified["species"]["id"], rationale="", confirmed=True), 400, "Quick Verify requires a short rationale")
        response = review(report_quick, action="quick_verify", speciesId=identified["species"]["id"], rationale="Visible leaf arrangement matches the accepted reference.", confirmed=True)
        check(response.status_code == 200 and response.json()["status"] == "verified" and response.json()["trainingCandidateStatus"] == "pending_review" and response.json()["trainingQueued"] is False, "Quick Verify records a human verification but keeps the consented image out of training until separate eligibility approval")
        quick_record = database.sightings.find_one({"_id": __import__("bson").ObjectId(report_quick)})
        check(quick_record["reviewHistory"][-1]["action"] == "quick_verify" and quick_record["reviewHistory"][-1]["trainingEligible"] is False and quick_record["verifiedCitation"].startswith("https://"), "Quick Verify audit stores the action, training decision and reused HTTPS citation")
        check(report_quick in [row["id"] for row in rita.get(BASE + "/api/sightings?trainingCandidates=1", timeout=15).json()["reports"]], "consented Quick Verify image remains in the separate training-eligibility review queue")

        # 3. Request correction -> contributor sees the reason -> correction returns the report to the queue.
        # 2. Request correction -> contributor sees the reason -> correction returns the report to the queue.
        status(review(report_b, action="request_correction", rationale=""), 400, "a correction request needs a reason")
        response = review(report_b, action="request_correction", rationale="Please name the barangay where you found it.")
        check(response.status_code == 200 and response.json()["status"] == "correction_requested", "reviewer requests a correction")
        mine = alice.get(BASE + f"/api/sightings/{report_b}", timeout=15).json()
        check(mine["status"] == "correction_requested" and "barangay" in mine["latestReview"]["rationale"] and "reviewer" not in mine["latestReview"] and mine["editable"], "contributor sees the request and reason without the reviewer's identity, and can edit")
        check(report_b in [row["id"] for row in rita.get(BASE + "/api/admin/review", timeout=15).json()["reports"]], "report stays in the awaiting queue while a correction is pending")
        response = alice.patch(BASE + f"/api/sightings/{report_b}", json={"placeName": "Barangay Malanday, Marikina"}, timeout=15)
        check(response.status_code == 200 and response.json()["status"] == "pending", "contributor correction sends the report back for review")
        check(database.sightings.find_one({"placeName": "Barangay Malanday, Marikina"})["editHistory"][-1]["changes"]["status"] == {"from": "correction_requested", "to": "pending"}, "the resubmission is recorded in the edit history")

        # 4. Detailed review keeps the original prediction separate and reuses the accepted species citation.
        status(review(report_a, action="detailed_verify", speciesId="lantana_camara", rationale="Leaf and flower clusters match Lantana."), 400, "detailed verification requires the reviewer's explicit confirmation")
        response = review(report_a, action="detailed_verify", speciesId="lantana_camara", confirmed=True, trainingEligible=True, rationale="Leaf and flower clusters match Lantana.", description="Shrub with opposite leaves and clustered orange-pink flowers.")
        check(response.status_code == 200 and response.json()["status"] == "verified" and response.json()["trainingCandidateStatus"] == "approved", "reviewer verifies a corrected species in detailed review and separately approves the consented image for training: " + response.text[:250])
        stored = database.sightings.find_one({"_id": __import__("bson").ObjectId(report_a)})
        check(stored["prediction"]["species"]["id"] == "chromolaena_odorata" and stored["prediction"]["confidence"] == identified["confidence"], "the original model prediction is preserved unchanged")
        check(stored["verifiedSpeciesId"] == "lantana_camara" and stored["status"] == "verified" and stored["verifiedAt"], "the reviewer-confirmed species and verification time are stored separately")
        check(stored["verifiedCitation"] == "https://www.nparks.gov.sg/florafaunaweb/flora/2/1/2178" and stored["reviewHistory"][-1]["action"] == "detailed_verify" and stored["reviewHistory"][-1]["trainingEligible"] is True, "detailed review reuses the server-accepted citation and audits the separate training decision")
        mine = alice.get(BASE + f"/api/sightings/{report_a}", timeout=15).json()
        check(mine["species"] == "Lantana camara" and mine["verifiedSpecies"]["scientificName"] == "Lantana camara" and mine["prediction"]["species"]["scientific_name"].startswith("Chromolaena") and not mine["editable"], "contributor sees both the confirmed species and the original prediction, and can no longer edit")
        status(alice.patch(BASE + f"/api/sightings/{report_a}", json={"placeName": "late"}, timeout=15), 409, "a verified report cannot be corrected")
        status(review(report_a, action="reject", rationale="second decision"), 409, "a decided report cannot be reviewed again")

        # 4. Reject with reason; audit history.
        review(report_c, action="reject", rationale="Photo does not show a plant clearly.")
        mine = alice.get(BASE + f"/api/sightings/{report_c}", timeout=15).json()
        check(mine["status"] == "rejected" and mine["latestReview"]["action"] == "reject" and "clearly" in mine["latestReview"]["rationale"], "contributor sees the rejection and its reason")
        history = next(row for row in rita.get(BASE + "/api/admin/review?view=rejected", timeout=15).json()["reports"] if row["id"] == report_c)["reviewHistory"]
        check(history[-1]["reviewer"] == "rita_review" and history[-1]["action"] == "reject" and history[-1]["reviewedAt"], "moderators see the audit history with reviewer, action and time")
        b_history = database.sightings.find_one({"placeName": "Barangay Malanday, Marikina"})["reviewHistory"]
        check([entry["action"] for entry in b_history] == ["request_correction"], "the correction request remains in the audit history after resubmission")
        queue = rita.get(BASE + "/api/admin/review", timeout=15).json()
        check(queue["counts"] == {"pending": 1, "verified": 2, "rejected": 1} and [row["id"] for row in queue["reports"]] == [report_b], "queue counts and awaiting view reflect the decisions")
        check({row["id"] for row in rita.get(BASE + "/api/admin/review?view=verified", timeout=15).json()["reports"]} == {report_a, report_quick}, "verified view lists both verified sightings")
        sightings = alice.get(BASE + "/api/sightings", timeout=15).json()["reports"]
        check({row["id"]: row["status"] for row in sightings} == {report_a: "verified", report_b: "pending", report_c: "rejected", report_quick: "verified"}, "the contributor's map listing carries each report's verification status")

        # 5. Catalog browsing with references, review status and model support.
        status(requests.get(BASE + "/api/catalog", timeout=15), 401, "catalog requires sign-in")
        catalog = alice.get(BASE + "/api/catalog", timeout=30).json()
        check(catalog["catalogTotal"] == seeded and all(entry["reviewStatus"] == "approved" and entry["reviewBasis"] == "owner_attestation" for entry in catalog["species"]) and catalog["reviewCounts"] == {"approved": seeded}, "catalog lists the seeded records with their owner-attested approval")
        model = alice.get(BASE + "/api/catalog?filter=model", timeout=15).json()["species"]
        check(sorted(entry["binomial"] for entry in model) == ["chromolaena odorata", "lantana camara", "pontederia crassipes"] and all(entry["activeModel"] for entry in model), "live-model filter shows exactly the active model's species")
        verified = alice.get(BASE + "/api/catalog?filter=verified", timeout=15).json()["species"]
        check([(entry["binomial"], entry["verifiedSightings"]) for entry in verified] == [("chromolaena odorata", 1), ("lantana camara", 1)], "verified-sighting counts follow reviewer-confirmed species, not model predictions")
        lantana = alice.get(BASE + "/api/catalog?q=lantana", timeout=15).json()["species"][0]
        check(lantana["gbif"]["doi"] and lantana["gbif"]["citation"].startswith("GBIF.org") and lantana["verifiedEcologicalStatuses"] == [], "entries carry the GBIF reference and no verified ecological status")
        listed = alice.get(BASE + "/api/catalog?filter=listed", timeout=15).json()["species"]
        check(listed and all(entry["sourceListings"] and entry["sourceListings"][0]["title"] for entry in listed), "source-listed filter shows staged introduced/naturalized source listings with titles")
        check(alice.get(BASE + "/api/catalog?filter=all&page=99", timeout=15).json()["species"] == [], "pages past the end are empty")

        # 6. Live overview counts.
        overview = alice.get(BASE + "/api/overview", timeout=15).json()
        check(overview["sightings"] == {"awaitingReview": 1, "verified": 2, "rejected": 1, "mine": 4, "canReview": False}, "overview sighting counts are live")
        check(overview["catalog"]["records"] == seeded and overview["model"]["ready"] and overview["model"]["species"] == 3 and overview["model"]["version"] == "mobilenetv2_v3_seed42", "overview catalog and model values are live")
        check(MongoClient("mongodb://127.0.0.1:27017").geoflora.species_catalog.estimated_document_count() == live_before, "the live catalog was only read; no import or write occurred")
    finally:
        web.kill()
    OUTPUT.write_text(json.dumps({"checkedAt": datetime.now(timezone.utc).isoformat(), "database": URI, "seededCatalogRecords": seeded, "checks": checks}, indent=2), encoding="utf-8")
    print(f"{len(checks)} checks passed")


if __name__ == "__main__":
    main()
