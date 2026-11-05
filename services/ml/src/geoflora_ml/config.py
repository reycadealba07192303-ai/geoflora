from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_DATA_DIR = REPOSITORY_ROOT / "storage" / "datasets"
SPECIES_FILE = Path(__file__).with_name("species.yaml")


@dataclass(frozen=True)
class Species:
    id: str
    scientific_name: str
    common_name: str
    # "invasive" for monitored species; "lookalike" for non-invasive plants the model learns so it can tell them apart.
    role: str = "invasive"


def load_species(path: Path = SPECIES_FILE) -> list[Species]:
    with path.open(encoding="utf-8") as species_file:
        content = yaml.safe_load(species_file)
    entries = content.get("species") if isinstance(content, dict) else None
    if not isinstance(entries, list) or not entries:
        raise ValueError(f"Species catalog must contain a non-empty list: {path}")

    species = [Species(**entry) for entry in entries]
    ids = [entry.id for entry in species]
    names = [entry.scientific_name.casefold() for entry in species]
    if len(ids) != len(set(ids)) or len(names) != len(set(names)):
        raise ValueError(f"Species catalog contains duplicate ids or names: {path}")
    return species


def data_dir_from_environment() -> Path:
    return Path(os.environ.get("GEOFLORA_DATA_DIR", DEFAULT_DATA_DIR)).expanduser()
