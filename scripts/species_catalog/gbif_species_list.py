from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import json
import logging
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


LOGGER = logging.getLogger("geoflora.species_catalog.gbif")
ROOT = Path(__file__).resolve().parents[2]
# Credentials and settings come from apps/web/.env.local (see services/ml/src/geoflora_ml/env.py).
sys.path.insert(0, str(ROOT / "services/ml/src"))
from geoflora_ml.env import load_env  # noqa: E402

load_env()
CATALOG_DIR = ROOT / "storage" / "species_catalog"
DOWNLOAD_DIR = CATALOG_DIR / "downloads"
STAGING_DIR = CATALOG_DIR / "staging"
GBIF_API = "https://api.gbif.org/v1"
GBIF_DOWNLOAD_URL = "https://api.gbif.org/occurrence/download/request"
REQUEST_PREDICATE = {
    "type": "and",
    "predicates": [
        {"type": "equals", "key": "COUNTRY", "value": "PH"},
        {"type": "equals", "key": "KINGDOM", "value": "Plantae"},
    ],
}
REQUIRED_COLUMNS = {
    "taxonkey",
    "scientificname",
    "acceptedtaxonkey",
    "acceptedscientificname",
    "taxonrank",
    "taxonomicstatus",
    "kingdom",
}
class CatalogImportError(RuntimeError):
    pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Request and stage a Philippines/Plantae GBIF Species List download."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    request = commands.add_parser("request", help="Submit an authenticated GBIF download")
    request.add_argument(
        "--output-dir", type=Path, default=DOWNLOAD_DIR, help="Download metadata directory"
    )

    status = commands.add_parser("status", help="Show the status of a GBIF download")
    status.add_argument("download_key")

    download = commands.add_parser("download", help="Download a completed GBIF ZIP archive")
    download.add_argument("download_key")
    download.add_argument("--output-dir", type=Path, default=DOWNLOAD_DIR)
    download.add_argument(
        "--max-download-gb",
        type=float,
        default=5.0,
        help="Maximum archive size in GB (default: 5)",
    )

    stage = commands.add_parser(
        "stage",
        help="Validate and stage records from a GBIF Species List CSV or ZIP",
    )
    stage.add_argument("input_file", type=Path)
    stage.add_argument("--download-key", required=True)
    stage.add_argument("--source-doi", help="GBIF download DOI, for manually obtained files")
    stage.add_argument("--citation", help="Exact source citation supplied by GBIF")
    stage.add_argument(
        "--source-filter",
        default=(
            "Country is one of (Philippines); TaxonKey is one of "
            "(Plantae [Catalogue of Life])"
        ),
        help="Exact filter description from the GBIF download record",
    )
    stage.add_argument(
        "--source-record-count",
        type=_positive_int,
        help="Expected total rows reported by GBIF, used to validate the supplied file",
    )
    stage.add_argument(
        "--metadata-dir",
        type=Path,
        default=DOWNLOAD_DIR,
        help="Directory containing metadata created by the request/download commands",
    )
    limit = stage.add_mutually_exclusive_group()
    limit.add_argument(
        "--limit",
        type=_positive_int,
        default=100,
        help="Maximum accepted species to stage (default: 100)",
    )
    limit.add_argument(
        "--all-records",
        action="store_true",
        help="Stage all eligible accepted species in the archive",
    )
    stage.add_argument("--output-dir", type=Path, default=STAGING_DIR)
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    args = build_parser().parse_args(argv)
    try:
        if args.command == "request":
            download_key = request_download(args.output_dir)
            print(download_key)
        elif args.command == "status":
            print(json.dumps(get_download_status(args.download_key), indent=2))
        elif args.command == "download":
            archive = download_archive(
                args.download_key, args.output_dir, args.max_download_gb
            )
            print(archive)
        elif args.command == "stage":
            limit_value = None if args.all_records else args.limit
            csv_path, audit_path = stage_species_list_file(
                args.input_file,
                args.download_key,
                args.source_doi,
                args.citation,
                args.source_filter,
                args.source_record_count,
                args.output_dir,
                limit_value,
                args.metadata_dir,
            )
            print(f"Staged manifest: {csv_path}")
            print(f"Audit report: {audit_path}")
        return 0
    except (CatalogImportError, OSError, ValueError, urllib.error.URLError) as exc:
        LOGGER.error("%s", exc)
        return 1


