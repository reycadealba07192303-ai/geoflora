"""Read manifest metadata only to audit historical-test overlap with auto-training inputs."""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from model_promotion import _observation_keys, benchmark_hashes
from auto_training_worker import benchmark_lookalike_filter
DATASETS = {
    "v3": ROOT / "storage/datasets/curated/v3/manifest.csv",
    "v5": ROOT / "storage/datasets/curated/v5_part2_final_five_classes/manifest.csv",
    "11class": ROOT / "storage/datasets/curated/auto_6ae5cd74af23d762feaa0889_weakreview_v3_20261101/manifest.csv",
}
OUT = ROOT / "docs/training-holdout-boundary-audit-2026-11-01.json"


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def ids(rows, fields):
    return {str(row.get(field)) for row in rows for field in fields if row.get(field)}


def main():
    datasets = {name: read(path) for name, path in DATASETS.items()}
    v5_train = [r for r in datasets["v5"] if r["split"] == "train"]
    v5_validation = [r for r in datasets["v5"] if r["split"] == "validation"]
    v5_test = [r for r in datasets["v5"] if r["split"] == "test"]
    non_test = v5_train + v5_validation
    non_test_hashes = ids(non_test, ["sha256"])
    non_test_groups = set().union(*(_observation_keys(r) for r in non_test)) if non_test else set()
    historical_test_rows = {}
    for manifest in sorted((ROOT / "storage/datasets/curated").rglob("manifest.csv")):
        try:
            rows = [r for r in read(manifest) if r.get("split") == "test"]
        except Exception:
            continue
        if rows:
            historical_test_rows[manifest.relative_to(ROOT).as_posix()] = rows
    all_historical_rows = [r for rows in historical_test_rows.values() for r in rows]
    historical_hashes = ids(all_historical_rows, ["sha256"])
    historical_groups = set().union(*(_observation_keys(r) for r in all_historical_rows)) if all_historical_rows else set()
    held_hashes, held_groups = benchmark_hashes()
    safe_v5_base = [r for r in non_test if r.get("sha256") not in held_hashes and not (_observation_keys(r) & held_groups)]
    same_as_test, save_phash = benchmark_lookalike_filter()
    exact_group_safe_v5_base = len(safe_v5_base)
    safe_v5_base = [r for r in safe_v5_base if not same_as_test(r["sha256"], ROOT / r["local_path"])]
    save_phash()
    remaining_test_hash_overlap = len(ids(safe_v5_base, ["sha256"]) & historical_hashes)
    remaining_test_group_overlap = len(set().union(*(_observation_keys(r) for r in safe_v5_base)) & historical_groups) if safe_v5_base else 0
    report = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "method": "Manifest metadata plus perceptual-hash comparison; images were decoded for duplicate screening but not scored by a classifier.",
        "manifest_counts": {name: {"rows": len(rows), "splits": dict(Counter(r["split"] for r in rows))} for name, rows in datasets.items()},
        "automatic_worker_policy": "Worker excludes hashes and normalized observation identities for every curated historical test partition, then excludes perceptual near-duplicates against historical test images from baseline and consented additions.",
        "auto_training_source_overlap": {
            "v5_test_exact_hashes_in_v5_train_validation": sum(r.get("sha256") in non_test_hashes for r in v5_test),
            "v5_test_observation_or_near_duplicate_groups_in_v5_train_validation": sum(bool({str(r.get("group_id", "")), str(r.get("near_duplicate_group_id", ""))} & non_test_groups) for r in v5_test),
            "any_curated_test_partition_rows": sum(len(rows) for rows in historical_test_rows.values()),
            "unique_any_curated_test_hashes": len(historical_hashes),
            "any_curated_test_hashes_in_v5_train_validation": len(historical_hashes & non_test_hashes),
            "any_curated_test_group_ids_in_v5_train_validation": len(historical_groups & non_test_groups),
            "historical_test_hashes_in_candidate_train_validation_after_worker_filter": remaining_test_hash_overlap,
            "historical_test_groups_in_candidate_train_validation_after_worker_filter": remaining_test_group_overlap,
            "effective_held_out_hash_count": len(held_hashes),
            "effective_held_out_group_key_count": len(held_groups),
            "v5_train_validation_rows_left_after_exact_and_observation_group_filter": exact_group_safe_v5_base,
            "v5_train_validation_rows_left_after_perceptual_duplicate_filter": len(safe_v5_base),
            "test_manifests": {path: len(rows) for path, rows in historical_test_rows.items()},
        },
        "earlier_historical_test_overlap_with_auto_training_base": {},
        "user_report_training_gate": "Automatic job query requires trainingConsent=true AND trainingCandidateStatus=approved AND trainingJobId=null. Report approval without contributor consent leaves trainingCandidateStatus=not_requested.",
        "interpretation": "All historical curated test exact hashes and normalized source observation keys are held out, and baseline/eligible contribution images are also perceptually compared with historical test photos (Hamming distance <= 6). 24 v5 train/validation rows remain from the baseline; pending, AI-only, research-grade-only, rejected, non-consented, and license-ineligible additions are excluded. No training was run.",
    }
    for name in ("v3", "11class"):
        test = [r for r in datasets[name] if r["split"] == "test"]
        report["earlier_historical_test_overlap_with_auto_training_base"][name] = {
            "test_rows": len(test),
            "exact_hashes_in_v5_train_validation": sum(r.get("sha256") in non_test_hashes for r in test),
            "observation_or_near_duplicate_groups_in_v5_train_validation": sum(bool({str(r.get("group_id", "")), str(r.get("near_duplicate_group_id", ""))} & non_test_groups) for r in test),
        }
    assert remaining_test_hash_overlap == 0 and remaining_test_group_overlap == 0, report["auto_training_source_overlap"]
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
