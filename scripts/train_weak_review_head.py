"""Train a fresh 11-class head with the MobileNetV2 backbone frozen.

Uses only train/validation rows from the immutable weak-review v3 dataset.
Historical test records are checked for split isolation but their image files
are never opened or scored by this script.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
os.environ.setdefault("TF_NUM_INTRAOP_THREADS", "2")
os.environ.setdefault("TF_NUM_INTEROP_THREADS", "2")
os.environ.setdefault("KERAS_HOME", str(Path(__file__).resolve().parents[1] / "storage/model_cache"))

import numpy as np
import tensorflow as tf
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix

from geoflora_ml.inference.preprocess import TRAIN_ONLY_AUGMENTATION, load_training_views, preprocess_rgb_batch

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "storage/datasets/curated/auto_6ae5cd74af23d762feaa0889_weakreview_v3_20261101"
BASE = ROOT / "storage/models/candidates/auto_6ae5cd74af23d762feaa0889"
DEFAULT_OUT = ROOT / "storage/models/candidates/mobilenetv2_11class_head_weakreview_v1_20261101"
SEED = 42
MAX_EPOCHS = 60
PATIENCE = 8
BATCH = 16
LR = 1e-3


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def arrays_for(rows, class_to_index, *, augment):
    arrays, labels, base_flags = [], [], []
    for row in rows:
        views = load_training_views(ROOT / row["local_path"], augment=augment)
        arrays.extend(np.asarray(view, dtype=np.uint8) for view in views)
        labels.extend([class_to_index[row["species_id"]]] * len(views))
        base_flags.extend([not bool(row.get("review_decision_key"))] * len(views))
    return np.stack(arrays), np.asarray(labels, dtype=np.int32), np.asarray(base_flags, dtype=bool)


def evaluate(probabilities, labels, names):
    predicted = probabilities.argmax(axis=1)
    report = classification_report(labels, predicted, labels=list(range(len(names))), target_names=names, output_dict=True, zero_division=0)
    loss = float(np.mean(tf.keras.losses.sparse_categorical_crossentropy(labels, probabilities).numpy()))
    return {
        "loss": loss,
        "accuracy": float(accuracy_score(labels, predicted)),
        "macro_precision": float(report["macro avg"]["precision"]),
        "macro_recall": float(report["macro avg"]["recall"]),
        "macro_f1": float(report["macro avg"]["f1-score"]),
        "per_class": {name: report[name] for name in names},
        "confusion_matrix": confusion_matrix(labels, predicted, labels=list(range(len(names)))).tolist(),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    dataset = args.dataset.resolve() if args.dataset.is_absolute() else (ROOT / args.dataset).resolve()
    output = args.output.resolve() if args.output.is_absolute() else (ROOT / args.output).resolve()
    if not dataset.is_relative_to((ROOT / "storage/datasets/curated").resolve()):
        raise SystemExit("Dataset must be under storage/datasets/curated")
    if not output.is_relative_to((ROOT / "storage/models/candidates").resolve()) or output.exists():
        raise SystemExit("Candidate output must be a new directory under storage/models/candidates")
    metadata = json.loads((dataset / "dataset_metadata.json").read_text(encoding="utf-8"))
    if sha(dataset / "manifest.csv") != metadata["manifest_sha256"]:
        raise SystemExit("Dataset manifest checksum mismatch")
    rows = read_csv(dataset / "manifest.csv")
    mapping = json.loads((dataset / "class_mapping.json").read_text(encoding="utf-8"))
    if mapping != json.loads((BASE / "class_mapping.json").read_text(encoding="utf-8")):
        raise SystemExit("Preserved 11-class mapping mismatch")
    classes = mapping["classes"]
    class_names = [item["id"] for item in classes]
    class_to_index = {name: i for i, name in enumerate(class_names)}
    train_rows = [r for r in rows if r["split"] == "train"]
    val_rows = [r for r in rows if r["split"] == "validation"]
    test_rows = [r for r in rows if r["split"] == "test"]
    if not train_rows or not val_rows or not test_rows:
        raise SystemExit("Expected frozen train, validation, and held-out test partitions")
    # Split integrity check uses only manifest metadata; no test image is read.
    partition_keys = defaultdict(set)
    for row in rows:
        for field in ("sha256", "group_id", "near_duplicate_group_id"):
            if row.get(field):
                partition_keys[(field, row[field])].add(row["split"])
    if any(len(splits) != 1 for splits in partition_keys.values()):
        raise SystemExit("Dataset has a cross-partition image/observation/duplicate key")
    if {r["species_id"] for r in train_rows} != set(class_names) or {r["species_id"] for r in val_rows} != set(class_names):
        raise SystemExit("Every class must be represented in train and validation")

    tf.keras.utils.set_random_seed(SEED)
    source = tf.keras.models.load_model(BASE / "mobilenetv2.keras", compile=False)
    backbone = source.get_layer("mobilenetv2_1.00_224")
    backbone.trainable = False
    feature_model = tf.keras.Model(source.input, backbone(source.input, training=False), name="frozen_mobilenetv2_features")

    # Compute original-checkpoint baseline on the same development validation rows.
    val_pixels, val_y, _ = arrays_for(val_rows, class_to_index, augment=False)
    base_scores = source.predict(preprocess_rgb_batch(val_pixels), batch_size=BATCH, verbose=0)
    baseline = evaluate(base_scores, val_y, class_names)

    train_pixels, train_y, train_base_flags = arrays_for(train_rows, class_to_index, augment=True)
    train_features = feature_model.predict(preprocess_rgb_batch(train_pixels), batch_size=BATCH, verbose=0)
    val_features = feature_model.predict(preprocess_rgb_batch(val_pixels), batch_size=BATCH, verbose=0)

    # Fresh classifier head. The backbone remains frozen throughout this run.
    head_input = tf.keras.Input(shape=(int(train_features.shape[1]),), name="pooled_features")
    x = tf.keras.layers.Dropout(0.2, name="head_dropout")(head_input)
    output_tensor = tf.keras.layers.Dense(len(classes), activation="softmax", name="plant_classification")(x)
    head = tf.keras.Model(head_input, output_tensor, name="fresh_frozen_backbone_classifier")
    head.compile(optimizer=tf.keras.optimizers.Adam(learning_rate=LR), loss="sparse_categorical_crossentropy")
    class_counts = Counter(train_y.tolist())
    weights_by_class = {i: min(2.0, max(0.5, (len(train_y) / (len(classes) * count)) ** 0.5)) for i, count in class_counts.items()}
    sample_weights = np.asarray([weights_by_class[i] for i in train_y], dtype=np.float32)

    baseline_loss = baseline["loss"]
    best_loss, best_weights, stale, history = float("inf"), None, 0, []
    rng = np.random.default_rng(SEED)
    for epoch in range(MAX_EPOCHS):
        order = rng.permutation(len(train_y))
        losses = []
        for start in range(0, len(order), BATCH):
            ix = order[start:start + BATCH]
            result = head.train_on_batch(train_features[ix], train_y[ix], sample_weight=sample_weights[ix], return_dict=True)
            losses.append(float(result["loss"]))
        val_probs = head.predict(val_features, batch_size=BATCH, verbose=0)
        val_loss = float(np.mean(tf.keras.losses.sparse_categorical_crossentropy(val_y, val_probs).numpy()))
        history.append({"epoch": epoch + 1, "train_loss": float(np.mean(losses)), "validation_loss": val_loss})
        print(json.dumps({"stage": "head_only", **history[-1], "best_validation_loss": best_loss}), flush=True)
        if val_loss < best_loss - 1e-5:
            best_loss, best_weights, stale = val_loss, head.get_weights(), 0
        else:
            stale += 1
            if stale >= PATIENCE:
                break
    head.set_weights(best_weights)
    head_scores = head.predict(val_features, batch_size=BATCH, verbose=0)
    head_metrics = evaluate(head_scores, val_y, class_names)

    # Recompose the Keras model in the same input/preprocessing contract.
    source_backbone = source.get_layer("mobilenetv2_1.00_224")
    candidate_input = tf.keras.Input(shape=(224, 224, 3), name="image")
    features = source_backbone(candidate_input, training=False)
    candidate_head = tf.keras.Sequential([
        tf.keras.layers.Dropout(0.2, name="head_dropout"),
        tf.keras.layers.Dense(len(classes), activation="softmax", name="plant_classification"),
    ], name="classification_head")
    _ = candidate_head(tf.zeros((1, int(train_features.shape[1]))))
    candidate_head.set_weights(head.get_weights())
    candidate_output = candidate_head(features)
    candidate = tf.keras.Model(candidate_input, candidate_output, name="mobilenetv2_11class_head_only")
    output.mkdir(parents=True)
    candidate.save(output / "mobilenetv2.keras")
    (output / "class_mapping.json").write_text(json.dumps(mapping, indent=2), encoding="utf-8")
    reloaded = tf.keras.models.load_model(output / "mobilenetv2.keras", compile=False)
    probe = np.zeros((1, 224, 224, 3), dtype=np.float32)
    np.testing.assert_allclose(candidate(probe, training=False).numpy(), reloaded(probe, training=False).numpy(), atol=1e-5)
    baseline_priority = {name: baseline["per_class"][name] for name in ("mikania_micrantha", "coccinia_grandis", "broussonetia_papyrifera")}
    head_priority = {name: head_metrics["per_class"][name] for name in baseline_priority}
    evaluation = {
        "candidate": output.name, "dataset": str(dataset.relative_to(ROOT)), "dataset_manifest_sha256": metadata["manifest_sha256"],
        "base_candidate": BASE.name, "base_model_sha256": sha(BASE / "mobilenetv2.keras"), "class_mapping_unchanged": True,
        "experiment": "Fresh classification head trained on final weak-review dataset while MobileNetV2 backbone was frozen for every epoch.",
        "test_policy": {"historical_test_partition_loaded": False, "historical_test_images_opened": False, "used_for_training_validation_selection_threshold_tuning_or_scoring": False, "row_count_held_out": len(test_rows)},
        "training": {"train_base_images": int(train_base_flags.sum() // 3), "train_approved_addition_images": int((~train_base_flags).sum() // 3), "train_augmented_views": len(train_y), "validation_images": len(val_y), "validation_groups": len({r["group_id"] for r in val_rows}), "historical_test_images_held_out": len(test_rows)},
        "settings": {"backbone": "saved ImageNet MobileNetV2 backbone frozen throughout", "head": "fresh Dropout(0.2) + Dense(11, softmax)", "optimizer": "Adam", "learning_rate": LR, "batch_size": BATCH, "max_epochs": MAX_EPOCHS, "early_stopping_patience": PATIENCE, "class_weighting": "square-root inverse frequency clipped to [0.5, 2.0]", "train_only_augmentation": TRAIN_ONLY_AUGMENTATION, "checkpoint_selection": "minimum development validation cross entropy", "seed": SEED},
        "validation_original_checkpoint": baseline, "validation_fresh_head_candidate": head_metrics,
        "validation_loss_baseline": baseline_loss, "validation_loss_candidate": head_metrics["loss"], "validation_improved": head_metrics["loss"] < baseline_loss,
        "priority_class_validation_before": baseline_priority, "priority_class_validation_after": head_priority,
        "confusion_matrix_class_order": class_names, "validation_only_result": True,
        "limitations": ["No test or threshold result is reported; historical test pixels were never opened by this script.", "Repeated generic owner visual approvals are not independent botanical verification.", "Only 34 new additions, no Broussonetia additions; validation estimates remain development-only.", "The source candidate and development corpus include CC BY-NC material; keep candidate local/research-only until client use permission is confirmed.", "Candidate is experimental and inactive."],
        "active_model_changed": False, "created_at_utc": datetime.now(timezone.utc).isoformat(), "epoch_history": history,
    }
    (output / "evaluation.json").write_text(json.dumps(evaluation, indent=2), encoding="utf-8")
    checks = {file.name: sha(file) for file in output.iterdir() if file.is_file() and file.name != "checksums.json"}
    (output / "checksums.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")
    print(json.dumps({"candidate": output.name, "validation_baseline": {k: baseline[k] for k in ("accuracy", "loss", "macro_f1")}, "validation_head": {k: head_metrics[k] for k in ("accuracy", "loss", "macro_f1")}, "validation_improved": head_metrics["loss"] < baseline_loss, "epochs": len(history), "historical_test_opened": False, "active_model_changed": False}, indent=2), flush=True)


if __name__ == "__main__":
    main()
