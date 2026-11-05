from __future__ import annotations

import csv
from collections.abc import Iterator
from pathlib import Path

from geoflora_ml.collection.licensing import normalize_license
from geoflora_ml.collection.models import ImageCandidate
from geoflora_ml.config import Species

REQUIRED_COLUMNS = {
    "source_id",
    "species",
    "image_path",
    "source_url",
    "license",
    "attribution",
    "country",
}


class KaggleManifestSource:
    """Imports an already downloaded Kaggle dataset with per-image rights metadata."""

    def __init__(self, manifest_path: Path) -> None:
        self.manifest_path = manifest_path.resolve()
        self.root = self.manifest_path.parent

    def candidates(
        self, species: Species, limit: int | None, pages: int | None = None
    ) -> Iterator[ImageCandidate]:
        del pages
        with self.manifest_path.open(newline="", encoding="utf-8-sig") as manifest_file:
            reader = csv.DictReader(manifest_file)
            missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
            if missing:
                raise ValueError(
                    f"Kaggle manifest is missing required columns: {', '.join(sorted(missing))}"
                )
            emitted = 0
            for row in reader:
                scientific_name = row["species"].strip()
                if scientific_name.casefold() != species.scientific_name.casefold():
                    continue
                if row["country"].strip().casefold() not in {"ph", "philippines"}:
                    continue
                license_code = normalize_license(row["license"])
                if not license_code:
                    continue
                attribution = row["attribution"].strip()
                if license_code != "cc0" and not attribution:
                    continue
                image_path = (self.root / row["image_path"]).resolve()
                if not image_path.is_relative_to(self.root):
                    raise ValueError("Kaggle manifest image_path must stay within its directory")
                if not image_path.is_file():
                    raise ValueError(f"Kaggle manifest image does not exist: {image_path}")
                yield ImageCandidate(
                    source="kaggle",
                    source_id=row["source_id"].strip(),
                    group_id=(
                        f"kaggle:{str(row.get('group_id') or '').strip()}"
                        if str(row.get("group_id") or "").strip()
                        else f"kaggle:{row['source_id'].strip()}"
                    ),
                    species_id=species.id,
                    scientific_name=species.scientific_name,
                    image_url=image_path.as_uri(),
                    source_url=row["source_url"].strip(),
                    license=license_code,
                    attribution=attribution or "CC0",
                )
                emitted += 1
                if limit is not None and emitted >= limit:
                    return