def request_download(output_dir: Path = DOWNLOAD_DIR) -> str:
    username = os.environ.get("GBIF_USER", "").strip()
    password = os.environ.get("GBIF_PASSWORD", "")
    email = os.environ.get("GBIF_EMAIL", "").strip()
    if not username or not password or not email:
        raise CatalogImportError(
            "Set GBIF_USER, GBIF_PASSWORD, and GBIF_EMAIL in the local environment. "
            "Do not pass credentials as command-line arguments or commit them."
        )

    payload = {
        "notificationAddresses": [email],
        "sendNotification": True,
        "format": "SPECIES_LIST",
        "predicate": REQUEST_PREDICATE,
    }
    response = _request(
        f"{GBIF_API}/occurrence/download/request",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": _basic_auth(username, password),
        },
    )
    download_key = response.decode("utf-8").strip().strip('"')
    if not re.fullmatch(r"[0-9]{3,}-[0-9]{12,}", download_key):
        raise CatalogImportError(
            "GBIF returned an unexpected download key; check API response and credentials."
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        "download_key": download_key,
        "requested_at_utc": datetime.now(timezone.utc).isoformat(),
        "format": "SPECIES_LIST",
        "country": "PH",
        "kingdom": "Plantae",
        "predicate": REQUEST_PREDICATE,
        "filter_description": json.dumps(REQUEST_PREDICATE, ensure_ascii=False),
        "doi": None,
        "citation": None,
        "status": "PREPARING",
    }
    _write_json(_metadata_path(output_dir, download_key), metadata)
    return download_key


def get_download_status(download_key: str) -> dict[str, Any]:
    _validate_download_key(download_key)
    result = _request_json(f"{GBIF_API}/occurrence/download/{download_key}")
    if not isinstance(result, dict):
        raise CatalogImportError("GBIF returned an invalid download status response.")
    return result


