"""Train an expanded experimental candidate from a frozen dataset, preserving active artifacts.

Without --frozen-dataset this re-runs the historical six-class v4 freeze. For v5 pass
--frozen-dataset storage/datasets/curated/v5_part2_final_five_classes and a new --output.
Augmentation applies to the train split only; --fine-tune is kept only if validation loss improves.
Run from the repository root with services/ml/.venv/Scripts/python.exe.
No downloads, invented approvals, or changes to the active model/registry.
"""
from __future__ import annotations

import csv
import argparse
import hashlib
import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "storage/datasets"
OUT = ROOT / "storage/models/candidates/mobilenetv2_v4_six_seed42"
FROZEN = DATA / "curated/v4_six_classes"
STATUS = ROOT / "docs/expanded-training-status.json"
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
os.environ.setdefault("TF_NUM_INTRAOP_THREADS", "2")
os.environ.setdefault("TF_NUM_INTEROP_THREADS", "2")
os.environ.setdefault("KERAS_HOME", str(ROOT / "storage/model_cache"))

import numpy as np
import tensorflow as tf
from PIL import Image
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from geoflora_ml.datasets.audit import load_current_reviews
from geoflora_ml.datasets.duplicates import group_near_duplicates
from geoflora_ml.collection.licensing import normalize_license
from geoflora_ml.datasets.split import assign_group_splits
from geoflora_ml.inference.preprocess import TRAIN_ONLY_AUGMENTATION, load_training_views, preprocess_rgb_batch
import batch_review


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
    temporary.replace(path)


def status(stage, **details):
    value = {"stage": stage, "updated_at_utc": datetime.now(timezone.utc).isoformat(), "candidate": str(OUT.relative_to(ROOT)), **details}
    write_json(STATUS, value)
    print(json.dumps(value), flush=True)


