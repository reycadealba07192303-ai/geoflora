"""Leakage-safe train/val/test partitioning.

Rules
  * The split unit is the observation group (see grouping.py), so the same observation, exact
    duplicates and perceptual near-duplicates never straddle two partitions.
  * Assignments are sticky: once an image has been placed in a partition it keeps it in later
    re-splits (metadata/split_assignments.csv keeps history, including inactive rows). Test images
    therefore never migrate into training when species or images are added (historical test isolation).
  * metadata/locked_test_groups.txt may list image_ids or observation_ids that must stay in test
    (e.g. historical GeoFlora test data imported later).
  * Only approved, quality-passing, license-eligible images are assigned.
  * Species that are not model classes but have approved images (unknown_eval / lookalike /
    expansion_candidate) form the unsupported-species pool, split *by species* into unknown_val
    (threshold selection only) and unknown_test (final evaluation only).
"""

from __future__ import annotations

import hashlib
import logging
import shutil
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from .catalog import Species, by_id, load_catalog
from .config import project_path, project_root
from .grouping import near_duplicate_pairs
from .imaging import save_normalized_jpeg
from .manifest import load_manifest, save_manifest
from .utils import atomic_write_text, resolve_path, utc_now_iso, write_json
from .validation import is_provisional, training_eligible_mask

log = logging.getLogger(__name__)

KNOWN_SPLITS = ("train", "val", "test")
UNKNOWN_SPLITS = ("unknown_val", "unknown_test")
ALL_SPLITS = KNOWN_SPLITS + UNKNOWN_SPLITS
PRIORITY = {"test": 3, "unknown_test": 3, "val": 2, "unknown_val": 2, "train": 1}
TO_KNOWN = {"train": "train", "val": "val", "test": "test", "unknown_val": "val", "unknown_test": "test"}
TO_UNKNOWN = {"train": "unknown_val", "val": "unknown_val", "test": "unknown_test",
              "unknown_val": "unknown_val", "unknown_test": "unknown_test"}
ASSIGNMENT_COLUMNS = ["image_id", "species_id", "scientific_name", "observation_group", "observation_id",
                      "file_sha256", "split", "split_path", "active", "first_assigned", "last_updated"]


class SplitError(RuntimeError):
    pass


def _species_rng(seed: int, species_id: str) -> np.random.Generator:
    """Per-species RNG so adding one species never reshuffles another species' groups."""
    offset = int(hashlib.sha1(species_id.encode()).hexdigest()[:8], 16)
    return np.random.default_rng(seed + offset)


def _load_prior(path: Path) -> pd.DataFrame:
    if path.exists() and path.stat().st_size > 0:
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
        return df.reindex(columns=ASSIGNMENT_COLUMNS, fill_value="")
    return pd.DataFrame(columns=ASSIGNMENT_COLUMNS)


