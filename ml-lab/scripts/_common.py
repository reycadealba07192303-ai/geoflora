"""Shared CLI setup for scripts/ (adds the project root to sys.path, configures logging)."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")


def parser(description: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=description)
    p.add_argument("--config", default=None, help="YAML file overriding configs/default.yaml")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def setup(args) -> dict:
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%H:%M:%S")
    from geoflora_ml.config import load_config

    return load_config(args.config)


def latest_dir(parent: Path, prefix: str = "") -> Path | None:
    dirs = [d for d in parent.glob(f"{prefix}*") if d.is_dir()] if parent.exists() else []
    return max(dirs, key=lambda d: d.stat().st_mtime) if dirs else None
