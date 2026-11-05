from __future__ import annotations

import csv
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from gbif_species_list import (
    CatalogImportError,
    _curate_rows,
    _read_species_list,
    stage_archive,
    stage_species_list_file,
)


HEADERS = [
    "taxonKey",
    "scientificName",
    "acceptedTaxonKey",
    "acceptedScientificName",
    "numberOfOccurrences",
    "taxonRank",
    "taxonomicStatus",
    "kingdom",
    "family",
    "genus",
    "species",
    "speciesKey",
    "iucnRedListCategory",
]


def species_row(
    taxon_key: str,
    scientific_name: str,
    accepted_key: str,
    accepted_name: str,
    *,
    status: str = "ACCEPTED",
    kingdom: str = "Plantae",
    rank: str = "SPECIES",
    count: str = "1",
) -> dict[str, str]:
    return {
        "taxonkey": taxon_key,
        "scientificname": scientific_name,
        "acceptedtaxonkey": accepted_key,
        "acceptedscientificname": accepted_name,
        "numberofoccurrences": count,
        "taxonrank": rank,
        "taxonomicstatus": status,
        "kingdom": kingdom,
        "family": "Asteraceae",
        "genus": "Chromolaena",
        "species": accepted_name,
        "specieskey": accepted_key,
        "iucnredlistcategory": "",
    }


