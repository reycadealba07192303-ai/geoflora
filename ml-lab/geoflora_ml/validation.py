"""Dataset validation: readability, quality, license eligibility, label consistency, duplicates,
observation-group independence and class balance. Writes results back into the manifest and
produces reports/validation_summary.json and reports/dataset_inventory.md."""

from __future__ import annotations

import logging
from collections import Counter
from pathlib import Path

import pandas as pd

from .catalog import by_id, load_catalog
from .config import project_path, project_root
from .grouping import compute_groups
from .imaging import inspect_image, quality_flags
from .licenses import is_license_allowed
from .manifest import REVIEW_STATUSES, load_manifest, save_manifest
from .utils import resolve_path, sha256_file, utc_now_iso, write_json

log = logging.getLogger(__name__)

IMAGE_QUALITY_FLAGS = {"unreadable", "low_resolution", "extreme_aspect_ratio", "blurry", "too_dark", "overexposed"}


def validate_manifest(cfg: dict, recheck_images: bool = True) -> dict:
    vcfg = cfg["validation"]
    root = project_root(cfg)
    catalog = load_catalog(project_path(cfg, "species_catalog"))
    cat = by_id(catalog)
    manifest_path = project_path(cfg, "image_manifest")
    df = load_manifest(manifest_path)
    if df.empty:
        summary = {"generated": utc_now_iso(), "total_images": 0, "note": "manifest is empty - run download first"}
        write_json(project_path(cfg, "reports") / "validation_summary.json", summary)
        write_inventory(cfg, df, catalog, summary)
        return summary

    label_issues: list[str] = []
    for idx, row in df.iterrows():
        flags: list[str] = []
        path = resolve_path(row["local_path"], root) if row["local_path"] else None
        if path is None or not path.exists():
            df.at[idx, "readable"] = "false"
            df.at[idx, "quality_flags"] = "missing_file"
            df.at[idx, "quality_pass"] = "false"
            continue
        if recheck_images or not row["phash"]:
            sha = sha256_file(path)
            if row["file_sha256"] and row["file_sha256"] != sha:
                flags.append("file_changed_since_download")
            df.at[idx, "file_sha256"] = sha
            info = inspect_image(path)
            df.at[idx, "readable"] = "true" if info.readable else "false"
            df.at[idx, "width"] = str(info.width)
            df.at[idx, "height"] = str(info.height)
            df.at[idx, "phash"] = info.phash
            flags += quality_flags(info, vcfg)
        else:
            flags += [f for f in row["quality_flags"].split(";") if f in IMAGE_QUALITY_FLAGS]

        # label consistency
        sp = cat.get(row["species_id"])
        if sp is None:
            flags.append("species_not_in_catalog")
        else:
            if row["scientific_name"] != sp.scientific_name:
                flags.append("scientific_name_mismatch")
            if sp.gbif_taxon_key and row["accepted_taxon_key"] and str(sp.gbif_taxon_key) != row["accepted_taxon_key"]:
                flags.append("taxon_key_mismatch")
            if path.parent.name != sp.folder:
                flags.append("folder_label_mismatch")
            if row["ecological_role"] != sp.role:
                df.at[idx, "ecological_role"] = sp.role  # role may change in the catalog; keep in sync
        if row["review_status"] not in REVIEW_STATUSES:
            flags.append("invalid_review_status")
        if row["review_status"] == "approved" and not row["reviewer"].strip():
            flags.append("approved_without_reviewer")
        if flags and any(f in flags for f in ("species_not_in_catalog", "scientific_name_mismatch",
                                               "taxon_key_mismatch", "folder_label_mismatch")):
            label_issues.append(row["image_id"])

        df.at[idx, "license_eligible"] = "true" if is_license_allowed(row["license"], cfg["download"]["allowed_licenses"]) else "false"
        if df.at[idx, "license_eligible"] != "true":
            flags.append("license_not_allowed")
        df.at[idx, "quality_flags"] = ";".join(dict.fromkeys(flags))
        blocking = [f for f in flags if f not in ("file_changed_since_download",)]
        df.at[idx, "quality_pass"] = "false" if blocking else "true"

    groups = compute_groups(df, int(vcfg["phash_hamming_threshold"]), bool(cfg["split"]["group_by_recorder_and_date"]))
    for col in groups.columns:
        df[col] = groups[col]
    save_manifest(df, manifest_path)

    summary = summarize(df, cfg, label_issues)
    write_json(project_path(cfg, "reports") / "validation_summary.json", summary)
    write_inventory(cfg, df, catalog, summary)
    return summary


