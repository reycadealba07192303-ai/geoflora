"""Image manifest: one row per image with full provenance, validation and review state.

The manifest (metadata/image_manifest.csv) is the authoritative record. Image folders are
derived from it; nothing is trained on that is not traceable to a manifest row.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .utils import atomic_write_text

REVIEW_STATUSES = ("pending", "approved", "rejected", "uncertain")

MANIFEST_COLUMNS = [
    # identity
    "image_id", "species_id", "scientific_name", "accepted_taxon_key", "verbatim_scientific_name",
    "ecological_role",
    # provenance
    "source", "source_dataset_key", "source_dataset_name", "publisher", "observation_id",
    "occurrence_id", "gbif_occurrence_key", "media_reference_url", "original_image_url",
    "fetched_image_url", "creator", "rights_holder", "license_raw", "license", "attribution",
    "basis_of_record", "country_code", "event_date", "recorded_by", "identified_by",
    "occurrence_metadata_ref", "download_timestamp", "is_geoflora_field_observation",
    # file
    "local_path", "file_sha256", "phash", "width", "height", "file_bytes", "image_format",
    # validation
    "readable", "quality_flags", "quality_pass", "license_eligible", "exact_duplicate_of",
    "near_duplicate_cluster", "observation_group", "label_conflict",
    # review (filled by a human reviewer only)
    "review_status", "reviewer", "review_date", "review_notes",
    "cond_lighting", "cond_background", "cond_organ", "cond_growth_stage",
    # split
    "split",
]


def empty_manifest() -> pd.DataFrame:
    return pd.DataFrame(columns=MANIFEST_COLUMNS)


def load_manifest(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if not path.exists() or path.stat().st_size == 0:
        return empty_manifest()
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    for col in MANIFEST_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    extra = [c for c in df.columns if c not in MANIFEST_COLUMNS]
    return df[MANIFEST_COLUMNS + extra]


def save_manifest(df: pd.DataFrame, path: str | Path) -> None:
    for col in MANIFEST_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    extra = [c for c in df.columns if c not in MANIFEST_COLUMNS]
    df = df[MANIFEST_COLUMNS + extra].sort_values(["species_id", "image_id"], kind="stable")
    atomic_write_text(path, df.to_csv(index=False))


def append_rows(df: pd.DataFrame, rows: list[dict]) -> pd.DataFrame:
    if not rows:
        return df
    new = pd.DataFrame(rows).astype(str)
    new = new.reindex(columns=df.columns.union(new.columns, sort=False), fill_value="")
    df = df.reindex(columns=new.columns, fill_value="")
    out = pd.concat([df, new], ignore_index=True)
    return out.drop_duplicates("image_id", keep="first").reset_index(drop=True)
