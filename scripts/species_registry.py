"""Keeps the database list of species classes (collection species_classes) in step with the training data on disk.

The web app reads this list when reviewers verify a report, so it works without access to this computer's storage
folder (for example on Vercel). Sources: the five classes of the v5 dataset and every collected staging group
(storage/datasets/staging/{role}_{group}_ph/group.json). Species added by reviewers live on the reports themselves.

Run directly to sync now; the training worker and the photo collector also sync on their own.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from pymongo import MongoClient, UpdateOne

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "storage/datasets/curated/v5_part2_final_five_classes/class_mapping.json"
STAGING = ROOT / "storage/datasets/staging"


def local_classes():
    classes = {entry["id"]: {**entry, "role": entry.get("role", "unclassified")} for entry in json.loads(BASE.read_text(encoding="utf-8"))["classes"]}
    for folder in sorted(STAGING.glob("*_ph")):
        if not folder.name.startswith(("invasive_", "lookalike_")) or not (folder / "group.json").exists():
            continue
        group = json.loads((folder / "group.json").read_text(encoding="utf-8"))
        role = group.get("role", "lookalike")
        if role == "invasive" and not (group.get("status") == "confirmed_target_invasive" and group.get("ecological_review_confirmed") is True and group.get("ecological_reviewer")):
            role = "unclassified"
        classes.setdefault(group["id"], {"id": group["id"], "scientific_name": group["scientific_name"], "common_name": group["common_name"],
                                         "role": role, "ecological_status": group.get("status", "pending_ecological_review"), "ecological_review_confirmed": group.get("ecological_review_confirmed") is True,
                                         "ecological_citation": group.get("ecological_citation", ""), "ecological_reviewer": group.get("ecological_reviewer", ""),
                                         **({"citation": group["citation"]} if group.get("citation") else {})})
    return classes


def sync(db):
    now = datetime.now(timezone.utc)
    classes = local_classes()
    db.species_classes.bulk_write([UpdateOne({"_id": key}, {"$set": {k: v for k, v in entry.items() if k in ("scientific_name", "common_name", "role", "citation", "ecological_status", "ecological_review_confirmed", "ecological_citation", "ecological_reviewer")} | {"updatedAt": now}}, upsert=True)
                                   for key, entry in classes.items()])
    return len(classes)


def database_uri():
    return os.environ.get("GEOFLORA_MONGODB_URI", "mongodb://127.0.0.1:27017/geoflora")


def sync_now():
    with MongoClient(database_uri(), serverSelectionTimeoutMS=8000) as client:
        return sync(client.get_default_database())


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(ROOT / "services/ml/src"))
    from geoflora_ml.env import load_env
    load_env()
    print(f"Species classes in the database: {sync_now()}")