def is_provisional(cfg: dict) -> bool:
    return bool(cfg.get("provisional", {}).get("enabled"))


def training_eligible_mask(df: pd.DataFrame, cfg: dict) -> pd.Series:
    allowed = set(cfg["validation"]["allowed_review_statuses_for_training"])
    labelled = df["review_status"].isin(allowed) & (df["reviewer"].str.strip() != "")
    if is_provisional(cfg):
        # PILOT ONLY: unreviewed images whose source dataset has community-agreed identifications.
        # Rejected/uncertain images stay excluded. Never use for reported results or export.
        sources = set(cfg["provisional"]["accepted_source_dataset_keys"])
        labelled = labelled | ((df["review_status"] == "pending") & df["source_dataset_key"].isin(sources))
    return (
        (df["readable"] == "true")
        & (df["quality_pass"] == "true")
        & (df["license_eligible"] == "true")
        & labelled
        & (df["exact_duplicate_of"] == "")
        & (df["label_conflict"] != "true")
    )


def summarize(df: pd.DataFrame, cfg: dict, label_issues: list[str] | None = None) -> dict:
    eligible = training_eligible_mask(df, cfg)
    flag_counts: Counter = Counter()
    for f in df["quality_flags"]:
        for part in filter(None, f.split(";")):
            flag_counts[part] += 1
    per_species = []
    for sid, g in df.groupby("species_id"):
        e = g[eligible.loc[g.index]]
        per_species.append({
            "species_id": sid,
            "scientific_name": g["scientific_name"].iloc[0],
            "role": g["ecological_role"].iloc[0],
            "images": int(len(g)),
            "observation_groups": int(g["observation_group"].nunique()),
            "readable": int((g["readable"] == "true").sum()),
            "quality_pass": int((g["quality_pass"] == "true").sum()),
            "license_eligible": int((g["license_eligible"] == "true").sum()),
            "review_status": {k: int(v) for k, v in g["review_status"].value_counts().items()},
            "exact_duplicates": int((g["exact_duplicate_of"] != "").sum()),
            "in_near_duplicate_clusters": int((g["near_duplicate_cluster"] != "").sum()),
            "label_conflicts": int((g["label_conflict"] == "true").sum()),
            "training_eligible_images": int(len(e)),
            "training_eligible_groups": int(e["observation_group"].nunique()),
            "countries": {k: int(v) for k, v in g["country_code"].replace("", "unknown").value_counts().head(10).items()},
            "licenses": {k: int(v) for k, v in g["license"].value_counts().items()},
        })
    counts = [s["training_eligible_images"] for s in per_species if s["training_eligible_images"] > 0]
    return {
        "generated": utc_now_iso(),
        "total_images": int(len(df)),
        "total_observation_groups": int(df["observation_group"].nunique()),
        "readable": int((df["readable"] == "true").sum()),
        "quality_pass": int((df["quality_pass"] == "true").sum()),
        "license_eligible": int((df["license_eligible"] == "true").sum()),
        "review_status": {k: int(v) for k, v in df["review_status"].value_counts().items()},
        "training_eligible_images": int(eligible.sum()),
        "quality_flag_counts": dict(flag_counts),
        "label_issue_images": label_issues or [],
        "class_balance_ratio_max_min": (max(counts) / min(counts)) if counts else None,
        "per_species": per_species,
    }


