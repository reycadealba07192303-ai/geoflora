"""Record the owner's approval of the full GBIF catalog import and approve its pending records.

Basis is owner attestation, not independent per-record taxonomic review. Only `reviewStatus` changes
(pending -> approved) with a `catalogReview` provenance block; ecological statuses and AI support are untouched.
Each approval keeps its previous status so the batch can be reverted. Re-imports keep the decision
(services/catalog sets reviewStatus only on insert).

    python scripts/approve_catalog_owner.py --statement "<owner's words>" --confirm
    python scripts/approve_catalog_owner.py --target staging --statement "<owner's words>" --confirm
    python scripts/approve_catalog_owner.py [--target staging] --revert <batch-id> --confirm

--target staging approves species_catalog_staging source rows (catalog_review_status, with a review_events entry);
their source_ecological_status stays an unverified source claim (ecological_status_is_verified is left false).
"""
import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from pymongo import MongoClient

ROOT = Path(__file__).resolve().parents[1]
URI = os.environ.get("GEOFLORA_MONGODB_URI", "mongodb://127.0.0.1:27017/geoflora")
SOURCE_SHA = "d891ea67543dfcd3d317e9d16adabe9ab21e53c9da136ab20fc2d8f09a60ca2d"
EVIDENCE = {"catalog": ROOT / "docs/catalog-owner-approval.json", "staging": ROOT / "docs/catalog-staging-owner-approval.json"}


def counts(collection, field="reviewStatus"):
    return {row["_id"]: row["n"] for row in collection.aggregate([{"$group": {"_id": f"${field}", "n": {"$sum": 1}}}])}


