"""Small shared helpers: paths, hashing, atomic file writes, environment capture."""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import platform
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def utc_now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


def utc_stamp() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def species_folder_name(scientific_name: str) -> str:
    """Filesystem-safe folder name derived from the scientific name ("Lantana camara" -> "Lantana_camara")."""
    name = re.sub(r"[^A-Za-z0-9\-]+", "_", scientific_name.strip())
    return name.strip("_")


def sha256_file(path: str | Path, chunk_size: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def rel_to_root(path: str | Path, root: Path = PROJECT_ROOT) -> str:
    """Project-relative POSIX path (stable across Windows/Linux checkouts)."""
    p = Path(path).resolve()
    try:
        return p.relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        return p.as_posix()


def resolve_path(path: str | Path, root: Path = PROJECT_ROOT) -> Path:
    p = Path(path)
    return p if p.is_absolute() else (Path(root) / p)


def atomic_write_text(path: str | Path, text: str, encoding: str = "utf-8") -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def write_json(path: str | Path, obj: Any) -> None:
    atomic_write_text(path, json.dumps(obj, indent=2, ensure_ascii=False, default=_json_default) + "\n")


def read_json(path: str | Path) -> Any:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _json_default(o: Any) -> Any:
    try:
        import numpy as np

        if isinstance(o, np.integer):
            return int(o)
        if isinstance(o, np.floating):
            return float(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
        if isinstance(o, np.bool_):
            return bool(o)
    except ImportError:
        pass
    if isinstance(o, Path):
        return o.as_posix()
    raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")


def environment_info() -> dict:
    """Software/hardware context recorded with every run for reproducibility."""
    info = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "processor": platform.processor(),
        "machine": platform.machine(),
        "cpu_count": os.cpu_count(),
    }
    for mod in ("tensorflow", "keras", "numpy", "pandas", "sklearn", "PIL", "imagehash"):
        try:
            m = __import__(mod)
            info[f"{mod}_version"] = getattr(m, "__version__", "unknown")
        except Exception:
            info[f"{mod}_version"] = None
    try:
        import tensorflow as tf

        info["tf_gpus"] = [d.name for d in tf.config.list_physical_devices("GPU")]
    except Exception:
        info["tf_gpus"] = None
    return info


def truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, float) and value != value:  # NaN
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "t"}


def clean_str(value: Any) -> str:
    """String value with NaN/None mapped to ''."""
    if value is None:
        return ""
    if isinstance(value, float) and value != value:
        return ""
    return str(value).strip()
