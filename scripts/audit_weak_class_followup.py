"""Audit remaining strict-rights field observations without changing labels."""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/ml/src"))
from geoflora_ml.collection.licensing import training_license_eligible
from geoflora_ml.datasets.manifest import read_jsonl

FROZEN = ROOT / "storage/datasets/curated/auto_6ae5cd74af23d762feaa0889_weakreview_v3_20261101/manifest.csv"
DECISIONS = ROOT / "docs/weak-class-human-decisions-2026-11-01.json"
OUT = ROOT / "docs/weak-class-followup-available-inventory-2026-11-01.json"
QUEUE = ROOT / "docs/weak-class-followup-review-queue-2026-11-01.csv"
WEAK = {"broussonetia_papyrifera", "mikania_micrantha", "coccinia_grandis"}


def csv_rows(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def image_quality(path):
    with Image.open(path) as im:
        width, height = im.size
        gray = np.asarray(im.convert("L").resize((128, 128), Image.Resampling.LANCZOS), dtype=np.float32)
    lap = -4 * gray + np.roll(gray, 1, 0) + np.roll(gray, -1, 0) + np.roll(gray, 1, 1) + np.roll(gray, -1, 1)
    clipped = float(((gray <= 8) | (gray >= 247)).mean())
    flags = []
    if min(width, height) < 320: flags.append("small_image")
    if float(lap.var()) < 18: flags.append("possible_soft_focus")
    if clipped > 0.35: flags.append("possible_exposure_loss")
    return f"{width}x{height}", ",".join(flags), round(float(lap.var()), 2), round(clipped, 3)


def main():
    frozen = csv_rows(FROZEN)
    frozen_hashes = {r.get("sha256") for r in frozen}
    frozen_groups = set()
    for r in frozen:
        for value in (r.get("observation_id"), r.get("group_id"), r.get("near_duplicate_group_id")):
            if value:
                frozen_groups.add(str(value))
    decisions = json.loads(DECISIONS.read_text(encoding="utf-8"))["decisions"]
    decision_index = {}
    for d in decisions.values():
        decision_index[(d["species_id"], str(d["group_id"]))] = d
    inventory = {"generated_at_utc": datetime.now(timezone.utc).isoformat(), "basis": "Strict CC0/CC BY/CC BY-SA allowlist; PH iNaturalist field-photo records only; exact and observation-group duplicates removed against frozen v3; source/community labels are not expert verification.", "classes": {}, "new_pending_review_queue": str(QUEUE.relative_to(ROOT).as_posix()), "newly_collected_pool": "storage/datasets/review_pools/weak_classes_followup_20261101/review_queue.csv", "test_set_status": "No new observation has independent botanical review; zero records designated as a blind test set."}
    queue = []
    for sid in sorted(WEAK):
        folders = [ROOT / f"storage/datasets/staging/invasive_{sid}_ph"]
        if sid == "mikania_micrantha":
            folders.append(ROOT / "storage/datasets/staging/mikania_micrantha_ph")
        rows = []
        for folder in folders:
            manifest = folder / "raw/manifest.jsonl"
            if manifest.exists():
                rows.extend({**r, "_dataset_root": folder.relative_to(ROOT).as_posix()} for r in read_jsonl(manifest))
        valid_groups = defaultdict(list)
        excluded = Counter()
        raw_eligible_groups = set()
        for r in rows:
            if r.get("source") != "inaturalist":
                excluded["not_iNaturalist_field_photo"] += 1; continue
            if r.get("country_code") != "PH" or not r.get("source_url") or not r.get("observation_id"):
                excluded["insufficient_PH_provenance"] += 1; continue
            if not training_license_eligible(r.get("license"), r.get("attribution")):
                excluded["license_not_in_training_allowlist"] += 1; continue
            obs = str(r["observation_id"])
            raw_eligible_groups.add(obs)
            row_root = (ROOT / r["_dataset_root"]).resolve()
            path = (row_root / str(r.get("local_path", ""))).resolve()
            if not path.is_relative_to(row_root) or not path.is_file():
                excluded["missing_or_unsafe_image"] += 1; continue
            actual_sha = digest(path)
            if actual_sha != r.get("sha256"):
                excluded["checksum_mismatch"] += 1; continue
            dims, flags, sharpness, clipped = image_quality(path)
            r["_quality"] = {"dimensions": dims, "flags": flags, "laplacian_variance": sharpness, "clipped_fraction": clipped}
            if actual_sha in frozen_hashes:
                excluded["exact_duplicate_of_frozen"] += 1; continue
            if obs in frozen_groups or str(r.get("group_id", "")) in frozen_groups or str(r.get("near_duplicate_group_id", "")) in frozen_groups:
                excluded["observation_or_near_duplicate_of_frozen"] += 1; continue
            valid_groups[obs].append(r)
        decision_counts = Counter()
        explicitly_training_ineligible = 0
        for obs, group_rows in valid_groups.items():
            group_id = str(group_rows[0].get("group_id") or obs)
            decision = decision_index.get((sid, obs)) or decision_index.get((sid, group_id))
            status = decision.get("decision") if decision else "pending"
            decision_counts[status] += 1
            include_for_human_queue = status in {"pending", "uncertain"}
            queue_status = status
            if status == "approve" and decision and decision.get("training_eligible") is False:
                explicitly_training_ineligible += 1
            elif status == "approve" and decision and decision.get("basis") == "human_visual_review_pending_independent_taxonomic_citation":
                include_for_human_queue = True
                queue_status = "owner_visual_approved_needs_independent_botanical_verification"
            if include_for_human_queue:
                for r in group_rows:
                    q = r["_quality"]
                    queue.append({"species_id": sid, "observation_id": obs, "group_id": group_id, "image_sha256": r["sha256"], "source_id": r.get("source_id", ""), "source_url": r.get("source_url", ""), "license": r.get("license", ""), "attribution": r.get("attribution", ""), "country_code": r.get("country_code", ""), "locality": r.get("locality", ""), "observed_at": r.get("observed_at", ""), "image_dimensions": q["dimensions"], "quality_flags": q["flags"], "laplacian_variance": q["laplacian_variance"], "clipped_fraction": q["clipped_fraction"], "local_path": (row_root / r["local_path"]).relative_to(ROOT).as_posix(), "review_status": queue_status, "reviewer": decision.get("reviewer", "") if decision else "", "review_rationale": decision.get("rationale", "") if decision else "", "label_basis": "iNaturalist research-grade/community identification; independent botanical verification required"})
        inventory["classes"][sid] = {"staging_images": len(rows), "strict_rights_PH_field_observation_groups_seen": len(raw_eligible_groups), "unique_not_in_frozen_observation_groups": len(valid_groups), "images_in_unique_groups": sum(map(len, valid_groups.values())), "review_decision_groups": dict(decision_counts), "owner_approved_but_explicitly_training_ineligible_groups": explicitly_training_ineligible, "excluded_image_records": dict(excluded), "newly_collected_in_followup_scan": 0}
    fields = list(queue[0]) if queue else ["species_id", "observation_id", "group_id", "image_sha256", "source_id", "source_url", "license", "attribution", "country_code", "locality", "observed_at", "local_path", "review_status", "reviewer", "review_rationale", "label_basis"]
    with QUEUE.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields); writer.writeheader(); writer.writerows(queue)
    inventory["new_unresolved_candidate_images"] = len(queue)
    inventory["new_unresolved_observation_groups"] = len({(r["species_id"], r["observation_id"]) for r in queue})
    OUT.write_text(json.dumps(inventory, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(inventory, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
