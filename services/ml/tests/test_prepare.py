import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from geoflora_ml.datasets.prepare import prepare_dataset
from geoflora_ml.datasets.audit import record_review


class DatasetPreparationTests(unittest.TestCase):
    def test_deduplicates_and_writes_grouped_splits(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "datasets"
            image_dir = data_dir / "raw" / "species_a"
            image_dir.mkdir(parents=True)
            records = []
            for index in range(3):
                image = image_dir / f"{index}.jpg"
                Image.new(
                    "RGB", (100, 100), color=(index * 50, 100, 150)
                ).save(image, format="JPEG")
                records.append(
                    {
                        "species_id": "species_a",
                        "source": "gbif",
                        "source_id": f"{index}:photo",
                        "group_id": f"gbif:occurrence:{index}",
                        "license": "cc-by",
                        "attribution": "Photographer",
                        "review_status": "approved",
                        "sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
                        "local_path": image.relative_to(data_dir).as_posix(),
                    }
                )
            records.append({**records[0], "source_id": "other:photo"})
            manifest = data_dir / "raw" / "manifest.jsonl"
            manifest.write_text(
                "".join(json.dumps(record) + "\n" for record in records),
                encoding="utf-8",
            )
            for record in records:
                record_review(
                    data_dir,
                    record["source"],
                    record["source_id"],
                    "approved",
                    "reviewer",
                    "Verified test label",
                )
            for index, decision in enumerate(("pending", "flagged", "rejected"), 3):
                image = image_dir / f"{index}.jpg"
                Image.new("RGB", (100, 100), color=(index * 30, 80, 130)).save(
                    image, format="JPEG"
                )
                record = {
                    **records[0],
                    "source_id": f"unreviewed:{index}",
                    "group_id": f"gbif:observation:unreviewed:{index}",
                    "sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
                    "local_path": image.relative_to(data_dir).as_posix(),
                }
                with manifest.open("a", encoding="utf-8") as manifest_file:
                    manifest_file.write(json.dumps(record) + "\n")
                if decision != "pending":
                    record_review(
                        data_dir,
                        record["source"],
                        record["source_id"],
                        decision,
                        "reviewer",
                        f"Test exclusion: {decision}",
                    )

            count, duplicates = prepare_dataset(
                manifest_path=manifest,
                data_dir=data_dir,
                output_dir=data_dir / "curated" / "v1",
                seed=42,
            )

            self.assertEqual((count, duplicates), (3, 1))
            with (data_dir / "curated" / "v1" / "manifest.csv").open(
                newline="", encoding="utf-8"
            ) as csv_file:
                prepared = list(csv.DictReader(csv_file))
            self.assertEqual(
                {record["split"] for record in prepared},
                {"train", "validation", "test"},
            )
