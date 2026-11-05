"""Local background worker: approved target-invasive data -> frozen data -> evaluated experimental candidate.

New sighting photos require contributor training consent, a human detailed verification, independently recorded
Philippine target-invasive status, and separate human rights/provenance training approval. AI labels, source folder
names, source flags, user suggestions and classifier scores do not count. A training candidate remains inactive
until an administrator explicitly approves promotion after evaluation. The previous model is kept for rollback.
Run with --once for one queue pass, otherwise poll every 15 seconds.
"""
import argparse
import csv
import hashlib
import json
import os
import subprocess
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bson import ObjectId
from PIL import Image
from pymongo import MongoClient, ReturnDocument
from pymongo.errors import DuplicateKeyError
from geoflora_ml.datasets.duplicates import group_near_duplicates, perceptual_hash
from geoflora_ml.datasets.split import assign_group_splits
from geoflora_ml.collection.licensing import training_license_eligible
from geoflora_ml.env import load_env
from model_promotion import _observation_keys, benchmark_hashes, benchmark_rows, candidate_promotion_decision, compare, historical_test_rows, promote
from species_registry import sync as sync_species

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "storage/datasets/curated/v5_part2_final_five_classes"
load_env()
MINIMUM = max(1, int(os.environ.get("GEOFLORA_MIN_TRAINING_REPORTS", "1")))
MIN_GROUPS_PER_CLASS = max(3, int(os.environ.get("GEOFLORA_MIN_TRAINING_GROUPS_PER_CLASS", "10")))


class WaitingForData(ValueError):
    pass


def worker_status(db, stage, job_id=None):
    """Shown on the admin review page; kept in the database so the web app can read it wherever it runs."""
    db.worker_status.replace_one({"_id": "auto_training"}, {"database": db.name, "stage": stage, "pid": os.getpid(), "jobId": str(job_id) if job_id else None,
                                                           "updatedAt": datetime.now(timezone.utc).isoformat()}, upsert=True)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, default=str), encoding="utf-8")


# Staging photos also need explicit human label approval plus a cited Philippine target-invasive status decision;
# source flags, community identifications and folder names are not ecological approval.
USABLE = {"approved"}


def training_report_query(job_id=None):
    query = {"status": "verified", "labelReviewStatus": "approved", "verifiedEcologicalStatus": "target_invasive", "trainingConsent": True, "trainingCandidateStatus": "approved",
             "reviewHistory": {"$elemMatch": {"basis": "human", "trainingEligible": True, "confirmed": True}}}
    query["trainingJobId"] = None if job_id is None else {"$ne": None}
    return query


def manually_reviewed_staging_row(row):
    reviewer = str(row.get("reviewer") or "").strip()
    rationale = str(row.get("review_rationale") or row.get("rationale") or "").strip()
    return row.get("review_status") in USABLE and bool(reviewer) and not reviewer.lower().startswith("ai:") and len(rationale) >= 10


def staging_ecology_eligible(meta):
    """Source labels/collection folder names are not an ecological-status decision."""
    if (meta.get("role") != "invasive" or meta.get("status") != "confirmed_target_invasive"
            or meta.get("ecological_review_confirmed") is not True or not str(meta.get("ecological_reviewer") or "").strip()):
        return False
    citation = str(meta.get("ecological_citation") or "")
    rationale = str(meta.get("ecological_rationale") or "").strip()
    try:
        from urllib.parse import urlparse
        parsed = urlparse(citation)
        return parsed.scheme == "https" and bool(parsed.netloc) and len(rationale) >= 20
    except ValueError:
        return False


PHASH_CACHE = ROOT / "storage/datasets/staging/.perceptual_hashes.json"


