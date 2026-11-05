"""Freeze approved weak-class photos into a grouped experimental dataset v2.

The original 11-class test partition remains byte-for-byte represented in the
manifest and is never assigned to train/validation. The script fails closed on
missing approvals, provenance, rights, decode/checksum problems, or leakage.
"""
from __future__ import annotations

import csv
import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from geoflora_ml.collection.licensing import training_license_eligible

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "storage/datasets/curated/auto_6ae5cd74af23d762feaa0889"
OUT = ROOT / "storage/datasets/curated/auto_6ae5cd74af23d762feaa0889_weakreview_v2_20261101"
QUEUE = ROOT / "docs/weak-class-manual-review-queue-2026-11-01.csv"
DECISIONS = ROOT / "docs/weak-class-human-decisions-2026-11-01.json"
AUDIT = ROOT / "docs/weak-class-visual-audit-2026-11-01.json"
MIN_DIMENSION = 320


def read_csv(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def split_for(group: str) -> str:
    # Stable class/group hash; roughly one in five approved new groups goes to
    # validation. Existing validation rows remain validation; old test is held.
    value = int(hashlib.sha256(group.encode()).hexdigest()[:8], 16) % 5
    return "validation" if value == 0 else "train"


def main():
    global OUT
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, help="New curated dataset directory; must not already exist")
    args = parser.parse_args()
    if args.output:
        OUT = args.output.resolve() if args.output.is_absolute() else (ROOT / args.output).resolve()
        if not OUT.is_relative_to((ROOT / "storage/datasets/curated").resolve()):
            raise SystemExit("Output must remain under storage/datasets/curated")
    if OUT.exists():
        raise SystemExit(f"Refusing to overwrite immutable dataset: {OUT}")
    original_manifest = read_csv(BASE / "manifest.csv")
    # Preserve historical test rows byte-for-byte for comparable scoring, while
    # removing redundant exact-hash repetitions from development partitions.
    seen_development_hashes = set()
    manifest = []
    base_duplicate_rows_removed = 0
    for row in original_manifest:
        if row["split"] == "test":
            manifest.append(row)
        elif row["sha256"] in seen_development_hashes:
            base_duplicate_rows_removed += 1
        else:
            seen_development_hashes.add(row["sha256"])
            manifest.append(row)
    queue = read_csv(QUEUE)
    decisions = json.loads(DECISIONS.read_text(encoding="utf-8"))["decisions"]
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    mapping = json.loads((BASE / "class_mapping.json").read_text(encoding="utf-8"))
    class_ids = {item["id"] for item in mapping["classes"]}
    frozen_hashes = {item["sha256"] for item in audit["near_duplicate_matches_to_frozen"]}
    quality_by_sha = {record["sha256"]: record["quality"] for group in audit["groups"] for record in group["records"]}
    base_hashes = {row["sha256"] for row in original_manifest}

    # Known cross-provider alias: retain the direct iNaturalist record only.
    alias_group = "gbif:occurrence:1945468596"
    kept_groups = defaultdict(list)
    excluded = Counter()
    review_snapshot = []
    for row in queue:
        key = f'{row["species_id"]}|{row["group_id"]}'
        decision = decisions.get(key)
        if not decision:
            excluded["unreviewed"] += 1
            continue
        if decision.get("decision") != "approve":
            excluded[decision.get("decision", "invalid_decision")] += 1
            continue
        if len((decision.get("rationale") or "").strip()) < 10:
            excluded["missing_visible_rationale"] += 1
            continue
        if decision.get("reviewer") != "owner_local_review":
            excluded["invalid_reviewer"] += 1
            continue
        if row["group_id"] == alias_group:
            excluded["cross_provider_alias"] += 1
            continue
        if row["sha256"] in frozen_hashes or row["sha256"] in base_hashes:
            excluded["frozen_or_exact_duplicate"] += 1
            continue
        if row["species_id"] not in class_ids:
            excluded["class_not_in_preserved_mapping"] += 1
            continue
        if row.get("country_code") != "PH" or not all(row.get(k) for k in ("source_url", "source_id", "group_id", "attribution", "locality", "sha256")):
            excluded["insufficient_provenance"] += 1
            continue
        if not training_license_eligible(row.get("license"), row.get("attribution")):
            excluded["license_ineligible"] += 1
            continue
        image = (ROOT / row["local_image_path"]).resolve()
        if not image.is_relative_to(ROOT.resolve()) or not image.is_file() or sha(image) != row["sha256"]:
            excluded["missing_or_checksum_mismatch"] += 1
            continue
        try:
            with Image.open(image) as opened:
                opened.verify()
            with Image.open(image) as opened:
                width, height = opened.size
        except Exception:
            excluded["decode_failure"] += 1
            continue
        # Exclude objectively small originals from model training. Heuristic
        # focus/exposure flags remain in the snapshot for informed review.
        if min(width, height) < MIN_DIMENSION:
            excluded["below_minimum_resolution"] += 1
            continue
        if "possible_exposure_loss" in quality_by_sha.get(row["sha256"], {}).get("flags", []):
            excluded["severe_exposure_flag"] += 1
            continue
        row_out = {
            "species_id": row["species_id"], "scientific_name": row["species_id"].replace("_", " "),
            "source": row["source"], "source_id": row["source_id"], "source_url": row["source_url"],
            "group_id": f'{row["species_id"]}:{row["source"]}:{row["group_id"]}',
            "observation_id": row["group_id"], "local_path": row["local_image_path"], "sha256": row["sha256"],
            "license": row["license"], "attribution": row["attribution"], "country_code": "PH",
            "locality": row["locality"], "observed_at": row.get("observed_at", ""),
            "split": split_for(f'{row["species_id"]}|{row["group_id"]}'),
            "review_status": "owner_visual_review_approved", "label_basis": "owner_visual_review_not_independent_expert_verification",
            "review_rationale": decision["rationale"], "reviewed_at": decision.get("reviewedAt", ""),
            "review_decision_key": key, "width": width, "height": height,
        }
        kept_groups[(row_out["species_id"], row_out["group_id"])].append(row_out)
        review_snapshot.append({"decision": decision, "record": row_out, "independent_expert_verification": False})

    additions = [row for records in kept_groups.values() for row in records]
    if not additions:
        raise SystemExit("No eligible reviewed images; dataset not created")

    # Ensure new files and their observation groups do not cross partitions.
    group_splits = defaultdict(set)
    for row in additions:
        group_splits[row["group_id"]].add(row["split"])
    if any(len(value) != 1 for value in group_splits.values()):
        raise SystemExit("Observation-group split leakage")

    combined = manifest + additions
    addition_hashes = [row["sha256"] for row in additions]
    if len(set(addition_hashes)) != len(addition_hashes) or set(addition_hashes) & base_hashes:
        raise SystemExit("Exact duplicate entered from approved additions")
    # Preserve the frozen class mapping exactly.
    split_counts = {class_id: Counter(row["split"] for row in combined if row["species_id"] == class_id) for class_id in class_ids}
    if any(not counts["train"] or not counts["validation"] for counts in split_counts.values()):
        raise SystemExit("A class is missing train or validation data")
    if any(row["split"] == "test" and row not in manifest for row in combined):
        raise SystemExit("New data must not enter the historical test partition")

    OUT.mkdir(parents=True)
    fields = sorted(set().union(*(row.keys() for row in combined)))
    with (OUT / "manifest.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader(); writer.writerows(combined)
    (OUT / "class_mapping.json").write_text(json.dumps(mapping, indent=2), encoding="utf-8")
    (OUT / "species.yaml").write_text((BASE / "species.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    (OUT / "reviews_snapshot.json").write_text(json.dumps(review_snapshot, indent=2), encoding="utf-8")
    metadata = {
        "version": OUT.name, "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "base_dataset": str(BASE.relative_to(ROOT)), "base_manifest_sha256": sha(BASE / "manifest.csv"),
        "manifest_sha256": sha(OUT / "manifest.csv"), "class_mapping_sha256": sha(OUT / "class_mapping.json"),
        "images": len(combined), "base_images": len(manifest), "base_development_duplicate_rows_removed": base_duplicate_rows_removed, "approved_addition_images": len(additions),
        "approved_addition_groups": len(kept_groups), "per_class_split_counts": {k: dict(v) for k, v in split_counts.items()},
        "excluded_counts": dict(excluded), "excluded_frozen_match_sha256": sorted(frozen_hashes),
        "historical_test_policy": "Original test rows remain test only; no candidate image matching a frozen row included; no test rows used in fitting or checkpoint selection.",
        "new_addition_split_policy": "Stable SHA256(species|source-observation-group) modulo 5: one bucket validation, others train; groups remain intact.",
        "label_limit": "Owner visual approval and generic visible-feature rationale; not independent expert botanical verification.",
        "rights_limit": "New additions restricted to CC0/CC-BY/CC-BY-SA with attribution; CC BY-NC excluded. Base candidate corpus contains CC BY-NC records and candidate remains research-only pending client-use permission.",
        "quality_rule": f"Verified decode/checksum; originals with min dimension below {MIN_DIMENSION}px excluded. Soft-focus/exposure cues preserved for interpretation; no automated identity claims.",
    }
    (OUT / "dataset_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps({"dataset": str(OUT.relative_to(ROOT)), "base_images": len(manifest), "added_images": len(additions), "added_groups": len(kept_groups), "added_by_class": {k: {"images": sum(r["species_id"] == k for r in additions), "groups": len({r["group_id"] for r in additions if r["species_id"] == k})} for k in sorted(class_ids)}, "excluded": dict(excluded), "per_class_split_counts": metadata["per_class_split_counts"], "manifest_sha256": metadata["manifest_sha256"]}, indent=2))


if __name__ == "__main__":
    main()
