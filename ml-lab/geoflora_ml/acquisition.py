"""Bounded, resumable dataset acquisition from GBIF into dataset/raw/<species>/."""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field

from .catalog import Species, load_catalog
from .config import project_path, project_root
from .gbif import (RateLimitedSession, append_occurrence_metadata, eligible_media, fetch_image,
                   iter_occurrences, manifest_row, resize_inaturalist_url, resolve_taxon_key)
from .manifest import append_rows, load_manifest, save_manifest
from .utils import utc_now_iso, utc_stamp, write_json

log = logging.getLogger(__name__)


@dataclass
class DownloadBudget:
    max_bytes: int
    used_bytes: int = 0

    @property
    def exhausted(self) -> bool:
        return self.used_bytes >= self.max_bytes


@dataclass
class SpeciesResult:
    species_id: str
    scientific_name: str
    requested: int
    already_present: int
    downloaded: int = 0
    accepted_taxon_key: int | None = None
    taxon_note: str = ""
    skipped: Counter = field(default_factory=Counter)
    countries: Counter = field(default_factory=Counter)
    error: str = ""


def download_species(cfg: dict, sp: Species, limit: int, session: RateLimitedSession,
                     manifest, budget: DownloadBudget):
    dcfg = cfg["download"]
    root = project_root(cfg)
    raw_dir = project_path(cfg, "raw") / sp.folder
    meta_dir = project_path(cfg, "occurrence_metadata")

    existing = manifest[manifest["species_id"] == sp.species_id]
    seen_occ = set(existing["gbif_occurrence_key"])
    res = SpeciesResult(sp.species_id, sp.scientific_name, limit, len(existing))
    need = limit - len(existing)
    if need <= 0:
        return manifest, res

    try:
        key, note = resolve_taxon_key(session, dcfg["api_base"], sp)
    except Exception as exc:  # network or taxonomy problem: record and continue with other species
        res.error = f"taxon resolution failed: {exc}"
        return manifest, res
    res.accepted_taxon_key, res.taxon_note = key, note

    rows: list[dict] = []
    for country in dcfg.get("country_priority") or [None]:
        if need <= 0 or budget.exhausted:
            break
        try:
            for occ in iter_occurrences(session, dcfg, key, country):
                if need <= 0 or budget.exhausted:
                    break
                okey = str(occ.get("key", ""))
                if okey in seen_occ:
                    continue
                seen_occ.add(okey)
                cands = eligible_media(occ, dcfg["allowed_licenses"], int(dcfg.get("max_images_per_occurrence", 1)))
                if not cands:
                    res.skipped["no_media_with_allowed_license"] += 1
                    continue
                meta_ref = None
                for cand in cands:
                    url = resize_inaturalist_url(cand.media["identifier"], dcfg.get("inaturalist_photo_size", "medium"))
                    try:
                        data, ext = fetch_image(session, url, int(dcfg["max_image_bytes"]))
                    except Exception as exc:
                        res.skipped[f"fetch_failed:{type(exc).__name__}"] += 1
                        log.debug("fetch failed %s: %s", url, exc)
                        continue
                    if meta_ref is None:
                        meta_ref = append_occurrence_metadata(meta_dir, sp, occ)
                    image_id = f"gbif-{okey}-{cand.media_index}"
                    path = raw_dir / f"{image_id}{ext}"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(data)
                    rows.append(manifest_row(sp, key, cand, url, path, data, ext, meta_ref, root))
                    budget.used_bytes += len(data)
                    res.downloaded += 1
                    res.countries[occ.get("countryCode") or "unknown"] += 1
                    need -= 1
                    if need <= 0:
                        break
        except Exception as exc:
            res.error = f"occurrence search failed ({country or 'global'}): {exc}"
            log.warning("%s: %s", sp.scientific_name, res.error)
    return append_rows(manifest, rows), res


def run_download(cfg: dict, species_ids: list[str] | None = None, roles: list[str] | None = None,
                 max_per_species: int | None = None, max_total_mb: float | None = None,
                 dry_run: bool = False) -> dict:
    dcfg = cfg["download"]
    catalog = load_catalog(project_path(cfg, "species_catalog"))
    selected = [s for s in catalog if s.download_enabled]
    if species_ids:
        wanted = set(species_ids)
        selected = [s for s in catalog if s.species_id in wanted or s.scientific_name in wanted]
    if roles:
        selected = [s for s in selected if s.role in roles]

    plan = []
    for sp in selected:
        limit = max_per_species if max_per_species is not None else int(dcfg["per_role_default_limit"].get(sp.role, 0))
        if limit > 0:
            plan.append((sp, limit))
    if dry_run:
        return {"dry_run": True, "plan": [{"species_id": s.species_id, "scientific_name": s.scientific_name,
                                           "role": s.role, "limit": n} for s, n in plan]}

    manifest_path = project_path(cfg, "image_manifest")
    manifest = load_manifest(manifest_path)
    session = RateLimitedSession(dcfg["user_agent"], float(dcfg["request_interval_seconds"]),
                                 float(dcfg["timeout_seconds"]), int(dcfg["max_retries"]))
    budget = DownloadBudget(int(float(max_total_mb if max_total_mb is not None else dcfg["max_total_megabytes"]) * 1e6))
    started = utc_now_iso()
    results = []
    for sp, limit in plan:
        if budget.exhausted:
            log.warning("storage budget exhausted; stopping before %s", sp.scientific_name)
            break
        log.info("%s (%s): target %d images", sp.scientific_name, sp.role, limit)
        manifest, res = download_species(cfg, sp, limit, session, manifest, budget)
        # Re-read before saving: review imports or validation may have updated the file during this download.
        # Only rows this run added are appended, so their changes are never overwritten.
        on_disk = load_manifest(manifest_path)
        new = manifest[~manifest["image_id"].isin(on_disk["image_id"])]
        manifest = append_rows(on_disk, new.to_dict("records")) if len(new) else on_disk
        save_manifest(manifest, manifest_path)  # persist after each species so interruptions are safe
        log.info("  downloaded %d (already had %d) %s", res.downloaded, res.already_present, res.error)
        results.append(res)

    summary = {
        "started": started,
        "finished": utc_now_iso(),
        "source": dcfg["source"],
        "allowed_licenses": dcfg["allowed_licenses"],
        "country_priority": dcfg.get("country_priority"),
        "bytes_downloaded": budget.used_bytes,
        "storage_budget_bytes": budget.max_bytes,
        "species": [{
            "species_id": r.species_id, "scientific_name": r.scientific_name,
            "accepted_taxon_key": r.accepted_taxon_key, "taxon_note": r.taxon_note,
            "requested": r.requested, "already_present": r.already_present, "downloaded": r.downloaded,
            "countries": dict(r.countries), "skipped": dict(r.skipped), "error": r.error,
        } for r in results],
        "note": "All downloaded images have review_status=pending and are NOT GeoFlora field observations.",
    }
    write_json(project_path(cfg, "reports") / "download_logs" / f"download_{utc_stamp()}.json", summary)
    return summary
