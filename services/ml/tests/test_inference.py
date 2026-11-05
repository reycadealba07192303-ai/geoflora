from __future__ import annotations

import io
import csv
import json
import math
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image

from geoflora_ml.inference.api import create_app
from geoflora_ml.inference.predictor import (
    InvalidImageError,
    PlantPredictor,
    decode_image,
)


class InferenceServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        # Other test modules load the project .env file; these route tests own their API-key scenarios explicitly.
        self.api_key_patch = patch.dict(os.environ, {"GEOFLORA_ML_API_KEY": ""})
        self.api_key_patch.start()

    def tearDown(self) -> None:
        self.api_key_patch.stop()

    def test_active_model_generates_real_normalized_embedding_from_a_field_photo(self) -> None:
        root = Path(__file__).resolve().parents[3]
        model_path = root / "storage/models/mobilenetv2.keras"
        mapping_path = root / "storage/models/class_mapping.json"
        metadata = json.loads((root / "storage/models/active_model.json").read_text(encoding="utf-8"))
        manifest = root / "storage/datasets/curated/v3/manifest.csv"
        if not model_path.is_file() or not mapping_path.is_file() or not manifest.is_file():
            self.skipTest("Local active model or curated v3 field photo is not installed")
        with manifest.open(encoding="utf-8-sig", newline="") as stream:
            row = next(item for item in csv.DictReader(stream) if item["split"] == "train")
        photo_path = root / "storage/datasets" / row["local_path"]
        if not photo_path.is_file():
            self.skipTest("Curated v3 fixture photo is unavailable")
        predictor = PlantPredictor(model_path=model_path, class_mapping_path=mapping_path)
        self.assertTrue(predictor.ready, predictor.unavailable_reason)
        vector = predictor.embed(photo_path.read_bytes())
        # Whatever model is active, the service must report the version and threshold recorded in active_model.json.
        self.assertEqual(predictor.model_version, metadata.get("candidate"))
        self.assertEqual(predictor.confidence_threshold, metadata.get("confidence_threshold"))
        self.assertEqual(len(vector), 1280)
        self.assertTrue(math.isclose(math.sqrt(sum(value * value for value in vector)), 1.0, abs_tol=1e-5))

    def test_embed_endpoint_returns_versioned_uncalibrated_features(self) -> None:
        class ReadyPredictor:
            ready = True
            model_version = "mobilenetv2_v3_seed42"
            embedding_version = "mobilenetv2_v3_seed42:backbone-output-v1"
            supported_species_count = 3
            species = []
            def embed(self, _image: bytes) -> list[float]:
                return [0.6, 0.8]

        image_bytes = io.BytesIO()
        Image.new("RGB", (80, 80), (20, 120, 30)).save(image_bytes, format="JPEG")
        with TestClient(create_app(ReadyPredictor())) as client:  # type: ignore[arg-type]
            response = client.post("/embed", files={"image": ("plant.jpg", image_bytes.getvalue(), "image/jpeg")})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"embedding": [0.6, 0.8], "embedding_version": "mobilenetv2_v3_seed42:backbone-output-v1", "score_type": "uncalibrated_cosine_similarity"})

    def test_embed_rejects_when_active_model_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            predictor = PlantPredictor(model_path=root / "missing.keras", class_mapping_path=root / "missing.json")
            with TestClient(create_app(predictor)) as client:
                response = client.post("/embed", files={"image": ("plant.jpg", b"not-processed", "image/jpeg")})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "The image identification model is unavailable. Please try again later.")

    def test_health_reports_missing_model_without_claiming_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            predictor = PlantPredictor(
                model_path=root / "missing.keras",
                class_mapping_path=root / "missing.json",
            )
            with TestClient(create_app(predictor)) as client:
                response = client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["ready"])
        self.assertEqual(response.json()["supported_species_count"], 0)
        self.assertIsNone(response.json()["model_version"])
        self.assertEqual(response.json()["reason"], "The image identification model is unavailable. Please try again later.")
        self.assertNotIn(directory, response.text)

    def test_reload_keeps_the_running_model_when_the_installed_one_cannot_load(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            running = PlantPredictor(model_path=root / "missing.keras", class_mapping_path=root / "missing.json")
            with patch.dict(os.environ, {"GEOFLORA_MODEL_PATH": str(root / "absent.keras"), "GEOFLORA_CLASS_MAPPING_PATH": str(root / "absent.json")}):
                app = create_app(running)
                with TestClient(app) as client:
                    response = client.post("/reload")

        self.assertEqual(response.status_code, 409)
        self.assertIn("No trained", response.json()["detail"])
        self.assertIs(app.state.predictor, running)

    def test_reload_refuses_callers_from_other_machines(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            running = PlantPredictor(model_path=root / "missing.keras", class_mapping_path=root / "missing.json")
            with TestClient(create_app(running), client=("192.168.1.20", 50000)) as client:
                response = client.post("/reload")

        self.assertEqual(response.status_code, 403)

    def test_reload_from_another_machine_needs_the_reload_token(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            running = PlantPredictor(model_path=root / "missing.keras", class_mapping_path=root / "missing.json")
            with patch.dict(os.environ, {"GEOFLORA_ML_RELOAD_TOKEN": "s3cret", "GEOFLORA_MODEL_PATH": str(root / "absent.keras"), "GEOFLORA_CLASS_MAPPING_PATH": str(root / "absent.json")}):
                with TestClient(create_app(running), client=("203.0.113.5", 50000)) as client:
                    wrong = client.post("/reload", headers={"X-GeoFlora-Reload": "guess"})
                    right = client.post("/reload", headers={"X-GeoFlora-Reload": "s3cret"})

        self.assertEqual(wrong.status_code, 403)
        self.assertEqual(right.status_code, 409)  # Allowed through; nothing installed to load.

    def test_service_key_is_required_when_configured(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            predictor = PlantPredictor(model_path=root / "missing.keras", class_mapping_path=root / "missing.json")
            with patch.dict(os.environ, {"GEOFLORA_ML_API_KEY": "k3y"}):
                with TestClient(create_app(predictor)) as client:
                    missing = client.get("/health")
                    wrong = client.get("/health", headers={"X-GeoFlora-Key": "nope"})
                    right = client.get("/health", headers={"X-GeoFlora-Key": "k3y"})
                    root_page = client.get("/")

        self.assertEqual((missing.status_code, wrong.status_code, right.status_code, root_page.status_code), (401, 401, 200, 200))
        self.assertEqual(right.json()["species"], [])

    def test_prediction_returns_service_unavailable_when_model_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            predictor = PlantPredictor(
                model_path=root / "missing.keras",
                class_mapping_path=root / "missing.json",
            )
            with TestClient(create_app(predictor)) as client:
                response = client.post(
                    "/predict",
                    files={"image": ("leaf.jpg", b"not-read-without-model", "image/jpeg")},
                )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "The image identification model is unavailable. Please try again later.")

    def test_prediction_rejects_unsupported_mime_type(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            predictor = PlantPredictor(
                model_path=root / "missing.keras",
                class_mapping_path=root / "missing.json",
            )
            with TestClient(create_app(predictor)) as client:
                response = client.post(
                    "/predict",
                    files={"image": ("leaf.gif", b"gif", "image/gif")},
                )

        self.assertEqual(response.status_code, 415)

    def test_decoder_rejects_unsupported_image_format(self) -> None:
        image_bytes = io.BytesIO()
        Image.new("RGB", (80, 80)).save(image_bytes, format="GIF")

        with self.assertRaisesRegex(InvalidImageError, "JPEG, PNG, or WebP"):
            decode_image(image_bytes.getvalue())

    def test_decoder_rejects_empty_upload(self) -> None:
        with self.assertRaisesRegex(InvalidImageError, "empty"):
            decode_image(b"")

    def test_installed_model_metadata_sets_version_and_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "models"
            root.mkdir()
            (root / "active_model.json").write_text(
                '{"candidate": "mobilenetv2_v3_seed42", "confidence_threshold": 0.8}', encoding="utf-8"
            )
            with patch.dict(os.environ, {"GEOFLORA_CONFIDENCE_THRESHOLD": ""}):
                installed = PlantPredictor(model_path=root / "mobilenetv2.keras", class_mapping_path=root / "missing.json")
            with patch.dict(os.environ, {"GEOFLORA_CONFIDENCE_THRESHOLD": "0.7"}):
                overridden = PlantPredictor(model_path=root / "mobilenetv2.keras", class_mapping_path=root / "missing.json")
            candidate = PlantPredictor(model_path=root / "candidates" / "v5_demo" / "mobilenetv2.keras", class_mapping_path=root / "missing.json", confidence_threshold=0.9)

        self.assertEqual(installed.confidence_threshold, 0.8)
        self.assertEqual(installed._version, "mobilenetv2_v3_seed42")
        self.assertEqual(overridden.confidence_threshold, 0.7)
        self.assertEqual(candidate._version, "v5_demo")
        self.assertEqual(candidate.confidence_threshold, 0.9)

    def test_installed_species_list_beside_the_model_is_used(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "models"
            root.mkdir()
            (root / "species.yaml").write_text("species:\n  - {id: nymphaea, scientific_name: Nymphaea, common_name: Water lily, role: lookalike}\n", encoding="utf-8")
            installed = PlantPredictor(model_path=root / "mobilenetv2.keras", class_mapping_path=root / "missing.json")
            bare = PlantPredictor(model_path=Path(directory) / "elsewhere" / "mobilenetv2.keras", class_mapping_path=root / "missing.json")

        self.assertEqual(installed.species_path, root / "species.yaml")
        self.assertIsNone(bare.species_path)


if __name__ == "__main__":
    unittest.main()
