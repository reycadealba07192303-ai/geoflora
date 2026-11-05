"""Bounded 11-class MobileNetV2 fine-tune from the saved experimental checkpoint.

Only the frozen dataset's train/validation rows are used during fitting and
selection. The historical test split is scored once after model selection for
comparison only; it is not an independent blind test and cannot promote model.
"""
from __future__ import annotations

import csv
import argparse
import hashlib
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
os.environ.setdefault("TF_NUM_INTRAOP_THREADS", "2")
os.environ.setdefault("TF_NUM_INTEROP_THREADS", "2")
os.environ.setdefault("KERAS_HOME", str(Path(__file__).resolve().parents[1] / "storage/model_cache"))

import numpy as np
import tensorflow as tf
from PIL import Image
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix

from geoflora_ml.inference.preprocess import TRAIN_ONLY_AUGMENTATION, load_training_views, preprocess_rgb_batch, rgb_array

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "storage/datasets/curated/auto_6ae5cd74af23d762feaa0889_weakreview_v2_20261101"
BASE = ROOT / "storage/models/candidates/auto_6ae5cd74af23d762feaa0889"
OUT = ROOT / "storage/models/candidates/mobilenetv2_11class_weakreview_v2_20261101"
MAX_EPOCHS = 8
PATIENCE = 2
BATCH_SIZE = 16
LR = 1e-5
SEED = 42


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_rows(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def image_arrays(rows, *, augment: bool):
    arrays, labels = [], []
    for row in rows:
        views = load_training_views(ROOT / row["local_path"], augment=augment)
        arrays.extend(np.asarray(view, dtype=np.uint8) for view in views)
        labels.extend([row["species_id"]] * len(views))
    return np.stack(arrays), np.asarray(labels)


def score(model, arrays, ids, class_to_index, class_names):
    encoded = np.asarray([class_to_index[value] for value in ids], dtype=np.int32)
    probabilities = model.predict(preprocess_rgb_batch(arrays), batch_size=BATCH_SIZE, verbose=0)
    predicted = probabilities.argmax(axis=1)
    report = classification_report(encoded, predicted, labels=list(range(len(class_names))), target_names=class_names, output_dict=True, zero_division=0)
    return {
        "accuracy": float(accuracy_score(encoded, predicted)),
        "macro_precision": float(report["macro avg"]["precision"]),
        "macro_recall": float(report["macro avg"]["recall"]),
        "macro_f1": float(report["macro avg"]["f1-score"]),
        "per_class": {name: report[name] for name in class_names},
        "confusion_matrix": confusion_matrix(encoded, predicted, labels=list(range(len(class_names)))).tolist(),
        "predicted": predicted.tolist(),
        "probabilities": probabilities,
    }


def main():
    global DATASET, OUT
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    DATASET = args.dataset.resolve() if args.dataset.is_absolute() else (ROOT / args.dataset).resolve()
    OUT = args.output.resolve() if args.output.is_absolute() else (ROOT / args.output).resolve()
    if not DATASET.is_relative_to((ROOT / "storage/datasets/curated").resolve()):
        raise SystemExit("Dataset must be under storage/datasets/curated")
    if not OUT.is_relative_to((ROOT / "storage/models/candidates").resolve()):
        raise SystemExit("Output must be under storage/models/candidates")
    if OUT.exists():
        raise SystemExit(f"Refusing to overwrite candidate: {OUT}")
    metadata = json.loads((DATASET / "dataset_metadata.json").read_text(encoding="utf-8"))
    if digest(DATASET / "manifest.csv") != metadata["manifest_sha256"]:
        raise SystemExit("Frozen dataset manifest checksum mismatch")
    rows = read_rows(DATASET / "manifest.csv")
    mapping = json.loads((DATASET / "class_mapping.json").read_text(encoding="utf-8"))
    classes = mapping["classes"]
    class_ids = [entry["id"] for entry in classes]
    class_names = [entry["id"] for entry in classes]
    base_mapping = json.loads((BASE / "class_mapping.json").read_text(encoding="utf-8"))
    if mapping != base_mapping:
        raise SystemExit("Class mapping differs from existing 11-class candidate")
    train_rows = [row for row in rows if row["split"] == "train"]
    val_rows = [row for row in rows if row["split"] == "validation"]
    test_rows = [row for row in rows if row["split"] == "test"]
    if not train_rows or not val_rows or len({r["species_id"] for r in train_rows}) != len(classes) or len({r["species_id"] for r in val_rows}) != len(classes):
        raise SystemExit("Train and validation must both cover the preserved class mapping")
    class_to_index = {value: index for index, value in enumerate(class_ids)}
    train_pixels, train_ids = image_arrays(train_rows, augment=True)
    val_pixels, val_ids = image_arrays(val_rows, augment=False)
    test_pixels, test_ids = image_arrays(test_rows, augment=False)
    train_y = np.asarray([class_to_index[value] for value in train_ids], dtype=np.int32)

    model = tf.keras.models.load_model(BASE / "mobilenetv2.keras", compile=False)
    initial_weights = model.get_weights()
    val_before = score(model, val_pixels, val_ids, class_to_index, class_names)
    initial_val_loss = float(np.mean(tf.keras.losses.sparse_categorical_crossentropy(
        np.asarray([class_to_index[value] for value in val_ids]),
        model.predict(preprocess_rgb_batch(val_pixels), batch_size=BATCH_SIZE, verbose=0),
    ).numpy()))

    backbone = model.get_layer("mobilenetv2_1.00_224")
    backbone.trainable = True
    for layer in backbone.layers:
        layer.trainable = False
    for layer in backbone.layers[-20:]:
        if not isinstance(layer, tf.keras.layers.BatchNormalization):
            layer.trainable = True
    model.compile(optimizer=tf.keras.optimizers.Adam(learning_rate=LR), loss="sparse_categorical_crossentropy")
    class_counts = Counter(train_y.tolist())
    weights_by_class = {index: min(2.0, max(0.5, (len(train_y) / (len(classes) * count)) ** 0.5)) for index, count in class_counts.items()}
    sample_weights = np.asarray([weights_by_class[index] for index in train_y], dtype=np.float32)
    val_y = np.asarray([class_to_index[value] for value in val_ids], dtype=np.int32)

    best_loss, best_weights = initial_val_loss, initial_weights
    stale, history = 0, []
    rng = np.random.default_rng(SEED)
    for epoch in range(MAX_EPOCHS):
        order = rng.permutation(len(train_y))
        epoch_loss = []
        for start in range(0, len(order), BATCH_SIZE):
            indexes = order[start:start + BATCH_SIZE]
            batch = preprocess_rgb_batch(train_pixels[indexes])
            result = model.train_on_batch(batch, train_y[indexes], sample_weight=sample_weights[indexes], return_dict=True)
            epoch_loss.append(float(result["loss"]))
        val_probs = model.predict(preprocess_rgb_batch(val_pixels), batch_size=BATCH_SIZE, verbose=0)
        val_loss = float(np.mean(tf.keras.losses.sparse_categorical_crossentropy(val_y, val_probs).numpy()))
        history.append({"epoch": epoch + 1, "train_loss": float(np.mean(epoch_loss)), "validation_loss": val_loss})
        print(json.dumps({"stage": "fine_tune", **history[-1], "best_validation_loss": best_loss}), flush=True)
        if val_loss < best_loss - 1e-5:
            best_loss, best_weights, stale = val_loss, model.get_weights(), 0
        else:
            stale += 1
            if stale >= PATIENCE:
                break
    model.set_weights(best_weights)
    val_after = score(model, val_pixels, val_ids, class_to_index, class_names)

    # One post-selection pass over the old held-out test, for historical
    # comparability only. No thresholds or weights are selected from it.
    test_result = score(model, test_pixels, test_ids, class_to_index, class_names)
    prior_predictions = json.loads((BASE / "test_predictions.json").read_text(encoding="utf-8"))
    old_manifest = read_rows(ROOT / "storage/datasets/curated/auto_6ae5cd74af23d762feaa0889/manifest.csv")
    old_test = [row for row in old_manifest if row["split"] == "test"]
    if len(prior_predictions) != len(old_test) or len(test_rows) != len(old_test):
        raise SystemExit("Historical test set does not match stored baseline predictions")
    if [(p["source"], p["source_id"], p["expected"]) for p in prior_predictions] != [(r["source"], r["source_id"], r["species_id"]) for r in old_test]:
        raise SystemExit("Historical test order/identity mismatch")
    old_expected = np.asarray([class_to_index[p["expected"]] for p in prior_predictions])
    old_predicted = np.asarray([class_to_index[p["predicted"]] for p in prior_predictions])
    old_report = classification_report(old_expected, old_predicted, labels=list(range(len(classes))), target_names=class_names, output_dict=True, zero_division=0)
    old_metrics = {
        "accuracy": float(accuracy_score(old_expected, old_predicted)),
        "macro_precision": float(old_report["macro avg"]["precision"]),
        "macro_recall": float(old_report["macro avg"]["recall"]),
        "macro_f1": float(old_report["macro avg"]["f1-score"]),
        "per_class": {name: old_report[name] for name in class_names},
        "confusion_matrix": confusion_matrix(old_expected, old_predicted, labels=list(range(len(classes)))).tolist(),
    }

    OUT.mkdir(parents=True)
    model.save(OUT / "mobilenetv2.keras")
    (OUT / "class_mapping.json").write_text(json.dumps(mapping, indent=2), encoding="utf-8")
    reloaded = tf.keras.models.load_model(OUT / "mobilenetv2.keras", compile=False)
    np.testing.assert_allclose(model(np.zeros((1, 224, 224, 3), dtype=np.float32), training=False).numpy(), reloaded(np.zeros((1, 224, 224, 3), dtype=np.float32), training=False).numpy(), atol=1e-5)
    test_predictions = []
    for row, pred, confidence in zip(test_rows, test_result["predicted"], test_result["probabilities"].max(axis=1)):
        test_predictions.append({"source": row["source"], "source_id": row["source_id"], "expected": row["species_id"], "predicted": class_ids[int(pred)], "confidence": float(confidence)})
    (OUT / "test_predictions.json").write_text(json.dumps(test_predictions, indent=2), encoding="utf-8")
    target_classes = {key: {"before": old_metrics["per_class"][key], "after": test_result["per_class"][key]} for key in ("mikania_micrantha", "coccinia_grandis", "broussonetia_papyrifera")}
    evaluation = {
        "candidate": OUT.name, "dataset": str(DATASET.relative_to(ROOT)), "dataset_manifest_sha256": metadata["manifest_sha256"],
        "base_candidate": BASE.name, "base_model_sha256": digest(BASE / "mobilenetv2.keras"), "class_mapping_unchanged": True,
        "training": {"train_images_after_augmentation": len(train_pixels), "train_observation_groups": len({row["group_id"] for row in train_rows}), "train_base_images": sum(not row.get("review_decision_key") for row in train_rows), "train_approved_additions": sum(bool(row.get("review_decision_key")) for row in train_rows), "validation_images": len(val_rows), "validation_groups": len({row["group_id"] for row in val_rows}), "historical_test_images": len(test_rows), "historical_test_used_for_selection": False},
        "settings": {"initialization": "saved 11-class candidate checkpoint", "trainable_layers": "last 20 MobileNetV2 layers excluding BatchNormalization", "learning_rate": LR, "max_epochs": MAX_EPOCHS, "early_stopping_patience": PATIENCE, "batch_size": BATCH_SIZE, "augmentation": TRAIN_ONLY_AUGMENTATION, "class_weighting": "sqrt inverse class frequency clipped to [0.5, 2.0]", "selection": "minimum validation cross entropy; baseline weights retained unless validation loss improves"},
        "validation_before": {k: v for k, v in val_before.items() if k not in ("predicted", "probabilities")},
        "validation_after": {k: v for k, v in val_after.items() if k not in ("predicted", "probabilities")},
        "validation_loss_before": initial_val_loss, "validation_loss_after": best_loss, "validation_improved": best_loss < initial_val_loss,
        "historical_test_baseline": old_metrics, "historical_test_candidate": {k: v for k, v in test_result.items() if k not in ("predicted", "probabilities")},
        "historical_test_comparison": "same previously inspected held-out test partition; used once after checkpoint selection only. Comparable to stored baseline, not a blind independent test.",
        "target_class_comparison": target_classes,
        "limitations": ["Historical test was previously examined and is not a blind independent accuracy estimate.", "Owner approvals with repeated generic rationale are not expert botanical verification.", "The unchanged 11-class source checkpoint was trained using a corpus containing CC BY-NC images; this candidate remains research-only pending client permitted-use confirmation.", "Small new Mikania/Coccinia increments; no new Broussonetia photos; no non-target rejection/calibration claim."],
        "created_at_utc": datetime.now(timezone.utc).isoformat(), "active_model_changed": False, "tensorflow_version": tf.__version__, "epoch_history": history,
    }
    (OUT / "evaluation.json").write_text(json.dumps(evaluation, indent=2), encoding="utf-8")
    checksums = {p.name: digest(p) for p in OUT.iterdir() if p.is_file()}
    (OUT / "checksums.json").write_text(json.dumps(checksums, indent=2), encoding="utf-8")
    print(json.dumps({"candidate": OUT.name, "validation_before": {k: val_before[k] for k in ("accuracy", "macro_precision", "macro_recall", "macro_f1")}, "validation_after": {k: val_after[k] for k in ("accuracy", "macro_precision", "macro_recall", "macro_f1")}, "historical_test_before": {k: old_metrics[k] for k in ("accuracy", "macro_precision", "macro_recall", "macro_f1")}, "historical_test_after": {k: test_result[k] for k in ("accuracy", "macro_precision", "macro_recall", "macro_f1")}, "validation_improved": best_loss < initial_val_loss, "active_model_changed": False, "output": str(OUT.relative_to(ROOT))}, indent=2), flush=True)


if __name__ == "__main__":
    main()
