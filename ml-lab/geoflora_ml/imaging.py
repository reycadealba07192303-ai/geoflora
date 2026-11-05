"""Image readability, quality metrics, perceptual hashing and normalisation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import imagehash
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

Image.MAX_IMAGE_PIXELS = 120_000_000  # guard against decompression bombs


@dataclass
class ImageInfo:
    readable: bool
    width: int = 0
    height: int = 0
    image_format: str = ""
    phash: str = ""
    blur_variance: float = 0.0
    mean_brightness: float = 0.0
    error: str = ""
    flags: list[str] = field(default_factory=list)


def open_rgb(path: str | Path) -> Image.Image:
    """Open an image, apply EXIF orientation and convert to RGB (the canonical decode path)."""
    with Image.open(path) as im:
        im.load()
        im = ImageOps.exif_transpose(im)
        if im.mode != "RGB":
            if im.mode in ("RGBA", "LA", "P"):
                im = im.convert("RGBA")
                bg = Image.new("RGB", im.size, (255, 255, 255))
                bg.paste(im, mask=im.split()[-1])
                im = bg
            else:
                im = im.convert("RGB")
        return im.copy()


def laplacian_variance(gray: np.ndarray) -> float:
    """Variance of a 4-neighbour Laplacian; a standard sharpness proxy."""
    g = gray.astype(np.float32)
    lap = (-4 * g[1:-1, 1:-1] + g[:-2, 1:-1] + g[2:, 1:-1] + g[1:-1, :-2] + g[1:-1, 2:])
    return float(lap.var())


def inspect_image(path: str | Path) -> ImageInfo:
    try:
        with Image.open(path) as probe:
            fmt = probe.format or ""
            probe.verify()
        im = open_rgb(path)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        return ImageInfo(readable=False, error=f"{type(exc).__name__}: {exc}")
    w, h = im.size
    small = im.copy()
    small.thumbnail((256, 256))
    gray = np.asarray(small.convert("L"))
    return ImageInfo(
        readable=True,
        width=w,
        height=h,
        image_format=fmt,
        phash=str(imagehash.phash(im)),
        blur_variance=laplacian_variance(gray) if min(gray.shape) > 2 else 0.0,
        mean_brightness=float(gray.mean()),
    )


def quality_flags(info: ImageInfo, vcfg: dict) -> list[str]:
    """Return a list of quality problems (empty list = passes)."""
    if not info.readable:
        return ["unreadable"]
    flags = []
    if info.width < vcfg["min_width"] or info.height < vcfg["min_height"]:
        flags.append("low_resolution")
    ratio = max(info.width, info.height) / max(1, min(info.width, info.height))
    if ratio > vcfg["max_aspect_ratio"]:
        flags.append("extreme_aspect_ratio")
    if info.blur_variance < vcfg["min_blur_variance"]:
        flags.append("blurry")
    if info.mean_brightness < vcfg["min_mean_brightness"]:
        flags.append("too_dark")
    if info.mean_brightness > vcfg["max_mean_brightness"]:
        flags.append("overexposed")
    return flags


def phash_distance(a: str, b: str) -> int:
    return imagehash.hex_to_hash(a) - imagehash.hex_to_hash(b)


def save_normalized_jpeg(src: str | Path, dst: str | Path, max_side: int = 1024, quality: int = 95) -> None:
    """Write an EXIF-corrected RGB JPEG copy (used for train/val/test folders)."""
    im = open_rgb(src)
    if max_side and max(im.size) > max_side:
        im.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    im.save(dst, format="JPEG", quality=quality)