def benchmark_lookalike_filter():
    """Returns a test for photos close to any historical test photo (perceptual hash within 6 bits).

    The same picture can reach us twice, for example from GBIF in the benchmark and from iNaturalist in staging, with
    different bytes; training on it would inflate the candidate's benchmark score. Hashes are cached by checksum.
    """
    cache = json.loads(PHASH_CACHE.read_text()) if PHASH_CACHE.exists() else {}
    def phash(sha, path):
        if sha not in cache:
            cache[sha] = perceptual_hash(path)
        return cache[sha]
    benchmark = []
    seen = set()
    for row in historical_test_rows():
        sha = str(row.get("sha256") or "")
        path = ROOT / str(row.get("local_path") or "")
        if sha and sha not in seen and (sha in cache or path.is_file()):
            benchmark.append(phash(sha, path))
            seen.add(sha)
    def same_as_benchmark(sha, path):
        value = phash(sha, path)
        return any((value ^ other).bit_count() <= 6 for other in benchmark)
    def save():
        PHASH_CACHE.write_text(json.dumps(cache))
    return same_as_benchmark, save


def approved_staging(held_out=frozenset(), held_groups=frozenset(), check_benchmark=False):
    """Usable staging photos for confirmed invasive target classes only.

    Photos of the fixed promotion benchmark, by checksum or observation (and, with check_benchmark, by look), never
    join training. The visual check is slow, so only the dataset freeze runs it, not the queue poll.
    """
    rows, classes, skipped, skipped_exact = [], [], 0, 0
    staged_checksums: dict[str, str] = {}
    same_as_benchmark, save = benchmark_lookalike_filter() if check_benchmark else (None, None)
    for folder in sorted((ROOT / "storage/datasets/staging").glob("*_ph")):
        if not folder.name.startswith(("invasive_", "lookalike_")):
            continue
        meta_path, queue = folder / "group.json", folder / "review_queue.csv"
        if not meta_path.exists() or not queue.exists():
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if not staging_ecology_eligible(meta):
            continue
        with queue.open(encoding="utf-8", newline="") as stream:
            approved = [row for row in csv.DictReader(stream)
                        if manually_reviewed_staging_row(row)
                        and row.get("sha256") not in held_out
                        and not (_observation_keys(row) & held_groups)
                        and training_license_eligible(row.get("license"), row.get("attribution"))]
        if not approved:
            continue
        role = meta["role"]
        classes.append({"id": meta["id"], "scientific_name": meta["scientific_name"], "common_name": meta["common_name"], "role": role})
        for row in approved:
            previous_species = staged_checksums.get(row["sha256"])
            if previous_species is not None:
                if previous_species != meta["id"]:
                    raise ValueError(f"Exact staged image has conflicting labels: {row['sha256']}")
                skipped_exact += 1
                continue
            staged_checksums[row["sha256"]] = meta["id"]
            if same_as_benchmark and same_as_benchmark(row["sha256"], folder / row["local_path"]):
                skipped += 1
                continue
            owner = row["source"] == "owner_field_photo"
            rows.append({"species_id": meta["id"], "scientific_name": meta["scientific_name"], "source": row["source"], "source_id": row["source_id"], "group_id": f"{meta['id']}:{row['group_id']}",
                         "sha256": row["sha256"], "local_path": (folder / row["local_path"]).relative_to(ROOT).as_posix(), "license": row["license"], "attribution": row["attribution"],
                         "label_basis": "owner_attested_ai_screened" if owner else "inaturalist_research_grade" if row["review_status"] == "research_grade" else "source_label_ai_screened",
                         "country_basis": "owner_attestation" if owner else "source_PH_filter", "selection_status": f"staging_{role}", "role": role})
    if save:
        save()
        print(f"Staging photos left out as look-alikes of benchmark photos: {skipped}; exact duplicate staging copies: {skipped_exact}", flush=True)
    return rows, classes


