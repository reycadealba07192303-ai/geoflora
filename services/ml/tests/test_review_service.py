import csv
import hashlib
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from geoflora_ml.datasets.audit import record_review
from geoflora_ml.datasets.manifest import append_jsonl
from geoflora_ml.datasets.review_service import (
    export_approved_manifest,
    get_review_items,
)


class ReviewServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.data_dir = Path(self.temp_dir.name)
        raw_dir = self.data_dir / "raw"
        image_dir = raw_dir / "images"
        image_dir.mkdir(parents=True)
        self.records = []
        species = "chromolaena_odorata"
        for index in range(5):
            image_path = image_dir / f"{index}.jpg"
            color_index = 0 if index == 1 else index
            Image.new(
                "RGB", (96, 96), color=(color_index * 40, color_index * 25, 120)
            ).save(
                image_path, format="JPEG"
            )
            record = {
                "source": "inaturalist" if index < 3 else "gbif",
                "source_id": f"photo-{index}",
                "observation_id": f"observation-{index}",
                "species_id": species,
                "scientific_name": "Chromolaena odorata",
                "source_url": f"https://example.org/{index}",
                "image_url": "https://example.org/image.jpg",
                "license": "cc-by",
                "attribution": "Contributor",
                "group_id": f"source-group-{index}",
                "latitude": 14.5,
                "longitude": 121.0,
                "sha256": hashlib.sha256(image_path.read_bytes()).hexdigest(),
                "local_path": image_path.relative_to(self.data_dir).as_posix(),
            }
            append_jsonl(raw_dir / "manifest.jsonl", record)
            self.records.append(record)

    def test_filters_by_species_status_source_and_duplicate_group(self) -> None:
        record_review(
            self.data_dir,
            "inaturalist",
            "photo-0",
            "approved",
            "Reviewer",
            "Label confirmed",
        )
        record_review(
            self.data_dir,
            "inaturalist",
            "photo-1",
            "flagged",
            "Reviewer",
            "Needs expert confirmation",
        )
        result = get_review_items(
            self.data_dir,
            species_id="chromolaena_odorata",
            status="flagged",
            source="inaturalist",
            duplicate_group=f"exact:{self.records[0]['sha256'][:12]}",
        )
        self.assertEqual(result["total"], 1)
        item = result["items"][0]
        self.assertEqual(item["source_id"], "photo-1")
        self.assertEqual(item["observation_id"], "observation-1")
        self.assertEqual(item["review_status"], "flagged")
        self.assertEqual(item["duplicate_group_type"], "exact")
        self.assertEqual(len(item["review_history"]), 1)

    def test_relabel_updates_effective_label_and_export_contains_approved_only(self) -> None:
        record_review(
            self.data_dir,
            "inaturalist",
            "photo-0",
            "approved",
            "Reviewer",
            "Confirmed",
        )
        record_review(
            self.data_dir,
            "inaturalist",
            "photo-1",
            "rejected",
            "Reviewer",
            "Irrelevant image",
        )
        record_review(
            self.data_dir,
            "inaturalist",
            "photo-2",
            "flagged",
            "Reviewer",
            "Unsure of species",
        )
        record_review(
            self.data_dir,
            "gbif",
            "photo-3",
            "relabelled",
            "Reviewer",
            "Verified as Lantana",
            relabel_to="lantana_camara",
        )

        listed = get_review_items(self.data_dir, status="relabelled")
        self.assertEqual(listed["total"], 1)
        self.assertEqual(listed["items"][0]["species_id"], "lantana_camara")
        self.assertEqual(
            listed["items"][0]["original_species_id"], "chromolaena_odorata"
        )

        export_path = export_approved_manifest(self.data_dir)
        with export_path.open(newline="", encoding="utf-8") as export_file:
            exported = list(csv.DictReader(export_file))
        self.assertEqual(len(exported), 2)
        self.assertTrue(
            all(row["review_status"] in {"approved", "relabelled"} for row in exported)
        )
        self.assertIn("lantana_camara", {row["species_id"] for row in exported})

    def test_invalid_relabel_target_is_not_saved(self) -> None:
        with self.assertRaisesRegex(ValueError, "species in the GeoFlora catalog"):
            record_review(
                self.data_dir,
                "inaturalist",
                "photo-0",
                "relabelled",
                "Reviewer",
                "Correct label",
                relabel_to="not-a-species",
            )
