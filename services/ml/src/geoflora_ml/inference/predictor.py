from __future__ import annotations

import json
import io
import logging
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, UnidentifiedImageError

from geoflora_ml.config import DEFAULT_DATA_DIR, load_species
from geoflora_ml.inference.preprocess import preprocess_rgb_batch, rgb_array

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
SUPPORTED_FORMATS = {"JPEG", "PNG", "WEBP"}
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
LOGGER = logging.getLogger(__name__)


class InvalidImageError(ValueError):
    """Raised when an uploaded plant photo is invalid or unsafe."""


class ModelUnavailableError(RuntimeError):
    """Raised when no valid trained classifier artifact is installed."""


@dataclass(frozen=True)
class SpeciesClass:
    id: str
    scientific_name: str
    common_name: str
    role: str = "invasive"


@dataclass(frozen=True)
class Prediction:
    status: str
    species: SpeciesClass | None
    confidence: float
    confidence_threshold: float
    candidates: list[dict[str, Any]]
    model_version: str


def decode_image(image_bytes: bytes) -> np.ndarray:
    if not image_bytes:
        raise InvalidImageError("Image is empty.")
    if len(image_bytes) > MAX_UPLOAD_BYTES:
        raise InvalidImageError("Image exceeds the 20 MB upload limit.")

    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            if image.format not in SUPPORTED_FORMATS:
                raise InvalidImageError("Use a JPEG, PNG, or WebP image.")
            if image.width < 64 or image.height < 64:
                raise InvalidImageError("Image dimensions must be at least 64 by 64 pixels.")
            if image.width * image.height > MAX_IMAGE_PIXELS:
                raise InvalidImageError("Image dimensions exceed the supported limit.")
            image.verify()
        with Image.open(io.BytesIO(image_bytes)) as image:
            pixels = rgb_array(image)
    except InvalidImageError:
        raise
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise InvalidImageError("Image could not be safely decoded.") from exc

    try:
        return preprocess_rgb_batch(pixels)
    except RuntimeError as exc:
        raise ModelUnavailableError(str(exc)) from exc


def default_model_path() -> Path:
    return Path(
        os.environ.get(
            "GEOFLORA_MODEL_PATH",
            str(DEFAULT_DATA_DIR.parent / "models" / "mobilenetv2.keras"),
        )
    ).expanduser()


def default_class_mapping_path() -> Path:
    return Path(
        os.environ.get(
            "GEOFLORA_CLASS_MAPPING_PATH",
            str(DEFAULT_DATA_DIR.parent / "models" / "class_mapping.json"),
        )
    ).expanduser()


def read_active_metadata(model_path: Path) -> dict[str, Any]:
    """Owner-maintained active_model.json beside an installed model; empty when absent or invalid."""
    path = model_path.parent / "active_model.json"
    try:
        content = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return content if isinstance(content, dict) else {}


