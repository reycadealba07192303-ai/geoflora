"""Train an experimental, frozen MobileNetV2 baseline; never activates it.

Run: services/ml/.venv/Scripts/python.exe scripts/train_baseline.py
Artifacts: storage/models/candidates/mobilenetv2_v3_seed42 (must not exist).
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
os.environ.setdefault("TF_NUM_INTRAOP_THREADS", "2")
os.environ.setdefault("TF_NUM_INTEROP_THREADS", "2")
os.environ.setdefault("KERAS_HOME", str(Path(__file__).resolve().parents[1] / "storage/model_cache"))

import numpy as np
import tensorflow as tf
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix

from geoflora_ml.config import load_species
from geoflora_ml.datasets.audit import load_current_reviews
from geoflora_ml.datasets.duplicates import group_near_duplicates
from geoflora_ml.inference.preprocess import load_training_views, preprocess_rgb_batch

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "storage/datasets"


def main():
    tf.keras.utils.set_random_seed(42)
    manifest = DATA / "curated/v3/manifest.csv"
    output = ROOT / "storage/models/candidates/mobilenetv2_v3_seed42"
    if output.exists():
        raise ValueError(f"Preserve existing run: {output}")
    with manifest.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    classes = sorted(load_species(), key=lambda entry: entry.id)
    labels = {entry.id: index for index, entry in enumerate(classes)}
    reviews = load_current_reviews(DATA)
    groups = defaultdict(set)
    for row in rows:
        path = (DATA / row["local_path"]).resolve()
        if not path.is_relative_to(DATA.resolve()):
            raise ValueError("Unsafe image path")
        if hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
            raise ValueError("Image checksum mismatch")
        review = reviews.get((row["source"], row["source_id"]), {})
        if review.get("decision") not in {"approved", "relabelled"}:
            raise ValueError("Unapproved image")
        effective = review.get("relabel_to") if review["decision"] == "relabelled" else row["original_species_id"]
        if effective != row["species_id"]:
            raise ValueError("Current reviewed label differs from manifest")
        for field in ("sha256", "group_id", "near_duplicate_group_id"):
            groups[(field, row[field])].add(row["split"])
    recomputed, _ = group_near_duplicates(rows, DATA)
    for row in recomputed:
        groups[("recomputed_near", row["near_duplicate_group_id"])].add(row["split"])
    if any(len(splits) != 1 for splits in groups.values()):
        raise ValueError("Cross-partition duplicate/observation leakage")
    for split in ("train", "validation", "test"):
        if {row["species_id"] for row in rows if row["split"] == split} != set(labels):
            raise ValueError(f"Missing class in {split}")

    base = tf.keras.applications.MobileNetV2(
        input_shape=(224, 224, 3), include_top=False, pooling="avg", weights="imagenet"
    )
    base.trainable = False
    features, targets = {}, {}
    for split in ("train", "validation", "test"):
        selected = [row for row in rows if row["split"] == split]
        batches = []
        for offset in range(0, len(selected), 16):
            pixels = []
            for row in selected[offset:offset + 16]:
                pixels.append(np.asarray(load_training_views(DATA / row["local_path"], augment=False)[0], dtype=np.float32))
            batches.append(base(preprocess_rgb_batch(pixels), training=False).numpy())
        features[split] = np.concatenate(batches)
        targets[split] = np.array([labels[row["species_id"]] for row in selected])
        print(split, len(selected), flush=True)
    head = tf.keras.Sequential([
        tf.keras.Input(shape=(1280,)), tf.keras.layers.Dropout(0.2),
        tf.keras.layers.Dense(len(classes), activation="softmax"),
    ])
    head.compile(optimizer=tf.keras.optimizers.Adam(0.001), loss="sparse_categorical_crossentropy")
    counts = Counter(targets["train"])
    weights = np.array([len(targets["train"]) / (len(classes) * counts[y]) for y in targets["train"]], dtype=np.float32)
    best_loss, best_weights, history, stale = float("inf"), None, [], 0
    rng = np.random.default_rng(42)
    for epoch in range(30):
        order = rng.permutation(len(targets["train"]))
        for offset in range(0, len(order), 16):
            indices = order[offset:offset + 16]
            head.train_on_batch(features["train"][indices], targets["train"][indices], sample_weight=weights[indices])
        scores = head(features["validation"], training=False).numpy()
        loss = float(np.mean(tf.keras.losses.sparse_categorical_crossentropy(targets["validation"], scores).numpy()))
        history.append({"epoch": epoch + 1, "validation_loss": loss})
        print(history[-1], flush=True)
        if loss < best_loss:
            best_loss, best_weights, stale = loss, head.get_weights(), 0
        else:
            stale += 1
        if stale >= 5:
            break
    head.set_weights(best_weights)
    inputs = tf.keras.Input(shape=(224, 224, 3))
    model = tf.keras.Model(inputs, head(base(inputs, training=False)))
    scores = head(features["test"], training=False).numpy()
    predicted = scores.argmax(axis=1)
    report = classification_report(targets["test"], predicted, labels=list(range(len(classes))), target_names=list(labels), output_dict=True, zero_division=0)
    evaluation = {
        "accuracy": float(accuracy_score(targets["test"], predicted)),
        "classification_report": report,
        "confusion_matrix": confusion_matrix(targets["test"], predicted, labels=list(range(len(classes)))).tolist(),
        "class_order": list(labels), "split_counts": dict(Counter(row["split"] for row in rows)),
        "cross_partition_groups": 0, "history": history,
        "seed": 42, "weights": "ImageNet", "backbone_frozen": True,
        "settings": {"max_epochs": 30, "batch_size": 16, "learning_rate": 0.001, "dropout": 0.2, "patience": 5, "selection": "minimum validation cross entropy", "input_size": [224, 224], "resize": "Pillow default RGB resize; same as inference", "preprocessing": "shared geoflora_ml.inference.preprocess; mobilenet_v2.preprocess_input external to saved model", "train_only_augmentation": "none in this preserved v3 baseline"},
        "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "reviews_sha256": hashlib.sha256((DATA / "raw/reviews.jsonl").read_bytes()).hexdigest(),
        "tensorflow_version": tf.__version__,
        "limitations": ["Labels approved from owner attestation", "PH geography not independently verified", "Small test set", "No unsupported-input or user evaluation yet", "Confidence is uncalibrated; threshold not tuned", "No image augmentation or fine-tuning in this baseline"],
    }
    output.mkdir(parents=True)
    model.save(output / "mobilenetv2.keras")
    (output / "class_mapping.json").write_text(json.dumps({"classes": [asdict(entry) for entry in classes]}, indent=2), encoding="utf-8")
    (output / "evaluation.json").write_text(json.dumps(evaluation, indent=2), encoding="utf-8")
    reloaded = tf.keras.models.load_model(output / "mobilenetv2.keras")
    np.testing.assert_allclose(model(np.zeros((1, 224, 224, 3)), training=False).numpy(), reloaded(np.zeros((1, 224, 224, 3)), training=False).numpy(), atol=1e-5)
    print("Saved candidate:", output, "accuracy:", evaluation["accuracy"], flush=True)


if __name__ == "__main__":
    main()
