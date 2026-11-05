from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from geoflora_ml.inference.predictor import decode_image
from geoflora_ml.inference.preprocess import (
    IMAGE_SIZE,
    load_training_views,
    preprocess_rgb_batch,
    rgb_array,
    rgb_224,
    training_views,
)


def _asymmetric_image(size: tuple[int, int] = (80, 120)) -> Image.Image:
    image = Image.new("RGB", size, color=(12, 80, 160))
    pixels = image.load()
    for x in range(size[0] // 3):
        for y in range(size[1]):
            pixels[x, y] = (200, 10, y % 180)
    return image


def _png_bytes(size: tuple[int, int] = (80, 120)) -> bytes:
    buffer = io.BytesIO()
    _asymmetric_image(size).save(buffer, format="PNG")
    return buffer.getvalue()


class SharedPreprocessTests(unittest.TestCase):
    def test_training_views_keep_evaluation_on_the_original_image(self) -> None:
        image = _asymmetric_image()
        evaluation = training_views(image, augment=False)
        augmented = training_views(image, augment=True)

        self.assertEqual(len(evaluation), 1)
        self.assertEqual(evaluation[0].size, IMAGE_SIZE)
        self.assertEqual(len(augmented), 3)
        np.testing.assert_array_equal(np.asarray(evaluation[0]), np.asarray(augmented[0]))
        self.assertFalse(np.array_equal(np.asarray(augmented[0]), np.asarray(augmented[1])))
        self.assertFalse(np.array_equal(np.asarray(augmented[0]), np.asarray(augmented[2])))

    def test_inference_decoder_matches_training_original_view(self) -> None:
        payload = _png_bytes()
        inferred = decode_image(payload)
        with Image.open(io.BytesIO(payload)) as image:
            trained = preprocess_rgb_batch([rgb_array(image)])
            mirrored = preprocess_rgb_batch([np.asarray(training_views(image, augment=True)[1], dtype=np.float32)])

        np.testing.assert_allclose(inferred, trained, atol=1e-6)
        self.assertEqual(inferred.shape, (1, 224, 224, 3))
        self.assertFalse(np.allclose(inferred, mirrored, atol=1e-3))

    def test_file_loader_does_not_augment_validation_paths(self) -> None:
        payload = _png_bytes((96, 96))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "photo.png"
            path.write_bytes(payload)
            views = load_training_views(path, augment=False)
        with Image.open(io.BytesIO(payload)) as image:
            expected = rgb_224(image)
        self.assertEqual(len(views), 1)
        np.testing.assert_array_equal(np.asarray(views[0]), np.asarray(expected))


if __name__ == "__main__":
    unittest.main()