class PlantPredictor:
    def __init__(
        self,
        model_path: Path | None = None,
        class_mapping_path: Path | None = None,
        confidence_threshold: float | None = None,
        species_path: Path | None = None,
    ) -> None:
        self.model_path = model_path or default_model_path()
        self.class_mapping_path = class_mapping_path or default_class_mapping_path()
        # An installed model may carry its own served-species list (written by automatic promotion); otherwise the
        # packaged species.yaml applies.
        installed = self.model_path.parent / "species.yaml"
        self.species_path = species_path if species_path is not None else installed if installed.is_file() else None
        metadata = read_active_metadata(self.model_path)
        # Precedence: explicit argument, environment, the installed model's validation-selected value, default.
        self.confidence_threshold = (
            confidence_threshold
            if confidence_threshold is not None
            else float(os.environ.get("GEOFLORA_CONFIDENCE_THRESHOLD") or metadata.get("confidence_threshold") or 0.65)
        )
        candidate = metadata.get("candidate")
        self._version = (
            candidate if isinstance(candidate, str) and candidate
            else self.model_path.parent.name if self.model_path.parent.name != "models"
            else self.model_path.stem
        )
        if not 0 < self.confidence_threshold <= 1:
            raise ValueError("GEOFLORA_CONFIDENCE_THRESHOLD must be in (0, 1].")
        self._model: Any = None
        self._embedding_model: Any = None
        self._classes: list[SpeciesClass] = []
        self._load_error: str | None = None
        self._load_artifacts()

    @property
    def ready(self) -> bool:
        return self._model is not None

    @property
    def species(self) -> list[dict[str, str]]:
        """The classes this model answers with, for clients that need the served list (the web catalog)."""
        return [dict(entry.__dict__) for entry in self._classes] if self.ready else []

    @property
    def supported_species_count(self) -> int:
        return len(self._classes) if self.ready else 0

    @property
    def model_version(self) -> str | None:
        return self._version if self.ready else None

    @property
    def unavailable_reason(self) -> str | None:
        return self._load_error

    def predict(self, image_bytes: bytes) -> Prediction:
        if not self.ready:
            raise ModelUnavailableError(self._load_error or "No trained model is installed.")

        image_batch = decode_image(image_bytes)
        output = np.asarray(self._model.predict(image_batch, verbose=0))
        if output.ndim != 2 or output.shape[0] != 1 or output.shape[1] != len(self._classes):
            raise RuntimeError("Model output does not match the saved class mapping.")
        probabilities = output[0]
        if (
            not np.isfinite(probabilities).all()
            or np.any(probabilities < 0)
            or np.any(probabilities > 1)
            or not math.isclose(float(probabilities.sum()), 1.0, abs_tol=0.02)
        ):
            raise RuntimeError("Model output is not a valid probability distribution.")

        ranked_indices = np.argsort(probabilities)[::-1]
        best_index = int(ranked_indices[0])
        confidence = float(probabilities[best_index])
        species = (
            self._classes[best_index]
            if confidence >= self.confidence_threshold
            else None
        )
        candidates = [
            {
                "species": self._classes[int(index)].__dict__,
                "confidence": float(probabilities[index]),
            }
            for index in ranked_indices[: min(3, len(self._classes))]
        ]
        return Prediction(
            status="identified" if species else "uncertain",
            species=species,
            confidence=confidence,
            confidence_threshold=self.confidence_threshold,
            candidates=candidates,
            model_version=self._version,
        )

    @property
    def embedding_version(self) -> str | None:
        return f"{self._version}:backbone-output-v1" if self.ready and self._embedding_model is not None else None

    def embed(self, image_bytes: bytes) -> list[float]:
        """Return an L2-normalized penultimate MobileNetV2 feature vector, not a class probability."""
        if not self.ready or self._embedding_model is None:
            raise ModelUnavailableError(self._load_error or "The visual feature extractor is unavailable.")
        vector = np.asarray(self._embedding_model.predict(decode_image(image_bytes), verbose=0), dtype=np.float32)
        if vector.ndim != 2 or vector.shape[0] != 1 or not np.isfinite(vector).all():
            raise RuntimeError("The visual feature extractor returned an invalid vector.")
        norm = float(np.linalg.norm(vector[0]))
        if not math.isfinite(norm) or norm <= 1e-12:
            raise RuntimeError("The visual feature vector has no usable magnitude.")
        return (vector[0] / norm).astype(np.float32).tolist()

    def _load_artifacts(self) -> None:
        if not self.model_path.is_file():
            self._load_error = "No trained MobileNetV2 model is installed yet."
            LOGGER.error("Configured model artifact is missing: %s", self.model_path)
            return
        if not self.class_mapping_path.is_file():
            self._load_error = "The trained model has no class mapping file."
            LOGGER.error("Configured model class mapping is missing: %s", self.class_mapping_path)
            return

        try:
            content = json.loads(self.class_mapping_path.read_text(encoding="utf-8"))
            if not isinstance(content, dict) or content.get("classes") is None:
                raise ValueError("Class mapping must contain a classes list.")
            classes = content["classes"]
            if not isinstance(classes, list) or not classes:
                raise ValueError("Class mapping must contain a non-empty classes list.")
            self._classes = [SpeciesClass(**entry) for entry in classes]
            catalog = load_species(self.species_path) if self.species_path is not None else load_species()
            configured = {species.id: species for species in catalog}
            if (
                len({entry.id for entry in self._classes}) != len(self._classes)
                or any(
                    entry.id not in configured
                    or configured[entry.id].scientific_name != entry.scientific_name
                    or configured[entry.id].common_name != entry.common_name
                    for entry in self._classes
                )
            ):
                raise ValueError("Class mapping contains unsupported or mismatched species.")

            from tensorflow.keras.models import Model, load_model

            model = load_model(self.model_path)
            output_shape = model.output_shape
            if (
                isinstance(output_shape, list)
                or len(output_shape) != 2
                or output_shape[-1] != len(self._classes)
            ):
                raise ValueError("Model output width does not match the class mapping.")
            # These trained artifacts wrap the MobileNetV2 backbone and a classifier head in a Functional model.
            # Select its final rank-2, 1280-wide layer before the head, keeping the live classifier untouched.
            feature_layers = []
            for layer in model.layers[:-1]:
                try:
                    shape = tuple(layer.output.shape)
                except (AttributeError, TypeError):
                    continue
                if len(shape) == 2 and shape[-1] == 1280:
                    feature_layers.append(layer)
            if not feature_layers:
                raise ValueError("The saved model has no compatible MobileNetV2 feature layer.")
            feature_layer = feature_layers[-1]
            if isinstance(feature_layer, Model):
                # The shipped v3 artifact nests MobileNetV2 as a Functional layer and the head as a Sequential
                # layer. Its internal symbolic tensor is not directly connected to the outer graph, so expose the
                # backbone using its own input/output graph.
                embedding_model = Model(inputs=feature_layer.inputs, outputs=feature_layer.outputs)
            else:
                embedding_model = Model(inputs=model.inputs, outputs=feature_layer.output)
            self._model = model
            self._embedding_model = embedding_model
            self._load_error = None
        except Exception as exc:  # noqa: BLE001 - retain details in logs, report a safe unavailable state publicly.
            self._model = None
            self._embedding_model = None
            self._classes = []
            self._load_error = f"Model artifacts could not be loaded: {exc}"
            LOGGER.exception("Model artifacts could not be loaded from configured model location")