def download_archive(
    download_key: str,
    output_dir: Path = DOWNLOAD_DIR,
    max_download_gb: float = 5.0,
) -> Path:
    _validate_download_key(download_key)
    if max_download_gb <= 0:
        raise ValueError("max_download_gb must be greater than zero")

    status = get_download_status(download_key)
    state = str(status.get("status", "")).upper()
    if state != "SUCCEEDED":
        raise CatalogImportError(
            f"GBIF download {download_key} is {state or 'in an unknown state'}; "
            "download it only after status is SUCCEEDED."
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    archive = output_dir / f"{download_key}.zip"
    if not archive.exists():
        _stream_archive(download_key, archive, int(max_download_gb * 1024**3))

    metadata_path = _metadata_path(output_dir, download_key)
    metadata = _read_json(metadata_path) if metadata_path.exists() else {}
    metadata.update(
        {
            "download_key": download_key,
            "status": state,
            "doi": status.get("doi") or status.get("doiUrl"),
            "citation": status.get("citation"),
            "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
            "archive": archive.name,
            "archive_sha256": _sha256(archive),
            "archive_bytes": archive.stat().st_size,
            "source_record_count": status.get("totalRecords"),
        }
    )
    _write_json(metadata_path, metadata)
    return archive


def stage_archive(
    archive: Path,
    download_key: str,
    output_dir: Path = STAGING_DIR,
    limit: int | None = 100,
    metadata_dir: Path = DOWNLOAD_DIR,
) -> tuple[Path, Path]:
    _validate_download_key(download_key)
    if limit is not None and limit <= 0:
        raise ValueError("limit must be greater than zero or None")
    archive = archive.expanduser().resolve()
    if not archive.is_file():
        raise FileNotFoundError(f"GBIF download archive not found: {archive}")

    metadata = _metadata_for_download(download_key, metadata_dir)
    if (
        metadata.get("format") != "SPECIES_LIST"
        or metadata.get("country") != "PH"
        or metadata.get("kingdom") != "Plantae"
    ):
        raise CatalogImportError(
            "Download metadata does not confirm the required SPECIES_LIST, "
            "Philippines, Plantae filters."
        )
    rows = _read_species_list(archive)
    return _write_staged_species(
        rows,
        archive,
        download_key,
        metadata,
        output_dir,
        limit,
    )


def stage_species_list_file(
    input_file: Path,
    download_key: str,
    source_doi: str | None = None,
    citation: str | None = None,
    source_filter: str = (
        "Country is one of (Philippines); TaxonKey is one of "
        "(Plantae [Catalogue of Life])"
    ),
    source_record_count: int | None = None,
    output_dir: Path = STAGING_DIR,
    limit: int | None = 100,
    metadata_dir: Path = DOWNLOAD_DIR,
) -> tuple[Path, Path]:
    _validate_download_key(download_key)
    if limit is not None and limit <= 0:
        raise ValueError("limit must be greater than zero or None")
    input_file = input_file.expanduser().resolve()
    if not input_file.is_file():
        raise FileNotFoundError(f"GBIF Species List file not found: {input_file}")

    metadata_path = _metadata_path(metadata_dir, download_key)
    if metadata_path.is_file():
        metadata = _metadata_for_download(download_key, metadata_dir)
        if (
            metadata.get("format") != "SPECIES_LIST"
            or metadata.get("country") != "PH"
            or metadata.get("kingdom") != "Plantae"
        ):
            raise CatalogImportError(
                "Download metadata does not confirm SPECIES_LIST, Philippines, "
                "and Plantae filters."
            )
        if source_doi and metadata.get("doi") and source_doi != metadata["doi"]:
            raise CatalogImportError("Provided DOI does not match GBIF download metadata.")
        if citation and metadata.get("citation") and citation != metadata["citation"]:
            raise CatalogImportError(
                "Provided citation does not match GBIF download metadata."
            )
        source_doi = source_doi or metadata.get("doi")
        citation = citation or metadata.get("citation")
    else:
        metadata = {
            "download_key": download_key,
            "format": "SPECIES_LIST",
            "country": "PH",
            "kingdom": "Plantae",
            "doi": source_doi,
            "citation": citation,
            "filter_description": source_filter,
            "taxon_filter": "Plantae [Catalogue of Life] (GBIF taxon key P)",
            "source_record_count": source_record_count,
        }
    if not metadata.get("filter_description"):
        metadata["filter_description"] = source_filter

    rows = (
        _read_species_list(input_file)
        if input_file.suffix.casefold() == ".zip"
        else _read_species_list_file(input_file)
    )
    expected_record_count = metadata.get("source_record_count") or source_record_count
    if expected_record_count is not None and len(rows) != int(expected_record_count):
        raise CatalogImportError(
            "GBIF file row count does not match the expected download count: "
            f"{len(rows)} != {expected_record_count}"
        )
    if expected_record_count is not None:
        metadata["source_record_count"] = int(expected_record_count)
    return _write_staged_species(
        rows,
        input_file,
        download_key,
        metadata,
        output_dir,
        limit,
    )


def _write_staged_species(
    rows: list[dict[str, str]],
    source_file: Path,
    download_key: str,
    metadata: dict[str, Any],
    output_dir: Path,
    limit: int | None,
) -> tuple[Path, Path]:
    eligible, audit, rejected_rows = _curate_rows_detailed(rows)
    expected_record_count = metadata.get("source_record_count")
    if expected_record_count is not None and len(rows) != int(expected_record_count):
        raise CatalogImportError(
            "GBIF file row count does not match download metadata: "
            f"{len(rows)} != {expected_record_count}"
        )
    all_species_count = len(eligible)
    staged_rows = eligible if limit is None else eligible[:limit]
    for row in staged_rows:
        row["source_download_key"] = download_key
        row["source_download_doi"] = str(metadata.get("doi") or "")

    audit.update(
        {
            "dataset": "GeoFlora Philippine flora species-catalog staging",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "download_key": download_key,
            "source_doi": metadata.get("doi"),
            "source_citation": metadata.get("citation"),
            "source_filter": metadata.get("filter_description")
            or json.dumps(metadata.get("predicate"), ensure_ascii=False),
            "source_format": metadata.get("format", "SPECIES_LIST"),
            "source_country_filter": metadata.get("country", "PH"),
            "source_taxon_filter": metadata.get(
                "taxon_filter", metadata.get("kingdom", "Plantae")
            ),
            "observed_kingdoms": sorted(
                {
                    row.get("kingdom", "")
                    for row in rows
                    if row.get("kingdom", "")
                }
            ),
            "source_file": source_file.name,
            "source_file_sha256": _sha256(source_file),
            "source_rows_read": len(rows),
            "download_reported_record_count": expected_record_count or len(rows),
            "unique_accepted_species_available": all_species_count,
            "staged_accepted_species": len(staged_rows),
            "sample_limit": limit,
            "is_sample": limit is not None and len(staged_rows) < all_species_count,
            "not_a_verified_national_checklist": True,
            "status_policy": {
                "ecological_status": "blank pending authoritative evidence and review",
                "catalog_review_status": "staged_pending_taxonomic_and_source_review",
                "ai_model_supported": False,
                "training_data": False,
            },
            "count_note": (
                "GBIF SPECIES_LIST is an occurrence-derived summary. Its output count "
                "does not represent a complete Philippine flora checklist or validate "
                "the reference total of 11,435 species."
            ),
        }
    )

    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = "sample" if limit is not None else "full"
    stem = f"gbif_philippines_plantae_{suffix}_{download_key}"
    csv_path = output_dir / f"{stem}_staging.csv"
    audit_path = output_dir / f"{stem}_audit.json"
    provenance_path = output_dir / f"{stem}_provenance.json"
    unresolved_path = output_dir / f"{stem}_unresolved.csv"
    _write_manifest(csv_path, staged_rows)
    _write_unresolved_manifest(unresolved_path, rows, rejected_rows)
    audit["staging_csv_sha256"] = _sha256(csv_path)
    audit["unresolved_records_csv"] = unresolved_path.name
    audit["unresolved_records_rows"] = len(rejected_rows)
    audit["unresolved_records_csv_sha256"] = _sha256(unresolved_path)
    _write_json(audit_path, audit)
    _write_json(
        provenance_path,
        {
            **audit,
            "source_dataset": {
                "title": "GBIF Philippines Plantae occurrence Species List",
                "key": download_key,
                "doi": metadata.get("doi"),
                "citation": metadata.get("citation"),
                "license": "GBIF occurrence records; retain dataset-level source attribution",
            },
            "output_csv": csv_path.name,
            "unresolved_records_csv": unresolved_path.name,
        },
    )
    return csv_path, audit_path


def _read_species_list(archive: Path) -> list[dict[str, str]]:
    try:
        with zipfile.ZipFile(archive) as zipped:
            for member in zipped.namelist():
                if Path(member).suffix.casefold() not in {".txt", ".tsv", ".csv"}:
                    continue
                if Path(member).name.casefold() in {"citation.txt", "readme.txt"}:
                    continue
                with zipped.open(member) as binary:
                    text = io.TextIOWrapper(binary, encoding="utf-8-sig", newline="")
                    reader = csv.DictReader(text, delimiter="\t")
                    fieldnames = {
                        (name or "").strip().lstrip("\ufeff").casefold()
                        for name in reader.fieldnames or []
                    }
                    if not REQUIRED_COLUMNS.issubset(fieldnames):
                        continue
                    return _normalize_rows(reader)
    except (OSError, zipfile.BadZipFile, UnicodeError, csv.Error) as exc:
        raise CatalogImportError(f"Cannot read GBIF Species List archive: {exc}") from exc
    raise CatalogImportError(
        "Archive contains no tab-separated species-list file with required GBIF columns."
    )


def _read_species_list_file(path: Path) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as source:
            sample = source.read(8192)
            source.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters="\t,")
            except csv.Error:
                dialect = csv.excel_tab
            reader = csv.DictReader(source, dialect=dialect)
            fieldnames = {
                (name or "").strip().lstrip("\ufeff").casefold()
                for name in reader.fieldnames or []
            }
            if not REQUIRED_COLUMNS.issubset(fieldnames):
                raise CatalogImportError(
                    "Input file does not have the required GBIF Species List columns."
                )
            return _normalize_rows(reader)
    except (OSError, UnicodeError, csv.Error) as exc:
        raise CatalogImportError(f"Cannot read GBIF Species List file: {exc}") from exc


