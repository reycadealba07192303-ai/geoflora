"""GBIF acquisition client (official REST API, https://www.gbif.org/developer/occurrence).

Downloads are bounded (per-species limits and a session storage cap), rate limited, resumable,
and every image keeps its occurrence metadata, license and attribution. Downloaded photographs
are external records - they are never marked as GeoFlora field observations, and every image
starts with review_status = "pending".
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import requests

from .catalog import Species
from .licenses import build_attribution, is_license_allowed, normalize_license
from .utils import rel_to_root, sha256_bytes, utc_now_iso

log = logging.getLogger(__name__)

CONTENT_TYPE_EXT = {"image/jpeg": ".jpg", "image/jpg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
INAT_SIZE_RE = re.compile(r"/(original|large|medium|small|square|thumb)\.(jpe?g|png|gif)$", re.IGNORECASE)


class RateLimitedSession:
    """requests.Session wrapper enforcing a minimum interval between calls plus retry with backoff."""

    def __init__(self, user_agent: str, interval: float, timeout: float, max_retries: int):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = user_agent
        self.interval = interval
        self.timeout = timeout
        self.max_retries = max_retries
        self._last = 0.0

    def get(self, url: str, **kwargs) -> requests.Response:
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            wait = self.interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            try:
                resp = self.session.get(url, timeout=self.timeout, **kwargs)
            except requests.RequestException as exc:
                last_exc = exc
            else:
                if resp.status_code == 429 or resp.status_code >= 500:
                    retry_after = resp.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after and retry_after.isdigit() else 2 ** (attempt + 1)
                    log.warning("HTTP %s from %s; backing off %.0fs", resp.status_code, url, delay)
                    resp.close()
                    time.sleep(min(delay, 60))
                    last_exc = requests.HTTPError(f"HTTP {resp.status_code}")
                    continue
                return resp
            time.sleep(2 ** (attempt + 1))
        raise last_exc or RuntimeError(f"request failed: {url}")


def match_taxon(session: RateLimitedSession, api_base: str, scientific_name: str) -> dict:
    resp = session.get(f"{api_base}/species/match", params={"name": scientific_name, "kingdom": "Plantae", "strict": "true"})
    resp.raise_for_status()
    return resp.json()


def resolve_taxon_key(session: RateLimitedSession, api_base: str, sp: Species) -> tuple[int, str]:
    """Confirm the catalog's taxon key against the GBIF backbone. Returns (accepted_key, note)."""
    m = match_taxon(session, api_base, sp.scientific_name)
    if m.get("matchType") in (None, "NONE"):
        if sp.gbif_taxon_key:
            return sp.gbif_taxon_key, "name not matched by GBIF; using catalog key"
        raise ValueError(f"GBIF could not match '{sp.scientific_name}' and catalog has no taxon key")
    accepted = int(m.get("acceptedUsageKey") or m.get("usageKey"))
    note = f"GBIF match {m.get('matchType')} status={m.get('status')}"
    if sp.gbif_taxon_key and sp.gbif_taxon_key != accepted:
        note += f"; WARNING catalog key {sp.gbif_taxon_key} != GBIF accepted key {accepted} (using catalog key)"
        return sp.gbif_taxon_key, note
    return accepted, note


def iter_occurrences(session: RateLimitedSession, dcfg: dict, taxon_key: int, country: str | None,
                     start_offset: int = 0) -> Iterator[dict]:
    """Yield occurrence records that have still images, paging through the GBIF search API."""
    offset = start_offset
    page = int(dcfg.get("page_size", 100))
    while True:
        params: list[tuple[str, str]] = [
            ("taxonKey", str(taxon_key)), ("mediaType", "StillImage"),
            ("limit", str(page)), ("offset", str(offset)),
        ]
        params += [("basisOfRecord", b) for b in dcfg.get("basis_of_record") or []]
        params += [("datasetKey", k) for k in dcfg.get("dataset_keys") or []]
        if country:
            params.append(("country", country))
        resp = session.get(f"{dcfg['api_base']}/occurrence/search", params=params)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        yield from results
        offset += len(results)
        if data.get("endOfRecords", True) or not results or offset >= 100_000:
            return


def resize_inaturalist_url(url: str, size: str) -> str:
    """iNaturalist open-data URLs end in /original.jpg; swap to a smaller published size."""
    if size == "original" or "inaturalist" not in url:
        return url
    return INAT_SIZE_RE.sub(lambda m: f"/{size}.{m.group(2)}", url)


