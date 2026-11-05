"""One bounded MobileNetV2 fine-tuning pass from an existing 11-class candidate.

Checkpoint selection uses validation loss only. The historical test partition is
loaded and scored once after checkpoint selection and is never used for tuning.
The active model path and source candidate are read-only.
"""
from __future__ import annotations

import csv
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
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, log_loss

from geoflora_ml.inference.preprocess import load_training_views, preprocess_rgb_batch

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "storage/datasets/curated/auto_6ae5cd74af23d762feaa0889"
SOURCE = ROOT / "storage/models/candidates/auto_6ae5cd74af23d762feaa0889"
OUT = ROOT / "storage/models/candidates/mobilenetv2_11class_finetune_v1_20261101"
STATUS = ROOT / "docs/11class-finetune-status-2026-11-01.json"
SEED = 42
LAST_LAYERS = 20
MAX_EPOCHS = 8
PATIENCE = 3
BATCH_SIZE = 16
LEARNING_RATE = 1e-5


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")


def load_split(rows: list[dict[str, str]], labels: dict[str, int], *, augment: bool) -> tuple[np.ndarray, np.ndarray]:
    arrays: list[np.ndarray] = []
    targets: list[int] = []
    for row in rows:
        path = (ROOT / row["local_path"]).resolve()
        if not path.is_relative_to((ROOT / "storage/datasets").resolve()):
            raise ValueError(f"Image path escapes dataset storage: {row['local_path']}")
        if digest(path) != row["sha256"]:
            raise ValueError(f"Image checksum changed: {row['local_path']}")
        views = load_training_views(path, augment=augment)
        arrays.extend(np.asarray(view, dtype=np.uint8) for view in views)
        targets.extend([labels[row["species_id"]]] * len(views))
    return preprocess_rgb_batch(arrays), np.asarray(targets, dtype=np.int32)


def metrics(y_true: np.ndarray, probabilities: np.ndarray, classes: list[dict]) -> dict:
    predicted = probabilities.argmax(axis=1)
    report = classification_report(
        y_true, predicted, labels=list(range(len(classes))),
        target_names=[item["id"] for item in classes], output_dict=True, zero_division=0,
    )
    return {
        "images": int(len(y_true)),
        "accuracy": float(accuracy_score(y_true, predicted)),
        "macro_f1": float(report["macro avg"]["f1-score"]),
        "cross_entropy": float(log_loss(y_true, probabilities, labels=list(range(len(classes))))),
        "per_class": {item["id"]: {key: float(report[item["id"]][key]) for key in ("precision", "recall", "f1-score")} | {"support": int(report[item["id"]]["support"])} for item in classes},
        "confusion_matrix": confusion_matrix(y_true, predicted, labels=list(range(len(classes)))).tolist(),
    }


