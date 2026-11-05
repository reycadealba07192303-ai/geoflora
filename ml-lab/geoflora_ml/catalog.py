"""Species catalog: the single source of truth for species identity, ecological status and role.

Ecological status categories are deliberately kept separate:
  target_invasive         confirmed target invasive alien species (client scope)
  introduced_naturalized  introduced/naturalized, invasive status not confirmed
  native_nontarget        native or endemic non-target species
  unresolved              ecological status not yet established with evidence

A species is never labelled invasive because it appears in a dataset. `status_verification`
stays "unverified" until a named person records Philippine-specific evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .utils import clean_str, species_folder_name, truthy

ECOLOGICAL_STATUSES = ("target_invasive", "introduced_naturalized", "native_nontarget", "unresolved")
STATUS_VERIFICATIONS = ("unverified", "verified")
ROLES = ("target", "lookalike", "unknown_eval", "expansion_candidate")

REQUIRED_COLUMNS = [
    "species_id", "scientific_name", "synonyms", "common_names", "family", "gbif_taxon_key",
    "ecological_status", "status_verification", "status_verified_by", "status_verified_date",
    "status_evidence", "role", "training_enabled", "download_enabled", "notes",
]


class CatalogError(ValueError):
    pass


@dataclass(frozen=True)
class Species:
    species_id: str
    scientific_name: str
    synonyms: str
    common_names: str
    family: str
    gbif_taxon_key: int | None
    ecological_status: str
    status_verification: str
    status_verified_by: str
    status_verified_date: str
    status_evidence: str
    role: str
    training_enabled: bool
    download_enabled: bool
    notes: str

    @property
    def folder(self) -> str:
        return species_folder_name(self.scientific_name)

    @property
    def primary_common_name(self) -> str:
        return self.common_names.split(";")[0].strip() if self.common_names else ""


def load_catalog(path: str | Path) -> list[Species]:
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    validate_catalog_frame(df)
    out = []
    for _, r in df.iterrows():
        key = clean_str(r["gbif_taxon_key"])
        out.append(Species(
            species_id=clean_str(r["species_id"]),
            scientific_name=clean_str(r["scientific_name"]),
            synonyms=clean_str(r["synonyms"]),
            common_names=clean_str(r["common_names"]),
            family=clean_str(r["family"]),
            gbif_taxon_key=int(key) if key else None,
            ecological_status=clean_str(r["ecological_status"]),
            status_verification=clean_str(r["status_verification"]),
            status_verified_by=clean_str(r["status_verified_by"]),
            status_verified_date=clean_str(r["status_verified_date"]),
            status_evidence=clean_str(r["status_evidence"]),
            role=clean_str(r["role"]),
            training_enabled=truthy(r["training_enabled"]),
            download_enabled=truthy(r["download_enabled"]),
            notes=clean_str(r["notes"]),
        ))
    return out


def validate_catalog_frame(df: pd.DataFrame) -> None:
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise CatalogError(f"species catalog missing columns: {missing}")
    errors = []
    if df["species_id"].duplicated().any():
        errors.append(f"duplicate species_id: {sorted(df.loc[df['species_id'].duplicated(), 'species_id'])}")
    if df["scientific_name"].duplicated().any():
        errors.append("duplicate scientific_name values")
    folders = df["scientific_name"].map(species_folder_name)
    if folders.duplicated().any():
        errors.append("two scientific names map to the same folder name")
    for i, r in df.iterrows():
        sid = r["species_id"] or f"row {i + 2}"
        if not r["species_id"].strip() or not r["scientific_name"].strip():
            errors.append(f"{sid}: species_id and scientific_name are required")
        if r["ecological_status"] not in ECOLOGICAL_STATUSES:
            errors.append(f"{sid}: invalid ecological_status '{r['ecological_status']}'")
        if r["status_verification"] not in STATUS_VERIFICATIONS:
            errors.append(f"{sid}: invalid status_verification '{r['status_verification']}'")
        if r["status_verification"] == "verified" and not (r["status_verified_by"].strip() and r["status_verified_date"].strip()):
            errors.append(f"{sid}: status_verification=verified requires status_verified_by and status_verified_date")
        if r["role"] not in ROLES:
            errors.append(f"{sid}: invalid role '{r['role']}'")
        if r["role"] == "unknown_eval" and truthy(r["training_enabled"]):
            errors.append(f"{sid}: unknown_eval species must not be training_enabled")
        key = r["gbif_taxon_key"].strip()
        if key and not key.isdigit():
            errors.append(f"{sid}: gbif_taxon_key must be an integer")
    if errors:
        raise CatalogError("species catalog invalid:\n  " + "\n  ".join(errors))


def by_id(catalog: list[Species]) -> dict[str, Species]:
    return {s.species_id: s for s in catalog}


def by_name(catalog: list[Species]) -> dict[str, Species]:
    return {s.scientific_name: s for s in catalog}