def _normalize_rows(reader: csv.DictReader[str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for row in reader:
        normalized = {
            (key or "").strip().lstrip("\ufeff").casefold(): (
                value.strip() if value is not None else ""
            )
            for key, value in row.items()
        }
        rows.append(normalized)
    return rows


def _curate_rows(
    rows: list[dict[str, str]],
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    curated, audit, _ = _curate_rows_detailed(rows)
    return curated, audit


def _curate_rows_detailed(
    rows: list[dict[str, str]],
) -> tuple[list[dict[str, str]], dict[str, Any], list[dict[str, str]]]:
    groups: dict[str, list[dict[str, str]]] = {}
    rejected_non_plant = 0
    missing_kingdom = 0
    unresolved_by_reason: Counter[str] = Counter()
    taxonomic_status_counts: Counter[str] = Counter()
    species_rank_status_counts: Counter[str] = Counter()
    species_rank_plant_rows = 0
    rejected_rows: list[dict[str, str]] = []

    for row in rows:
        kingdom = row.get("kingdom", "").casefold()
        if not kingdom:
            missing_kingdom += 1
            unresolved_by_reason["missing_kingdom"] += 1
            rejected_rows.append({**row, "review_flag": "missing_kingdom"})
            continue
        if kingdom != "plantae":
            rejected_non_plant += 1
            rejected_rows.append({**row, "review_flag": "non_plant_kingdom"})
            continue
        if row.get("taxonomicstatus"):
            taxonomic_status_counts[row["taxonomicstatus"]] += 1
        if row.get("taxonrank", "").casefold() != "species":
            unresolved_by_reason["not_species_rank"] += 1
            rejected_rows.append({**row, "review_flag": "not_species_rank"})
            continue
        species_rank_plant_rows += 1
        if row.get("taxonomicstatus"):
            species_rank_status_counts[row["taxonomicstatus"]] += 1
        accepted_key = _taxon_key(row.get("acceptedtaxonkey", ""))
        accepted_name = row.get("acceptedscientificname", "").strip()
        if accepted_key is None:
            unresolved_by_reason["missing_or_invalid_accepted_taxon_key"] += 1
            rejected_rows.append(
                {**row, "review_flag": "missing_or_invalid_accepted_taxon_key"}
            )
            continue
        if not accepted_name:
            unresolved_by_reason["missing_accepted_scientific_name"] += 1
            rejected_rows.append(
                {**row, "review_flag": "missing_accepted_scientific_name"}
            )
            continue
        taxonomic_status = row.get("taxonomicstatus", "").upper()
        if taxonomic_status not in {"ACCEPTED", "SYNONYM"}:
            unresolved_by_reason["unsupported_taxonomic_status"] += 1
            rejected_rows.append(
                {**row, "review_flag": "unsupported_taxonomic_status"}
            )
            continue
        groups.setdefault(accepted_key, []).append(row)

    curated: list[dict[str, str]] = []
    taxonomy_conflicts = 0
    reconciled_name_usages = 0
    for accepted_key, group in groups.items():
        accepted_names = {item["acceptedscientificname"].strip() for item in group}
        families = {item.get("family", "").strip() for item in group if item.get("family")}
        genera = {item.get("genus", "").strip() for item in group if item.get("genus")}
        if len(accepted_names) != 1 or len(families) > 1 or len(genera) > 1:
            taxonomy_conflicts += 1
            unresolved_by_reason["conflicting_taxonomy_for_accepted_key"] += len(group)
            rejected_rows.extend(
                {
                    **item,
                    "review_flag": "conflicting_taxonomy_for_accepted_key",
                }
                for item in group
            )
            continue
        reconciled_name_usages += sum(
            item.get("taxonkey") != accepted_key for item in group
        )

        accepted_row = next(
            (
                item
                for item in group
                if item.get("taxonkey") == accepted_key
                and item.get("taxonomicstatus", "").casefold() == "accepted"
            ),
            group[0],
        )
        occurrence_counts = [
            _nonnegative_int(item.get("numberofoccurrences", "")) for item in group
        ]
        curated.append(
            {
                "accepted_taxon_key": accepted_key,
                "accepted_scientific_name": next(iter(accepted_names)),
                "family": accepted_row.get("family", ""),
                "genus": accepted_row.get("genus", ""),
                "source_taxonomic_status": accepted_row.get("taxonomicstatus", ""),
                "source_taxon_keys": _json_array(
                    sorted({item.get("taxonkey", "") for item in group if item.get("taxonkey")})
                ),
                "source_scientific_names": _json_array(
                    sorted(
                        {
                            item.get("scientificname", "")
                            for item in group
                            if item.get("scientificname")
                        }
                    )
                ),
                "source_taxonomic_statuses": _json_array(
                    sorted(
                        {
                            item.get("taxonomicstatus", "")
                            for item in group
                            if item.get("taxonomicstatus")
                        }
                    )
                ),
                "source_iucn_red_list_categories": _json_array(
                    sorted(
                        {
                            item.get("iucnredlistcategory", "")
                            for item in group
                            if item.get("iucnredlistcategory")
                        }
                    )
                ),
                "source_usage_details": json.dumps(
                    [
                        {
                            "source_taxon_key": item.get("taxonkey", ""),
                            "scientific_name": item.get("scientificname", ""),
                            "taxonomic_rank": item.get("taxonrank", ""),
                            "taxonomic_status": item.get("taxonomicstatus", ""),
                            "occurrence_count": _nonnegative_int(
                                item.get("numberofoccurrences", "")
                            ),
                            "family": item.get("family", ""),
                            "genus": item.get("genus", ""),
                            "iucn_red_list_category": item.get(
                                "iucnredlistcategory", ""
                            ),
                        }
                        for item in sorted(
                            group,
                            key=lambda usage: (
                                usage.get("taxonkey", ""),
                                usage.get("taxonomicstatus", ""),
                                usage.get("scientificname", ""),
                            ),
                        )
                    ],
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                "source_occurrence_count": str(sum(occurrence_counts)),
                "source_usage_count": str(len(group)),
                "source_country": "PH",
                "source_kingdom": "Plantae",
                "source_download_key": "",
                "source_download_doi": "",
                "catalog_review_status": "staged_pending_taxonomic_and_source_review",
                "ecological_status": "",
                "ai_model_supported": "false",
            }
        )

    accepted_name_keys: dict[str, set[str]] = {}
    for item in curated:
        accepted_name_keys.setdefault(
            item["accepted_scientific_name"].strip().casefold(), set()
        ).add(item["accepted_taxon_key"])
    colliding_name_groups = {
        name: keys for name, keys in accepted_name_keys.items() if len(keys) > 1
    }
    colliding_taxon_keys = {
        key for keys in colliding_name_groups.values() for key in keys
    }
    collision_source_rows = 0
    if colliding_taxon_keys:
        for accepted_key in sorted(colliding_taxon_keys):
            group = groups[accepted_key]
            collision_source_rows += len(group)
            rejected_rows.extend(
                {
                    **item,
                    "review_flag": "accepted_scientific_name_collision_across_taxon_keys",
                }
                for item in group
            )
            unresolved_by_reason[
                "accepted_scientific_name_collision_across_taxon_keys"
            ] += len(group)
        curated = [
            item
            for item in curated
            if item["accepted_taxon_key"] not in colliding_taxon_keys
        ]

    curated.sort(
        key=lambda item: (
            item["accepted_taxon_key"],
            item["accepted_scientific_name"].casefold(),
        )
    )
    return curated, {
        "source_rows_total": len(rows),
        "non_plant_rows_rejected": rejected_non_plant,
        "missing_kingdom_rows": missing_kingdom,
        "plant_rows": len(rows) - rejected_non_plant - missing_kingdom,
        "species_rank_plant_rows": species_rank_plant_rows,
        "source_name_usages_reconciled_to_accepted_taxa": reconciled_name_usages,
        "taxonomy_conflict_groups_rejected": taxonomy_conflicts,
        "accepted_taxon_key_candidates_before_name_collision": (
            len(curated) + len(colliding_taxon_keys)
        ),
        "accepted_name_collision_groups": len(colliding_name_groups),
        "accepted_name_collision_taxon_keys": len(colliding_taxon_keys),
        "accepted_name_collision_source_rows": collision_source_rows,
        "unique_accepted_species_available": len(curated),
        "unresolved_rows": sum(unresolved_by_reason.values()),
        "unresolved_rows_by_reason": dict(sorted(unresolved_by_reason.items())),
        "taxonomic_status_usage_counts_all_ranks": dict(
            sorted(taxonomic_status_counts.items())
        ),
        "taxonomic_status_usage_counts_species_rank": dict(
            sorted(species_rank_status_counts.items())
        ),
    }, rejected_rows


def _write_manifest(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = [
        "accepted_taxon_key",
        "accepted_scientific_name",
        "family",
        "genus",
        "source_taxonomic_status",
        "source_taxon_keys",
        "source_scientific_names",
        "source_taxonomic_statuses",
        "source_iucn_red_list_categories",
        "source_usage_details",
        "source_occurrence_count",
        "source_usage_count",
        "source_country",
        "source_kingdom",
        "source_download_key",
        "source_download_doi",
        "catalog_review_status",
        "ecological_status",
        "ai_model_supported",
    ]
    temp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        with temp_path.open("w", encoding="utf-8-sig", newline="") as output:
            writer = csv.DictWriter(output, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        temp_path.replace(path)
    except OSError:
        temp_path.unlink(missing_ok=True)
        raise


def _write_unresolved_manifest(
    path: Path,
    source_rows: list[dict[str, str]],
    rejected_rows: list[dict[str, str]],
) -> None:
    fieldnames = list(source_rows[0]) if source_rows else []
    fieldnames.append("review_flag")
    temp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        with temp_path.open("w", encoding="utf-8-sig", newline="") as output:
            writer = csv.DictWriter(output, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rejected_rows)
        temp_path.replace(path)
    except OSError:
        temp_path.unlink(missing_ok=True)
        raise


def _stream_archive(download_key: str, target: Path, max_bytes: int) -> None:
    url = f"{GBIF_DOWNLOAD_URL}/{download_key}.zip"
    request = urllib.request.Request(url, headers={"User-Agent": "GeoFlora/0.1"})
    temp_path: Path | None = None
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            declared_size = response.headers.get("Content-Length")
            if declared_size and int(declared_size) > max_bytes:
                raise CatalogImportError(
                    f"GBIF archive exceeds the configured {max_bytes} byte limit."
                )
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=target.parent, prefix=f"{target.name}.", suffix=".tmp", delete=False
            ) as temporary:
                temp_path = Path(temporary.name)
                total = 0
                while chunk := response.read(1024 * 1024):
                    total += len(chunk)
                    if total > max_bytes:
                        raise CatalogImportError(
                            f"GBIF archive exceeded the configured {max_bytes} byte limit."
                        )
                    temporary.write(chunk)
        if not zipfile.is_zipfile(temp_path):
            raise CatalogImportError("GBIF download did not return a valid ZIP archive.")
        temp_path.replace(target)
    except (OSError, urllib.error.URLError):
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise
    except CatalogImportError:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise


def _request(
    url: str,
    *,
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> bytes:
    request = urllib.request.Request(url, data=data, headers=headers or {})
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code not in {429, 500, 502, 503, 504} or attempt == 3:
                raise CatalogImportError(
                    f"GBIF API request failed with HTTP {exc.code}."
                ) from exc
            retry_after = exc.headers.get("Retry-After")
            delay = _retry_delay(retry_after, attempt)
        except urllib.error.URLError as exc:
            last_error = exc
            if attempt == 3:
                raise CatalogImportError(f"GBIF API request failed: {exc.reason}") from exc
            delay = min(2**attempt, 30)
        time.sleep(delay)
    raise CatalogImportError(f"GBIF API request failed: {last_error}")


def _request_json(url: str) -> Any:
    try:
        return json.loads(_request(url).decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise CatalogImportError(f"GBIF returned invalid JSON: {exc}") from exc


def _metadata_for_download(download_key: str, metadata_dir: Path) -> dict[str, Any]:
    path = _metadata_path(metadata_dir, download_key)
    if not path.is_file():
        raise CatalogImportError(
            f"Request metadata not found for {download_key}: {path}. "
            "Use the request/download commands before staging."
        )
    metadata = _read_json(path)
    if metadata.get("download_key") != download_key:
        raise CatalogImportError(f"Download metadata does not match {download_key}.")
    return metadata


def _metadata_path(directory: Path, download_key: str) -> Path:
    return directory / f"{download_key}.json"


def _write_json(path: Path, content: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        temp_path.write_text(
            json.dumps(content, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temp_path.replace(path)
    except OSError:
        temp_path.unlink(missing_ok=True)
        raise


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CatalogImportError(f"Cannot read download metadata {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise CatalogImportError(f"Download metadata must be a JSON object: {path}")
    return value


def _taxon_key(value: str) -> str | None:
    value = value.strip()
    return value if value and value.isalnum() else None


def _nonnegative_int(value: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    return number if number >= 0 else 0


def _json_array(values: list[str]) -> str:
    return json.dumps(values, ensure_ascii=False, separators=(",", ":"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_download_key(download_key: str) -> None:
    if not re.fullmatch(r"[0-9]{3,}-[0-9]{12,}", download_key):
        raise ValueError("Invalid GBIF download key.")


def _basic_auth(username: str, password: str) -> str:
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def _retry_delay(retry_after: str | None, attempt: int) -> int:
    if retry_after:
        try:
            return min(max(int(retry_after), 1), 60)
        except ValueError:
            pass
    return min(2**attempt, 30)


def _positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if number <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


if __name__ == "__main__":
    sys.exit(main())