def maybe_queue(db):
    db.trainingjobs.create_index("activeKey", unique=True, sparse=True)
    if db.trainingjobs.find_one({"activeKey": "training"}):
        return
    ready = list(db.sightings.find(training_report_query(), {"_id": 1, "verifiedSpeciesId": 1, "identificationId": 1, "photoHash": 1, "sourcePhotoHash": 1}).sort("_id", 1).limit(500))
    per_class_groups = Counter()
    seen_groups = set()
    for report in ready:
        species = report.get("verifiedSpeciesId")
        group = report.get("identificationId") or report.get("photoHash") or report.get("sourcePhotoHash") or str(report["_id"])
        key = (species, str(group))
        if species and key not in seen_groups:
            per_class_groups[species] += 1
            seen_groups.add(key)
    ready = [row for row in ready if row.get("verifiedSpeciesId") and per_class_groups[row["verifiedSpeciesId"]] >= MIN_GROUPS_PER_CLASS]
    # New usable staging photos also start a job, even without new reports.
    staged = len(approved_staging()[0])
    last = db.trainingjobs.find_one({"stagingPhotos": {"$exists": True}}, sort=[("createdAt", -1)])
    new_staged = staged > (last or {}).get("stagingPhotos", 0)
    if len(ready) < MINIMUM and not new_staged:
        return
    try:
        now = datetime.now(timezone.utc)
        result = db.trainingjobs.insert_one({"activeKey": "training", "status": "queued", "reportIds": [str(row["_id"]) for row in ready], "stagingPhotos": staged, "createdAt": now, "updatedAt": now, "detail": "Queued automatically after verified-label threshold" if len(ready) >= MINIMUM else "Queued automatically after new usable staging photos"})
        db.sightings.update_many({"_id": {"$in": [row["_id"] for row in ready]}, "trainingJobId": None}, {"$set": {"trainingJobId": str(result.inserted_id)}})
    except DuplicateKeyError:
        pass