def write_inventory(cfg: dict, df: pd.DataFrame, catalog, summary: dict) -> Path:
    """Human-readable dataset inventory including botanical review requirements (Stage 4)."""
    scfg = cfg["split"]
    lines = [
        "# GeoFlora-ML-Lab Dataset Inventory",
        "",
        f"Generated: {summary.get('generated')}",
        "",
        "This inventory describes externally sourced photographs (e.g. GBIF-mediated records). They are **not**",
        "original GeoFlora field observations and none has been botanically reviewed unless the review columns",
        "below say so. Only images with `review_status = approved` and a named reviewer can be used as training labels.",
        "",
        "## Totals",
        "",
        f"- Images in manifest: {summary.get('total_images', 0)}",
        f"- Independent observation groups: {summary.get('total_observation_groups', 0)}",
        f"- Readable: {summary.get('readable', 0)} | Quality pass: {summary.get('quality_pass', 0)} | License eligible: {summary.get('license_eligible', 0)}",
        f"- Review status: {summary.get('review_status', {})}",
        f"- Training-eligible (approved + quality + license + not duplicate/conflict): {summary.get('training_eligible_images', 0)}",
        f"- Quality flags: {summary.get('quality_flag_counts', {})}",
        "",
        "## Per species",
        "",
        "| Species ID | Scientific name | Role | Ecological status | Status verified | Images | Obs. groups | Quality pass | Pending review | Approved | Training-eligible imgs / groups | Ready to train? |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    stats = {s["species_id"]: s for s in summary.get("per_species", [])}
    for sp in catalog:
        s = stats.get(sp.species_id)
        if s is None and not sp.download_enabled:
            continue
        s = s or {}
        rs = s.get("review_status", {})
        ei, eg = s.get("training_eligible_images", 0), s.get("training_eligible_groups", 0)
        if not sp.training_enabled:
            ready = "n/a (not a training class)"
        elif ei >= scfg["min_images_per_class"] and eg >= scfg["min_groups_per_class"]:
            ready = "yes"
        else:
            ready = f"no (needs >= {scfg['min_images_per_class']} imgs and >= {scfg['min_groups_per_class']} groups)"
        lines.append(
            f"| {sp.species_id} | *{sp.scientific_name}* | {sp.role} | {sp.ecological_status} | {sp.status_verification} | "
            f"{s.get('images', 0)} | {s.get('observation_groups', 0)} | {s.get('quality_pass', 0)} | {rs.get('pending', 0)} | "
            f"{rs.get('approved', 0)} | {ei} / {eg} | {ready} |")
    lines += [
        "",
        "## Botanical review requirements",
        "",
        "1. A qualified botanist (or the client's designated reviewer) must confirm species identity for each image",
        "   used as a training, validation, test or unsupported-species label. Use `python scripts/review_images.py export`",
        "   to create review sheets, then `python scripts/review_images.py import <sheet.csv> --reviewer \"Name\"`.",
        "2. Community identifications on source platforms (e.g. iNaturalist research grade) are recorded as provenance",
        "   only; they are not treated as botanical verification by this project.",
        "3. Ecological status for every species with `status_verification = unverified` requires Philippine-specific",
        "   evidence (citation, issuing body, date) and the name of the person who verified it before the model's",
        "   outputs are described as identifying *invasive* species for that class.",
        "4. Reviewers may optionally tag lighting, background, plant organ and growth stage so that the evaluation can",
        "   report performance by photographic condition (research question 8).",
        "",
        "## Licensing",
        "",
        f"Allowed licenses: {', '.join(cfg['download']['allowed_licenses'])}. Non-commercial (NC) licensed images restrict",
        "commercial use of the image collection; attribution for every image is stored in `metadata/image_manifest.csv`.",
    ]
    path = project_path(cfg, "reports") / "dataset_inventory.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
