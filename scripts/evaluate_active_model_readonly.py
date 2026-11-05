"""Read-only evaluation of the installed v3 classifier and held-out split audits."""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/ml/src"))
from geoflora_ml.datasets.audit import load_current_reviews  # noqa: E402
from geoflora_ml.datasets.duplicates import group_near_duplicates  # noqa: E402
from geoflora_ml.inference.preprocess import preprocess_rgb_batch, rgb_array  # noqa: E402
from geoflora_ml.inference.predictor import PlantPredictor  # noqa: E402


DATA = ROOT / "storage/datasets"
ACTIVE = ROOT / "storage/models"
V3 = DATA / "curated/v3/manifest.csv"
NON_TARGET = DATA / "curated/owner_approved_five_class_plus_mikania_supplement_20261031/manifest.csv"
TARGET_IDS = ["chromolaena_odorata", "lantana_camara", "pontederia_crassipes"]


def read_manifest(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def image_path(row: dict[str, str]) -> Path:
    relative = Path(row["local_path"])
    path = (ROOT / relative if relative.parts[:2] == ("storage", "datasets") else DATA / relative).resolve()
    if not path.is_relative_to(DATA.resolve()):
        raise ValueError(f"Unsafe image path in manifest: {row['local_path']}")
    return path


def image_batch(rows: list[dict[str, str]]) -> np.ndarray:
    images = []
    for row in rows:
        path = image_path(row)
        with Image.open(path) as image:
            images.append(rgb_array(image))
    return preprocess_rgb_batch(images)


def evaluate_split(predictor: PlantPredictor, rows: list[dict[str, str]]) -> dict[str, object]:
    classes = predictor.species
    order = [entry["id"] for entry in classes]
    indices = {species_id: index for index, species_id in enumerate(order)}
    y_true = np.asarray([indices[row["species_id"]] for row in rows], dtype=np.int64)
    scores = np.asarray(predictor._model.predict(image_batch(rows), verbose=0))
    y_pred = scores.argmax(axis=1)
    report = classification_report(y_true, y_pred, labels=list(range(len(order))), target_names=order, output_dict=True, zero_division=0)
    misclassified = [
        {"true_species": rows[index]["species_id"], "predicted_species": order[int(y_pred[index])],
         "confidence": float(scores[index, int(y_pred[index])]), "local_path": rows[index]["local_path"],
         "group_id": rows[index]["group_id"]}
        for index in range(len(rows)) if y_true[index] != y_pred[index]
    ]
    return {
        "images": len(rows),
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "per_class": {name: report[name] for name in order},
        "macro_avg": report["macro avg"],
        "confusion_matrix_rows_actual_columns_predicted": confusion_matrix(y_true, y_pred, labels=list(range(len(order)))).tolist(),
        "misclassified": misclassified,
    }


def main() -> None:
    predictor = PlantPredictor()
    if not predictor.ready or predictor.model_version != "mobilenetv2_v3_seed42":
        raise RuntimeError(f"Unexpected active model state: ready={predictor.ready}, version={predictor.model_version}")
    rows = read_manifest(V3)
    reviews = load_current_reviews(DATA)

    splits: dict[str, object] = {}
    for split in ("train", "validation", "test"):
        selected = [row for row in rows if row["split"] == split]
        splits[split] = evaluate_split(predictor, selected)

    class_counts = {}
    for species_id in TARGET_IDS:
        selected = [row for row in rows if row["split"] == "train" and row["species_id"] == species_id]
        approved = 0
        for row in selected:
            review = reviews.get((row["source"], row["source_id"]), {})
            decision = review.get("decision")
            effective = review.get("relabel_to") if decision == "relabelled" else row["original_species_id"]
            approved += int(decision in {"approved", "relabelled"} and effective == row["species_id"])
        class_counts[species_id] = {"train_images": len(selected), "owner_approved_current_labels": approved,
                                    "observation_groups": len({row["group_id"] for row in selected})}

    partitions: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in rows:
        for field in ("sha256", "group_id", "near_duplicate_group_id"):
            partitions[(field, row.get(field, ""))].add(row["split"])
    recomputed, near_groups = group_near_duplicates(rows, DATA)
    near_partitions: dict[str, set[str]] = defaultdict(set)
    near_group_sizes: Counter[tuple[str, str]] = Counter()
    for row in recomputed:
        near_partitions[row["near_duplicate_group_id"]].add(row["split"])
        near_group_sizes[(row["near_duplicate_group_id"], row["split"])] += 1
    cross_keys = [key for key, values in partitions.items() if len(values) > 1]
    cross_near = [key for key, values in near_partitions.items() if len(values) > 1]
    observation_group_sizes: Counter[tuple[str, str]] = Counter((row["group_id"], row["split"]) for row in rows)
    within_split_repeats = {
        split: {
            "observation_groups_with_multiple_rows": sum(size > 1 for (group, part), size in observation_group_sizes.items() if part == split),
            "extra_observation_rows": sum(size - 1 for (group, part), size in observation_group_sizes.items() if part == split and size > 1),
            "near_duplicate_groups_with_multiple_rows": sum(size > 1 for (group, part), size in near_group_sizes.items() if part == split),
            "extra_near_duplicate_rows": sum(size - 1 for (group, part), size in near_group_sizes.items() if part == split and size > 1),
        }
        for split in ("train", "validation", "test")
    }
    independence_support = {}
    for split in ("train", "validation", "test"):
        selected = [row for row in recomputed if row["split"] == split]
        independence_support[split] = {
            "images": len(selected),
            "observation_groups": len({row["group_id"] for row in selected}),
            "recomputed_near_duplicate_groups": len({row["near_duplicate_group_id"] for row in selected}),
            "by_species_observation_groups": {
                species_id: len({row["group_id"] for row in selected if row["species_id"] == species_id})
                for species_id in TARGET_IDS
            },
        }
    seen_test_near_groups: set[str] = set()
    test_near_representatives = []
    for row in recomputed:
        if row["split"] == "test" and row["near_duplicate_group_id"] not in seen_test_near_groups:
            seen_test_near_groups.add(row["near_duplicate_group_id"])
            test_near_representatives.append(row)

    unknown_rows = [row for row in read_manifest(NON_TARGET)
                    if row["split"] == "test" and row["species_id"] not in TARGET_IDS]
    # Exclude exact byte matches to any v3 image before unknown-class evaluation.
    v3_hashes = {row["sha256"] for row in rows}
    unknown_rows = [row for row in unknown_rows if row["sha256"] not in v3_hashes]
    unknown_results = []
    for row in unknown_rows:
        result = predictor.predict(image_path(row).read_bytes())
        unknown_results.append({"true_species": row["species_id"], "top_supported_species": result.candidates[0]["species"]["id"],
                                "top_score": result.confidence, "threshold_status": result.status})
    unknown_summary = {
        "dataset": "owner-approved five-class plus Mikania supplement held-out split",
        "limitations": "Owner-gallery labels; small open-set sample; exact duplicates of v3 excluded.",
        "images": len(unknown_results),
        "by_species": dict(Counter(row["true_species"] for row in unknown_results)),
        "accepted_as_one_of_three_at_active_threshold": sum(row["threshold_status"] == "identified" for row in unknown_results),
        "always_has_top_supported_class": len(unknown_results),
        "predictions": unknown_results,
    }

    print(json.dumps({
        "model_version": predictor.model_version,
        "model_path": str(predictor.model_path.relative_to(ROOT)),
        "confidence_threshold": predictor.confidence_threshold,
        "classes": TARGET_IDS,
        "splits": splits,
        "test_deduplicated_to_one_row_per_recomputed_near_duplicate_group": evaluate_split(predictor, test_near_representatives),
        "verified_training_images_by_species": class_counts,
        "leakage_audit": {
            "manifest_rows": len(rows), "cross_split_exact_hash_or_observation_or_stored_near_group_keys": len(cross_keys),
            "recomputed_near_duplicate_groups": len(near_groups), "cross_split_recomputed_near_duplicate_groups": len(cross_near),
            "within_split_repeated_groups": within_split_repeats,
            "independence_support": independence_support,
        },
        "non_target_open_set": unknown_summary,
    }, indent=2))


if __name__ == "__main__":
    main()
