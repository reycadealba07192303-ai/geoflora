"""Test fixtures: an isolated temporary project with synthetic images (no network, no real data)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

from geoflora_ml.catalog import REQUIRED_COLUMNS  # noqa: E402
from geoflora_ml.config import load_config  # noqa: E402
from geoflora_ml.manifest import save_manifest, empty_manifest, append_rows  # noqa: E402
from geoflora_ml.utils import species_folder_name  # noqa: E402

TEST_SPECIES = [
    # species_id, name, role, training_enabled, colour family
    ("GF-SP-0001", "Alpha testii", "target", True, (200, 40, 40)),
    ("GF-SP-0002", "Beta testii", "target", True, (40, 170, 40)),
    ("GF-SP-0003", "Gamma testii", "target", True, (40, 60, 200)),
    ("GF-SP-0201", "Delta unknownii", "unknown_eval", False, (200, 180, 30)),
    ("GF-SP-0202", "Epsilon unknownii", "unknown_eval", False, (160, 40, 180)),
]

TEST_OVERRIDES = {
    "split": {"min_images_per_class": 10, "min_groups_per_class": 8, "min_test_images_per_class": 2,
              "group_by_recorder_and_date": True},
    "train": {"image_size": 96, "batch_size": 8, "weights": None, "head_epochs": 1, "fine_tune_epochs": 1,
              "fine_tune_at_layer": 140, "early_stopping_patience": 2},
    "evaluate": {"bootstrap_resamples": 50, "timing_warmup": 1, "timing_runs": 3},
    "export": {"min_test_images_total": 5},
}


def synthetic_image(path: Path, colour, rng: np.random.Generator, size: int = 256, shape: int = 0) -> None:
    """Random, structurally distinct image whose dominant colour/shape encodes the class."""
    bg = tuple(int(x) for x in rng.integers(90, 170, 3))
    im = Image.new("RGB", (size, size), bg)
    d = ImageDraw.Draw(im)
    for _ in range(int(rng.integers(6, 12))):
        x0, y0 = rng.integers(0, size - 40, 2)
        w, h = rng.integers(20, 90, 2)
        c = tuple(int(np.clip(v + rng.integers(-30, 30), 0, 255)) for v in colour)
        box = [int(x0), int(y0), int(x0 + w), int(y0 + h)]
        (d.ellipse if shape % 2 == 0 else d.rectangle)(box, fill=c, outline=(0, 0, 0))
    noise = rng.integers(-12, 12, (size, size, 3))
    arr = np.clip(np.asarray(im).astype(int) + noise, 0, 255).astype(np.uint8)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(arr).save(path, quality=92)


def write_catalog(path: Path, species=TEST_SPECIES) -> None:
    rows = []
    for sid, name, role, train, _ in species:
        r = {c: "" for c in REQUIRED_COLUMNS}
        r.update(species_id=sid, scientific_name=name, ecological_status="target_invasive" if role == "target" else "unresolved",
                 status_verification="unverified", role=role, training_enabled=str(train).lower(),
                 download_enabled="true", family="Testaceae", gbif_taxon_key="")
        rows.append(r)
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=REQUIRED_COLUMNS).to_csv(path, index=False)


@pytest.fixture
def make_project(tmp_path):
    def _make(n_per_species: int = 16, approve: bool = True, species=TEST_SPECIES, seed: int = 0, overrides=None):
        cfg = load_config(overrides={"paths": {"root": str(tmp_path)}, **TEST_OVERRIDES, **(overrides or {})})
        write_catalog(tmp_path / cfg["paths"]["species_catalog"], species)
        rng = np.random.default_rng(seed)
        rows = []
        for k, (sid, name, role, _, colour) in enumerate(species):
            for i in range(n_per_species):
                iid = f"test-{sid}-{i:03d}"
                rel = f"dataset/raw/{species_folder_name(name)}/{iid}.jpg"
                synthetic_image(tmp_path / rel, colour, rng, shape=k)
                rows.append({
                    "image_id": iid, "species_id": sid, "scientific_name": name, "ecological_role": role,
                    "source": "synthetic-test", "observation_id": f"obs:{sid}:{i}", "license": "CC0-1.0",
                    "local_path": rel, "review_status": "approved" if approve else "pending",
                    "reviewer": "Test Reviewer" if approve else "", "recorded_by": f"rec{i}",
                    "event_date": f"2025-01-{(i % 28) + 1:02d}", "country_code": "PH",
                    "is_geoflora_field_observation": "false", "attribution": "synthetic test image",
                })
        save_manifest(append_rows(empty_manifest(), rows), tmp_path / cfg["paths"]["image_manifest"])
        return cfg
    return _make