@dataclass
class MediaCandidate:
    occurrence: dict
    media: dict
    media_index: int
    license_code: str | None
    license_raw: str


def eligible_media(occ: dict, allowed_licenses: list[str], max_per_occurrence: int) -> list[MediaCandidate]:
    """Still images of an occurrence whose own (image-level) license is allowed."""
    out = []
    for idx, media in enumerate(occ.get("media") or []):
        if media.get("type") != "StillImage" or not media.get("identifier"):
            continue
        # Image-level license takes precedence; fall back to the occurrence license.
        raw = media.get("license") or occ.get("license") or ""
        code = normalize_license(raw)
        if not is_license_allowed(code, allowed_licenses):
            continue
        out.append(MediaCandidate(occ, media, idx, code, raw))
        if len(out) >= max_per_occurrence:
            break
    return out


def manifest_row(sp: Species, accepted_key: int, cand: MediaCandidate, fetched_url: str,
                 local_path: Path, data: bytes, ext: str, meta_ref: str, root: Path) -> dict:
    occ, media = cand.occurrence, cand.media
    gbif_key = str(occ.get("key", ""))
    creator = media.get("creator") or occ.get("recordedBy") or ""
    rights = media.get("rightsHolder") or occ.get("rightsHolder") or ""
    reference = media.get("references") or occ.get("occurrenceID") or f"https://www.gbif.org/occurrence/{gbif_key}"
    return {
        "image_id": f"gbif-{gbif_key}-{cand.media_index}",
        "species_id": sp.species_id,
        "scientific_name": sp.scientific_name,
        "accepted_taxon_key": str(accepted_key),
        "verbatim_scientific_name": occ.get("scientificName", ""),
        "ecological_role": sp.role,
        "source": "GBIF",
        "source_dataset_key": occ.get("datasetKey", ""),
        "source_dataset_name": occ.get("datasetName", ""),
        "publisher": media.get("publisher") or occ.get("institutionCode") or "",
        "observation_id": f"gbif:{gbif_key}",
        "occurrence_id": occ.get("occurrenceID", ""),
        "gbif_occurrence_key": gbif_key,
        "media_reference_url": media.get("references", ""),
        "original_image_url": media.get("identifier", ""),
        "fetched_image_url": fetched_url,
        "creator": creator,
        "rights_holder": rights,
        "license_raw": cand.license_raw,
        "license": cand.license_code or "",
        "attribution": build_attribution(creator, rights, cand.license_code,
                                         occ.get("datasetName") or "GBIF", reference),
        "basis_of_record": occ.get("basisOfRecord", ""),
        "country_code": occ.get("countryCode", ""),
        "event_date": occ.get("eventDate", ""),
        "recorded_by": occ.get("recordedBy", ""),
        "identified_by": occ.get("identifiedBy", ""),
        "occurrence_metadata_ref": meta_ref,
        "download_timestamp": utc_now_iso(),
        "is_geoflora_field_observation": "false",
        "local_path": rel_to_root(local_path, root),
        "file_sha256": sha256_bytes(data),
        "file_bytes": str(len(data)),
        "image_format": ext.lstrip("."),
        "license_eligible": "true",
        "review_status": "pending",
    }


def fetch_image(session: RateLimitedSession, url: str, max_bytes: int) -> tuple[bytes, str]:
    """Download an image with a size cap. Returns (bytes, extension)."""
    resp = session.get(url, stream=True)
    try:
        resp.raise_for_status()
        ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ctype not in CONTENT_TYPE_EXT:
            raise ValueError(f"unexpected content type '{ctype}'")
        declared = resp.headers.get("Content-Length")
        if declared and declared.isdigit() and int(declared) > max_bytes:
            raise ValueError(f"image larger than limit ({declared} bytes)")
        chunks, total = [], 0
        for chunk in resp.iter_content(64 * 1024):
            total += len(chunk)
            if total > max_bytes:
                raise ValueError("image exceeded size limit during download")
            chunks.append(chunk)
        return b"".join(chunks), CONTENT_TYPE_EXT[ctype]
    finally:
        resp.close()


def append_occurrence_metadata(meta_dir: Path, sp: Species, occ: dict) -> str:
    """Append the full original occurrence JSON to a per-species JSONL file; return a reference string."""
    meta_dir.mkdir(parents=True, exist_ok=True)
    path = meta_dir / f"{sp.folder}.jsonl"
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(occ, ensure_ascii=False) + "\n")
    return f"{path.name}#gbif:{occ.get('key')}"
