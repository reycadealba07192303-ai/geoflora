from __future__ import annotations

import csv
import hashlib
import logging
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError

from geoflora_ml.datasets.audit import load_current_reviews
from geoflora_ml.datasets.duplicates import group_near_duplicates
from geoflora_ml.datasets.manifest import read_jsonl
from geoflora_ml.datasets.split import assign_group_splits

LOGGER = logging.getLogger(__name__)
REQUIRED_FIELDS = {
    "species_id",
    "source",
    "source_id",
    "license",
    "attribution",
    "sha256",
    "local_path",
    "group_id",
}


def prepare_dataset(
    manifest_path: Path,
    data_dir: Path,
    output_dir: Path,
    seed: int,
) -> tuple[int, int]:
    records = read_jsonl(manifest_path)
    root = data_dir.resolve()
    validated: list[dict[str, Any]] = []
    seen_checksums: set[str] = set()
    species_by_checksum: dict[str, set[str]] = {}
    duplicate_count = 0
    current_reviews = load_current_reviews(data_dir)
    pending_review = 0

    for index, record in enumerate(records, start=1):
        missing = REQUIRED_FIELDS - record.keys()
        if missing:
            raise ValueError(
                f"Manifest entry {index} is missing fields: {', '.join(sorted(missing))}"
            )
        checksum = str(record["sha256"])
        review = current_reviews.get(
            (str(record.get("source")), str(record.get("source_id")))
        )
        review_status = review["decision"] if review else "pending"
        if review_status not in {"approved", "relabelled"}:
            pending_review += 1
            continue
        effective_species_id = (
            review["relabel_to"]
            if review_status == "relabelled"
            else str(record["species_id"])
        )
        species_by_checksum.setdefault(checksum, set()).add(effective_species_id)
        if checksum in seen_checksums:
            LOGGER.info("Skipping duplicate image checksum=%s", checksum)
            duplicate_count += 1
            continue
        image_path = (root / str(record["local_path"])).resolve()
        if not image_path.is_relative_to(root):
            raise ValueError(f"Manifest image path escapes the dataset directory: {image_path}")
        if not image_path.is_file():
            raise ValueError(f"Manifest image is missing: {image_path}")
        actual_checksum = hashlib.sha256(image_path.read_bytes()).hexdigest()
        if actual_checksum != checksum:
            raise ValueError(f"Image checksum mismatch at manifest entry {index}")
        try:
            with Image.open(image_path) as image:
                image.verify()
        except (OSError, UnidentifiedImageError) as exc:
            raise ValueError(
                f"Invalid image at manifest entry {index}: {image_path}"
            ) from exc
        seen_checksums.add(checksum)
        validated.append(
            {
                **record,
                "species_id": effective_species_id,
                "original_species_id": record["species_id"],
                "review_status": review_status,
            }
        )

    conflicts = [
        checksum
        for checksum, species_ids in species_by_checksum.items()
        if len(species_ids) > 1
    ]
    if conflicts:
        raise ValueError(
            "Approved records assign identical image checksums to multiple species; "
            "resolve these label conflicts before preparing splits"
        )
    if not validated:
        raise ValueError(
            "No approved, unique images are available. Review pending labels before "
            f"preparing evaluation splits (pending or rejected={pending_review})."
        )
    validated, _ = group_near_duplicates(validated, root)
    assigned = assign_group_splits(validated, seed=seed)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "manifest.csv"
    fields = sorted(set().union(*(record.keys() for record in assigned)))
    with output_path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(assigned)
    return len(assigned), duplicate_count
