"""Shared MobileNetV2 image preparation for training and inference.

Training may add extra views. Validation, test, and live inference use the
original resized RGB image only. TensorFlow preprocessing is applied after
resize so the saved Keras model still expects already-scaled inputs.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance, ImageOps

IMAGE_SIZE = (224, 224)
TRAIN_ONLY_AUGMENTATION = (
    "original, horizontal mirror, +10 degree rotation with brightness x0.9"
)


def rgb_224(image: Image.Image) -> Image.Image:
    return image.convert("RGB").resize(IMAGE_SIZE)


def rgb_array(image: Image.Image) -> np.ndarray:
    return np.asarray(rgb_224(image), dtype=np.float32)


def training_views(image: Image.Image, *, augment: bool) -> list[Image.Image]:
    original = rgb_224(image)
    if not augment:
        return [original]
    rotated = original.rotate(10, resample=Image.Resampling.BILINEAR)
    return [
        original,
        ImageOps.mirror(original),
        ImageEnhance.Brightness(rotated).enhance(0.9),
    ]


def load_training_views(path: Path, *, augment: bool) -> list[Image.Image]:
    with Image.open(path) as image:
        return training_views(image, augment=augment)


def preprocess_rgb_batch(arrays: list[np.ndarray] | np.ndarray) -> np.ndarray:
    stacked = np.stack(arrays) if isinstance(arrays, list) else np.asarray(arrays)
    if stacked.ndim == 3:
        stacked = np.expand_dims(stacked, axis=0)
    try:
        from tensorflow.keras.applications.mobilenet_v2 import preprocess_input
    except ImportError as exc:
        raise RuntimeError(
            "TensorFlow is not installed. Install the ML training or inference extra."
        ) from exc
    return preprocess_input(np.asarray(stacked, dtype=np.float32))
