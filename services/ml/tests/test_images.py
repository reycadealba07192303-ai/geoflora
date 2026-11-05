import io
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from geoflora_ml.datasets.images import InvalidImageError, validate_and_store


class ImageValidationTests(unittest.TestCase):
    def test_normalizes_valid_image_and_returns_checksum(self) -> None:
        image_buffer = io.BytesIO()
        Image.new("RGB", (100, 100), color="green").save(image_buffer, format="PNG")
        with tempfile.TemporaryDirectory() as temp_dir:
            checksum, path = validate_and_store(image_buffer.getvalue(), Path(temp_dir))
            self.assertEqual(len(checksum), 64)
            self.assertTrue(path.is_file())
            with Image.open(path) as stored_image:
                self.assertEqual(stored_image.format, "JPEG")

    def test_rejects_non_image_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(InvalidImageError):
                validate_and_store(b"not an image", Path(temp_dir))

    def test_rejects_small_images(self) -> None:
        image_buffer = io.BytesIO()
        Image.new("RGB", (32, 32)).save(image_buffer, format="JPEG")
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(InvalidImageError):
                validate_and_store(image_buffer.getvalue(), Path(temp_dir))
