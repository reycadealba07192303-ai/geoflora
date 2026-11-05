from __future__ import annotations

"""Summarize existing image staging and frozen development partitions.

This is an inventory only: it never changes review decisions or dataset files.
"""

import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
STAGING = ROOT / "storage/datasets/staging"
CURATED = ROOT / "storage/datasets/curated"
OUTPUT = ROOT / "storage/species_catalog/exports/image_dataset_readiness.json"
sys.path.insert(0, str(ROOT / "services/ml/src"))
from geoflora_ml.collection.licensing import training_license_eligible  # noqa: E402


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid JSONL at {path}:{line_number}: {exc}") from exc
    return rows


def historical_test_hashes() -> set[str]:
    hashes: set[str] = set()
    for path in CURATED.glob("*/manifest.csv"):
        for row in read_csv(path):
            if row.get("split", "").casefold() == "test" and row.get("sha256"):
                hashes.add(row["sha256"].casefold())
    return hashes


def source_label(record: dict[str, Any]) -> str:
    return str(record.get("scientific_name") or record.get("species_id") or "unknown").strip()


def stage_inventory(test_hashes: set[str]) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    manifest_count = 0
    for manifest in STAGING.glob("**/raw/manifest.jsonl"):
        manifest_count += 1
        records.extend(read_jsonl(manifest))

    by_species: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        by_species[source_label(row)].append(row)

    species_output = {}
    global_hash_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        if row.get("sha256"):
            global_hash_rows[str(row["sha256"]).casefold()].append(row)
    duplicate_hash_groups = {key: value for key, value in global_hash_rows.items() if len(value) > 1}

    for species, rows in sorted(by_species.items(), key=lambda pair: pair[0].casefold()):
        by_hash: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            key = str(row.get("sha256") or f"missing:{id(row)}").casefold()
            by_hash[key].append(row)
        unique_rows = [group[0] for group in by_hash.values()]
        groups = {str(row.get("group_id") or row.get("observation_id") or row.get("source_id") or row.get("sha256")) for row in unique_rows}
        eligible = [row for row in unique_rows if training_license_eligible(str(row.get("license") or ""), str(row.get("attribution") or ""))]
        status_counts = Counter(str(row.get("review_status") or "pending") for row in rows)
        approved = [row for row in rows if str(row.get("review_status") or "").casefold() in {"approved", "owner_visual_review_approved"} and str(row.get("reviewer") or row.get("reviewed_by") or "").strip() and str(row.get("review_rationale") or row.get("review_rationale") or "").strip()]
        test_overlap = [row for row in unique_rows if str(row.get("sha256") or "").casefold() in test_hashes]
        license_counts = Counter(str(row.get("license") or "missing") for row in unique_rows)
        species_output[species] = {
            "candidate_records": len(rows),
            "unique_exact_images": len(unique_rows),
            "unique_observation_groups": len(groups),
            "exact_duplicate_records": len(rows) - len(unique_rows),
            "license_eligible_unique_images": len(eligible),
            "license_eligible_unique_images_excluding_historical_test": sum(1 for row in eligible if str(row.get("sha256") or "").casefold() not in test_hashes),
            "license_breakdown": dict(sorted(license_counts.items())),
            "review_status_counts": dict(sorted(status_counts.items())),
            "explicit_human_approved_images_with_reviewer_and_rationale": len(approved),
            "historical_test_exact_overlaps_excluded": len(test_overlap),
            "development_training_ready_images": sum(1 for row in approved if row in eligible and row not in test_overlap),
            "validation_test_readiness": "not established; staging observations are not partitioned",
        }

    cross_taxon_hashes = {
        checksum: sorted({source_label(row) for row in rows})
        for checksum, rows in duplicate_hash_groups.items()
        if len({source_label(row) for row in rows}) > 1
    }
    all_duplicate_hash_groups = sum(len(group) > 1 for group in global_hash_rows.values())
    return {
        "staging_manifest_files": manifest_count,
        "staging_records": len(records),
        "species_count": len(species_output),
        "historical_test_unique_hashes_checked": len(test_hashes),
        "cross_species_exact_duplicate_hash_groups": cross_taxon_hashes,
        "all_exact_duplicate_hash_group_count": all_duplicate_hash_groups,
        "species": species_output,
        "limitations": [
            "Research-grade/community identifications are not independent botanical verification.",
            "License eligibility is a screening result; it does not replace terms review or human label approval.",
            "Perceptual/near-duplicate checks are represented by the existing collection audit, not recomputed here.",
            "No staging image is made training-ready by this inventory.",
        ],
    }


def frozen_development_summary() -> dict[str, Any]:
    path = CURATED / "auto_6ae5cd74af23d762feaa0889_weakreview_v3_20261101/manifest.csv"
    if not path.is_file():
        return {"status": "missing", "file": str(path.relative_to(ROOT))}
    rows = read_csv(path)
    classes: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        key = (row.get("scientific_name") or row.get("species_id") or "unknown").casefold().strip()
        classes[key].append(row)
    output = {}
    for name, class_rows in sorted(classes.items()):
        reviewed = [row for row in class_rows if row.get("review_status") == "owner_visual_review_approved"]
        license_ok = [row for row in class_rows if training_license_eligible(row.get("license"), row.get("attribution"))]
        approved_train = [row for row in reviewed if row.get("split") == "train" and training_license_eligible(row.get("license"), row.get("attribution"))]
        output[name] = {
            "frozen_candidate_images": len(class_rows),
            "unique_observation_groups": len({row.get("group_id") or row.get("sha256") for row in class_rows}),
            "split_images": dict(sorted(Counter(row.get("split") or "unspecified" for row in class_rows).items())),
            "owner_visual_review_approved": len(reviewed),
            "license_eligible_for_training_screen": len(license_ok),
            "explicitly_reviewed_license_eligible_train_images": len(approved_train),
            "scope_note": "Counts describe the preserved experimental development dataset; training eligibility still requires project gates and does not equal botanical expert certification.",
        }
    return {
        "dataset": str(path.relative_to(ROOT)),
        "dataset_images": len(rows),
        "class_count": len(output),
        "classes": output,
    }


def main() -> int:
    test_hashes = historical_test_hashes()
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Read-only inventory of existing staged photos and the frozen 11-class development dataset.",
        "training_policy": "No automatic approval; held-out test hashes are explicitly excluded from development training counts.",
        "staging": stage_inventory(test_hashes),
        "frozen_11_class_development_dataset": frozen_development_summary(),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "output": str(OUTPUT.relative_to(ROOT)),
        "staging_manifest_files": report["staging"]["staging_manifest_files"],
        "staging_records": report["staging"]["staging_records"],
        "staging_species": report["staging"]["species_count"],
        "development_dataset_images": report["frozen_11_class_development_dataset"].get("dataset_images"),
        "development_classes": report["frozen_11_class_development_dataset"].get("class_count"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
