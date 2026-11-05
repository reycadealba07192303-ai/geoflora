from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from collections.abc import Iterable
from pathlib import Path
from urllib.request import url2pathname
from urllib.parse import urlparse

import requests
from geoflora_ml.collection.http import ApiClient
from geoflora_ml.collection.licensing import normalize_license
from geoflora_ml.collection.models import ImageCandidate
from geoflora_ml.datasets.images import MAX_IMAGE_BYTES, validate_and_store
from geoflora_ml.datasets.manifest import append_jsonl, read_jsonl

LOGGER = logging.getLogger(__name__)


def collect_candidates(
    candidates: Iterable[ImageCandidate],
    data_dir: Path,
    max_images: int | None,
    source_name: str,
    max_storage_bytes: int | None = None,
    minimum_interval: float = 0.5,
    max_retries: int = 4,
    allow_noncommercial: bool = False,
) -> tuple[int, int]:
    raw_dir = data_dir / "raw"
    manifest_path = raw_dir / "manifest.jsonl"
    rejected_path = raw_dir / "rejected.jsonl"
    client = ApiClient(source_name, minimum_interval, max_retries)
    existing_ids: set[tuple[str, str]] = set()
    known_checksums: dict[tuple[str, str], str] = {}
    known_rejections: set[tuple[str, str, str]] = set()
    if manifest_path.exists():
        for record in read_jsonl(manifest_path):
            if not _manifest_image_exists(record, data_dir):
                continue
            if record.get("source") and record.get("source_id"):
                existing_ids.add((str(record["source"]), str(record["source_id"])))
            if record.get("species_id") and record.get("sha256"):
                known_checksums.setdefault(
                    (str(record["species_id"]), str(record["sha256"])),
                    str(record.get("source_id", "")),
                )
    if rejected_path.exists():
        for record in read_jsonl(rejected_path):
            known_rejections.add(
                (
                    str(record.get("source", "")),
                    str(record.get("source_id", "")),
                    str(record.get("reason", "")),
                )
            )
    seen_ids = set(existing_ids)
    known_images = set(raw_dir.rglob("*.jpg")) if raw_dir.exists() else set()
    stored_bytes = sum(path.stat().st_size for path in known_images)
    downloaded = 0
    rejected = 0

    for candidate in candidates:
        if max_images is not None and downloaded >= max_images:
            break
        if (
            max_storage_bytes is not None
            and max_storage_bytes - stored_bytes < MAX_IMAGE_BYTES
        ):
            LOGGER.info("Storage budget reached; stopping source=%s", source_name)
            break
        license_code = normalize_license(candidate.license, allow_noncommercial)
        if not license_code or (
            license_code != "cc0" and not candidate.attribution.strip()
        ):
            rejected += 1
            LOGGER.warning(
                "Rejected source=%s id=%s reason=license or attribution is not eligible",
                candidate.source,
                candidate.source_id,
            )
            _record_rejection(
                rejected_path,
                candidate,
                "license or attribution is not eligible",
                known_rejections,
            )
            continue
        identity = (candidate.source, candidate.source_id)
        if identity in seen_ids:
            continue
        seen_ids.add(identity)
        try:
            image_bytes = _load_candidate_bytes(candidate, client)
            checksum, image_path = validate_and_store(
                image_bytes, raw_dir / candidate.species_id
            )
        except (OSError, ValueError, requests.RequestException) as exc:
            rejected += 1
            LOGGER.warning(
                "Rejected source=%s id=%s reason=%s",
                candidate.source,
                candidate.source_id,
                exc,
            )
            _record_rejection(rejected_path, candidate, str(exc), known_rejections)
            continue
        checksum_key = (candidate.species_id, checksum)
        if checksum_key in known_checksums:
            append_jsonl(
                manifest_path,
                {
                    **candidate.to_dict(),
                    "downloaded_at": datetime.now(timezone.utc).isoformat(),
                    "sha256": checksum,
                    "local_path": image_path.relative_to(data_dir).as_posix(),
                    "duplicate_of_source_id": known_checksums[checksum_key],
                    "review_status": "pending",
                },
            )
            LOGGER.info(
                "Recorded duplicate image provenance source=%s id=%s",
                candidate.source,
                candidate.source_id,
            )
            continue
        if image_path not in known_images:
            known_images.add(image_path)
            stored_bytes += image_path.stat().st_size

        append_jsonl(
            manifest_path,
            {
                **candidate.to_dict(),
                "downloaded_at": datetime.now(timezone.utc).isoformat(),
                "sha256": checksum,
                "local_path": image_path.relative_to(data_dir).as_posix(),
                "review_status": "pending",
            },
        )
        downloaded += 1
        known_checksums[checksum_key] = candidate.source_id
        LOGGER.info(
            "Collected source=%s id=%s species=%s",
            candidate.source,
            candidate.source_id,
            candidate.species_id,
        )
    return downloaded, rejected


def image_storage_bytes(data_dir: Path) -> int:
    raw_dir = data_dir / "raw"
    if not raw_dir.exists():
        return 0
    return sum(path.stat().st_size for path in raw_dir.rglob("*.jpg"))


def _manifest_image_exists(record: dict[str, object], data_dir: Path) -> bool:
    local_path = record.get("local_path")
    if not isinstance(local_path, str):
        return False
    root = data_dir.resolve()
    image_path = (root / local_path).resolve()
    if not image_path.is_relative_to(root) or not image_path.is_file():
        return False
    expected_checksum = record.get("sha256")
    if not isinstance(expected_checksum, str):
        return False
    return hashlib.sha256(image_path.read_bytes()).hexdigest() == expected_checksum


def _record_rejection(
    path: Path,
    candidate: ImageCandidate,
    reason: str,
    known_rejections: set[tuple[str, str, str]],
) -> None:
    key = (candidate.source, candidate.source_id, reason)
    if key in known_rejections:
        return
    known_rejections.add(key)
    append_jsonl(
        path,
        {
            **candidate.to_dict(),
            "rejected_at": datetime.now(timezone.utc).isoformat(),
            "reason": reason,
        },
    )


def _load_candidate_bytes(candidate: ImageCandidate, client: ApiClient) -> bytes:
    parsed = urlparse(candidate.image_url)
    if parsed.scheme == "file":
        local_path = Path(url2pathname(parsed.path))
        if not local_path.is_file():
            raise ValueError("Local image file does not exist")
        if local_path.stat().st_size > MAX_IMAGE_BYTES:
            raise ValueError(f"Image exceeds the {MAX_IMAGE_BYTES}-byte limit")
        with local_path.open("rb") as image_file:
            return image_file.read(MAX_IMAGE_BYTES + 1)
    if parsed.scheme != "https":
        raise ValueError("Image URLs must use HTTPS")
    return client.get_bytes(candidate.image_url, MAX_IMAGE_BYTES)
