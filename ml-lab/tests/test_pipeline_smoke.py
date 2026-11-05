"""End-to-end pipeline smoke test on SYNTHETIC images (pipeline correctness only - not a model result).

Uses MobileNetV2 without pretrained weights at 96 px for speed and to stay offline.
"""

import json

import numpy as np
import pytest

from geoflora_ml.config import project_path
from geoflora_ml.evaluation import evaluate_run
from geoflora_ml.export import ExportBlocked, export_run
from geoflora_ml.inference import Predictor
from geoflora_ml.openset import apply_temperature, expected_calibration_error, fit_temperature, select_threshold
from geoflora_ml.splitting import prepare_splits
from geoflora_ml.training import train
from geoflora_ml.utils import read_json, sha256_file
from geoflora_ml.validation import validate_manifest


def test_threshold_selection_uses_validation_only():
    known = np.array([0.9, 0.8, 0.95, 0.7, 0.85])
    unknown = np.array([0.4, 0.5, 0.75, 0.3])
    t = select_threshold(known, unknown, "youden", 0.95)
    assert t["strategy"] == "youden" and 0.5 < t["threshold"] <= 0.8
    t2 = select_threshold(known, None, "youden", 0.8)
    assert t2["strategy"] == "known_acceptance" and "note" in t2


def test_temperature_scaling_reduces_overconfidence():
    rng = np.random.default_rng(0)
    labels = rng.integers(0, 3, 400)
    probs = np.full((400, 3), 0.01)
    pred = np.where(rng.random(400) < 0.6, labels, (labels + 1) % 3)  # 60% accurate but ~98% confident
    probs[np.arange(400), pred] = 0.98
    ece_raw, _ = expected_calibration_error(probs, labels)
    t = fit_temperature(probs, labels)
    ece_cal, _ = expected_calibration_error(apply_temperature(probs, t), labels)
    assert t > 1 and ece_cal < ece_raw


@pytest.mark.slow
def test_train_evaluate_export_predict(make_project):
    cfg = make_project(n_per_species=20)
    validate_manifest(cfg)
    assert prepare_splits(cfg)["ready_for_training"]

    run = train(cfg, run_name="smoke")
    for f in ("model.keras", "history.json", "train_summary.json", "class_mapping.json", "run_config.yaml",
              "environment.json", "training_log.csv", "train_images.csv", "test_images.csv"):
        assert (run / f).exists(), f
    summary = read_json(run / "train_summary.json")
    assert summary["num_classes"] == 3

    m = evaluate_run(cfg, run)
    assert m["test"]["images"] > 0 and 0 <= m["test"]["accuracy"] <= 1
    assert len(m["confusion_matrix"]["matrix"]) == 3
    assert m["unsupported_species"]["test"]["unknown_images"] > 0
    assert "selected_on" in m["unsupported_species"]["threshold"]
    assert set(m["robustness_synthetic"]) >= {"darker_40pct", "gaussian_blur"}
    ev = run / "evaluation"
    for f in ("research_evaluation_report.md", "confusion_matrix_counts.png", "training_curves.png",
              "reliability_diagram.png", "unknown_score_distribution.png", "metrics.json"):
        assert (ev / f).exists(), f
    report = (ev / "research_evaluation_report.md").read_text(encoding="utf-8")
    assert "Proposed future improvements (not yet tested)" in report and "Unsupported-species evaluation" in report

    class_ids = [c["species_id"] for c in read_json(run / "class_mapping.json")["classes"]]
    project_path(cfg, "species_descriptions").write_text(json.dumps(
        {class_ids[0]: {"summary": "test description", "review_status": "draft_unverified"},
         "GF-SP-9999": {"summary": "not a model class"}}), encoding="utf-8")
    out = export_run(cfg, run, model_version="test-model-v0")
    assert set(read_json(out / "species_descriptions.json")) == {class_ids[0]}  # only model classes are shipped
    meta = read_json(out / "model_metadata.json")
    assert [s["description_review_status"] for s in meta["supported_species"]] == \
        ["draft_unverified"] + ["missing"] * (len(class_ids) - 1)
    assert meta["status"] == "candidate_not_activated"
    assert meta["model_sha256"] == sha256_file(out / "model.keras")
    assert [s["species_id"] for s in meta["supported_species"]] == [c["species_id"] for c in read_json(out / "class_mapping.json")["classes"]]
    for f in ("preprocessing.json", "prediction_output_spec.json", "evaluation_report.md", "SHA256SUMS.txt"):
        assert (out / f).exists(), f
    with pytest.raises(ExportBlocked):
        export_run(cfg, run, model_version="test-model-v0")  # never overwrites an existing export

    img = next(project_path(cfg, "test").rglob("*.jpg"))
    res = Predictor(out).predict(img)
    assert res["model_version"] == "test-model-v0"
    assert res["prediction"]["species_id"].startswith("GF-SP-")
    expected = "test description" if res["prediction"]["species_id"] == class_ids[0] else None
    assert (res["prediction"]["description"] or {}).get("summary") == expected
    assert res["unknown_handling"]["decision"] in ("supported_species", "unsupported_or_uncertain")
    assert "latitude" not in json.dumps(res).lower()
    assert abs(sum(t["softmax_score"] for t in Predictor(out).predict(img, top_k=3)["top_k"]) - 1) < 1e-4
