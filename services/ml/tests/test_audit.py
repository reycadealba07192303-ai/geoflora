import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from geoflora_ml.datasets.audit import build_audit_report, record_review
from geoflora_ml.datasets.manifest import append_jsonl


class DatasetAuditTests(unittest.TestCase):
    def test_audit_reports_review_progress_and_remaining_targets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            raw_dir = data_dir / "raw" / "species_a"
            raw_dir.mkdir(parents=True)
            records = []
            for index in range(3):
                image_path = raw_dir / f"{index}.jpg"
                Image.new("RGB", (96, 96), color=(index * 60, 100, 130)).save(
                    image_path, format="JPEG"
                )
                records.append(
                    {
                        "source": "inaturalist",
                        "source_id": f"photo-{index}",
                        "observation_id": f"observation-{index}",
                        "group_id": f"inaturalist:observation:{index}",
                        "species_id": "species_a",
                        "license": "cc-by",
                        "attribution": "Contributor",
                        "sha256": hashlib.sha256(image_path.read_bytes()).hexdigest(),
                        "local_path": image_path.relative_to(data_dir).as_posix(),
                    }
                )
                append_jsonl(data_dir / "raw" / "manifest.jsonl", records[-1])

            record_review(
                data_dir,
                "inaturalist",
                "photo-0",
                "approved",
                "reviewer",
                "Species confirmed",
            )
            report = build_audit_report(data_dir, target_per_species=10)

            self.assertEqual(report["totals"]["valid_images"], 3)
            self.assertEqual(report["totals"]["approved_images"], 1)
            self.assertEqual(report["totals"]["pending_review"], 2)
            self.assertEqual(
                report["species"]["species_a"]["remaining_to_verified_target"], 9
            )
            self.assertFalse(report["external_training_data_included"])

    def test_audit_counts_flagged_duplicate_groups(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            image_dir = data_dir / "raw" / "images"
            image_dir.mkdir(parents=True)
            records = []
            for index in range(3):
                image_path = image_dir / f"{index}.jpg"
                if index == 2:
                    image_path.write_bytes(records[1]["image_bytes"])
                else:
                    Image.new("RGB", (96, 96), color=(index * 60, 100, 130)).save(
                        image_path, format="JPEG"
                    )
                image_bytes = image_path.read_bytes()
                record = {
                    "source": "inaturalist",
                    "source_id": f"photo-{index}",
                    "species_id": "chromolaena_odorata",
                    "license": "cc-by",
                    "attribution": "Contributor",
                    "sha256": hashlib.sha256(image_bytes).hexdigest(),
                    "local_path": image_path.relative_to(data_dir).as_posix(),
                }
                records.append({**record, "image_bytes": image_bytes})
                append_jsonl(data_dir / "raw" / "manifest.jsonl", record)
            record_review(
                data_dir,
                "inaturalist",
                "photo-2",
                "flagged",
                "reviewer",
                "Possible duplicate requiring review",
            )

            report = build_audit_report(data_dir, target_per_species=10)
            self.assertEqual(report["totals"]["flagged_review"], 1)
            self.assertGreaterEqual(report["totals"]["flagged_duplicate_groups"], 1)
