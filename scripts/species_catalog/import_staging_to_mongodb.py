from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pymongo import MongoClient, UpdateOne
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import PyMongoError


LOGGER = logging.getLogger("geoflora.species_catalog.mongodb")
ROOT = Path(__file__).resolve().parents[2]
# Credentials and settings come from apps/web/.env.local (see services/ml/src/geoflora_ml/env.py).
sys.path.insert(0, str(ROOT / "services/ml/src"))
from geoflora_ml.env import load_env  # noqa: E402

load_env()
DEFAULT_STAGING_DIR = ROOT / "storage" / "species_catalog" / "staging"
DEFAULT_URI = "mongodb://127.0.0.1:27017"
DEFAULT_DATABASE = "geoflora"
STAGING_COLLECTION = "species_catalog_staging"
IMPORT_COLLECTION = "catalog_imports"


class MongoImportError(RuntimeError):
    pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Import review-required species catalog staging CSV records "
            "into the local GeoFlora MongoDB database."
        )
    )
    parser.add_argument(
        "csv_files",
        nargs="*",
        type=Path,
        help="Staging CSVs (defaults to all supported staging CSVs)",
    )
    parser.add_argument(
        "--provenance-dir",
        type=Path,
        default=DEFAULT_STAGING_DIR,
        help="Directory containing each CSV's provenance JSON",
    )
    parser.add_argument(
        "--uri",
        default=os.environ.get("GEOFLORA_MONGODB_URI", DEFAULT_URI),
        help="MongoDB URI; must point to localhost",
    )
    parser.add_argument(
        "--database",
        default=os.environ.get("GEOFLORA_MONGODB_DATABASE", DEFAULT_DATABASE),
        help="Local GeoFlora database name",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate files and report planned records without writing to MongoDB",
    )
    parser.add_argument(
        "--batch-size",
        type=_positive_int,
        default=500,
        help="Maximum records per MongoDB bulk write (default: 500)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    args = build_parser().parse_args(argv)
    try:
        paths = args.csv_files or default_staging_files(args.provenance_dir)
        if args.dry_run:
            for path in paths:
                records, provenance, checksum = load_staging_records(
                    path, args.provenance_dir
                )
                print(
                    json.dumps(
                        {
                            "file": str(path),
                            "records": len(records),
                            "sha256": checksum,
                            "source": _source_info(
                                provenance, _provenance_filename(path)
                            ).get("title"),
                            "write": False,
                        },
                        ensure_ascii=False,
                    )
                )
            return 0

        validate_local_mongodb_uri(args.uri)
        with MongoClient(
            args.uri,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000,
            appname="GeoFloraSpeciesCatalogStaging",
        ) as client:
            client.admin.command("ping")
            database = client[args.database]
            ensure_indexes(database)
            for path in paths:
                summary = import_staging_file(
                    database, path, args.provenance_dir, args.batch_size
                )
                print(json.dumps(summary, ensure_ascii=False))
        return 0
    except (MongoImportError, OSError, ValueError) as exc:
        LOGGER.error("%s", exc)
        return 1
    except PyMongoError as exc:
        LOGGER.error("MongoDB operation failed: %s", exc)
        return 1


def default_staging_files(provenance_dir: Path) -> list[Path]:
    names = (
        "malnaf_v1_philippines_staging.csv",
        "gbif_philippine_regional_flora_staging.csv",
        "griis_philippines_plant_staging.csv",
    )
    paths = [provenance_dir / name for name in names]
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "Default staging CSVs are missing: " + ", ".join(missing)
        )
    return paths


def load_staging_records(
    csv_path: Path, provenance_dir: Path
) -> tuple[list[dict[str, str]], dict[str, Any], str]:
    csv_path = csv_path.expanduser().resolve()
    if not csv_path.is_file():
        raise FileNotFoundError(f"Staging CSV not found: {csv_path}")
    provenance_path = provenance_dir.expanduser().resolve() / (
        csv_path.stem.replace("_staging", "_provenance") + ".json"
    )
    if not provenance_path.is_file():
        raise MongoImportError(f"Provenance sidecar not found: {provenance_path}")
    try:
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MongoImportError(f"Invalid provenance JSON {provenance_path}: {exc}") from exc
    if not isinstance(provenance, dict):
        raise MongoImportError(f"Provenance sidecar must be a JSON object: {provenance_path}")

    checksum = _sha256(csv_path)
    expected_checksum = provenance.get("staging_csv_sha256")
    if expected_checksum and checksum != expected_checksum:
        raise MongoImportError(
            f"Staging CSV checksum does not match provenance: {csv_path}"
        )
    expected_name = provenance.get("output_csv")
    if expected_name and Path(expected_name).name != csv_path.name:
        raise MongoImportError(
            f"Staging CSV does not match provenance output_csv: {expected_name}"
        )

    try:
        with csv_path.open(encoding="utf-8-sig", newline="") as source:
            reader = csv.DictReader(source)
            if not reader.fieldnames:
                raise MongoImportError(f"CSV has no header: {csv_path}")
            records = [
                {
                    str(key): (value or "").strip()
                    for key, value in row.items()
                    if key is not None
                }
                for row in reader
            ]
    except csv.Error as exc:
        raise MongoImportError(f"Cannot parse staging CSV {csv_path}: {exc}") from exc
    if not records:
        raise MongoImportError(f"Staging CSV contains no records: {csv_path}")

    _validate_staging_records(records, csv_path)
    return records, provenance, checksum


