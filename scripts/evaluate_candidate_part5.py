"""Part 5 evaluation of a frozen expanded candidate, without retraining or activation.

Confidence threshold is chosen on validation only, then applied once to test. Unsupported-species
inputs come from the 100-species staging archive (species outside the candidate's classes, no shared
checksums). Non-plant inputs are synthetic proxies. Blur/lighting are perturbations of held-out test
photos. Latency is measured in-process and through the FastAPI app on this machine.
Run from the repository root with services/ml/.venv/Scripts/python.exe.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import platform
import statistics
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter
from fastapi.testclient import TestClient
from geoflora_ml.inference.api import create_app
from geoflora_ml.inference.predictor import PlantPredictor, decode_image

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "storage/datasets/curated/v5_part2_final_five_classes"
CANDIDATE = ROOT / "storage/models/candidates/mobilenetv2_v5_five_seed42"
STAGING = ROOT / "storage/datasets/staging/species_100_ph"
OUTPUT = ROOT / "docs/part-5-v5-evaluation.json"
THRESHOLDS = [round(0.40 + 0.05 * i, 2) for i in range(12)]
TARGET_SELECTIVE_ACCURACY = 0.90
# Synonyms of supported classes, so they are never treated as unsupported inputs.
SYNONYMS = {"chromolaena odorata": {"eupatorium odoratum"}, "pontederia crassipes": {"eichhornia crassipes"}}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def image_path(row: dict) -> Path:
    # v5 manifests are workspace-relative; the preserved v3 manifest is relative to storage/datasets.
    path = ROOT / row["local_path"]
    return path if path.is_file() else ROOT / "storage/datasets" / row["local_path"]


def png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def scores_for(model, payloads: list[bytes]) -> np.ndarray:
    # decode_image is the exact live inference path (validation + shared preprocessing).
    batch = np.concatenate([decode_image(payload) for payload in payloads])
    return np.concatenate([model.predict(batch[i:i + 16], verbose=0) for i in range(0, len(batch), 16)])


def selective(scores: np.ndarray, targets: np.ndarray, threshold: float) -> dict:
    confidence, predicted = scores.max(axis=1), scores.argmax(axis=1)
    accepted = confidence >= threshold
    correct = int(((predicted == targets) & accepted).sum())
    return {"threshold": threshold, "coverage": float(accepted.mean()), "accepted": int(accepted.sum()),
            "accepted_correct": correct, "selective_accuracy": correct / int(accepted.sum()) if accepted.any() else None,
            "top1_accuracy": float((predicted == targets).mean())}


def acceptance(scores: np.ndarray, threshold: float, classes: list[str]) -> dict:
    confidence, predicted = scores.max(axis=1), scores.argmax(axis=1)
    accepted = confidence >= threshold
    return {"images": len(scores), "false_acceptance_rate": float(accepted.mean()), "falsely_accepted": int(accepted.sum()),
            "mean_top_confidence": float(confidence.mean()), "max_top_confidence": float(confidence.max()),
            "accepted_as": dict(Counter(classes[int(p)] for p, a in zip(predicted, accepted) if a))}


def synthetic_non_plants() -> list[tuple[str, Image.Image]]:
    rng = np.random.default_rng(42)
    images = [(f"solid_{name}", Image.new("RGB", (256, 256), color)) for name, color in
              [("black", (0, 0, 0)), ("white", (255, 255, 255)), ("grey", (128, 128, 128)), ("red", (200, 30, 30)),
               ("green", (40, 160, 60)), ("blue", (30, 60, 200)), ("brown", (110, 75, 40)), ("sky", (135, 190, 235))]]
    for index in range(6):
        images.append((f"noise_{index}", Image.fromarray(rng.integers(0, 256, (256, 256, 3), dtype=np.uint8))))
    ramp = np.linspace(0, 255, 256, dtype=np.uint8)
    images.append(("gradient_horizontal", Image.fromarray(np.stack([np.tile(ramp, (256, 1))] * 3, axis=-1))))
    images.append(("gradient_green", Image.fromarray(np.stack([np.zeros((256, 256), np.uint8), np.tile(ramp, (256, 1)), np.zeros((256, 256), np.uint8)], axis=-1))))
    checker = ((np.indices((256, 256)) // 32).sum(axis=0) % 2 * 255).astype(np.uint8)
    images.append(("checkerboard", Image.fromarray(np.stack([checker] * 3, axis=-1))))
    stripes = np.zeros((256, 256, 3), np.uint8); stripes[::16] = (250, 220, 40)
    images.append(("stripes", Image.fromarray(stripes)))
    return images


PERTURBATIONS = {
    "blur_radius_2": lambda im: im.filter(ImageFilter.GaussianBlur(2)),
    "blur_radius_5": lambda im: im.filter(ImageFilter.GaussianBlur(5)),
    "dark_brightness_0.4": lambda im: ImageEnhance.Brightness(im).enhance(0.4),
    "bright_brightness_1.8": lambda im: ImageEnhance.Brightness(im).enhance(1.8),
    "low_contrast_0.5": lambda im: ImageEnhance.Contrast(im).enhance(0.5),
}


def percentile(values: list[float], q: float) -> float:
    return float(np.percentile(np.asarray(values), q))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frozen-dataset", type=Path, default=DATA)
    parser.add_argument("--candidate", type=Path, default=CANDIDATE)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--per-unsupported-species", type=int, default=2)
    parser.add_argument("--latency-requests", type=int, default=36)
    args = parser.parse_args()
    data, candidate = args.frozen_dataset.resolve(), args.candidate.resolve()

    for name, expected in json.loads((candidate / "checksums.json").read_text()).items():
        assert sha(candidate / name) == expected, name
    metadata = json.loads((data / "dataset_metadata.json").read_text())
    assert sha(data / "manifest.csv") == metadata["manifest_sha256"]
    active = ROOT / "storage/models/mobilenetv2.keras"
    active_before = sha(active)

    with (data / "manifest.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    mapping = json.loads((candidate / "class_mapping.json").read_text())["classes"]
    classes = [entry["id"] for entry in mapping]
    supported_names = set()
    for entry in mapping:
        name = entry["scientific_name"].strip().lower()
        supported_names |= {name} | SYNONYMS.get(name, set())
    index = {name: i for i, name in enumerate(classes)}

    started = time.perf_counter()
    predictor = PlantPredictor(model_path=candidate / "mobilenetv2.keras", class_mapping_path=candidate / "class_mapping.json",
                               species_path=data / "species.yaml" if (data / "species.yaml").is_file() else None)
    cold_load_seconds = time.perf_counter() - started
    assert predictor.ready, predictor.unavailable_reason
    model = predictor._model

    split_rows = {split: [r for r in rows if r["split"] == split] for split in ("validation", "test")}
    payloads = {split: [image_path(r).read_bytes() for r in items] for split, items in split_rows.items()}
    targets = {split: np.array([index[r["species_id"]] for r in items]) for split, items in split_rows.items()}
    scores = {split: scores_for(model, payloads[split]) for split in payloads}

    # 1. Threshold selection on validation only.
    sweep = [selective(scores["validation"], targets["validation"], t) for t in THRESHOLDS]
    eligible = [s for s in sweep if s["selective_accuracy"] is not None and s["selective_accuracy"] >= TARGET_SELECTIVE_ACCURACY]
    selected = eligible[0]["threshold"] if eligible else None
    threshold = selected if selected is not None else predictor.confidence_threshold
    test_at_selected = selective(scores["test"], targets["test"], threshold)
    test_at_current = selective(scores["test"], targets["test"], predictor.confidence_threshold)

    # 2. Held-out error listing.
    errors = []
    for row, probabilities in zip(split_rows["test"], scores["test"]):
        predicted = int(probabilities.argmax())
        if classes[predicted] != row["species_id"]:
            errors.append({"source": row["source"], "source_id": row["source_id"], "source_url": row.get("source_url"),
                           "expected": row["species_id"], "predicted": classes[predicted],
                           "confidence": float(probabilities.max()), "accepted_at_threshold": bool(probabilities.max() >= threshold)})

    # 3. Unsupported species from the staging archive.
    known = {r["sha256"] for r in rows}
    unsupported, names = [], set()
    for manifest in sorted(STAGING.glob("*/raw/manifest.jsonl")):
        records = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines() if line.strip()]
        records = [r for r in records if r.get("scientific_name", "").strip().lower() not in supported_names and r["sha256"] not in known]
        for record in sorted(records, key=lambda r: r["sha256"])[: args.per_unsupported_species]:
            path = manifest.parent.parent / record["local_path"]
            if path.is_file() and sha(path) == record["sha256"]:
                unsupported.append((record["scientific_name"], path.read_bytes()))
                names.add(record["scientific_name"])
    unsupported_scores = scores_for(model, [payload for _, payload in unsupported])
    unsupported_result = acceptance(unsupported_scores, threshold, classes)
    unsupported_result.update({"species": len(names), "source": "storage/datasets/staging/species_100_ph (outside candidate classes; no shared checksums)",
                               "at_current_threshold": acceptance(unsupported_scores, predictor.confidence_threshold, classes)})
    ranked = sorted(zip(unsupported, unsupported_scores), key=lambda item: -item[1].max())[:10]
    unsupported_result["highest_scores"] = [{"scientific_name": name, "predicted": classes[int(s.argmax())], "confidence": float(s.max())} for (name, _), s in ranked]

    # 4. Synthetic non-plant proxies.
    synthetic = synthetic_non_plants()
    synthetic_scores = scores_for(model, [png_bytes(image) for _, image in synthetic])
    synthetic_result = acceptance(synthetic_scores, threshold, classes)
    synthetic_result["at_current_threshold"] = acceptance(synthetic_scores, predictor.confidence_threshold, classes)
    synthetic_result["per_image"] = [{"name": name, "predicted": classes[int(s.argmax())], "confidence": float(s.max())} for (name, _), s in zip(synthetic, synthetic_scores)]

    # 5. Blur and lighting perturbations of held-out test photos.
    robustness = {"original": selective(scores["test"], targets["test"], threshold)}
    for name, transform in PERTURBATIONS.items():
        perturbed = []
        for payload in payloads["test"]:
            with Image.open(io.BytesIO(payload)) as image:
                perturbed.append(png_bytes(transform(image.convert("RGB"))))
        result = selective(scores_for(model, perturbed), targets["test"], threshold)
        robustness[name] = result

    # 6. Latency on this machine: warm in-process predict and FastAPI /predict.
    latency_payloads = (payloads["test"] * ((args.latency_requests // len(payloads["test"])) + 1))[: args.latency_requests]
    for payload in latency_payloads[:3]:
        predictor.predict(payload)
    in_process = []
    for payload in latency_payloads:
        tick = time.perf_counter(); predictor.predict(payload); in_process.append((time.perf_counter() - tick) * 1000)
    http = []
    with TestClient(create_app(predictor)) as client:
        for payload in latency_payloads:
            tick = time.perf_counter()
            response = client.post("/predict", files={"image": ("photo.jpg", payload, "image/jpeg")})
            http.append((time.perf_counter() - tick) * 1000)
            assert response.status_code == 200, response.text
    sizes = [len(p) for p in latency_payloads]
    latency = {"requests": len(latency_payloads), "concurrency": 1, "cold_model_load_seconds": cold_load_seconds,
               "payload_bytes": {"min": min(sizes), "median": statistics.median(sizes), "max": max(sizes)},
               "in_process_predict_ms": {"p50": percentile(in_process, 50), "p95": percentile(in_process, 95), "max": max(in_process)},
               "fastapi_testclient_predict_ms": {"p50": percentile(http, 50), "p95": percentile(http, 95), "max": max(http)},
               "scope": "Local in-process/ASGI timing on held-out photos; excludes browser upload, network and the Next.js proxy (Part 6)."}

    assert sha(active) == active_before
    import tensorflow as tf
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "candidate": candidate.relative_to(ROOT).as_posix(), "dataset": data.relative_to(ROOT).as_posix(),
        "class_order": classes,
        "threshold_selection": {"split": "validation", "rule": f"lowest threshold in {THRESHOLDS[0]}-{THRESHOLDS[-1]} (step 0.05) with validation selective accuracy >= {TARGET_SELECTIVE_ACCURACY}",
                                "validation_images": len(targets["validation"]), "sweep": sweep, "selected_threshold": selected,
                                "fallback": None if selected is not None else f"no threshold met the rule; kept current {predictor.confidence_threshold}",
                                "current_service_threshold": predictor.confidence_threshold},
        "test_at_selected_threshold": test_at_selected, "test_at_current_threshold": test_at_current,
        "test_errors": errors, "unsupported_species": unsupported_result, "synthetic_non_plants": synthetic_result,
        "robustness_test_perturbations": robustness, "latency": latency,
        "environment": {"platform": platform.platform(), "processor": platform.processor(), "cpu_count": os.cpu_count(),
                        "python": platform.python_version(), "tensorflow": tf.__version__,
                        "tf_threads": {k: os.environ.get(k) for k in ("TF_NUM_INTRAOP_THREADS", "TF_NUM_INTEROP_THREADS")}},
        "active_model_unchanged": True,
    }
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"selected_threshold": selected, "test_at_selected": test_at_selected,
                      "unsupported_far": unsupported_result["false_acceptance_rate"], "synthetic_far": synthetic_result["false_acceptance_rate"],
                      "latency_p95_ms": latency["fastapi_testclient_predict_ms"]["p95"], "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
