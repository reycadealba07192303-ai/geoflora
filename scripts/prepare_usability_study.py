"""Prepare an isolated usability-study workspace (docs/part-11-usability-kit.md). It records no participant data.

Creates the study database with:
- a read-only copy of the live species catalog and staging rows (task T7);
- clearly labeled practice sightings: 3 awaiting review (T6) and 12 verified across two months (T8);
- the T2/T3 photo in storage/study/materials, chosen as a Lantana held-out photo the live model identifies.
Refuses to touch a database that already holds study sessions unless --reset is given. The facilitator
creates the administrator and reviewer accounts in the app (see the run-day checklist).

    services/ml/.venv/Scripts/python.exe scripts/prepare_usability_study.py [--database geoflora_study] [--reset]
"""
import argparse
import csv
import hashlib
import io
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from bson import ObjectId
from PIL import Image
from pymongo import MongoClient

ROOT = Path(__file__).resolve().parents[1]
MATERIALS = ROOT / "storage/study/materials"
PRACTICE = "Practice data for the usability study — not a real sighting"
SPECIES = {"lantana_camara": ("Lantana camara", "Lantana"), "chromolaena_odorata": ("Chromolaena odorata", "Hagonoy"), "pontederia_crassipes": ("Pontederia crassipes", "Water Hyacinth")}
CITATIONS = {"lantana_camara": "https://www.cbd.int/doc/world/ph/ph-nr-04-en.pdf#page=23", "chromolaena_odorata": "https://www.philchm.ph/wp-content/uploads/2019/03/NISSAP-Philippines-2016_final-draft.pdf", "pontederia_crassipes": "https://www.philchm.ph/wp-content/uploads/2019/03/NISSAP-Philippines-2016_final-draft.pdf"}
SITES = [("Marikina River Park, Marikina", 14.6362, 121.0965), ("Laguna de Bay shore, Taguig", 14.5110, 121.0700), ("Pasig River, Santa Ana, Manila", 14.5800, 121.0130), ("UP Diliman, Quezon City", 14.6538, 121.0685)]