def freeze_job(db, job):
    folder = ROOT / f"storage/datasets/curated/auto_{job['_id']}"
    folder.mkdir(parents=True, exist_ok=False)
    (folder / "images").mkdir()
    with (BASE / "manifest.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    # Every curated historical test split, not only the fixed promotion benchmark, stays out of training.
    held_out, held_groups = benchmark_hashes()
    rows = [row for row in rows if row["sha256"] not in held_out and not (_observation_keys(row) & held_groups)]
    same_as_historical_test, save_phash_cache = benchmark_lookalike_filter()
    # Dataset-local near-duplicate IDs cannot be compared across versions. Recompute
    # perceptual hashes against every historical test photo before retaining base rows.
    base_rows = []
    filtered_near_test = 0
    for row in rows:
        image_path = ROOT / row["local_path"]
        if same_as_historical_test(row["sha256"], image_path):
            filtered_near_test += 1
            continue
        base_rows.append(row)
    rows = base_rows
    if filtered_near_test:
        print(f"Excluded baseline images visually matching historical test photos: {filtered_near_test}", flush=True)
    lookalike_rows, lookalike_classes = approved_staging(held_out, held_groups, check_benchmark=True)
    classes = [{**entry, "role": entry.get("role", "invasive")} for entry in json.loads((BASE / "class_mapping.json").read_text())["classes"]]
    names = {entry["id"]: entry["scientific_name"] for entry in classes}
    seen = {row["sha256"]: row["species_id"] for row in rows}
    snapshot = json.loads((BASE / "reviews_snapshot.json").read_text())
    added = 0
    # Keep all approved contributions in later versions; do not forget earlier batches.
    reports = list(db.sightings.find(training_report_query(job_id=True)))
    for report in reports:
        species = report.get("verifiedSpeciesId")
        review = report.get("reviewHistory", [])
        if report.get("verifiedEcologicalStatus") != "target_invasive" or not species or not review or review[-1].get("basis") != "human" or review[-1].get("action") != "detailed_verify" or not review[-1].get("confirmed") or review[-1].get("trainingEligible") is not True:
            raise ValueError("Candidate lacks administrator-confirmed target status and separate human training approval")
        by_ai = False
        if species not in names:
            if not report.get("verifiedScientificName") or not report.get("verifiedCitation"):
                raise ValueError("New species needs a verified scientific name and citation")
            classes.append({"id": species, "scientific_name": report["verifiedScientificName"], "common_name": report.get("verifiedCommonName") or report["verifiedScientificName"], "role": "invasive"})
            names[species] = report["verifiedScientificName"]
        data = bytes(report["photo"])
        sha = hashlib.sha256(data).hexdigest()
        if sha in held_out:
            continue
        if sha in seen:
            if seen[sha] != species:
                raise ValueError("Identical photo has conflicting verified labels")
            continue
        path = folder / "images" / f"{report['_id']}.jpg"
        path.write_bytes(data)
        with Image.open(path) as image:
            image.verify()
        if same_as_historical_test(sha, path):
            path.unlink(missing_ok=True)
            continue
        rows.append({"species_id": species, "scientific_name": names[species], "source": "user_report", "source_id": str(report["_id"]), "group_id": f"report:{report['_id']}", "sha256": sha, "local_path": path.relative_to(ROOT).as_posix(), "license": "explicit_user_permission" if by_ai else "explicit_user_permission_admin_checked", "attribution": f"Local contributor {report.get('ownerId', 'legacy')}", "label_basis": "ai_reviewer_with_classifier_agreement" if by_ai else "administrator_verified", "country_basis": "recorded_location_within_PH_bounds" if by_ai else "administrator_PH_confirmation", "selection_status": "experimental_only"})
        snapshot.append({"source": "user_report", "source_id": str(report["_id"]), "review": review[-1]})
        seen[sha] = species
        added += 1
    save_phash_cache()
    # Staging photos join after the reports so a sighting verified as a staged class uses that class.
    for entry in lookalike_classes:
        if entry["id"] not in names:
            classes.append(entry)
            names[entry["id"]] = entry["scientific_name"]
    unique_staging_rows = []
    for row in lookalike_rows:
        previous_species = seen.get(row["sha256"])
        if previous_species is not None:
            if previous_species != row["species_id"]:
                raise ValueError(f"Exact image has conflicting labels across baseline and staging: {row['sha256']}")
            continue
        seen[row["sha256"]] = row["species_id"]
        unique_staging_rows.append(row)
    lookalike_rows = unique_staging_rows
    rows += lookalike_rows
    if added + len(lookalike_rows) < MINIMUM:
        raise WaitingForData(f"Only {added} unique approved photos; {MINIMUM} required after duplicate removal")
    for row in rows:
        row.pop("near_duplicate_group_id", None)
    rows, _ = group_near_duplicates(rows, ROOT)
    held = []
    for entry in classes:
        selected = [row for row in rows if row["species_id"] == entry["id"]]
        try:
            assign_group_splits(selected, seed=42)
        except ValueError:
            held.append(entry["id"])
    if held:
        write_json(folder / "waiting_species.json", {"species_ids": held, "reason": "Need at least three independent source/near-duplicate groups for leakage-free train/validation/test splits"})
        rows = [row for row in rows if row["species_id"] not in held]
        classes = [entry for entry in classes if entry["id"] not in held]
    job_ids = set(job["reportIds"])
    if not any(row.get("source") == "user_report" and row["source_id"] in job_ids for row in rows) and not (job.get("stagingPhotos") and lookalike_rows):
        raise WaitingForData("Reviewed species saved for reference lookup; more independent photos are needed before classifier training")
    classes.sort(key=lambda entry: entry["id"])
    rows = assign_group_splits(rows, seed=42)
    fields = sorted(set().union(*(row.keys() for row in rows)))
    with (folder / "manifest.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    write_json(folder / "reviews_snapshot.json", snapshot)
    write_json(folder / "class_mapping.json", {"classes": classes})
    write_json(folder / "species.yaml", {"species": classes})
    metadata = {"seed": 42, "images": len(rows), "added_user_reports": added, "manifest_sha256": digest(folder / "manifest.csv"), "reviews_snapshot_sha256": digest(folder / "reviews_snapshot.json"), "per_class": {entry["id"]: dict(Counter(row["split"] for row in rows if row["species_id"] == entry["id"])) for entry in classes}, "scope": "Experimental batch; fresh grouped partition of previously explored baseline plus verified reports. Not a prospective nationwide benchmark."}
    write_json(folder / "dataset_metadata.json", metadata)
    return folder


def run_once(db):
    expired = datetime.now(timezone.utc) - timedelta(minutes=40)
    db.trainingjobs.update_many({"status": "running", "updatedAt": {"$lt": expired}}, {"$set": {"status": "failed", "detail": "Worker lease expired; candidate was not activated"}, "$unset": {"activeKey": ""}})
    process_approved_promotions(db)
    sync_species(db)
    maybe_queue(db)
    job = db.trainingjobs.find_one_and_update({"status": "queued"}, {"$set": {"status": "running", "updatedAt": datetime.now(timezone.utc), "detail": "Checking approved images and preparing grouped splits"}}, return_document=ReturnDocument.AFTER)
    if not job:
        worker_status(db, "waiting_for_approved_data")
        return False
    extra = list(db.sightings.find(training_report_query(), {"_id": 1}))
    if extra:
        ids = [row["_id"] for row in extra]
        db.sightings.update_many({"_id": {"$in": ids}, "trainingJobId": None}, {"$set": {"trainingJobId": str(job["_id"])}})
        db.trainingjobs.update_one({"_id": job["_id"]}, {"$addToSet": {"reportIds": {"$each": [str(value) for value in ids]}}})
        job = db.trainingjobs.find_one({"_id": job["_id"]})
    worker_status(db, "training", job["_id"])
    try:
        folder = freeze_job(db, job)
        output = ROOT / f"storage/models/candidates/auto_{job['_id']}"
        logs = ROOT / "storage/logs/training"
        logs.mkdir(parents=True, exist_ok=True)
        with (logs / f"{job['_id']}.log").open("w", encoding="utf-8") as stream:
            result = subprocess.run([str(ROOT / "services/ml/.venv/Scripts/python.exe"), str(ROOT / "scripts/train_expanded.py"), "--frozen-dataset", str(folder), "--output", str(output), "--status", str(folder / "training_status.json")], cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, timeout=1800)
        if result.returncode:
            raise RuntimeError(f"Training exited {result.returncode}; see storage/logs/training/{job['_id']}.log")
        evaluation = json.loads((output / "evaluation.json").read_text())
        report = evaluation["classification_report"]
        passed = evaluation["accuracy"] >= .85 and report["macro avg"]["f1-score"] >= .85 and all(report[name]["recall"] >= .80 for name in evaluation["class_order"])
        metrics = {
            "accuracy": evaluation["accuracy"], "macroF1": report["macro avg"]["f1-score"], "qualityTargetsPassed": passed, "activated": False,
            "perClass": {name: {key: report[name].get(key) for key in ("precision", "recall", "f1-score", "support")} for name in evaluation["class_order"]},
            "artifacts": {name: digest(output / name) for name in ("mobilenetv2.keras", "class_mapping.json", "evaluation.json")},
        }
        comparison = None
        promotion = candidate_promotion_decision(passed)
        detail = "Candidate evaluated; quality targets failed, active model preserved"
        if passed:
            worker_status(db, "benchmarking", job["_id"])
            comparison = compare(output)
            metrics["benchmark"] = comparison
            promotion = candidate_promotion_decision(True, comparison)
            if promotion["eligible"]:
                detail = "Candidate passed automated evaluation gates and is awaiting explicit administrator promotion approval"
            else:
                detail = f"Not eligible for promotion: {promotion['reason']}; active model preserved"
        db.trainingjobs.update_one({"_id": job["_id"]}, {"$set": {"status": "completed", "updatedAt": datetime.now(timezone.utc), "metrics": metrics, "promotion": promotion, "candidatePath": output.relative_to(ROOT).as_posix(), "detail": detail}, "$unset": {"activeKey": ""}})
    except WaitingForData as error:
        db.trainingjobs.update_one({"_id": job["_id"]}, {"$set": {"status": "waiting_for_data", "updatedAt": datetime.now(timezone.utc), "detail": str(error)}, "$unset": {"activeKey": ""}})
    except Exception as error:
        db.trainingjobs.update_one({"_id": job["_id"]}, {"$set": {"status": "failed", "updatedAt": datetime.now(timezone.utc), "detail": str(error)[:2000]}, "$unset": {"activeKey": ""}})
        print(f"Training job {job['_id']} failed: {error}", flush=True)
    worker_status(db, "waiting_for_approved_data")
    return True


def process_approved_promotions(db):
    """Install only a candidate explicitly approved by an administrator after evaluation."""
    job = db.trainingjobs.find_one({"status": "completed", "promotion.status": "approved", "promotion.eligible": True})
    if not job:
        return False
    candidates_root = (ROOT / "storage/models/candidates").resolve()
    candidate_dir = (ROOT / str(job.get("candidatePath") or "")).resolve()
    if candidates_root not in candidate_dir.parents or not (candidate_dir / "evaluation.json").is_file():
        db.trainingjobs.update_one({"_id": job["_id"]}, {"$set": {"promotion.status": "failed", "promotion.error": "Candidate path or evaluation record is invalid", "updatedAt": datetime.now(timezone.utc)}})
        return True
    try:
        evaluation = json.loads((candidate_dir / "evaluation.json").read_text(encoding="utf-8"))
        expected_artifacts = job.get("metrics", {}).get("artifacts", {})
        current_artifacts = {name: digest(candidate_dir / name) for name in ("mobilenetv2.keras", "class_mapping.json", "evaluation.json")}
        if not expected_artifacts or current_artifacts != expected_artifacts:
            raise ValueError("Candidate artifact changed after administrator evaluation")
        report = evaluation["classification_report"]
        passed = evaluation["accuracy"] >= .85 and report["macro avg"]["f1-score"] >= .85 and all(report[name]["recall"] >= .80 for name in evaluation["class_order"])
        if not passed:
            raise ValueError("Candidate evaluation no longer passes the promotion quality gates")
        metrics = {"accuracy": evaluation["accuracy"], "macroF1": report["macro avg"]["f1-score"], "qualityTargetsPassed": True, "activated": False}
        comparison = compare(candidate_dir)
        if not comparison["promote"]:
            raise ValueError(f"Candidate no longer passes the live-model comparison: {comparison['reason']}")
        result = promote(candidate_dir, str(job["_id"]), metrics, comparison, job["promotion"])
        if not result.get("activated"):
            raise RuntimeError(result.get("error", "Promotion failed and was rolled back"))
        db.trainingjobs.update_one({"_id": job["_id"], "promotion.status": "approved"}, {"$set": {
            "promotion.status": "promoted", "promotion.activatedAt": datetime.now(timezone.utc),
            "promotion.modelVersion": result.get("modelVersion"), "promotion.rollbackBackup": result.get("backup"),
            "metrics.activated": True, "detail": f"Administrator-approved candidate is now serving {result.get('modelVersion')}",
            "updatedAt": datetime.now(timezone.utc),
        }})
    except Exception as error:
        db.trainingjobs.update_one({"_id": job["_id"], "promotion.status": "approved"}, {"$set": {
            "promotion.status": "failed", "promotion.error": str(error)[:1000],
            "detail": "Administrator-approved promotion failed; previous active model preserved", "updatedAt": datetime.now(timezone.utc),
        }})
        print(f"Approved promotion {job['_id']} failed: {error}", flush=True)
    return True


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--once", action="store_true"); args = parser.parse_args()
    uri = os.environ.get("GEOFLORA_MONGODB_URI", "mongodb://127.0.0.1:27017/geoflora")
    # Local MongoDB or MongoDB Atlas (mongodb+srv://), the same database the web app uses.
    with MongoClient(uri, serverSelectionTimeoutMS=8000) as client:
        db = client.get_default_database()
        while True:
            try:
                run_once(db)
            except Exception as error:
                print(f"Queue unavailable: {type(error).__name__}: {error}", flush=True)
                if args.once: raise
            if args.once: break
            time.sleep(15)


if __name__ == "__main__":
    main()