def main() -> None:
    if OUT.exists():
        raise ValueError(f"Preserving existing output; choose a new path: {OUT}")
    metadata = json.loads((DATASET / "dataset_metadata.json").read_text(encoding="utf-8"))
    if digest(DATASET / "manifest.csv") != metadata["manifest_sha256"]:
        raise ValueError("Frozen manifest checksum mismatch")
    if digest(DATASET / "reviews_snapshot.json") != metadata["reviews_snapshot_sha256"]:
        raise ValueError("Frozen review snapshot checksum mismatch")
    rows = list(csv.DictReader((DATASET / "manifest.csv").open(encoding="utf-8-sig", newline="")))
    classes = json.loads((DATASET / "class_mapping.json").read_text(encoding="utf-8"))["classes"]
    source_mapping = json.loads((SOURCE / "class_mapping.json").read_text(encoding="utf-8"))["classes"]
    if [item["id"] for item in classes] != [item["id"] for item in source_mapping]:
        raise ValueError("Source candidate and frozen dataset class order differ")

    # Verify partitions before loading pixels. Observation and near-duplicate groups stay within a split.
    splits: dict[tuple[str, str], set[str]] = {}
    for row in rows:
        for field in ("sha256", "group_id", "near_duplicate_group_id"):
            splits.setdefault((field, row[field]), set()).add(row["split"])
    cross_split = sum(len(partitions) > 1 for partitions in splits.values())
    if cross_split:
        raise ValueError(f"Detected {cross_split} cross-split hash/group keys")
    if set(row["split"] for row in rows) != {"train", "validation", "test"}:
        raise ValueError("Expected train, validation, and test partitions")

    class_ids = [item["id"] for item in classes]
    labels = {class_id: index for index, class_id in enumerate(class_ids)}
    by_split = {name: [row for row in rows if row["split"] == name] for name in ("train", "validation", "test")}
    for split, partition in by_split.items():
        if {row["species_id"] for row in partition} != set(class_ids):
            raise ValueError(f"A class is absent from {split}")
    train_group_counts = {class_id: len({row["group_id"] for row in by_split["train"] if row["species_id"] == class_id}) for class_id in class_ids}

    tf.keras.utils.set_random_seed(SEED)
    model = tf.keras.models.load_model(SOURCE / "mobilenetv2.keras")
    backbone = next(layer for layer in model.layers if isinstance(layer, tf.keras.Model) and "mobilenetv2" in layer.name.lower())
    validation_x, validation_y = load_split(by_split["validation"], labels, augment=False)
    original_validation = metrics(validation_y, model.predict(validation_x, batch_size=BATCH_SIZE, verbose=0), classes)

    train_x, train_y = load_split(by_split["train"], labels, augment=True)
    counts = Counter(train_y.tolist())
    sample_weights = np.asarray([len(train_y) / (len(classes) * counts[int(target)]) for target in train_y], dtype=np.float32)

    # Keras ignores child trainable flags under a frozen parent; unfreeze the nested model,
    # then explicitly freeze all but the last 20 layers and every BatchNormalization layer.
    backbone.trainable = True
    for layer in backbone.layers:
        layer.trainable = False
    eligible = [layer for layer in backbone.layers[-LAST_LAYERS:] if not isinstance(layer, tf.keras.layers.BatchNormalization)]
    for layer in eligible:
        layer.trainable = True
    head = next(layer for layer in model.layers if isinstance(layer, tf.keras.Sequential))
    head.trainable = True
    trainable_names = [layer.name for layer in eligible if layer.trainable]
    trainable_parameters = int(sum(np.prod(variable.shape) for variable in model.trainable_weights))
    batchnorm_trainable = [layer.name for layer in backbone.layers if isinstance(layer, tf.keras.layers.BatchNormalization) and layer.trainable]
    if not trainable_names or batchnorm_trainable:
        raise ValueError("Fine-tuning configuration is invalid")

    model.compile(optimizer=tf.keras.optimizers.Adam(LEARNING_RATE), loss="sparse_categorical_crossentropy")
    best_loss = original_validation["cross_entropy"]
    best_weights = model.get_weights()
    best_epoch = 0
    history = []
    stale = 0
    rng = np.random.default_rng(SEED)
    write_json(STATUS, {"stage": "fine_tuning", "candidate": str(OUT.relative_to(ROOT)), "source_model_sha256": digest(SOURCE / "mobilenetv2.keras"), "dataset_manifest_sha256": metadata["manifest_sha256"], "baseline_validation": original_validation, "max_epochs": MAX_EPOCHS})
    for epoch in range(1, MAX_EPOCHS + 1):
        order = rng.permutation(len(train_y))
        for offset in range(0, len(order), BATCH_SIZE):
            indices = order[offset:offset + BATCH_SIZE]
            model.train_on_batch(train_x[indices], train_y[indices], sample_weight=sample_weights[indices])
        scores = model.predict(validation_x, batch_size=BATCH_SIZE, verbose=0)
        val = metrics(validation_y, scores, classes)
        history.append({"epoch": epoch, "validation": val})
        print(json.dumps({"epoch": epoch, "validation_loss": val["cross_entropy"], "accuracy": val["accuracy"], "macro_f1": val["macro_f1"]}), flush=True)
        if val["cross_entropy"] < best_loss:
            best_loss, best_weights, best_epoch, stale = val["cross_entropy"], model.get_weights(), epoch, 0
        else:
            stale += 1
        write_json(STATUS, {"stage": "fine_tuning", "candidate": str(OUT.relative_to(ROOT)), "epoch": epoch, "best_epoch": best_epoch, "best_validation_loss": best_loss, "baseline_validation_loss": original_validation["cross_entropy"], "max_epochs": MAX_EPOCHS})
        if stale >= PATIENCE:
            break
    model.set_weights(best_weights)
    selected_validation = metrics(validation_y, model.predict(validation_x, batch_size=BATCH_SIZE, verbose=0), classes)

    # Test partition is not loaded until selection is frozen; this is a single final score only.
    test_x, test_y = load_split(by_split["test"], labels, augment=False)
    final_test = metrics(test_y, model.predict(test_x, batch_size=BATCH_SIZE, verbose=0), classes)
    OUT.mkdir(parents=True)
    model.save(OUT / "mobilenetv2.keras")
    (OUT / "class_mapping.json").write_bytes((SOURCE / "class_mapping.json").read_bytes())
    evaluation = {
        "candidate": OUT.name,
        "source_candidate": SOURCE.name,
        "dataset": str(DATASET.relative_to(ROOT)),
        "dataset_manifest_sha256": metadata["manifest_sha256"],
        "class_order": class_ids,
        "active_model_changed": False,
        "activated": False,
        "selection": "minimum validation cross entropy; historical test partition was not loaded until checkpoint selection completed",
        "validation_before_fine_tune": original_validation,
        "validation_after_selected_checkpoint": selected_validation,
        "validation_history": history,
        "fine_tune": {"requested": True, "applied": best_epoch > 0, "improved_validation": best_epoch > 0, "selected_epoch": best_epoch, "max_epochs": MAX_EPOCHS, "patience": PATIENCE, "learning_rate": LEARNING_RATE, "unfrozen_backbone_layers": LAST_LAYERS, "trainable_backbone_layer_names": trainable_names, "trainable_parameters": trainable_parameters, "batch_normalization_trainable_layers": batchnorm_trainable},
        "final_test_once_after_selection": final_test,
        "split_counts": {split: len(partition) for split, partition in by_split.items()},
        "train_images_per_class": {class_id: sum(row["species_id"] == class_id for row in by_split["train"]) for class_id in class_ids},
        "train_observation_groups_per_class": train_group_counts,
        "cross_split_hash_or_group_keys": cross_split,
        "limitations": ["The 253-image test partition was already inspected in the earlier head-only evaluation; this one-time result is not an untouched blind test or independent Philippine field-accuracy estimate.", "Most new labels are iNaturalist research-grade community identifications, not expert botanical verification.", "Country filtering and owner attestations do not independently certify every photo's field provenance.", "Small class support, especially Broussonetia papyrifera (6 test images), gives wide uncertainty.", "No non-plant/unknown class; closed-set scores can force unsupported inputs into one of these eleven classes."],
        "tensorflow_version": tf.__version__,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    write_json(OUT / "evaluation.json", evaluation)
    reloaded = tf.keras.models.load_model(OUT / "mobilenetv2.keras")
    np.testing.assert_allclose(model(validation_x[:1], training=False).numpy(), reloaded(validation_x[:1], training=False).numpy(), atol=1e-5)
    (OUT / "checksums.json").write_text(json.dumps({path.name: digest(path) for path in OUT.iterdir() if path.is_file()}, indent=2), encoding="utf-8")
    write_json(STATUS, {"stage": "completed", "candidate": str(OUT.relative_to(ROOT)), "accuracy": final_test["accuracy"], "macro_f1": final_test["macro_f1"], "validation_before": original_validation, "validation_after": selected_validation, "fine_tune_applied": best_epoch > 0, "fine_tune_epoch": best_epoch, "activated": False, "active_model_changed": False, "reload_equivalence": "passed"})
    print(json.dumps({"completed": True, "candidate": OUT.name, "validation_before": original_validation, "validation_after": selected_validation, "test_once_after_selection": final_test, "fine_tune_applied": best_epoch > 0, "selected_epoch": best_epoch, "activated": False}, indent=2), flush=True)


if __name__ == "__main__":
    main()