def _load_locked(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")}


def _strictest(splits) -> str | None:
    splits = [s for s in splits if s]
    return max(splits, key=lambda s: PRIORITY[s]) if splits else None


def greedy_group_assign(groups: dict[str, int], ratios: dict[str, float], fixed: dict[str, str],
                        rng: np.random.Generator) -> dict[str, str]:
    """Assign groups (id -> image count) to splits so image counts approach the ratios.
    `fixed` groups keep their split; remaining groups are shuffled then placed where the
    relative deficit is largest."""
    out = dict(fixed)
    total = sum(groups.values())
    counts = Counter()
    for g, s in fixed.items():
        counts[s] += groups[g]
    free = sorted(g for g in groups if g not in fixed)
    order = [free[i] for i in rng.permutation(len(free))] if free else []
    names = list(ratios)
    for g in order:
        def deficit(s):
            target = ratios[s] * total
            return (target - counts[s]) / target if target > 0 else -np.inf
        best = max(names, key=lambda s: (deficit(s), -names.index(s)))
        out[g] = best
        counts[best] += groups[g]
    # make sure val and test are never empty when there are enough groups
    for needed in ("test", "val"):
        if needed in ratios and counts[needed] == 0 and len(groups) >= 3:
            donor = max((g for g, s in out.items() if s == "train" and g not in fixed), key=lambda g: groups[g], default=None)
            if donor:
                out[donor] = needed
                counts["train"] -= groups[donor]
                counts[needed] += groups[donor]
    return out


def class_readiness(eligible: pd.DataFrame, catalog: list[Species], scfg: dict) -> list[dict]:
    rows = []
    extra = set(scfg.get("extra_class_species") or [])  # experiment configs only; the catalog stays unchanged
    for sp in catalog:
        if not (sp.training_enabled or sp.species_id in extra):
            continue
        g = eligible[eligible["species_id"] == sp.species_id]
        n_img, n_grp = len(g), g["observation_group"].nunique()
        reasons = []
        if n_img < scfg["min_images_per_class"]:
            reasons.append(f"{n_img} < {scfg['min_images_per_class']} approved images")
        if n_grp < scfg["min_groups_per_class"]:
            reasons.append(f"{n_grp} < {scfg['min_groups_per_class']} observation groups")
        rows.append({"species_id": sp.species_id, "scientific_name": sp.scientific_name,
                     "eligible_images": int(n_img), "eligible_groups": int(n_grp),
                     "ready": not reasons, "reasons": reasons})
    return rows


def prepare_splits(cfg: dict, materialize: bool = True) -> dict:
    scfg = cfg["split"]
    seed = int(cfg["project"]["seed"])
    root = project_root(cfg)
    catalog = load_catalog(project_path(cfg, "species_catalog"))
    cat = by_id(catalog)
    manifest_path = project_path(cfg, "image_manifest")
    df = load_manifest(manifest_path)
    if df.empty:
        raise SplitError("manifest is empty; download and validate images first")
    if (df["observation_group"] == "").any():
        raise SplitError("manifest has rows without observation_group; run scripts/validate_images.py first")

    eligible = df[training_eligible_mask(df, cfg)].copy()
    readiness = class_readiness(eligible, catalog, scfg)
    model_classes = sorted([r["species_id"] for r in readiness if r["ready"]])
    unknown_species = sorted(
        sid for sid in eligible["species_id"].unique()
        if sid in cat and sid not in model_classes and cat[sid].role in ("unknown_eval", "lookalike", "expansion_candidate"))

    prior = _load_prior(project_path(cfg, "split_assignments"))
    prior_split = dict(zip(prior["image_id"], prior["split"]))
    prior_first = dict(zip(prior["image_id"], prior["first_assigned"]))
    locked = _load_locked(project_path(cfg, "locked_test_groups"))

    assignment: dict[str, str] = {}
    notes: list[str] = []
    known_ratios = {k: float(scfg["ratios"][k]) for k in KNOWN_SPLITS}

    def group_table(sub: pd.DataFrame):
        sizes = sub.groupby("observation_group").size().to_dict()
        members = sub.groupby("observation_group")["image_id"].apply(list).to_dict()
        return sizes, members

    for sid in model_classes:
        sub = eligible[eligible["species_id"] == sid]
        sizes, members = group_table(sub)
        fixed = {}
        for g, ids in members.items():
            locked_hit = any(i in locked for i in ids) or any(o in locked for o in sub.loc[sub["observation_group"] == g, "observation_id"])
            prev = _strictest(prior_split.get(i, "") for i in ids)
            if locked_hit:
                fixed[g] = "test"
            elif prev:
                fixed[g] = TO_KNOWN[prev]
        split_of = greedy_group_assign(sizes, known_ratios, fixed, _species_rng(seed, sid))
        for g, ids in members.items():
            for i in ids:
                assignment[i] = split_of[g]

    if unknown_species:
        frac = float(scfg["unknown_val_fraction"])
        species_part: dict[str, str] = {}
        for sid in unknown_species:
            ids = eligible.loc[eligible["species_id"] == sid, "image_id"]
            prev = Counter(TO_UNKNOWN[prior_split[i]] for i in ids if prior_split.get(i))
            if prev:
                species_part[sid] = prev.most_common(1)[0][0]
        rng = np.random.default_rng(seed)
        new = [s for s in unknown_species if s not in species_part]
        for sid in [new[i] for i in rng.permutation(len(new))] if new else []:
            n_val = sum(1 for v in species_part.values() if v == "unknown_val")
            n_all = len(species_part) + 1
            species_part[sid] = "unknown_val" if n_val < round(frac * n_all) or (n_val == 0 and n_all > 1) else "unknown_test"
        if len(unknown_species) == 1:
            sid = unknown_species[0]
            notes.append(f"Only one unsupported species ({cat[sid].scientific_name}); unknown_val/unknown_test are split by "
                         "observation group within that species, so they are NOT species-disjoint.")
            sub = eligible[eligible["species_id"] == sid]
            sizes, members = group_table(sub)
            fixed = {g: TO_UNKNOWN[p] for g, ids in members.items() if (p := _strictest(prior_split.get(i, "") for i in ids))}
            split_of = greedy_group_assign(sizes, {"unknown_val": frac, "unknown_test": 1 - frac}, fixed, rng)
            for g, ids in members.items():
                for i in ids:
                    assignment[i] = split_of[g]
        else:
            for sid in unknown_species:
                sub = eligible[eligible["species_id"] == sid]
                for g, ids in sub.groupby("observation_group")["image_id"]:
                    p = _strictest(prior_split.get(i, "") for i in ids)
                    target = TO_UNKNOWN[p] if p else species_part[sid]
                    for i in ids:
                        assignment[i] = target

    leakage = check_leakage(df, assignment, int(cfg["validation"]["phash_hamming_threshold"]))
    if leakage["violations"]:
        raise SplitError(f"leakage check failed: {leakage}")

    now = utc_now_iso()
    rows = []
    for _, r in df[df["image_id"].isin(assignment)].iterrows():
        split = assignment[r["image_id"]]
        sp = cat[r["species_id"]]
        rows.append({
            "image_id": r["image_id"], "species_id": r["species_id"], "scientific_name": r["scientific_name"],
            "observation_group": r["observation_group"], "observation_id": r["observation_id"],
            "file_sha256": r["file_sha256"], "split": split,
            "split_path": f"{cfg['paths'][split]}/{sp.folder}/{r['image_id']}.jpg",
            "active": "true", "first_assigned": prior_first.get(r["image_id"]) or now, "last_updated": now,
        })
    active = pd.DataFrame(rows, columns=ASSIGNMENT_COLUMNS)
    inactive = prior[~prior["image_id"].isin(assignment)].copy()
    inactive["active"] = "false"  # kept so a re-approved image returns to its historical partition
    assignments = pd.concat([active, inactive], ignore_index=True).sort_values(["split", "species_id", "image_id"])

    version = dataset_version_id(active)
    counts = {s: active[active["split"] == s].groupby("scientific_name").size().to_dict() for s in ALL_SPLITS}
    group_counts = {s: active[active["split"] == s].groupby("scientific_name")["observation_group"].nunique().to_dict()
                    for s in ALL_SPLITS}

    if not is_provisional(cfg):  # provisional pilots keep their assignments in their own folder only
        for i, row in df.iterrows():
            df.at[i, "split"] = assignment.get(row["image_id"], "")
        save_manifest(df, manifest_path)
    atomic_write_text(project_path(cfg, "split_assignments"), assignments.to_csv(index=False))

    mapping = build_class_mapping(model_classes, cat, version, is_provisional(cfg))
    write_json(project_path(cfg, "class_mapping"), mapping)
    version_info = {
        "dataset_version": version, "created": now, "num_classes": len(model_classes),
        "image_counts": counts, "observation_group_counts": group_counts,
        "split_config": scfg, "validation_config": cfg["validation"],
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
    }
    write_json(project_path(cfg, "dataset_version"), version_info)

    if materialize:
        materialize_splits(cfg, active, df, cat, root)

    report = {
        "generated": now, "dataset_version": version, "provisional": is_provisional(cfg),
        "ready_for_training": len(model_classes) >= 2,
        "model_classes": [cat[s].scientific_name for s in model_classes],
        "unsupported_species_pool": {cat[s].scientific_name: _first_split(active, s) for s in unknown_species},
        "class_readiness": readiness, "image_counts": counts, "observation_group_counts": group_counts,
        "leakage_check": leakage, "notes": notes,
    }
    if len(model_classes) < 2:
        report["notes"].append("Fewer than two classes meet the minimum verified-data requirements; training is blocked.")
    for sid in model_classes:
        n_test = counts["test"].get(cat[sid].scientific_name, 0)
        if n_test < scfg["min_test_images_per_class"]:
            report["notes"].append(f"{cat[sid].scientific_name}: only {n_test} test images (< {scfg['min_test_images_per_class']}).")
    write_json(project_path(cfg, "reports") / "split_report.json", report)
    return report


def _first_split(active: pd.DataFrame, sid: str) -> dict:
    return active[active["species_id"] == sid]["split"].value_counts().to_dict()


def check_leakage(df: pd.DataFrame, assignment: dict[str, str], phash_threshold: int) -> dict:
    sub = df[df["image_id"].isin(assignment)].copy()
    sub["split"] = sub["image_id"].map(assignment)
    out = {"images_checked": int(len(sub)), "violations": 0}
    for key in ("observation_group", "observation_id", "file_sha256"):
        k = sub[sub[key] != ""].groupby(key)["split"].nunique()
        out[f"{key}_cross_split"] = int((k > 1).sum())
    split_of = dict(zip(sub["image_id"], sub["split"]))
    pairs = near_duplicate_pairs(sub["image_id"].tolist(), sub["phash"].tolist(), phash_threshold)
    out["near_duplicate_cross_split"] = sum(1 for a, b, _ in pairs if split_of[a] != split_of[b])
    out["violations"] = sum(v for k, v in out.items() if k.endswith("_cross_split"))
    return out


def dataset_version_id(active: pd.DataFrame) -> str:
    lines = sorted(f"{r.image_id},{r.file_sha256},{r.split},{r.species_id}" for r in active.itertuples())
    digest = hashlib.sha256("\n".join(lines).encode()).hexdigest()[:10]
    return f"ds-{pd.Timestamp.utcnow().strftime('%Y%m%d')}-{digest}"


def build_class_mapping(model_classes: list[str], cat: dict, dataset_version: str, provisional: bool = False) -> dict:
    classes = []
    for idx, sid in enumerate(model_classes):
        sp = cat[sid]
        classes.append({
            "index": idx, "species_id": sid, "scientific_name": sp.scientific_name, "folder": sp.folder,
            "common_name": sp.primary_common_name, "family": sp.family, "gbif_taxon_key": sp.gbif_taxon_key,
            "ecological_status": sp.ecological_status, "status_verification": sp.status_verification,
            "is_target_invasive": sp.ecological_status == "target_invasive",
        })
    return {
        "schema_version": "1.0",
        "dataset_version": dataset_version,
        "num_classes": len(classes),
        "status": "ready" if len(classes) >= 2 else "insufficient_verified_data",
        "provisional": provisional,
        "index_note": "Output neuron i corresponds to classes[i]. Integrations must key on species_id, "
                      "not on the index, because indices can change between model versions.",
        "classes": classes,
    }


def materialize_splits(cfg: dict, active: pd.DataFrame, manifest: pd.DataFrame, cat: dict, root: Path) -> None:
    """Rebuild the derived split folders as EXIF-corrected RGB JPEGs."""
    for split in ALL_SPLITS:
        d = project_path(cfg, split)
        if d.exists():
            for sub in d.iterdir():
                if sub.is_dir():
                    shutil.rmtree(sub)
        d.mkdir(parents=True, exist_ok=True)
    src_of = dict(zip(manifest["image_id"], manifest["local_path"]))
    scfg = cfg["split"]
    for r in active.itertuples():
        raw = resolve_path(src_of[r.image_id], root)
        reviewed = project_path(cfg, "reviewed") / cat[r.species_id].folder / raw.name
        src = reviewed if reviewed.exists() else raw
        save_normalized_jpeg(src, resolve_path(r.split_path, root), int(scfg["normalize_max_side"]), int(scfg["jpeg_quality"]))


def load_split_frame(cfg: dict, split: str) -> pd.DataFrame:
    """Active assignments for one split, with absolute file paths."""
    df = _load_prior(project_path(cfg, "split_assignments"))
    df = df[(df["split"] == split) & (df["active"] == "true")].copy()
    root = project_root(cfg)
    df["abs_path"] = df["split_path"].map(lambda p: str(resolve_path(p, root)))
    return df.reset_index(drop=True)