def jpeg(path):
    with Image.open(path) as image:
        image = image.convert("RGB"); image.thumbnail((1600, 1600))
        buffer = io.BytesIO(); image.save(buffer, format="JPEG", quality=85)
    return buffer.getvalue()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", default="geoflora_study")
    parser.add_argument("--reset", action="store_true", help="Drop an existing study database, including any recorded sessions")
    args = parser.parse_args()
    if not args.database.startswith("geoflora_study"):
        raise SystemExit("Study databases must be named geoflora_study*; the live geoflora database is never used.")
    client = MongoClient("mongodb://127.0.0.1:27017", serverSelectionTimeoutMS=3000)
    if args.database in client.list_database_names():
        if client[args.database].studysessions.count_documents({}) and not args.reset:
            raise SystemExit(f"{args.database} already holds study sessions. Use --reset only if they should be deleted.")
        if not args.reset:
            raise SystemExit(f"{args.database} already exists. Use --reset to rebuild it.")
        client.drop_database(args.database)
    db, live = client[args.database], client.geoflora
    db.species_catalog.insert_many(list(live.species_catalog.find()))
    db.species_catalog_staging.insert_many(list(live.species_catalog_staging.find()))

    rows = [r for r in csv.DictReader((ROOT / "storage/datasets/curated/v3/manifest.csv").open(encoding="utf-8")) if r["split"] == "test"]
    path = lambda row: ROOT / "storage/datasets" / row["local_path"]
    # T2/T3 photo: the Lantana held-out photo the live model identifies with the highest score.
    scored = []
    for row in (r for r in rows if r["species_id"] == "lantana_camara"):
        result = requests.post("http://127.0.0.1:8000/predict", files={"image": ("plant.jpg", path(row).read_bytes(), "image/jpeg")}, timeout=60).json()
        if result.get("status") == "identified" and result["species"]["id"] == "lantana_camara":
            scored.append((result["confidence"], row))
    confidence, chosen = max(scored, key=lambda item: item[0])
    MATERIALS.mkdir(parents=True, exist_ok=True)
    (MATERIALS / "T2-T3-plant-photo.jpg").write_bytes(path(chosen).read_bytes())
    (MATERIALS / "T2-T3-plant-photo-attribution.txt").write_text(f"{chosen['attribution']}\nLicense: {chosen['license']}\nSource: {chosen['source_url']}\nLive model check: Lantana camara at {confidence:.3f}\n", encoding="utf-8")

    others = [r for r in rows if r["sha256"] != chosen["sha256"]]
    now = datetime(2026, 10, 27, 1, 0, tzinfo=timezone.utc)
    docs = []
    def doc(row, status, observed, site):
        photo = jpeg(path(row)); place, lat, lng = site
        base = {"_id": ObjectId(), "ownerId": "study-practice-data", "requestId": str(uuid.uuid4()), "payloadHash": uuid.uuid4().hex, "reportedSpecies": "unknown",
                "plantDescription": "Practice report: plant seen beside the path.", "notes": PRACTICE, "placeName": place, "observedAt": observed, "submittedAt": observed + timedelta(hours=3),
                "location": {"type": "Point", "coordinates": [lng, lat]}, "locationMethod": "manual", "locationAccuracy": None, "status": status, "photo": photo, "photoContentType": "image/jpeg",
                "photoHash": hashlib.sha256(photo).hexdigest(), "trainingConsent": False, "trainingCandidateStatus": "not_requested", "labelReviewStatus": "pending" if status == "pending" else "approved",
                "reviewHistory": [], "editHistory": [], "prediction": None, "technicalCheck": "accepted"}
        if status == "verified":
            name, common = SPECIES[row["species_id"]]
            base.update(verifiedSpeciesId=row["species_id"], verifiedScientificName=name, verifiedCommonName=common, verifiedDescription="Practice record for the usability study.", verifiedCitation=CITATIONS[row["species_id"]], verifiedAt=observed + timedelta(days=1),
                        reviewHistory=[{"reviewerId": "study-setup", "reviewer": "study-setup", "action": "approve", "confirmed": True, "speciesId": row["species_id"], "scientificName": name, "rationale": PRACTICE, "reviewedAt": observed + timedelta(days=1)}])
        return base
    # 12 verified: September and October 2026 (T8 reads the latest month).
    for index, row in enumerate(others[:12]):
        month = 9 if index < 5 else 10
        docs.append(doc(row, "verified", datetime(2026, month, 3 + index, 2, 0, tzinfo=timezone.utc), SITES[index % len(SITES)]))
    # 3 awaiting review (T6).
    for index, row in enumerate(others[12:15]):
        docs.append(doc(row, "pending", now - timedelta(days=index + 1), SITES[(index + 1) % len(SITES)]))
    db.sightings.insert_many(docs)
    db.sightings.create_index([("location", "2dsphere")])

    october = sorted({SPECIES[r["species_id"]][0] for r, d in zip(others[:12], docs[:12]) if d["observedAt"].month == 10})
    answers = {"T7": "Lantana camara is supported by the live model mobilenetv2_v3_seed42.",
               "T8": {name: sum(1 for d in docs[:12] if d["observedAt"].month == 10 and d["verifiedScientificName"] == name) for name in october}}
    summary = {"database": args.database, "preparedAt": datetime.now(timezone.utc).isoformat(), "catalogRecords": db.species_catalog.estimated_document_count(),
               "practiceSightings": {"verified": 12, "awaitingReview": 3}, "t2Photo": str((MATERIALS / "T2-T3-plant-photo.jpg").relative_to(ROOT)), "t2LiveModelScore": round(confidence, 3),
               "facilitatorAnswerKey": answers, "studySessions": 0}
    (MATERIALS / "study-setup.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