def _validate_staging_records(records: list[dict[str, str]], csv_path: Path) -> None:
    seen_ids: set[str] = set()
    for row_number, record in enumerate(records, start=2):
        record_id = _source_record_id(record)
        if not record_id:
            raise MongoImportError(
                f"Missing stable source record key at {csv_path}:{row_number}"
            )
        if record_id in seen_ids:
            raise MongoImportError(
                f"Duplicate source record key {record_id!r} at {csv_path}:{row_number}"
            )
        seen_ids.add(record_id)

        review_status = record.get("catalog_review_status", "").casefold()
        if not review_status.startswith("staged_pending"):
            raise MongoImportError(
                f"Refusing non-pending catalog record at {csv_path}:{row_number}"
            )
        ai_supported = record.get("ai_model_supported", "").casefold()
        if ai_supported not in {"false", "0", "no"}:
            raise MongoImportError(
                f"Refusing AI-supported catalog record at {csv_path}:{row_number}"
            )


def ensure_indexes(database: Database[Any]) -> None:
    collection = database[STAGING_COLLECTION]
    collection.create_index(
        [("source_key", 1), ("source_record_key", 1)],
        unique=True,
        name="uq_source_record",
    )
    collection.create_index(
        [("catalog_review_status", 1), ("scientific_name_normalized", 1)],
        name="ix_review_status_scientific_name",
    )
    collection.create_index(
        [("taxonomic_identifiers.gbif_backbone_key", 1)],
        sparse=True,
        name="ix_gbif_backbone_key",
    )


def import_staging_file(
    database: Database[Any],
    csv_path: Path,
    provenance_dir: Path,
    batch_size: int = 500,
) -> dict[str, Any]:
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    records, provenance, checksum = load_staging_records(csv_path, provenance_dir)
    collection: Collection[Any] = database[STAGING_COLLECTION]
    imports: Collection[Any] = database[IMPORT_COLLECTION]
    provenance_filename = _provenance_filename(csv_path)
    source_info = _source_info(provenance, provenance_filename)
    operations: list[UpdateOne] = []
    ids: list[str] = []
    for record in records:
        source_key = _source_key(record, source_info)
        source_record_key = _source_record_id(record)
        document_id = f"{source_key}:{source_record_key}"
        ids.append(document_id)
        document = _staging_document(
            document_id, source_key, source_record_key, record, source_info, provenance
        )
        insert_only_fields = {
            "_id",
            "schema_version",
            "catalog_review_status",
            "ecological_status_is_verified",
            "ai_model_supported",
            "created_at",
            "review_events",
        }
        operations.append(
            UpdateOne(
                {"_id": document_id},
                {
                    "$set": {
                        key: value
                        for key, value in document.items()
                        if key not in insert_only_fields
                    },
                    "$setOnInsert": {
                        key: value
                        for key, value in document.items()
                        if key in insert_only_fields
                    },
                },
                upsert=True,
            )
        )

    inserted = 0
    matched = 0
    for start in range(0, len(operations), batch_size):
        result = collection.bulk_write(
            operations[start : start + batch_size],
            ordered=False,
        )
        inserted += result.upserted_count
        matched += result.matched_count

    import_id = f"{source_info['source_key']}:{checksum}"
    import_audit = {
        "_id": import_id,
        "source_key": source_info["source_key"],
        "source_title": source_info.get("title"),
        "source_doi": source_info.get("doi"),
        "provenance_file": provenance_filename,
        "staging_file": csv_path.name,
        "staging_sha256": checksum,
        "records_in_file": len(records),
        "catalog_records": len(ids),
        "inserted_records": inserted,
        "already_present_records": matched,
        "catalog_collection": STAGING_COLLECTION,
        "review_policy": "all records remain pending human and taxonomic review",
        "ai_model_supported": False,
        "imported_at_utc": datetime.now(timezone.utc),
    }
    imports.update_one(
        {"_id": import_id},
        {"$setOnInsert": import_audit},
        upsert=True,
    )
    return {
        "source": source_info.get("title") or source_info["source_key"],
        "source_key": source_info["source_key"],
        "staging_file": csv_path.name,
        "records_in_file": len(records),
        "inserted_this_run": inserted,
        "already_present": matched,
        "database": database.name,
        "collection": STAGING_COLLECTION,
        "ai_model_supported": 0,
        "review_status": "pending",
    }


