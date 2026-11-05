"""Bounded, isolated iNaturalist collection for weak classes.

Records are written only to storage/datasets/review_pools and always remain
pending. They are not visible to the model-training worker.
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/ml/src"))

from geoflora_ml.collection.http import ApiClient
from geoflora_ml.collection.inaturalist import INaturalistSource
from geoflora_ml.collection.licensing import training_license_eligible
from geoflora_ml.config import Species
from geoflora_ml.datasets.images import MAX_IMAGE_BYTES, validate_and_store
from geoflora_ml.datasets.manifest import read_jsonl

CLASSES = {
    "broussonetia_papyrifera": Species("broussonetia_papyrifera", "Broussonetia papyrifera", "Paper mulberry"),
    "mikania_micrantha": Species("mikania_micrantha", "Mikania micrantha", "Mile-a-minute"),
    "coccinia_grandis": Species("coccinia_grandis", "Coccinia grandis", "Ivy gourd"),
}
POOL = ROOT / "storage/datasets/review_pools/weak_classes_followup_20261101"
FROZEN = ROOT / "storage/datasets/curated/auto_6ae5cd74af23d762feaa0889_weakreview_v3_20261101/manifest.csv"
OUT = ROOT / "docs/weak-class-followup-collection-2026-11-01.json"
CSV_FIELDS = ["species_id", "source", "source_id", "observation_id", "group_id", "source_url", "image_url", "license", "attribution", "country_code", "locality", "observed_at", "sha256", "local_path", "review_status", "reviewer", "review_rationale", "evaluation_holdout"]


def read_csv(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def all_existing():
    """Collect hashes and observation/source identities across curated + staging."""
    hashes: set[str] = set()
    observations: dict[str, set[str]] = defaultdict(set)
    photo_ids: set[tuple[str, str]] = set()
    if FROZEN.exists():
        for r in read_csv(FROZEN):
            hashes.add(r.get("sha256", ""))
            for field in ("observation_id", "group_id", "near_duplicate_group_id"):
                if r.get(field): observations[r["species_id"]].add(str(r[field]))
            if r.get("source") and r.get("source_id"):
                photo_ids.add((r["source"], str(r["source_id"])))
    staging = ROOT / "storage/datasets/staging"
    for manifest in staging.rglob("raw/manifest.jsonl"):
        try:
            rows = read_jsonl(manifest)
        except Exception:
            continue
        for r in rows:
            if r.get("sha256"): hashes.add(str(r["sha256"]))
            sid = str(r.get("species_id", ""))
            for field in ("observation_id", "group_id", "near_duplicate_group_id"):
                if r.get(field): observations[sid].add(str(r[field]))
            if r.get("source") and r.get("source_id"):
                photo_ids.add((str(r["source"]), str(r["source_id"])))
    for manifest in (ROOT / "storage/datasets/curated").glob("**/manifest.csv"):
        if manifest == FROZEN:
            continue
        try:
            for r in read_csv(manifest):
                if r.get("sha256"): hashes.add(str(r["sha256"]))
                sid = str(r.get("species_id", ""))
                for field in ("observation_id", "group_id", "near_duplicate_group_id"):
                    if r.get(field): observations[sid].add(str(r[field]))
                if r.get("source") and r.get("source_id"):
                    photo_ids.add((str(r["source"]), str(r["source_id"])))
        except Exception:
            pass
    return hashes - {""}, observations, photo_ids


def collect():
    POOL.mkdir(parents=True, exist_ok=True)
    image_dir = POOL / "images"
    image_dir.mkdir(exist_ok=True)
    manifest_path = POOL / "manifest.jsonl"
    local_rows = read_jsonl(manifest_path) if manifest_path.exists() else []
    known_hashes, known_observations, known_photo_ids = all_existing()
    pool_hashes = {r.get("sha256") for r in local_rows}
    pool_observations = {(r.get("species_id"), str(r.get("observation_id"))) for r in local_rows}
    pool_photo_ids = {(r.get("source"), str(r.get("source_id"))) for r in local_rows}
    source = INaturalistSource(minimum_interval=1.1, max_retries=1, allow_noncommercial=False)
    downloader = ApiClient("iNaturalist image", 1.1, max_retries=1)
    summary = {"started_utc": datetime.now(timezone.utc).isoformat(), "policy": "iNaturalist PH research-grade only; CC0/CC BY/CC BY-SA; attribution required except CC0; every record pending; no expert verification inferred", "page_limit_per_class": 15, "pagination": "bounded scan from earliest observations; known photos and observation groups skipped", "max_new_observation_groups_per_class": 20, "classes": {}}
    newly_added_hashes = set()
    for sid, species in CLASSES.items():
        seen_groups = {str(r.get("observation_id")) for r in local_rows if r.get("species_id") == sid}
        rows_before = len([r for r in local_rows if r.get("species_id") == sid])
        dup_photo = dup_obs = dup_hash = downloaded_bad = 0
        groups_added = set()
        try:
            candidates = source.candidates(species, limit=None, pages=15, id_above=None)
            for c in candidates:
                obs = str(c.observation_id or "")
                identity = (c.source, str(c.source_id))
                if not training_license_eligible(c.license, c.attribution):
                    continue
                if identity in known_photo_ids or identity in pool_photo_ids:
                    dup_photo += 1; continue
                if any(obs in values for values in known_observations.values()) or obs in seen_groups or any(group_id == obs for _, group_id in pool_observations):
                    dup_obs += 1; continue
                if len(groups_added) >= 20:
                    break
                try:
                    payload = downloader.get_bytes(c.image_url, MAX_IMAGE_BYTES)
                    checksum, stored = validate_and_store(payload, image_dir)
                except Exception:
                    downloaded_bad += 1; continue
                if checksum in known_hashes or checksum in pool_hashes or checksum in newly_added_hashes:
                    dup_hash += 1
                    if checksum not in pool_hashes and checksum not in newly_added_hashes:
                        stored.unlink(missing_ok=True)
                    continue
                row = {**c.to_dict(), "sha256": checksum, "local_path": stored.relative_to(ROOT).as_posix(), "review_status": "pending", "reviewer": "", "review_rationale": "", "evaluation_holdout": "not assigned; separate blind-set curation required", "collected_at": datetime.now(timezone.utc).isoformat()}
                with manifest_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
                local_rows.append(row); groups_added.add(obs); seen_groups.add(obs); pool_photo_ids.add(identity); pool_observations.add((sid, obs)); pool_hashes.add(checksum); newly_added_hashes.add(checksum)
        except Exception as e:
            summary["classes"][sid] = {"error": f"{type(e).__name__}: {str(e)[:300]}", "new_images": 0, "new_observation_groups": 0}
            continue
        rows_class = [r for r in local_rows if r.get("species_id") == sid]
        summary["classes"][sid] = {"new_images": len(rows_class) - rows_before, "new_observation_groups": len(groups_added), "duplicate_photo_ids_skipped": dup_photo, "existing_observation_groups_skipped": dup_obs, "exact_duplicate_images_skipped": dup_hash, "download_or_decode_failures": downloaded_bad, "all_pool_images": len(rows_class), "all_pool_groups": len({str(r.get('observation_id')) for r in rows_class}), "licenses": dict(Counter(r.get("license", "") for r in rows_class))}
    allrows = read_jsonl(manifest_path) if manifest_path.exists() else []
    with (POOL / "review_queue.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore"); writer.writeheader()
        writer.writerows({**r, "review_status": "pending"} for r in allrows)
    summary.update({"finished_utc": datetime.now(timezone.utc).isoformat(), "total_pending_images": len(allrows), "total_pending_observation_groups": len({(r.get('species_id'), str(r.get('observation_id'))) for r in allrows}), "review_queue": POOL.relative_to(ROOT).as_posix() + "/review_queue.csv", "manifest": POOL.relative_to(ROOT).as_posix() + "/manifest.jsonl", "training_and_active_models_modified": False, "test_images_opened": False})
    OUT.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    collect()
