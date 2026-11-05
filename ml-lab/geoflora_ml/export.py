"""Export an evaluated run as a self-contained integration bundle for the GeoFlora FastAPI service.

The bundle is written to models/exported/<model_version>/ only. Nothing is deployed, uploaded,
registered or activated; activation remains a manual decision in the GeoFlora application.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from .catalog import by_id, load_catalog
from .config import project_path
from .utils import read_json, sha256_file, utc_now_iso, utc_stamp, write_json


class ExportBlocked(RuntimeError):
    pass


PREDICTION_OUTPUT_SPEC = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "GeoFlora-ML-Lab prediction output",
    "description": "Returned per image by geoflora_ml.inference.Predictor.predict. The model never returns GPS "
                   "coordinates or occurrence records; GeoFlora attaches location from the user's observation.",
    "type": "object",
    "required": ["model_version", "prediction", "top_k", "unknown_handling", "disclaimer"],
    "properties": {
        "model_version": {"type": "string"},
        "dataset_version": {"type": "string"},
        "image": {"type": "object", "properties": {"filename": {"type": "string"}, "sha256": {"type": "string"}}},
        "prediction": {
            "type": "object",
            "required": ["species_id", "scientific_name", "softmax_score"],
            "properties": {
                "species_id": {"type": "string", "description": "Stable GeoFlora-ML-Lab species identifier (GF-SP-xxxx)."},
                "scientific_name": {"type": "string"},
                "common_name": {"type": "string"},
                "gbif_taxon_key": {"type": ["integer", "null"]},
                "ecological_status": {"enum": ["target_invasive", "introduced_naturalized", "native_nontarget", "unresolved"]},
                "status_verification": {"enum": ["unverified", "verified"]},
                "is_target_invasive": {"type": "boolean"},
                "softmax_score": {"type": "number", "minimum": 0, "maximum": 1,
                                  "description": "Uncalibrated model score - not a probability of correctness."},
                "description": {"type": ["object", "null"],
                                "description": "Species description from species_descriptions.json (summary, identifying "
                                               "features, impacts, look-alikes, references, review_status); null if none."},
            },
        },
        "top_k": {"type": "array", "items": {"type": "object", "properties": {
            "rank": {"type": "integer"}, "species_id": {"type": "string"},
            "scientific_name": {"type": "string"}, "softmax_score": {"type": "number"}}}},
        "unknown_handling": {"type": "object", "properties": {
            "score_type": {"type": "string"}, "score": {"type": "number"}, "threshold": {"type": ["number", "null"]},
            "decision": {"enum": ["supported_species", "unsupported_or_uncertain", None]}}},
        "inference_ms": {"type": "number"},
        "timestamp": {"type": "string"},
        "disclaimer": {"type": "string"},
    },
}


def export_run(cfg: dict, run_dir: str | Path, model_version: str | None = None, savedmodel: bool = False) -> Path:
    run_dir = Path(run_dir)
    run_cfg = yaml.safe_load((run_dir / "run_config.yaml").read_text(encoding="utf-8"))
    if run_cfg.get("provisional", {}).get("enabled"):
        raise ExportBlocked("this is a PROVISIONAL pilot run trained on unreviewed labels; it cannot be exported "
                            "as a GeoFlora integration candidate")
    metrics_path = run_dir / "evaluation" / "metrics.json"
    report_path = run_dir / "evaluation" / "research_evaluation_report.md"
    if cfg["export"]["require_evaluation"] and not (metrics_path.exists() and report_path.exists()):
        raise ExportBlocked("run has not been evaluated; run scripts/evaluate.py first")
    metrics = read_json(metrics_path)
    if metrics["test"]["images"] < int(cfg["export"]["min_test_images_total"]):
        raise ExportBlocked(f"only {metrics['test']['images']} test images (< {cfg['export']['min_test_images_total']}); "
                            "the evaluation is too small to support an integration candidate")
    mapping = read_json(run_dir / "class_mapping.json")
    # Ecological status describes the species, not the trained weights: take it from the current catalog so a status
    # verified after training is exported without retraining. Class order and species_id never change here.
    catalog = by_id(load_catalog(project_path(cfg, "species_catalog")))
    for c in mapping["classes"]:
        sp = catalog.get(c["species_id"])
        if sp is not None:
            c.update(ecological_status=sp.ecological_status, status_verification=sp.status_verification,
                     is_target_invasive=sp.ecological_status == "target_invasive")
    run_cfg = yaml.safe_load((run_dir / "run_config.yaml").read_text(encoding="utf-8"))
    summary = read_json(run_dir / "train_summary.json")
    size = int(run_cfg["train"]["image_size"])

    model_version = model_version or f"gfml-mnv2-{mapping['num_classes']}c-{utc_stamp()[:8]}-{run_dir.name[-6:]}"
    out = project_path(cfg, "exported") / model_version
    if out.exists():
        raise ExportBlocked(f"{out} already exists; choose a new --model-version")
    out.mkdir(parents=True)

    shutil.copy2(run_dir / "model.keras", out / "model.keras")
    write_json(out / "class_mapping.json", mapping)
    shutil.copy2(report_path, out / "evaluation_report.md")
    shutil.copy2(metrics_path, out / "evaluation_metrics.json")
    for png in (run_dir / "evaluation").glob("*.png"):
        shutil.copy2(png, out / png.name)
    if savedmodel:
        from tensorflow import keras

        keras.models.load_model(out / "model.keras").export(str(out / "savedmodel"))

    preprocessing = {
        "input_size": [size, size, 3],
        "color_space": "RGB",
        "steps": [
            "Decode image; apply EXIF orientation (PIL.ImageOps.exif_transpose); convert to RGB (alpha composited on white).",
            "Optional but recommended for parity with training: re-encode as JPEG quality 95 and decode.",
            f"Resize to {size}x{size} with bilinear interpolation (tf.image.resize, method='bilinear'); aspect ratio NOT preserved.",
            "Cast to float32 with values in [0, 255]; add batch dimension.",
            "Do NOT apply MobileNetV2 preprocess_input - scaling to [-1, 1] is performed inside the model.",
        ],
        "input_dtype": "float32", "input_range": [0, 255], "batch_axis": 0,
        "output": "softmax probabilities over class_mapping.json classes (index order)",
        "reference_implementation": "geoflora_ml/inference.py::preprocess_image",
    }
    write_json(out / "preprocessing.json", preprocessing)
    write_json(out / "prediction_output_spec.json", PREDICTION_OUTPUT_SPEC)
    desc_path = project_path(cfg, "species_descriptions") if "species_descriptions" in cfg["paths"] else None
    descriptions = read_json(desc_path) if desc_path and desc_path.exists() else {}
    descriptions = {c["species_id"]: descriptions[c["species_id"]] for c in mapping["classes"] if c["species_id"] in descriptions}
    write_json(out / "species_descriptions.json", descriptions)

    thr = metrics["unsupported_species"]["threshold"]
    checksum = sha256_file(out / "model.keras")
    meta = {
        "model_version": model_version,
        "status": "candidate_not_activated",
        "status_note": "Exported for review only. Not deployed or activated. Activation must be a manual decision in GeoFlora.",
        "exported": utc_now_iso(),
        "source_run": run_dir.name,
        "dataset_version": mapping["dataset_version"],
        "architecture": f"MobileNetV2 (alpha={run_cfg['train']['alpha']}, initial weights={run_cfg['train']['weights']}) "
                        f"+ Dense({mapping['num_classes']}, softmax)",
        "framework": {k: v for k, v in read_json(run_dir / "environment.json").items() if k in ("tensorflow_version", "keras_version", "python")},
        "model_file": "model.keras",
        "model_sha256": checksum,
        "num_classes": mapping["num_classes"],
        "supported_species": [{**{k: c[k] for k in ("index", "species_id", "scientific_name", "common_name",
                                                    "ecological_status", "status_verification", "is_target_invasive")},
                               "description_review_status": descriptions.get(c["species_id"], {}).get("review_status", "missing")}
                              for c in mapping["classes"]],
        "unknown_handling": {"score_type": thr["score_type"], "threshold": thr["threshold"], "strategy": thr["strategy"],
                             "selected_on": thr["selected_on"]},
        "evaluation_summary": {
            "test_images": metrics["test"]["images"],
            "test_accuracy": metrics["test"]["accuracy"],
            "test_accuracy_ci": metrics["test"]["uncertainty"].get("accuracy_exact_ci", metrics["test"]["uncertainty"]["accuracy_ci"]),
            "test_macro_f1": metrics["test"]["macro_f1"],
            "test_macro_f1_ci": metrics["test"]["uncertainty"]["macro_f1_ci"],
            "unknown_false_acceptance_with_threshold":
                metrics["unsupported_species"]["test"].get("unknown_false_acceptance_rate_with_threshold"),
            "unknown_test_images": metrics["unsupported_species"]["test"].get("unknown_images", 0),
            "batch1_latency_ms_median": metrics["runtime"]["batch1_latency_ms_median"],
            "device": metrics["runtime"]["device"],
        },
        "training": {"selected_phase": summary["selected_phase"], "epochs_run": summary["epochs_run"],
                     "images": summary["images"], "seed": run_cfg["project"]["seed"]},
        "integration_notes": [
            "Load with tensorflow.keras.models.load_model('model.keras') (TensorFlow/Keras versions in 'framework').",
            "Follow preprocessing.json exactly; key all downstream logic on species_id, not on output index.",
            "Verify model_sha256 before loading. Store model_version with each prediction record in GeoFlora.",
            "Location, occurrence records and administrative verification remain the responsibility of GeoFlora.",
        ],
    }
    write_json(out / "model_metadata.json", meta)
    write_json(out / "supported_species.json", meta["supported_species"])
    sums = [f"{sha256_file(p)}  {p.relative_to(out).as_posix()}" for p in sorted(out.rglob("*")) if p.is_file()]
    (out / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="utf-8")
    return out