def freeze():
    if FROZEN.exists() or OUT.exists():
        raise ValueError("Preserve existing frozen dataset and candidate; choose a new version for another run")
    selected = DATA / "selection/pilot_five_classes"
    classes = json.loads((selected / "selected_classes.json").read_text())["classes"]
    classes += [{"id": "caladium_bicolor", "scientific_name": "Caladium bicolor", "common_name": "Corazon de Maria"}]
    classes.sort(key=lambda c: c["id"])
    with (selected / "selected_candidates.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    history = batch_review.REVIEW / "review_events.jsonl"
    latest = {r["record_key"]: r for r in map(json.loads, history.read_text().splitlines()) if r}
    batch_index = {(r["source"], r["source_id"], r["sha256"]): r for r in batch_review.records()}
    original_reviews = load_current_reviews(DATA)
    review_snapshot = []
    for row in rows:
        if row["label_basis"] == "existing_owner_approval":
            review = original_reviews.get((row["source"], row["source_id"]), {})
            effective = review.get("relabel_to") if review.get("decision") == "relabelled" else row["species_id"]
            if review.get("decision") not in {"approved", "relabelled"} or effective != row["species_id"]:
                raise ValueError("Selected legacy record no longer has matching approval")
        else:
            audit = batch_index[(row["source"], row["source_id"], row["sha256"])]
            review = latest.get(audit["record_key"], {})
            if review.get("decision") != "approved" or review.get("verified_country") != "PH" or review.get("verified_domain") != "field":
                raise ValueError("New pilot record lacks field/location approval")
        review_snapshot.append({"source": row["source"], "source_id": row["source_id"], "review": review})
    caladium = DATA / "staging/species_100_ph/126581"
    for record in map(json.loads, (caladium / "raw/manifest.jsonl").read_text().splitlines()):
        audit = batch_index[(record["source"], record["source_id"], record["sha256"])]
        review = latest.get(audit["record_key"], {})
        if review.get("decision") != "approved" or review.get("verified_country") != "PH" or record.get("country_code") != "PH":
            raise ValueError("Caladium lacks existing owner label/PH attestation")
        rows.append({**record, "species_id": "caladium_bicolor", "local_path": (caladium / record["local_path"]).relative_to(ROOT).as_posix(),
                     "label_basis": "existing_owner_batch_approval", "domain_basis": "assistant_visual_screen_contact_sheet_10_photos",
                     "country_basis": "owner_PH_attestation_and_source_PH_filter", "selection_status": "experimental_only"})
        review_snapshot.append({"source": record["source"], "source_id": record["source_id"], "review": review,
                                "technical_screen": "Visible live Caladium-type foliage; retained owner label. Not independent botanical verification."})
    seen = set()
    for row in rows:
        path = (ROOT / row["local_path"]).resolve()
        if not path.is_relative_to(DATA.resolve()) or digest(path) != row["sha256"]:
            raise ValueError("Invalid path or checksum")
        if row["sha256"] in seen or not normalize_license(row["license"]) or not row["attribution"]:
            raise ValueError("Duplicate or unlicensed image")
        seen.add(row["sha256"])
        with Image.open(path) as image:
            image.verify()
        row.pop("near_duplicate_group_id", None)
    grouped, _ = group_near_duplicates(rows, ROOT)
    assigned = assign_group_splits(grouped, seed=42)
    partitions = defaultdict(set)
    for row in assigned:
        for key in ("sha256", "group_id", "near_duplicate_group_id"):
            partitions[(key, row[key])].add(row["split"])
    if any(len(splits) != 1 for splits in partitions.values()):
        raise ValueError("Cross-split leakage")
    for split in ("train", "validation", "test"):
        if {r["species_id"] for r in assigned if r["split"] == split} != {c["id"] for c in classes}:
            raise ValueError("Missing class in split")
    FROZEN.mkdir(parents=True)
    fields = sorted(set().union(*(r.keys() for r in assigned)))
    with (FROZEN / "manifest.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader(); writer.writerows(assigned)
    write_json(FROZEN / "class_mapping.json", {"classes": classes})
    # JSON is valid YAML and can be loaded as an isolated species registry.
    write_json(FROZEN / "species.yaml", {"species": classes})
    write_json(FROZEN / "reviews_snapshot.json", review_snapshot)
    metadata = {"seed": 42, "images": len(assigned), "per_class": {c["id"]: dict(Counter(r["split"] for r in assigned if r["species_id"] == c["id"])) for c in classes},
                "manifest_sha256": digest(FROZEN / "manifest.csv"), "reviews_snapshot_sha256": digest(FROZEN / "reviews_snapshot.json"),
                "cross_split_groups": 0, "caladium_ecology_reference": "https://forestry.denr.gov.ph/fmb_web/wp-content/uploads/2023/06/Philippine-Guidebook-on-Plant-Species-Suitable-for-Urban-Greening-EBOOK_compressed.pdf#page=157",
                "caladium_screen": "All ten existing owner-approved photos visually screened as live foliage in caladium-contact-sheet.jpg; no new owner/expert approval fabricated",
                "scope": "Experimental six-class candidate. Few new-class examples; cannot establish nationwide accuracy. Legacy labels/geography rely on owner attestation."}
    write_json(FROZEN / "dataset_metadata.json", metadata)
    return assigned, classes, metadata


def main():
    global OUT, FROZEN, STATUS
    parser = argparse.ArgumentParser()
    parser.add_argument("--frozen-dataset", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--status", type=Path)
    parser.add_argument("--fine-tune", action="store_true", help="Unfreeze the last MobileNetV2 blocks after the frozen-head stage; keep the change only if validation loss improves.")
    args = parser.parse_args()
    if args.output:
        OUT = args.output.resolve()
        if not OUT.is_relative_to((ROOT / "storage/models/candidates").resolve()) or OUT.exists():
            raise ValueError("Use a new candidate output under storage/models/candidates")
    if args.status:
        STATUS = args.status.resolve()
        if not STATUS.is_relative_to(ROOT):
            raise ValueError("Status path must stay inside the workspace")
    status("preparing_dataset")
    if args.frozen_dataset:
        FROZEN = args.frozen_dataset.resolve()
        if not FROZEN.is_relative_to((DATA / "curated").resolve()) or OUT.exists():
            raise ValueError("Use a frozen curated dataset and a new candidate output")
        metadata = json.loads((FROZEN / "dataset_metadata.json").read_text())
        if digest(FROZEN / "manifest.csv") != metadata["manifest_sha256"] or digest(FROZEN / "reviews_snapshot.json") != metadata["reviews_snapshot_sha256"]:
            raise ValueError("Frozen dataset snapshot mismatch")
        with (FROZEN / "manifest.csv").open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        classes = json.loads((FROZEN / "class_mapping.json").read_text())["classes"]
        partitions = defaultdict(set)
        for row in rows:
            path = (ROOT / row["local_path"]).resolve()
            if not path.is_relative_to(DATA.resolve()) or digest(path) != row["sha256"]:
                raise ValueError("Training image path/checksum mismatch")
            row.pop("near_duplicate_group_id", None)
        rows, _ = group_near_duplicates(rows, ROOT)
        for row in rows:
            for key in ("sha256", "group_id", "near_duplicate_group_id"):
                partitions[(key, row[key])].add(row["split"])
        if any(len(splits) != 1 for splits in partitions.values()):
            raise ValueError("Cross-split leakage")
        for split in ("train", "validation", "test"):
            if {r["species_id"] for r in rows if r["split"] == split} != {c["id"] for c in classes}:
                raise ValueError("Missing class in training partition")
    else:
        rows, classes, metadata = freeze()
    OUT.mkdir(parents=True)
    tf.keras.utils.set_random_seed(42)
    labels = {c["id"]: i for i, c in enumerate(classes)}
    base = tf.keras.applications.MobileNetV2(input_shape=(224, 224, 3), include_top=False, pooling="avg", weights="imagenet")
    base.trainable = False
    features, targets, pixels = {}, {}, {}
    for split in ("train", "validation", "test"):
        status("extracting_features", split=split, dataset=metadata)
        arrays, ys = [], []
        for row in (r for r in rows if r["split"] == split):
            for view in load_training_views(ROOT / row["local_path"], augment=split == "train"):
                # uint8 keeps memory at a quarter; preprocess_rgb_batch converts to float32, so results are unchanged.
                arrays.append(np.asarray(view, dtype=np.uint8))
                ys.append(labels[row["species_id"]])
        encoded = []
        for offset in range(0, len(arrays), 16):
            encoded.append(base(preprocess_rgb_batch(arrays[offset:offset + 16]), training=False).numpy())
        features[split], targets[split] = np.concatenate(encoded), np.array(ys)
        # Full pixel arrays are needed only to fine-tune and to score the test split.
        if args.fine_tune or split == "test":
            pixels[split] = preprocess_rgb_batch(arrays)
    head = tf.keras.Sequential([tf.keras.Input(shape=(1280,)), tf.keras.layers.Dropout(0.2), tf.keras.layers.Dense(len(classes), activation="softmax")])
    head.compile(optimizer=tf.keras.optimizers.Adam(0.001), loss="sparse_categorical_crossentropy")
    counts = Counter(targets["train"])
    weights = np.array([len(targets["train"]) / (len(classes) * counts[y]) for y in targets["train"]], dtype=np.float32)
    best, best_weights, stale, history = float("inf"), None, 0, []
    rng = np.random.default_rng(42)
    for epoch in range(60):
        order = rng.permutation(len(targets["train"]))
        for offset in range(0, len(order), 16):
            ix = order[offset:offset + 16]
            head.train_on_batch(features["train"][ix], targets["train"][ix], sample_weight=weights[ix])
        scores = head(features["validation"], training=False).numpy()
        loss = float(np.mean(tf.keras.losses.sparse_categorical_crossentropy(targets["validation"], scores).numpy()))
        history.append({"epoch": epoch + 1, "validation_loss": loss})
        if loss < best:
            best, best_weights, stale = loss, head.get_weights(), 0
        else:
            stale += 1
        status("training", epoch=epoch + 1, max_epochs=60, validation_loss=loss, best_validation_loss=best)
        if stale >= 8:
            break
    head.set_weights(best_weights)
    inputs = tf.keras.Input(shape=(224, 224, 3))
    model = tf.keras.Model(inputs, head(base(inputs, training=False)))
    selected_epoch = min(history, key=lambda e: e["validation_loss"])["epoch"]
    fine_tune = {"requested": bool(args.fine_tune), "applied": False, "improved_validation": False, "history": []}
    if args.fine_tune:
        status("fine_tuning", unfrozen_layers=20, learning_rate=1e-5)
        frozen_loss, frozen_weights = best, model.get_weights()
        # Re-enable the nested MobileNetV2 model before changing child layers;
        # Keras ignores trainable child flags under a frozen parent model.
        base.trainable = True
        for layer in base.layers:
            layer.trainable = False
        for layer in base.layers[-20:]:
            if not isinstance(layer, tf.keras.layers.BatchNormalization):
                layer.trainable = True
        model.compile(optimizer=tf.keras.optimizers.Adam(1e-5), loss="sparse_categorical_crossentropy")
        stale = 0
        for epoch in range(10):
            order = rng.permutation(len(targets["train"]))
            for offset in range(0, len(order), 16):
                ix = order[offset:offset + 16]
                model.train_on_batch(pixels["train"][ix], targets["train"][ix], sample_weight=weights[ix])
            scores = model.predict(pixels["validation"], verbose=0)
            loss = float(np.mean(tf.keras.losses.sparse_categorical_crossentropy(targets["validation"], scores).numpy()))
            fine_tune["history"].append({"epoch": epoch + 1, "validation_loss": loss})
            if loss < best:
                best, best_weights, stale = loss, model.get_weights(), 0
            else:
                stale += 1
            status("fine_tuning", epoch=epoch + 1, max_epochs=10, validation_loss=loss, best_validation_loss=best)
            if stale >= 3:
                break
        if best < frozen_loss:
            model.set_weights(best_weights)
            fine_tune["applied"] = True
            fine_tune["improved_validation"] = True
        else:
            model.set_weights(frozen_weights)
            best = frozen_loss
            base.trainable = False
        history.extend({"epoch": f"fine_tune_{item['epoch']}", "validation_loss": item["validation_loss"]} for item in fine_tune["history"])
    status("evaluating")
    scores = model.predict(pixels["test"], verbose=0)
    predicted = scores.argmax(axis=1)
    report = classification_report(targets["test"], predicted, labels=list(range(len(classes))), target_names=list(labels), output_dict=True, zero_division=0)
    evaluation = {"accuracy": float(accuracy_score(targets["test"], predicted)), "classification_report": report,
                  "confusion_matrix": confusion_matrix(targets["test"], predicted, labels=list(range(len(classes)))).tolist(),
                  "class_order": list(labels), "dataset": metadata, "history": history, "fine_tune": fine_tune,
                  "selected_epoch": selected_epoch,
                  "settings": {"seed": 42, "max_epochs": 60, "patience": 8, "batch_size": 16, "learning_rate": 0.001, "dropout": 0.2, "backbone": "Frozen ImageNet MobileNetV2", "fine_tune_last_blocks": args.fine_tune, "batch_normalization_frozen_during_fine_tuning": True, "fine_tune_learning_rate": 1e-5 if args.fine_tune else None, "selection": "minimum validation cross entropy", "train_only_augmentation": TRAIN_ONLY_AUGMENTATION, "input": "Pillow 224x224 RGB, shared geoflora_ml.inference.preprocess, external MobileNetV2 scaling"},
                  "limitations": ["Tiny validation/test samples for new classes", "Owner-attested labels/geography, not independent botanical verification", "Different frozen split from v3; scores not a direct model comparison", "No non-plant/unknown-class training; unsupported inputs can score highly", "Uncalibrated confidence", "Candidate only; active model unchanged"], "tensorflow_version": tf.__version__}
    model.save(OUT / "mobilenetv2.keras")
    write_json(OUT / "class_mapping.json", {"classes": classes})
    write_json(OUT / "evaluation.json", evaluation)
    reloaded = tf.keras.models.load_model(OUT / "mobilenetv2.keras")
    np.testing.assert_allclose(model(np.zeros((1, 224, 224, 3)), training=False).numpy(), reloaded(np.zeros((1, 224, 224, 3)), training=False).numpy(), atol=1e-5)
    test_rows = [r for r in rows if r["split"] == "test"]
    predictions = [{"source": r["source"], "source_id": r["source_id"], "expected": r["species_id"], "predicted": classes[int(p)]["id"], "confidence": float(max(s))} for r, p, s in zip(test_rows, predicted, scores)]
    write_json(OUT / "test_predictions.json", predictions)
    write_json(OUT / "checksums.json", {p.name: digest(p) for p in OUT.iterdir() if p.is_file()})
    status("completed", accuracy=evaluation["accuracy"], macro_f1=report["macro avg"]["f1-score"], images=len(rows), classes=len(classes), activated=False, reload_equivalence="passed")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        status("failed", error=f"{type(error).__name__}: {error}")
        raise
