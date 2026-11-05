from __future__ import annotations

import hashlib
import io
from pathlib import Path

from PIL import Image, UnidentifiedImageError

MAX_IMAGE_BYTES = 20 * 1024 * 1024
MIN_IMAGE_SIDE = 64
MAX_IMAGE_PIXELS = 40_000_000
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


class InvalidImageError(ValueError):
    pass


def validate_and_store(image_bytes: bytes, output_dir: Path) -> tuple[str, Path]:
    if not image_bytes:
        raise InvalidImageError("Image is empty")
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise InvalidImageError(f"Image exceeds the {MAX_IMAGE_BYTES}-byte limit")

    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            if image.format not in {"JPEG", "PNG", "WEBP"}:
                raise InvalidImageError(f"Unsupported image format: {image.format}")
            if image.width < MIN_IMAGE_SIDE or image.height < MIN_IMAGE_SIDE:
                raise InvalidImageError(
                    f"Image dimensions must be at least {MIN_IMAGE_SIDE}x{MIN_IMAGE_SIDE}"
                )
            if image.width * image.height > MAX_IMAGE_PIXELS:
                raise InvalidImageError(f"Image exceeds the {MAX_IMAGE_PIXELS}-pixel limit")
            image.verify()
        with Image.open(io.BytesIO(image_bytes)) as image:
            normalized = image.convert("RGB")
            output = io.BytesIO()
            normalized.save(output, format="JPEG", quality=95, optimize=True)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise InvalidImageError(f"Image could not be safely decoded: {exc}") from exc

    normalized_bytes = output.getvalue()
    if len(normalized_bytes) > MAX_IMAGE_BYTES:
        raise InvalidImageError(
            f"Normalized image exceeds the {MAX_IMAGE_BYTES}-byte limit"
        )
    checksum = hashlib.sha256(normalized_bytes).hexdigest()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{checksum}.jpg"
    if not output_path.exists():
        output_path.write_bytes(normalized_bytes)
    return checksum, output_path