def _staging_document(
    document_id: str,
    source_key: str,
    source_record_key: str,
    record: dict[str, str],
    source_info: dict[str, Any],
    provenance: dict[str, Any],
) -> dict[str, Any]:
    scientific_name = (
        record.get("accepted_scientific_name")
        or record.get("accepted_name")
        or record.get("canonical_name")
        or record.get("scientific_name")
        or record.get("accepted_binomial")
        or ""
    ).strip()
    if not scientific_name:
        raise MongoImportError(
            f"Missing scientific name for staged source record {source_record_key}"
        )
    taxonomic_identifiers = {
        field: record[field]
        for field in (
            "accepted_taxon_key",
            "taxonomic_identifier",
            "gbif_usage_key",
            "gbif_backbone_key",
            "species_key",
            "source_taxon_id",
        )
        if record.get(field)
    }
    source_meta: dict[str, Any] = {
        "key": source_key,
        "title": record.get("source_dataset_title") or source_info.get("title"),
        "doi": (
            record.get("source_doi")
            or record.get("dataset_doi")
            or source_info.get("doi")
        ),
        "citation": (
            record.get("source_citation")
            or record.get("dataset_citation")
            or source_info.get("citation")
        ),
        "license": record.get("source_license") or record.get("dataset_license"),
        "version": record.get("source_dataset_version") or record.get("dataset_version"),
        "provenance_file": (
            source_info.get("provenance_file")
        ),
    }
    source_ecological_status = (
        record.get("ecological_status") or record.get("source_status") or ""
    )
    return {
        "_id": document_id,
        "schema_version": 1,
        "source_key": source_key,
        "source_record_key": source_record_key,
        "scientific_name": scientific_name,
        "scientific_name_normalized": scientific_name.casefold(),
        "family": record.get("family") or "",
        "genus": record.get("genus") or "",
        "taxonomic_identifiers": taxonomic_identifiers,
        "source_taxonomic_status": (
            record.get("source_taxonomic_status")
            or record.get("taxonomic_status")
            or ""
        ),
        "source_ecological_status": source_ecological_status,
        "ecological_status_is_verified": False,
        "geographic_context": (
            record.get("geographic_context")
            or record.get("geographic_scope")
            or record.get("source_country")
            or "Philippines"
        ),
        "source": source_meta,
        "source_record": record,
        "source_provenance": {
            "file": source_info.get("provenance_file"),
            "download_doi": provenance.get("source_doi"),
        },
        "catalog_review_status": "pending",
        "ai_model_supported": False,
        "created_at": datetime.now(timezone.utc),
        "review_events": [],
    }


def _source_info(
    provenance: dict[str, Any], provenance_file: str
) -> dict[str, Any]:
    datasets = provenance.get("source_datasets")
    if isinstance(datasets, list) and datasets:
        first = datasets[0]
        return {
            "source_key": "gbif-regional-checklists",
            "title": "GBIF Philippine regional flora checklists",
            "doi": None,
            "citation": None,
            "provenance_file": provenance_file,
        }
    source = provenance.get("source_dataset")
    if isinstance(source, dict):
        return {
            "source_key": f"gbif:{source.get('key', 'unknown')}",
            "title": source.get("title"),
            "doi": source.get("doi"),
            "citation": source.get("citation"),
            "provenance_file": provenance_file,
        }
    if provenance.get("source_doi"):
        return {
            "source_key": f"malnaf:{provenance['source_doi']}",
            "title": provenance.get("source_publication"),
            "doi": provenance.get("source_doi"),
            "citation": provenance.get("attribution"),
            "provenance_file": provenance_file,
        }
    raise MongoImportError("Unrecognized source provenance format.")


def _source_key(record: dict[str, str], source_info: dict[str, Any]) -> str:
    dataset_key = record.get("source_dataset_key")
    if dataset_key:
        return f"gbif:{dataset_key}"
    download_key = record.get("source_download_key")
    if download_key:
        return f"gbif-download:{download_key}"
    return str(source_info["source_key"])


def _source_record_id(record: dict[str, str]) -> str:
    for field in (
        "gbif_usage_key",
        "staging_id",
        "accepted_taxon_key",
        "gbif_backbone_key",
        "species_key",
    ):
        value = record.get(field, "").strip()
        if value:
            return f"{field}:{value}"
    return ""


def _provenance_filename(csv_path: Path) -> str:
    return csv_path.stem.replace("_staging", "_provenance") + ".json"


def validate_local_mongodb_uri(uri: str) -> None:
    parsed = urlparse(uri)
    if parsed.scheme not in {"mongodb", "mongodb+srv"}:
        raise ValueError("MongoDB URI must use mongodb:// or mongodb+srv://")
    if parsed.scheme == "mongodb+srv":
        raise ValueError("Use a direct localhost MongoDB URI for local development.")
    hosts = parsed.netloc.rsplit("@", 1)[-1].split(",")
    for host in hosts:
        hostname = host.rsplit(":", 1)[0].strip("[]").casefold()
        if hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError(
                "Local catalog staging is restricted to localhost MongoDB. "
                "Remote MongoDB URIs are not accepted."
            )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
