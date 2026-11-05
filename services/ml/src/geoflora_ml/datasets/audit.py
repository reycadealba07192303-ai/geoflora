from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError

from geoflora_ml.config import load_species
from geoflora_ml.datasets.duplicates import group_near_duplicates
from geoflora_ml.datasets.manifest import append_jsonl, read_jsonl


def load_current_reviews(data_dir: Path) -> dict[tuple[str, str], dict[str, Any]]:
    review_path = data_dir / "raw" / "reviews.jsonl"
    reviews = read_jsonl(review_path) if review_path.exists() else []
    latest_reviews: dict[tuple[str, str], dict[str, Any]] = {}
    for review in reviews:
        latest_reviews[(str(review["source"]), str(review["source_id"]))] = review
    return latest_reviews


def record_review(
    data_dir: Path,
    source: str,
    source_id: str,
    decision: str,
    reviewer: str,
    rationale: str,
    relabel_to: str | None = None,
) -> None:
    if decision not in {"approved", "rejected", "flagged", "relabelled"}:
        raise ValueError("Review decision must be approved, rejected, flagged, or relabelled")
    if not reviewer.strip() or not rationale.strip():
        raise ValueError("A reviewer name and rationale are required")
    if decision == "relabelled":
        valid_species = {species.id for species in load_species()}
        if relabel_to not in valid_species:
            raise ValueError("Relabel target must be a species in the GeoFlora catalog")
    elif relabel_to is not None:
        raise ValueError("A relabel target is only valid for a relabelled decision")

    manifest_path = data_dir / "raw" / "manifest.jsonl"
    exists = any(
        record.get("source") == source and record.get("source_id") == source_id
        for record in read_jsonl(manifest_path)
    )
    if not exists:
        raise ValueError(f"Image source record not found: {source}:{source_id}")

    append_jsonl(
        data_dir / "raw" / "reviews.jsonl",
        {
            "source": source,
            "source_id": source_id,
            "decision": decision,
            "relabel_to": relabel_to,
            "reviewer": reviewer.strip(),
            "rationale": rationale.strip(),
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
        },
    )


