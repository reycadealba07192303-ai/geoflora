from __future__ import annotations

import csv
import hashlib
from collections import defaultdict
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError

from geoflora_ml.config import load_species
from geoflora_ml.datasets.audit import (
    build_audit_report,
    load_current_reviews,
    record_review,
)
from geoflora_ml.datasets.duplicates import group_near_duplicates
from geoflora_ml.datasets.manifest import read_jsonl

APPROVED_DECISIONS = {"approved", "relabelled"}
REVIEW_STATUSES = {"pending", "approved", "rejected", "flagged", "relabelled"}


def get_review_items(
    data_dir: Path,
    species_id: str = "",
    status: str = "",
    source: str = "",
    duplicate_group: str = "",
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    manifest_path = data_dir / "raw" / "manifest.jsonl"
    if not manifest_path.exists():
        return {
            "items": [],
            "total": 0,
            "limit": limit,
            "offset": offset,
            "filter_options": {"species": [], "sources": [], "duplicate_groups": []},
        }

    records = read_jsonl(manifest_path)
    reviews = load_current_reviews(data_dir)
    review_history_path = data_dir / "raw" / "reviews.jsonl"
    review_history = (
        read_jsonl(review_history_path) if review_history_path.exists() else []
    )
    history_by_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for event in review_history:
        history_by_key[(str(event.get("source")), str(event.get("source_id")))].append(
            event
        )
    valid: list[dict[str, Any]] = []
    invalid_count = 0
    root = data_dir.resolve()
    for record in records:
        key = (str(record.get("source", "")), str(record.get("source_id", "")))
        path = _safe_image_path(record, root)
        if path is None:
            invalid_count += 1
            continue
        review = reviews.get(key)
        decision = review.get("decision") if review else "pending"
        effective_species = (
            review.get("relabel_to")
            if decision == "relabelled"
            else record.get("species_id")
        )
        valid.append(
            {
                **record,
                "original_species_id": record.get("species_id"),
                "species_id": effective_species,
                "review_status": decision,
                "reviewer": review.get("reviewer") if review else "",
                "review_rationale": review.get("rationale") if review else "",
                "reviewed_at": review.get("reviewed_at") if review else "",
                "review_history": history_by_key[key],
            }
        )

    grouped, near_groups = group_near_duplicates(valid, data_dir) if valid else ([], [])
    exact_by_checksum: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in grouped:
        exact_by_checksum[str(item["sha256"])].append(item)

    near_group_by_key: dict[tuple[str, str], str] = {}
    for group in near_groups:
        for key in group["record_keys"]:
            near_group_by_key[(str(key["source"]), str(key["source_id"]))] = str(
                group["group_id"]
            )

    for item in grouped:
        exact_members = exact_by_checksum[str(item["sha256"])]
        if len(exact_members) > 1:
            item["duplicate_group_id"] = f"exact:{item['sha256'][:12]}"
            item["duplicate_group_type"] = "exact"
        else:
            key = (str(item.get("source")), str(item.get("source_id")))
            item["duplicate_group_id"] = near_group_by_key.get(key, "")
            item["duplicate_group_type"] = "near" if item["duplicate_group_id"] else ""
        item["image_url"] = (
            "/api/image?"
            f"source={_url_quote(str(item.get('source', '')))}"
            f"&source_id={_url_quote(str(item.get('source_id', '')))}"
        )

    filtered = [
        item
        for item in grouped
        if (not species_id or item.get("species_id") == species_id)
        and (not status or item.get("review_status") == status)
        and (not source or item.get("source") == source)
        and (
            not duplicate_group
            or item.get("duplicate_group_id") == duplicate_group
        )
    ]
    filtered.sort(
        key=lambda item: (
            str(item.get("review_status")),
            str(item.get("species_id")),
            str(item.get("source")),
            str(item.get("source_id")),
        )
    )
    return {
        "items": filtered[offset : offset + limit],
        "total": len(filtered),
        "limit": limit,
        "offset": offset,
        "invalid_records": invalid_count,
        "filter_options": {
            "species": sorted({str(item.get("species_id")) for item in grouped}),
            "sources": sorted({str(item.get("source")) for item in grouped}),
            "duplicate_groups": sorted(
                {
                    (str(item["duplicate_group_id"]), str(item["duplicate_group_type"]))
                    for item in grouped
                    if item["duplicate_group_id"]
                }
            ),
        },
    }


def get_review_stats(data_dir: Path, target_per_species: int = 1000) -> dict[str, Any]:
    return build_audit_report(data_dir, target_per_species)


def review_item(
    data_dir: Path,
    source: str,
    source_id: str,
    decision: str,
    reviewer: str,
    rationale: str,
    relabel_to: str | None = None,
) -> None:
    record_review(
        data_dir=data_dir,
        source=source,
        source_id=source_id,
        decision=decision,
        reviewer=reviewer,
        rationale=rationale,
        relabel_to=relabel_to,
    )


def export_approved_manifest(data_dir: Path) -> Path:
    manifest_path = data_dir / "raw" / "manifest.jsonl"
    records = read_jsonl(manifest_path) if manifest_path.exists() else []
    reviews = load_current_reviews(data_dir)
    root = data_dir.resolve()
    valid_species = {species.id for species in load_species()}
    approved: list[dict[str, Any]] = []
    species_by_checksum: dict[str, set[str]] = defaultdict(set)

    for record in records:
        key = (str(record.get("source", "")), str(record.get("source_id", "")))
        review = reviews.get(key)
        if not review or review.get("decision") not in APPROVED_DECISIONS:
            continue
        species_id = (
            review.get("relabel_to")
            if review["decision"] == "relabelled"
            else record.get("species_id")
        )
        if species_id not in valid_species:
            raise ValueError(f"Approved record has unknown species label: {species_id}")
        path = _safe_image_path(record, root)
        if path is None:
            raise ValueError(f"Approved image is missing or unsafe: {key[0]}:{key[1]}")
        checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        if checksum != record.get("sha256"):
            raise ValueError(f"Approved image failed checksum validation: {key[0]}:{key[1]}")
        approved.append(
            {
                **record,
                "original_species_id": record.get("species_id"),
                "species_id": species_id,
                "review_status": review["decision"],
                "reviewed_at": review["reviewed_at"],
                "reviewer": review["reviewer"],
                "review_rationale": review["rationale"],
            }
        )
        species_by_checksum[checksum].add(str(species_id))

    if any(len(species_ids) > 1 for species_ids in species_by_checksum.values()):
        raise ValueError("Approved duplicate image records have conflicting labels")
    grouped, _ = group_near_duplicates(approved, data_dir) if approved else ([], [])
    output_dir = data_dir / "curated"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "approved_manifest.csv"
    fields = sorted(set().union(*(item.keys() for item in grouped))) if grouped else [
        "source",
        "source_id",
        "species_id",
        "review_status",
        "reviewed_at",
        "reviewer",
        "review_rationale",
        "sha256",
        "local_path",
        "near_duplicate_group_id",
    ]
    with output_path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(grouped)
    return output_path


def _safe_image_path(record: dict[str, Any], root: Path) -> Path | None:
    local_path = record.get("local_path")
    if not isinstance(local_path, str):
        return None
    path = (root / local_path).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        return None
    expected = record.get("sha256")
    if not isinstance(expected, str):
        return None
    try:
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            return None
        with Image.open(path) as image:
            image.verify()
        return path
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError):
        return None


def _url_quote(value: str) -> str:
    from urllib.parse import quote

    return quote(value, safe="")