class GBIFSpeciesListTests(unittest.TestCase):
    def make_archive(
        self,
        archive_path: Path,
        rows: list[dict[str, str]],
        member_name: str = "species.txt",
    ) -> None:
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zipped:
            content = []
            from io import StringIO

            text = StringIO()
            writer = csv.DictWriter(text, fieldnames=HEADERS, delimiter="\t")
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {
                        header: row.get(header.casefold(), "")
                        for header in HEADERS
                    }
                )
            content.append(text.getvalue())
            zipped.writestr(member_name, content[0])

    def test_curate_merges_synonyms_by_accepted_taxon_key(self) -> None:
        rows = [
            species_row(
                "100", "Old name auct.", "10", "Accepted species A",
                status="SYNONYM", count="4",
            ),
            species_row(
                "10", "Accepted species A", "10", "Accepted species A",
                status="ACCEPTED", count="6",
            ),
            species_row(
                "200", "Accepted species B", "200", "Accepted species B",
                count="3",
            ),
            species_row(
                "300", "Animal species", "300", "Animal species",
                kingdom="Animalia",
            ),
            species_row(
                "400", "Genus sp.", "400", "Genus sp.", rank="GENUS",
            ),
            species_row(
                "500", "Unresolved species", "", "", status="DOUBTFUL",
            ),
            species_row(
                "600", "Doubtful name", "600", "Doubtful accepted name",
                status="DOUBTFUL",
            ),
            species_row(
                "700", "Unknown kingdom plant", "700", "Unknown kingdom plant",
                kingdom="",
            ),
        ]

        curated, audit = _curate_rows(rows)

        self.assertEqual([item["accepted_taxon_key"] for item in curated], ["10", "200"])
        self.assertEqual(curated[0]["source_usage_count"], "2")
        self.assertEqual(curated[0]["source_occurrence_count"], "10")
        self.assertEqual(json.loads(curated[0]["source_taxonomic_statuses"]), ["ACCEPTED", "SYNONYM"])
        usages = json.loads(curated[0]["source_usage_details"])
        self.assertEqual(
            sorted(usage["occurrence_count"] for usage in usages), [4, 6]
        )
        self.assertEqual(audit["source_rows_total"], 8)
        self.assertEqual(audit["non_plant_rows_rejected"], 1)
        self.assertEqual(audit["missing_kingdom_rows"], 1)
        self.assertEqual(audit["species_rank_plant_rows"], 5)
        self.assertEqual(audit["source_name_usages_reconciled_to_accepted_taxa"], 1)
        self.assertEqual(audit["unresolved_rows"], 4)
        self.assertEqual(
            audit["taxonomic_status_usage_counts_species_rank"]["DOUBTFUL"], 2
        )

    def test_conflicting_names_for_same_accepted_key_are_not_merged(self) -> None:
        rows = [
            species_row("10", "Name one", "10", "Accepted name one"),
            species_row("11", "Name two", "10", "Different accepted name"),
        ]

        curated, audit = _curate_rows(rows)

        self.assertEqual(curated, [])
        self.assertEqual(audit["taxonomy_conflict_groups_rejected"], 1)
        self.assertEqual(audit["unresolved_rows_by_reason"]["conflicting_taxonomy_for_accepted_key"], 2)

    def test_same_accepted_name_under_different_keys_is_flagged_not_merged(self) -> None:
        shared_name = "Duplicate accepted name"
        curated, audit = _curate_rows(
            [
                species_row("10", shared_name, "10", shared_name),
                species_row("20", shared_name, "20", shared_name),
            ]
        )

        self.assertEqual(curated, [])
        self.assertEqual(audit["accepted_name_collision_groups"], 1)
        self.assertEqual(audit["accepted_name_collision_taxon_keys"], 2)
        self.assertEqual(
            audit["unresolved_rows_by_reason"][
                "accepted_scientific_name_collision_across_taxon_keys"
            ],
            2,
        )

    def test_reads_species_list_tsv_from_zip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            archive = Path(temp_dir) / "download.zip"
            self.make_archive(
                archive,
                [species_row("10", "Accepted species A", "10", "Accepted species A")],
            )

            rows = _read_species_list(archive)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["acceptedtaxonkey"], "10")
        self.assertEqual(rows[0]["kingdom"], "Plantae")

    def test_accepts_alphanumeric_gbif_taxon_keys(self) -> None:
        curated, _ = _curate_rows(
            [
                species_row(
                    "VXC6",
                    "Cleistanthus vestitus Jabl.",
                    "VXC6",
                    "Cleistanthus vestitus Jabl.",
                )
            ]
        )
        self.assertEqual(curated[0]["accepted_taxon_key"], "VXC6")

    def test_stages_supplied_species_list_csv_with_download_doi(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_file = root / "0038372-260928105237408.csv"
            source_rows = [
                species_row(
                    "VXC6",
                    "Cleistanthus vestitus Jabl.",
                    "VXC6",
                    "Cleistanthus vestitus Jabl.",
                ),
                species_row(
                    "8WHTY",
                    "Monophrynium K.Schum.",
                    "8W2CX",
                    "Phrynium Willd.",
                    status="SYNONYM",
                    rank="GENUS",
                ),
                species_row(
                    "7G5Z2",
                    "Waltheria americana L.",
                    "7G5QT",
                    "Waltheria indica L.",
                    status="SYNONYM",
                ),
            ]
            with source_file.open("w", encoding="utf-8-sig", newline="") as output:
                writer = csv.DictWriter(output, fieldnames=HEADERS, delimiter="\t")
                writer.writeheader()
                writer.writerows(
                    {
                        header: row.get(header.casefold(), "")
                        for header in HEADERS
                    }
                    for row in source_rows
                )

            csv_path, audit_path = stage_species_list_file(
                input_file=source_file,
                download_key="0038372-260928105237408",
                source_doi="10.15468/dl.r3a2uq",
                citation=(
                    "GBIF.org (21 October 2026) GBIF Occurrence Download "
                    "https://doi.org/10.15468/dl.r3a2uq"
                ),
                source_record_count=3,
                output_dir=root / "staging",
                limit=100,
                metadata_dir=root / "no-metadata",
            )

            with csv_path.open(encoding="utf-8-sig", newline="") as manifest:
                staged = list(csv.DictReader(manifest))
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
            provenance = json.loads(
                csv_path.with_name(
                    csv_path.stem.replace("_staging", "_provenance") + ".json"
                ).read_text(encoding="utf-8")
            )
            unresolved_path = csv_path.with_name(
                csv_path.name.replace("_staging.csv", "_unresolved.csv")
            )
            with unresolved_path.open(encoding="utf-8-sig", newline="") as unresolved:
                flagged = list(csv.DictReader(unresolved))

        self.assertEqual(len(staged), 2)
        self.assertEqual(staged[0]["accepted_taxon_key"], "7G5QT")
        self.assertEqual(staged[1]["accepted_taxon_key"], "VXC6")
        self.assertEqual(staged[0]["source_download_doi"], "10.15468/dl.r3a2uq")
        self.assertEqual(audit["source_rows_read"], 3)
        self.assertEqual(audit["download_reported_record_count"], 3)
        self.assertEqual(audit["unique_accepted_species_available"], 2)
        self.assertEqual(audit["unresolved_records_rows"], 1)
        self.assertEqual(flagged[0]["review_flag"], "not_species_rank")
        self.assertEqual(
            json.loads(staged[0]["source_usage_details"])[0]["source_taxon_key"],
            "7G5Z2",
        )
        self.assertFalse(audit["is_sample"])
        self.assertEqual(provenance["source_dataset"]["doi"], "10.15468/dl.r3a2uq")

    def test_stages_species_list_zip_without_extracting_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive = root / "download.zip"
            self.make_archive(
                archive,
                [
                    species_row(
                        "VXC6",
                        "Cleistanthus vestitus Jabl.",
                        "VXC6",
                        "Cleistanthus vestitus Jabl.",
                    )
                ],
            )

            csv_path, audit_path = stage_species_list_file(
                input_file=archive,
                download_key="0038372-260928105237408",
                source_doi="10.15468/dl.r3a2uq",
                citation="GBIF.org occurrence download",
                source_record_count=1,
                output_dir=root / "staging",
                metadata_dir=root / "no-metadata",
            )

            with csv_path.open(encoding="utf-8-sig", newline="") as manifest:
                staged = list(csv.DictReader(manifest))
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
            self.assertEqual(len(staged), 1)
            self.assertEqual(audit["source_file"], archive.name)
            self.assertEqual(audit["source_rows_read"], 1)

    def test_rejects_archive_without_species_list_columns(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            archive = Path(temp_dir) / "invalid.zip"
            with zipfile.ZipFile(archive, "w") as zipped:
                zipped.writestr("occurrence.txt", "gbifID\tcountryCode\n1\tPH\n")

            with self.assertRaises(CatalogImportError):
                _read_species_list(archive)

    def test_stage_archive_caps_sample_and_records_source_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive = root / "download.zip"
            self.make_archive(
                archive,
                [
                    species_row("10", "Species A", "10", "Species A"),
                    species_row("20", "Species B", "20", "Species B"),
                ],
            )
            downloads = root / "downloads"
            downloads.mkdir()
            (downloads / "0001-1234567890123.json").write_text(
                json.dumps(
                    {
                        "download_key": "0001-1234567890123",
                        "doi": "10.15468/example",
                        "citation": "GBIF occurrence download citation",
                        "format": "SPECIES_LIST",
                        "country": "PH",
                        "kingdom": "Plantae",
                    }
                ),
                encoding="utf-8",
            )
            output_dir = root / "staging"

            csv_path, audit_path = stage_archive(
                archive,
                "0001-1234567890123",
                output_dir,
                limit=1,
                metadata_dir=downloads,
            )

            with csv_path.open(encoding="utf-8-sig", newline="") as manifest:
                staged = list(csv.DictReader(manifest))
            audit = json.loads(audit_path.read_text(encoding="utf-8"))

        self.assertEqual(len(staged), 1)
        self.assertEqual(staged[0]["source_download_doi"], "10.15468/example")
        self.assertEqual(staged[0]["catalog_review_status"], "staged_pending_taxonomic_and_source_review")
        self.assertEqual(staged[0]["ecological_status"], "")
        self.assertEqual(staged[0]["ai_model_supported"], "false")
        self.assertEqual(audit["unique_accepted_species_available"], 2)
        self.assertEqual(audit["staged_accepted_species"], 1)
        self.assertTrue(audit["is_sample"])
        self.assertEqual(audit["source_doi"], "10.15468/example")


if __name__ == "__main__":
    unittest.main()