def build_audit_report(data_dir: Path, target_per_species: int) -> dict[str, Any]:
    raw_dir = data_dir / "raw"
    manifest_path = raw_dir / "manifest.jsonl"
    records = read_jsonl(manifest_path) if manifest_path.exists() else []
    latest_reviews = load_current_reviews(data_dir)

    valid_records: list[dict[str, Any]] = []
    invalid_records: list[dict[str, Any]] = []
    for record in records:
        path = _resolve_image_path(record, data_dir)
        if path is None:
            invalid_records.append({**record, "invalid_reason": "missing or unsafe path"})
            continue
        try:
            image_bytes = path.read_bytes()
            if hashlib.sha256(image_bytes).hexdigest() != record.get("sha256"):
                raise ValueError("checksum mismatch")
            with Image.open(path) as image:
                image.verify()
        except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
            invalid_records.append({**record, "invalid_reason": str(exc)})
            continue
        review = latest_reviews.get((str(record.get("source")), str(record.get("source_id"))))
        status = review["decision"] if review else "pending"
        effective_species_id = (
            review.get("relabel_to")
            if review and status == "relabelled"
            else record.get("species_id")
        )
        reviewed_record = {
            **record,
            "original_species_id": record.get("species_id"),
            "species_id": effective_species_id,
            "review_status": status,
            "reviewer": review.get("reviewer") if review else None,
            "review_rationale": review.get("rationale") if review else None,
        }
        valid_records.append(reviewed_record)

    species_by_checksum: dict[str, set[str]] = defaultdict(set)
    for record in valid_records:
        species_by_checksum[str(record.get("sha256"))].add(
            str(record.get("species_id", "unknown"))
        )
    image_groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in valid_records:
        image_groups[
            (str(record.get("species_id", "unknown")), str(record.get("sha256")))
        ].append(record)

    unique_images: list[dict[str, Any]] = []
    for (species_id, checksum), group in image_groups.items():
        statuses = {str(record["review_status"]) for record in group}
        approved_statuses = {"approved", "relabelled"}
        if len(species_by_checksum[checksum]) > 1 or (
            statuses & approved_statuses and statuses & {"rejected", "flagged"}
        ):
            status = "conflict"
        elif statuses & approved_statuses:
            status = "relabelled" if "relabelled" in statuses else "approved"
        elif "flagged" in statuses:
            status = "flagged"
        elif statuses == {"rejected"}:
            status = "rejected"
        else:
            status = "pending"
        unique_images.append(
            {
                "species_id": species_id,
                "sha256": checksum,
                "review_status": status,
                "records": group,
            }
        )

    counts_by_species: dict[str, Counter[str]] = defaultdict(Counter)
    counts_by_source_species: dict[str, dict[str, Counter[str]]] = defaultdict(
        lambda: defaultdict(Counter)
    )
    licenses_by_species: dict[str, Counter[str]] = defaultdict(Counter)
    for image in unique_images:
        species_id = image["species_id"]
        status = image["review_status"]
        counts_by_species[species_id]["valid"] += 1
        counts_by_species[species_id][status] += 1
        for record in image["records"]:
            source = str(record.get("source", "unknown"))
            counts_by_source_species[species_id][source][status] += 1
            licenses_by_species[species_id][str(record.get("license", "unknown"))] += 1

    duplicate_records, near_duplicate_groups = group_near_duplicates(
        valid_records, data_dir
    ) if valid_records else ([], [])
    del duplicate_records
    review_status_by_key = {
        (str(record.get("source")), str(record.get("source_id"))): str(
            record.get("review_status")
        )
        for record in valid_records
    }
    for group in near_duplicate_groups:
        group["flagged_review"] = any(
            review_status_by_key.get(
                (str(key.get("source")), str(key.get("source_id")))
            )
            == "flagged"
            for key in group["record_keys"]
        )
    checksum_records: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in valid_records:
        checksum_records[str(record.get("sha256"))].append(record)
    exact_duplicate_groups = [
        {
            "sha256": checksum,
            "count": len(group),
            "source_ids": [str(record.get("source_id")) for record in group],
        }
        for checksum, group in checksum_records.items()
        if len(group) > 1
    ]
    cross_species_label_conflicts = [
        {
            "sha256": checksum,
            "species_ids": sorted(species),
            "source_ids": [
                str(record.get("source_id"))
                for record in valid_records
                if record.get("sha256") == checksum
            ],
        }
        for checksum, species in species_by_checksum.items()
        if len(species) > 1
    ]

    rejected_path = raw_dir / "rejected.jsonl"
    rejected_downloads = read_jsonl(rejected_path) if rejected_path.exists() else []
    rejected_by_species_source: dict[str, Counter[str]] = defaultdict(Counter)
    rejected_reasons: Counter[str] = Counter()
    for record in rejected_downloads:
        species_id = str(record.get("species_id", "unknown"))
        source = str(record.get("source", "unknown"))
        rejected_by_species_source[species_id][source] += 1
        rejected_reasons[str(record.get("reason", "unspecified"))] += 1

    species_ids = sorted(
        set(counts_by_species)
        | set(rejected_by_species_source)
        | {
            str(record.get("species_id", "unknown"))
            for record in records
        }
    )
    species_report = {}
    for species_id in species_ids:
        counts = counts_by_species[species_id]
        approved = counts["approved"] + counts["relabelled"]
        species_report[species_id] = {
            "valid_image_records": sum(
                record.get("species_id") == species_id for record in valid_records
            ),
            "valid_images": counts["valid"],
            "approved_images": approved,
            "relabelled_images": counts["relabelled"],
            "pending_review": counts["pending"],
            "flagged_review": counts["flagged"],
            "review_conflicts": counts["conflict"],
            "rejected_by_review": counts["rejected"],
            "invalid_images": sum(
                record.get("species_id") == species_id for record in invalid_records
            ),
            "exact_duplicate_groups": sum(
                any(
                    record.get("species_id") == species_id
                    for record in checksum_records[duplicate["sha256"]]
                )
                for duplicate in exact_duplicate_groups
            ),
            "near_duplicate_groups": sum(
                group["species_id"] == species_id for group in near_duplicate_groups
            ),
            "licenses": dict(licenses_by_species[species_id]),
            "sources": {
                source: {
                    "valid_image_records": sum(
                        1
                        for record in valid_records
                        if record.get("species_id") == species_id
                        and record.get("source") == source
                    ),
                    "valid_images": sum(source_counts.values()),
                    "approved_images": source_counts["approved"] + source_counts["relabelled"],
                    "relabelled_images": source_counts["relabelled"],
                    "pending_review": source_counts["pending"],
                    "flagged_review": source_counts["flagged"],
                    "rejected_by_review": source_counts["rejected"],
                    "review_conflicts": source_counts["conflict"],
                    "download_rejections": rejected_by_species_source[species_id][source],
                }
                for source in sorted(
                    set(counts_by_source_species[species_id])
                    | set(rejected_by_species_source[species_id])
                )
                for source_counts in [counts_by_source_species[species_id][source]]
            },
            "download_rejections": sum(rejected_by_species_source[species_id].values()),
            "remaining_to_verified_target": max(0, target_per_species - approved),
        }

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "geographic_scope": "PH",
        "target_verified_images_per_species": target_per_species,
        "external_training_data_included": False,
        "totals": {
            "manifest_records": len(records),
            "valid_image_records": len(valid_records),
            "valid_images": len(unique_images),
            "approved_images": sum(
                image["review_status"] in {"approved", "relabelled"}
                for image in unique_images
            ),
            "pending_review": sum(
                image["review_status"] in {"pending", "conflict"}
                for image in unique_images
            ),
            "review_conflicts": sum(
                image["review_status"] == "conflict" for image in unique_images
            ),
            "rejected_by_review": sum(
                image["review_status"] == "rejected" for image in unique_images
            ),
            "flagged_review": sum(
                image["review_status"] == "flagged" for image in unique_images
            ),
            "flagged_duplicate_groups": sum(
                group["flagged_review"] for group in near_duplicate_groups
            ),
            "invalid_images": len(invalid_records),
            "download_rejections": len(rejected_downloads),
            "exact_duplicate_groups": exact_duplicate_groups,
            "cross_species_label_conflicts": cross_species_label_conflicts,
            "near_duplicate_groups": near_duplicate_groups,
            "download_rejection_reasons": dict(rejected_reasons),
        },
        "species": species_report,
        "invalid_records": [
            {
                "source": record.get("source"),
                "source_id": record.get("source_id"),
                "species_id": record.get("species_id"),
                "reason": record["invalid_reason"],
            }
            for record in invalid_records
        ],
    }
    return report


def write_audit_report(data_dir: Path, target_per_species: int) -> Path:
    report = build_audit_report(data_dir, target_per_species)
    output_path = data_dir / "reports" / "dataset_audit.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return output_path


def _resolve_image_path(record: dict[str, Any], data_dir: Path) -> Path | None:
    local_path = record.get("local_path")
    if not isinstance(local_path, str):
        return None
    root = data_dir.resolve()
    path = (root / local_path).resolve()
    return path if path.is_relative_to(root) and path.is_file() else None