def approve_staging(database, args, now):
    staging, batches = database.species_catalog_staging, database.catalog_review_batches
    scope = {"catalog_review_status": "pending"}
    if args.revert:
        reverted = {"catalog_review.batchId": args.revert}
        if not args.confirm:
            raise SystemExit(f"Dry run: {staging.count_documents(reverted)} staging rows would revert. Add --confirm.")
        result = staging.update_many(reverted, [{"$set": {"catalog_review_status": "$catalog_review.previousStatus",
                                                          "review_events": {"$filter": {"input": "$review_events", "cond": {"$ne": ["$$this.batch_id", args.revert]}}}}},
                                                {"$unset": "catalog_review"}])
        batches.update_one({"_id": args.revert}, {"$set": {"revertedAt": now}})
        print(json.dumps({"reverted": result.modified_count, "catalog_review_status": counts(staging, "catalog_review_status")}))
        return
    if not args.statement or not args.statement.strip():
        raise SystemExit("Quote the owner's approval with --statement.")
    eligible, before = staging.count_documents(scope), counts(staging, "catalog_review_status")
    if not eligible:
        raise SystemExit("No pending staging rows; nothing to approve.")
    if not args.confirm:
        raise SystemExit(f"Dry run: {eligible} pending staging rows would be approved. Add --confirm.")
    batch_id = f"owner-staging-approval-{now:%Y%m%dT%H%M%SZ}"
    batches.insert_one({"_id": batch_id, "approvedAt": now, "basis": "owner_attestation", "statement": args.statement.strip(),
                        "scope": {"collection": "species_catalog_staging", "fromStatus": "pending", "toStatus": "approved", "records": eligible, "bySource": counts(staging, "source_key")},
                        "meaning": "Source rows approved for catalog use by owner attestation. Source-reported ecological statuses remain unverified claims; no AI support is implied.",
                        "reviewStatusBefore": before})
    event = {"event": "approved", "basis": "owner_attestation", "batch_id": batch_id, "at": now, "previous_status": "pending"}
    result = staging.update_many(scope, {"$set": {"catalog_review_status": "approved", "catalog_review": {"status": "approved", "basis": "owner_attestation", "batchId": batch_id, "approvedAt": now, "previousStatus": "pending"}},
                                         "$push": {"review_events": event}})
    after = counts(staging, "catalog_review_status")
    batches.update_one({"_id": batch_id}, {"$set": {"approvedRecords": result.modified_count, "reviewStatusAfter": after}})
    still_unverified = staging.count_documents({"ecological_status_is_verified": {"$ne": True}})
    EVIDENCE["staging"].write_text(json.dumps({"batchId": batch_id, "approvedAt": now.isoformat(), "statement": args.statement.strip(), "basis": "owner_attestation",
                                               "approvedRecords": result.modified_count, "reviewStatusBefore": before, "reviewStatusAfter": after,
                                               "bySource": counts(staging, "source_key"), "rowsWithUnverifiedEcologicalStatus": still_unverified,
                                               "revert": f"python scripts/approve_catalog_owner.py --target staging --revert {batch_id} --confirm"}, indent=2), encoding="utf-8")
    print(json.dumps({"batchId": batch_id, "approved": result.modified_count, "before": before, "after": after}))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--statement", help="The owner's approval, quoted as given")
    parser.add_argument("--revert", help="Batch ID to revert")
    parser.add_argument("--confirm", action="store_true", help="Required to write")
    parser.add_argument("--target", choices=["catalog", "staging"], default="catalog")
    args = parser.parse_args()
    if not re.match(r"^mongodb://(127\.0\.0\.1|localhost)(:\d+)?/", URI):
        raise SystemExit("Only a local MongoDB database is supported.")
    database = MongoClient(URI, serverSelectionTimeoutMS=3000).get_default_database()
    catalog, batches = database.species_catalog, database.catalog_review_batches
    now = datetime.now(timezone.utc)
    if args.target == "staging":
        return approve_staging(database, args, now)

    if args.revert:
        scope = {"catalogReview.batchId": args.revert}
        if not args.confirm:
            raise SystemExit(f"Dry run: {catalog.count_documents(scope)} records would revert. Add --confirm.")
        result = catalog.update_many(scope, [{"$set": {"reviewStatus": "$catalogReview.previousStatus"}}, {"$unset": "catalogReview"}])
        batches.update_one({"_id": args.revert}, {"$set": {"revertedAt": now}})
        print(json.dumps({"reverted": result.modified_count, "reviewStatus": counts(catalog)}))
        return

    if not args.statement or not args.statement.strip():
        raise SystemExit("Quote the owner's approval with --statement.")
    scope = {"source.sourceFileSha256": SOURCE_SHA, "reviewStatus": "pending"}
    before = counts(catalog)
    eligible = catalog.count_documents(scope)
    if not eligible:
        raise SystemExit("No pending records from this source; nothing to approve.")
    if not args.confirm:
        raise SystemExit(f"Dry run: {eligible} pending records from source {SOURCE_SHA[:12]}… would be approved. Add --confirm.")
    batch_id = f"owner-catalog-approval-{now:%Y%m%dT%H%M%SZ}"
    batch = {"_id": batch_id, "approvedAt": now, "basis": "owner_attestation", "statement": args.statement.strip(),
             "scope": {"collection": "species_catalog", "sourceFileSha256": SOURCE_SHA, "fromStatus": "pending", "toStatus": "approved", "records": eligible},
             "importApproval": "Owner confirmed the full GBIF import present since 2026-10-22 15:58 UTC was approved (recorded retroactively).",
             "meaning": "Approved for catalog inclusion. Not independent per-record taxonomic review; does not verify native, naturalized or invasive status or AI support.",
             "reviewStatusBefore": before}
    batches.insert_one(batch)
    review = {"status": "approved", "basis": "owner_attestation", "batchId": batch_id, "approvedAt": now, "previousStatus": "pending"}
    result = catalog.update_many(scope, {"$set": {"reviewStatus": "approved", "catalogReview": review, "updatedAt": now}})
    after = counts(catalog)
    batches.update_one({"_id": batch_id}, {"$set": {"approvedRecords": result.modified_count, "reviewStatusAfter": after}})
    unchanged = catalog.count_documents({"source.sourceFileSha256": SOURCE_SHA, "$or": [{"aiModelSupported": True}, {"ecologicalStatuses.0": {"$exists": True}}]})
    evidence = {**batch, "approvedAt": now.isoformat(), "approvedRecords": result.modified_count, "reviewStatusAfter": after,
                "recordsWithAiSupportOrEcologicalStatus": unchanged, "revert": f"python scripts/approve_catalog_owner.py --revert {batch_id} --confirm"}
    EVIDENCE["catalog"].write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps({"batchId": batch_id, "approved": result.modified_count, "before": before, "after": after}))


if __name__ == "__main__":
    main()
