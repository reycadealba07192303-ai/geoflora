"""Freeze a three-class recovery candidate using preliminary field-like v3 development photos plus licensed staging.

The v3 and v5 test sets are excluded by source group, checksum and perceptual similarity. This is an
experimental development snapshot; preliminary visual triage is not expert botanical verification.
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/ml/src"))

from geoflora_ml.collection.licensing import normalize_license
from geoflora_ml.datasets.duplicates import group_near_duplicates
from geoflora_ml.datasets.split import assign_group_splits

DATA = ROOT / "storage/datasets"
OUT = DATA / "curated/three_class_recovery_v2_20261031"
CLASSES = [
    {"id": "chromolaena_odorata", "scientific_name": "Chromolaena odorata", "common_name": "Hagonoy", "role": "invasive"},
    {"id": "lantana_camara", "scientific_name": "Lantana camara", "common_name": "Lantana", "role": "invasive"},
    {"id": "pontederia_crassipes", "scientific_name": "Pontederia crassipes", "common_name": "Water Hyacinth", "role": "invasive"},
]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def workspace_path(local_path: str) -> Path:
    direct = ROOT / local_path
    if direct.is_file():
        return direct.resolve()
    under_data = DATA / local_path
    if under_data.is_file():
        return under_data.resolve()
    raise FileNotFoundError(local_path)


def benchmark_rows() -> list[dict]:
    rows = []
    class_ids = {entry["id"] for entry in CLASSES}
    for relative in ("curated/v3/manifest.csv", "curated/v5_part2_final_five_classes/manifest.csv"):
        with (DATA / relative).open(encoding="utf-8", newline="") as stream:
            selected = [row for row in csv.DictReader(stream) if row.get("split") == "test"]
        for row in selected:
            if row["species_id"] not in class_ids:
                continue
            image = workspace_path(row["local_path"])
            rows.append({**row, "local_path": image.relative_to(ROOT).as_posix(), "benchmark": relative})
    return rows


def owner_staging_rows() -> tuple[list[dict], list[dict]]:
    rows, reviews = [], []
    for entry in CLASSES:
        folder = DATA / "staging" / f"invasive_{entry['id']}_ph"
        with (folder / "review_queue.csv").open(encoding="utf-8-sig", newline="") as stream:
            source_rows = list(csv.DictReader(stream))
        for row in source_rows:
            if row.get("species_id") != entry["id"] or row.get("country_code") != "PH":
                continue
            if not normalize_license(row.get("license")):
                continue
            if row.get("license") != "cc0" and not row.get("attribution", "").strip():
                continue
            image = (folder / row["local_path"]).resolve()
            if not image.is_relative_to(folder.resolve()) or not image.is_file() or digest(image) != row["sha256"]:
                raise ValueError(f"Bad staging path/checksum: {entry['id']}:{row.get('source_id')}")
            with Image.open(image) as opened:
                opened.verify()
            rows.append({**row, **entry, "local_path": image.relative_to(ROOT).as_posix(),
                         "label_basis": "owner_gallery_approval_and_iNaturalist_research_grade",
                         "source_review_basis": "owner gallery approval; community identification, not expert verified"})
            reviews.append({"species_id": entry["id"], "source": row["source"], "source_id": row["source_id"],
                            "sha256": row["sha256"], "owner_gallery_review": "approved",
                            "label_basis": "owner gallery approval and source community identification"})
    return rows, reviews


def v3_development_rows() -> tuple[list[dict], list[dict]]:
    source = ROOT / "docs/v3-corpus-audit/preliminary-field-photos.csv"
    with source.open(encoding="utf-8-sig", newline="") as stream:
        source_rows = list(csv.DictReader(stream))
    rows, reviews = [], []
    for row in source_rows:
        if row.get("species_id") not in {entry["id"] for entry in CLASSES} or row.get("split") == "test":
            continue
        if row.get("current_review_decision") != "approved" or not normalize_license(row.get("license")):
            continue
        if row.get("license") != "cc0" and not row.get("attribution", "").strip():
            continue
        image = workspace_path(row["local_path"])
        if digest(image) != row["sha256"]:
            raise ValueError(f"v3 candidate checksum mismatch: {row['review_id']}")
        with Image.open(image) as opened:
            opened.verify()
        entry = next(entry for entry in CLASSES if entry["id"] == row["species_id"])
        rows.append({**row, **entry, "local_path": image.relative_to(ROOT).as_posix(),
                     "label_basis": "owner_approved_v3_plus_preliminary_field_photo_triage",
                     "source_review_basis": "owner approved original source label; field context is preliminary visual triage"})
        reviews.append({"species_id": entry["id"], "review_id": row["review_id"], "source": row["source"],
                        "source_id": row["source_id"], "sha256": row["sha256"],
                        "label_basis": "owner-approved v3 review; preliminary field-like visual triage; no expert confirmation"})
    return rows, reviews


def main() -> None:
    if OUT.exists():
        raise FileExistsError(f"Preserving existing snapshot: {OUT}")

    staged, staged_reviews = owner_staging_rows()
    legacy, legacy_reviews = v3_development_rows()
    candidates = staged + legacy
    benchmarks = benchmark_rows()
    held_sha = {row["sha256"] for row in benchmarks}
    held_groups = {(row["species_id"], row.get("group_id")) for row in benchmarks if row.get("group_id")}
    filtered = [row for row in candidates if row["sha256"] not in held_sha and (row["species_id"], row.get("group_id")) not in held_groups]

    priority = {"cc0": 0, "cc-by": 1, "cc-by-sa": 2}
    unique = {}
    for row in filtered:
        key = row["sha256"]
        if key not in unique or priority[row["license"]] < priority[unique[key]["license"]]:
            unique[key] = row
    filtered = list(unique.values())

    tagged = [{**row, "_is_benchmark": False} for row in filtered]
    tagged.extend({**row, "_is_benchmark": True} for row in benchmarks)
    grouped_all, _ = group_near_duplicates(tagged, ROOT)
    benchmark_near_groups = {row["near_duplicate_group_id"] for row in grouped_all if row["_is_benchmark"]}
    filtered = [row for row in grouped_all if not row["_is_benchmark"] and row["near_duplicate_group_id"] not in benchmark_near_groups]
    filtered, near_duplicates = group_near_duplicates(filtered, ROOT)
    assigned = assign_group_splits(filtered, seed=42)

    split_keys = defaultdict(set)
    for row in assigned:
        for key in ("sha256", "group_id", "near_duplicate_group_id"):
            split_keys[(key, row[key])].add(row["split"])
    if any(len(splits) != 1 for splits in split_keys.values()):
        raise ValueError("Cross-split leakage detected")
    class_ids = {entry["id"] for entry in CLASSES}
    for split in ("train", "validation", "test"):
        if {row["species_id"] for row in assigned if row["split"] == split} != class_ids:
            raise ValueError(f"Missing class in {split}")

    OUT.mkdir(parents=True)
    fields = sorted(set().union(*(row.keys() for row in assigned)))
    with (OUT / "manifest.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(assigned)
    reviews = staged_reviews + legacy_reviews
    (OUT / "reviews_snapshot.json").write_text(json.dumps(reviews, indent=2), encoding="utf-8")
    (OUT / "class_mapping.json").write_text(json.dumps({"classes": CLASSES}, indent=2), encoding="utf-8")
    (OUT / "species.yaml").write_text(json.dumps({"species": CLASSES}, indent=2), encoding="utf-8")
    counts = {entry["id"]: dict(Counter(row["split"] for row in assigned if row["species_id"] == entry["id"])) for entry in CLASSES}
    metadata = {
        "dataset_id": OUT.name,
        "seed": 42,
        "images": len(assigned),
        "per_class": counts,
        "manifest_sha256": digest(OUT / "manifest.csv"),
        "reviews_snapshot_sha256": digest(OUT / "reviews_snapshot.json"),
        "development_sources": ["v3 preliminary field-like train/validation only", "owner-approved license-eligible staging"],
        "benchmarks_excluded": ["curated/v3 test", "curated/v5_part2_final_five_classes test"],
        "benchmark_rows_excluded": len(benchmarks),
        "staging_images_before_filter": len(staged),
        "v3_field_like_development_images_before_filter": len(legacy),
        "combined_candidates_before_filter": len(candidates),
        "candidate_images_after_exact_and_near_duplicate_filter": len(assigned),
        "near_duplicate_groups": len(near_duplicates),
        "scope": "Three-class recovery experiment. v3 field-like decisions are preliminary visual triage, not expert verification. Not a blind final test or 95% claim.",
    }
    (OUT / "dataset_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
