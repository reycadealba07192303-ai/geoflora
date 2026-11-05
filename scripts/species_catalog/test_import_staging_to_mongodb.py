from __future__ import annotations

import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from import_staging_to_mongodb import (
    MongoImportError,
    import_staging_file,
    load_staging_records,
    validate_local_mongodb_uri,
)


class FakeCollection:
    def __init__(self) -> None:
        self.documents: dict[str, dict[str, Any]] = {}
        self.indexes: list[tuple[Any, dict[str, Any]]] = []

    def create_index(self, keys: Any, **kwargs: Any) -> None:
        self.indexes.append((keys, kwargs))

    def bulk_write(self, operations: list[Any], ordered: bool = False) -> Any:
        inserted = 0
        matched = 0
        for operation in operations:
            document_id = operation._filter["_id"]
            if document_id in self.documents:
                self.documents[document_id].update(operation._doc["$set"])
                matched += 1
                continue
            update = dict(operation._doc["$set"])
            update.update(operation._doc["$setOnInsert"])
            self.documents[document_id] = update
            inserted += 1
        return SimpleNamespace(upserted_count=inserted, matched_count=matched)

    def update_one(
        self, query: dict[str, Any], update: dict[str, Any], upsert: bool = False
    ) -> None:
        document_id = query["_id"]
        if upsert and document_id not in self.documents:
            self.documents[document_id] = update["$setOnInsert"]


class FakeDatabase:
    name = "geoflora_test"

    def __init__(self) -> None:
        self.collections: dict[str, FakeCollection] = {}

    def __getitem__(self, name: str) -> FakeCollection:
        if name not in self.collections:
            self.collections[name] = FakeCollection()
        return self.collections[name]


class MongoStagingImportTests(unittest.TestCase):
    def make_staging_files(
        self, root: Path, ai_model_supported: str = "false"
    ) -> tuple[Path, Path]:
        csv_path = root / "sample_staging.csv"
        fields = [
            "source_dataset_title",
            "source_dataset_key",
            "source_doi",
            "source_citation",
            "source_license",
            "gbif_usage_key",
            "scientific_name",
            "canonical_name",
            "taxonomic_status",
            "rank",
            "kingdom",
            "family",
            "genus",
            "ecological_status",
            "catalog_review_status",
            "ai_model_supported",
        ]
        with csv_path.open("w", encoding="utf-8-sig", newline="") as output:
            writer = csv.DictWriter(output, fieldnames=fields)
            writer.writeheader()
            writer.writerow(
                {
                    "source_dataset_title": "Test flora checklist",
                    "source_dataset_key": "dataset-123",
                    "source_doi": "10.15468/example",
                    "source_citation": "Test citation",
                    "source_license": "CC BY 4.0",
                    "gbif_usage_key": "456",
                    "scientific_name": "Testus plantus",
                    "canonical_name": "Testus plantus",
                    "taxonomic_status": "ACCEPTED",
                    "rank": "SPECIES",
                    "kingdom": "Plantae",
                    "family": "Testaceae",
                    "genus": "Testus",
                    "ecological_status": "",
                    "catalog_review_status": "staged_pending_source_and_taxonomic_review",
                    "ai_model_supported": ai_model_supported,
                }
            )
        checksum = hashlib.sha256(csv_path.read_bytes()).hexdigest()
        provenance_path = root / "sample_provenance.json"
        provenance_path.write_text(
            json.dumps(
                {
                    "staging_csv_sha256": checksum,
                    "source_dataset": {
                        "title": "Test flora checklist",
                        "key": "dataset-123",
                        "doi": "10.15468/example",
                        "citation": "Test citation",
                    },
                }
            ),
            encoding="utf-8",
        )
        return csv_path, provenance_path

    def test_only_local_mongodb_uris_are_accepted(self) -> None:
        validate_local_mongodb_uri("mongodb://127.0.0.1:27017")
        validate_local_mongodb_uri("mongodb://user:pass@localhost:27017/geoflora")
        with self.assertRaises(ValueError):
            validate_local_mongodb_uri("mongodb://example.com:27017/geoflora")
        with self.assertRaises(ValueError):
            validate_local_mongodb_uri("mongodb+srv://cluster.example/geoflora")

    def test_loads_provenance_verified_pending_records(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            csv_path, _ = self.make_staging_files(root)

            rows, provenance, checksum = load_staging_records(csv_path, root)

        self.assertEqual(len(rows), 1)
        self.assertEqual(provenance["source_dataset"]["key"], "dataset-123")
        self.assertEqual(len(checksum), 64)

    def test_rejects_records_without_pending_review_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            csv_path, _ = self.make_staging_files(root, ai_model_supported="true")

            with self.assertRaises(MongoImportError):
                load_staging_records(csv_path, root)

    def test_import_is_idempotent_and_keeps_records_unverified(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            csv_path, _ = self.make_staging_files(root)
            database = FakeDatabase()
            import_id = (
                "gbif:dataset-123:"
                + hashlib.sha256(csv_path.read_bytes()).hexdigest()
            )

            first = import_staging_file(database, csv_path, root, batch_size=1)
            second = import_staging_file(database, csv_path, root, batch_size=1)

            documents = database["species_catalog_staging"].documents
            document = next(iter(documents.values()))

        self.assertEqual(first["inserted_this_run"], 1)
        self.assertEqual(second["inserted_this_run"], 0)
        self.assertEqual(second["already_present"], 1)
        self.assertEqual(document["catalog_review_status"], "pending")
        self.assertFalse(document["ecological_status_is_verified"])
        self.assertFalse(document["ai_model_supported"])
        self.assertEqual(document["source"]["doi"], "10.15468/example")
        self.assertEqual(document["source"]["provenance_file"], "sample_provenance.json")
        self.assertEqual(
            database["catalog_imports"].documents.keys(),
            {import_id},
        )

    def test_rejects_csv_modified_after_provenance_was_created(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            csv_path, _ = self.make_staging_files(root)
            with csv_path.open("a", encoding="utf-8") as output:
                output.write("\n")

            with self.assertRaises(MongoImportError):
                load_staging_records(csv_path, root)


if __name__ == "__main__":
    unittest.main()
