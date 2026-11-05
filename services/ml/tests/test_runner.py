import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from geoflora_ml.collection.models import ImageCandidate
from geoflora_ml.collection.runner import collect_candidates


class CollectionRunnerTests(unittest.TestCase):
    def test_collects_local_candidate_and_writes_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_image = root / "source.png"
            Image.new("RGB", (100, 100), color="green").save(source_image, format="PNG")
            candidate = ImageCandidate(
                source="kaggle",
                source_id="image-1",
                group_id="kaggle:observation-1",
                species_id="chromolaena_odorata",
                scientific_name="Chromolaena odorata",
                image_url=source_image.as_uri(),
                source_url="https://example.org/dataset/image-1",
                license="cc-by",
                attribution="Photographer",
            )

            downloaded, rejected = collect_candidates(
                [candidate],
                data_dir=root / "datasets",
                max_images=1,
                source_name="test",
            )

            self.assertEqual((downloaded, rejected), (1, 0))
            manifest = root / "datasets" / "raw" / "manifest.jsonl"
            record = json.loads(manifest.read_text(encoding="utf-8").strip())
            self.assertEqual(record["group_id"], "kaggle:observation-1")
            self.assertEqual(record["license"], "cc-by")
            self.assertTrue((root / "datasets" / record["local_path"]).is_file())

    def test_skips_existing_source_record_when_resuming(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_image = root / "source.png"
            Image.new("RGB", (100, 100), color="green").save(source_image, format="PNG")
            candidate = ImageCandidate(
                source="kaggle",
                source_id="image-1",
                group_id="kaggle:observation-1",
                species_id="chromolaena_odorata",
                scientific_name="Chromolaena odorata",
                image_url=source_image.as_uri(),
                source_url="https://example.org/dataset/image-1",
                license="cc-by",
                attribution="Photographer",
            )
            data_dir = root / "datasets"
            first = collect_candidates([candidate], data_dir, None, "test")
            second = collect_candidates([candidate], data_dir, None, "test")

            manifest = data_dir / "raw" / "manifest.jsonl"
            records = manifest.read_text(encoding="utf-8").splitlines()
            self.assertEqual(first, (1, 0))
            self.assertEqual(second, (0, 0))
            self.assertEqual(len(records), 1)

    def test_records_duplicate_provenance_without_counting_duplicate_image(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_image = root / "source.png"
            Image.new("RGB", (100, 100), color="green").save(source_image, format="PNG")
            candidate_a = ImageCandidate(
                source="inaturalist",
                source_id="photo-a",
                group_id="inaturalist:observation:a",
                species_id="chromolaena_odorata",
                scientific_name="Chromolaena odorata",
                image_url=source_image.as_uri(),
                source_url="https://example.org/observation/a",
                license="cc-by",
                attribution="Photographer",
            )
            candidate_b = ImageCandidate(
                source="gbif",
                source_id="occurrence-b:photo-b",
                group_id="gbif:occurrence:occurrence-b",
                species_id="chromolaena_odorata",
                scientific_name="Chromolaena odorata",
                image_url=source_image.as_uri(),
                source_url="https://example.org/occurrence/b",
                license="cc-by",
                attribution="Photographer",
            )

            downloaded, rejected = collect_candidates(
                [candidate_a, candidate_b],
                root / "datasets",
                max_images=None,
                source_name="test",
            )

            manifest_path = root / "datasets" / "raw" / "manifest.jsonl"
            records = [
                json.loads(line)
                for line in manifest_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual((downloaded, rejected), (1, 0))
            self.assertEqual(len(records), 2)
            self.assertIn("duplicate_of_source_id", records[1])
