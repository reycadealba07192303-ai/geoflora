"""Evaluation of a trained run on isolated test data, unsupported-species data, robustness and runtime."""

from __future__ import annotations

import logging
import time
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from sklearn.metrics import confusion_matrix, f1_score, precision_recall_fscore_support

from . import openset, plots
from .config import project_path, project_root
from .manifest import load_manifest
from .splitting import load_split_frame
from .utils import read_json, resolve_path, utc_now_iso, write_json

log = logging.getLogger(__name__)


def _load_run_frame(run_dir: Path, split: str, root: Path) -> pd.DataFrame:
    f = pd.read_csv(run_dir / f"{split}_images.csv", dtype=str, keep_default_na=False)
    f["abs_path"] = f["split_path"].map(lambda p: str(resolve_path(p, root)))
    return f


def predict_paths(model, paths: list[str], image_size: int, batch_size: int = 32) -> np.ndarray:
    from .data import make_dataset

    if not paths:
        return np.zeros((0, model.output_shape[-1]), dtype=np.float32)
    ds = make_dataset(paths, None, 0, image_size, batch_size)
    return model.predict(ds, verbose=0)


def group_bootstrap(y_true: np.ndarray, y_pred: np.ndarray, groups: np.ndarray, n: int, level: float,
                    seed: int, num_classes: int) -> dict:
    """Cluster (observation-group) bootstrap CIs for accuracy and macro F1."""
    rng = np.random.default_rng(seed)
    uniq = np.unique(groups)
    idx_of = {g: np.nonzero(groups == g)[0] for g in uniq}
    accs, f1s = [], []
    for _ in range(n):
        sample = rng.choice(uniq, size=len(uniq), replace=True)
        idx = np.concatenate([idx_of[g] for g in sample])
        accs.append((y_true[idx] == y_pred[idx]).mean())
        f1s.append(f1_score(y_true[idx], y_pred[idx], labels=list(range(num_classes)), average="macro", zero_division=0))
    a = (1 - level) / 2
    return {
        "method": f"observation-group bootstrap, {n} resamples",
        "confidence_level": level,
        "accuracy_ci": [float(np.quantile(accs, a)), float(np.quantile(accs, 1 - a))],
        "macro_f1_ci": [float(np.quantile(f1s, a)), float(np.quantile(f1s, 1 - a))],
        # Bootstrap intervals collapse to a point when every test image is correct; the exact binomial
        # interval does not, so it is the headline accuracy interval.
        "accuracy_exact_ci": clopper_pearson(int((y_true == y_pred).sum()), len(y_true), level),
        "accuracy_exact_ci_method": "Clopper-Pearson exact binomial (treats images as independent)",
    }


def clopper_pearson(k: int, n: int, level: float = 0.95) -> list[float]:
    from scipy.stats import beta

    if n == 0:
        return [0.0, 1.0]
    a = (1 - level) / 2
    lo = float(beta.ppf(a, k, n - k + 1)) if k > 0 else 0.0
    hi = float(beta.ppf(1 - a, k + 1, n - k)) if k < n else 1.0
    return [lo, hi]


def classification_metrics(y_true: np.ndarray, probs: np.ndarray, names: list[str], top_k: int) -> dict:
    n = len(names)
    y_pred = probs.argmax(axis=1)
    p, r, f, s = precision_recall_fscore_support(y_true, y_pred, labels=list(range(n)), zero_division=0)
    k = min(top_k, n)
    topk = np.argsort(-probs, axis=1)[:, :k]
    return {
        "images": int(len(y_true)),
        "accuracy": float((y_pred == y_true).mean()) if len(y_true) else None,
        f"top_{k}_accuracy": float(np.mean([t in row for t, row in zip(y_true, topk)])) if len(y_true) else None,
        "macro_precision": float(p.mean()), "macro_recall": float(r.mean()),
        "macro_f1": float(f1_score(y_true, y_pred, labels=list(range(n)), average="macro", zero_division=0)),
        "weighted_f1": float(f1_score(y_true, y_pred, labels=list(range(n)), average="weighted", zero_division=0)),
        "per_class": [{"species": names[i], "precision": float(p[i]), "recall": float(r[i]), "f1": float(f[i]),
                       "support": int(s[i])} for i in range(n)],
    }


def error_analysis(y_true, probs, names) -> list[dict]:
    y_pred = probs.argmax(axis=1)
    conf = probs.max(axis=1)
    out = []
    for i, name in enumerate(names):
        t = y_true == i
        pr = y_pred == i
        fn = Counter(names[j] for j in y_pred[t & ~pr])
        fp = Counter(names[j] for j in y_true[pr & ~t])
        out.append({
            "species": name, "support": int(t.sum()), "true_positives": int((t & pr).sum()),
            "false_negatives": int((t & ~pr).sum()), "false_positives": int((pr & ~t).sum()),
            "false_negatives_predicted_as": dict(fn.most_common()),
            "false_positives_true_species": dict(fp.most_common()),
            "mean_score_correct": float(conf[t & pr].mean()) if (t & pr).any() else None,
            "mean_score_incorrect": float(conf[t & ~pr].mean()) if (t & ~pr).any() else None,
        })
    return out


def top_confusions(cm: np.ndarray, names: list[str], k: int = 10) -> list[dict]:
    pairs = [(int(cm[i, j]), names[i], names[j]) for i in range(len(names)) for j in range(len(names)) if i != j and cm[i, j] > 0]
    return [{"true": t, "predicted": p, "count": c} for c, t, p in sorted(pairs, reverse=True)[:k]]


def perturb(images, kind: str):
    import tensorflow as tf

    x = tf.convert_to_tensor(images)
    if kind == "darker_40pct":
        return tf.clip_by_value(x * 0.6, 0, 255)
    if kind == "brighter_40pct":
        return tf.clip_by_value(x * 1.4, 0, 255)
    if kind == "low_contrast":
        m = tf.reduce_mean(x, axis=[1, 2], keepdims=True)
        return tf.clip_by_value((x - m) * 0.5 + m, 0, 255)
    if kind == "gaussian_blur":
        k = np.outer(*(2 * [np.exp(-0.5 * (np.arange(-3, 4) / 1.5) ** 2)]))
        k = (k / k.sum()).astype(np.float32)[:, :, None, None]
        k = tf.constant(np.repeat(k, 3, axis=2))
        return tf.nn.depthwise_conv2d(x, k, strides=[1, 1, 1, 1], padding="SAME")
    if kind == "rotate_90":
        return tf.image.rot90(x)
    if kind == "jpeg_q20":
        return tf.stack([tf.image.adjust_jpeg_quality(im / 255.0, 20) * 255.0 for im in tf.unstack(x)])
    if kind == "center_crop_60pct":
        s = x.shape[1]
        return tf.image.resize(tf.image.central_crop(x, 0.6), (s, s))
    raise ValueError(kind)


PERTURBATIONS = ["darker_40pct", "brighter_40pct", "low_contrast", "gaussian_blur", "rotate_90", "jpeg_q20", "center_crop_60pct"]


def robustness(model, paths, y_true, image_size, n_cls) -> dict:
    """Accuracy under synthetic photometric/geometric perturbations of the test images."""
    import tensorflow as tf

    from .data import decode_and_resize

    images = np.stack([decode_and_resize(tf.constant(p), image_size).numpy() for p in paths])
    out = {}
    for kind in PERTURBATIONS:
        preds = []
        for start in range(0, len(images), 32):
            xb = perturb(images[start:start + 32], kind)
            preds.append(model(xb, training=False).numpy())
        y_pred = np.concatenate(preds).argmax(axis=1)
        out[kind] = {"accuracy": float((y_pred == y_true).mean()),
                     "macro_f1": float(f1_score(y_true, y_pred, labels=list(range(n_cls)), average="macro", zero_division=0))}
    return out


def runtime_profile(model, model_path: Path, image_size: int, warmup: int, runs: int) -> dict:
    import tensorflow as tf

    infer = tf.function(lambda x: model(x, training=False))
    x1 = tf.random.uniform((1, image_size, image_size, 3), 0, 255)
    x32 = tf.random.uniform((32, image_size, image_size, 3), 0, 255)
    for _ in range(warmup):
        infer(x1)
        infer(x32)
    lat = []
    for _ in range(runs):
        t = time.perf_counter()
        infer(x1).numpy()
        lat.append((time.perf_counter() - t) * 1000)
    t = time.perf_counter()
    reps = max(3, runs // 10)
    for _ in range(reps):
        infer(x32).numpy()
    thr = 32 * reps / (time.perf_counter() - t)
    return {
        "device": "GPU" if tf.config.list_physical_devices("GPU") else "CPU",
        "batch1_latency_ms_median": float(np.median(lat)), "batch1_latency_ms_p95": float(np.percentile(lat, 95)),
        "batch32_throughput_images_per_s": float(thr), "timing_runs": runs,
        "model_file_bytes": int(model_path.stat().st_size), "model_file_mb": round(model_path.stat().st_size / 1e6, 2),
        "total_params": int(model.count_params()),
        "note": "Model forward pass only (excludes image decoding/resizing). Measured on this machine.",
    }


def condition_breakdown(test: pd.DataFrame, y_true, y_pred, manifest: pd.DataFrame) -> dict:
    cols = ["cond_lighting", "cond_background", "cond_organ", "cond_growth_stage"]
    m = manifest.set_index("image_id")
    out = {}
    for c in cols:
        vals = test["image_id"].map(m[c]) if c in m else pd.Series([""] * len(test))
        if (vals != "").sum() == 0:
            continue
        rows = {}
        for v in sorted(set(vals) - {""}):
            mask = (vals == v).to_numpy()
            rows[v] = {"images": int(mask.sum()), "accuracy": float((y_true[mask] == y_pred[mask]).mean())}
        out[c] = rows
    return out


def evaluate_run(cfg: dict, run_dir: str | Path, write_report: bool = True) -> dict:
    from tensorflow import keras

    run_dir = Path(run_dir)
    root = project_root(cfg)
    ecfg = cfg["evaluate"]
    run_cfg = yaml.safe_load((run_dir / "run_config.yaml").read_text(encoding="utf-8"))
    size = int(run_cfg["train"]["image_size"])
    mapping = read_json(run_dir / "class_mapping.json")
    names = [c["scientific_name"] for c in mapping["classes"]]
    index_of = {c["species_id"]: c["index"] for c in mapping["classes"]}
    n_cls = len(names)
    model_path = run_dir / "model.keras"
    model = keras.models.load_model(model_path)
    out_dir = run_dir / "evaluation"
    out_dir.mkdir(exist_ok=True)

    val = _load_run_frame(run_dir, "val", root)
    test = _load_run_frame(run_dir, "test", root)
    unk_val = load_split_frame(cfg, "unknown_val") if "unknown_val" in cfg["paths"] else pd.DataFrame()
    unk_test = load_split_frame(cfg, "unknown_test")

    y_val = val["species_id"].map(index_of).to_numpy()
    y_test = test["species_id"].map(index_of).to_numpy()
    p_val = predict_paths(model, val["abs_path"].tolist(), size)
    p_test = predict_paths(model, test["abs_path"].tolist(), size)
    p_uval = predict_paths(model, unk_val["abs_path"].tolist(), size) if len(unk_val) else None
    p_utest = predict_paths(model, unk_test["abs_path"].tolist(), size) if len(unk_test) else None

    test_metrics = classification_metrics(y_test, p_test, names, int(ecfg["top_k"]))
    test_metrics["uncertainty"] = group_bootstrap(y_test, p_test.argmax(1), test["observation_group"].to_numpy(),
                                                  int(ecfg["bootstrap_resamples"]), float(ecfg["confidence_level"]),
                                                  int(cfg["project"]["seed"]), n_cls)
    cm = confusion_matrix(y_test, p_test.argmax(1), labels=list(range(n_cls)))

    # unsupported-species handling: threshold chosen on validation data only
    kind = ecfg["unknown_score"]
    thr = openset.select_threshold(openset.unknown_scores(p_val, kind),
                                   openset.unknown_scores(p_uval, kind) if p_uval is not None else None,
                                   ecfg["threshold_strategy"], float(ecfg["known_acceptance_target"]))
    thr["score_type"] = kind
    thr["selected_on"] = "validation (val + unknown_val); test sets not used"
    os_test = openset.open_set_metrics(p_test, y_test, p_utest, thr["threshold"], kind)
    per_unknown = {}
    if p_utest is not None:
        us = openset.unknown_scores(p_utest, kind)
        for sp_name, g in unk_test.groupby("scientific_name"):
            idx = g.index.to_numpy()
            per_unknown[sp_name] = {
                "images": int(len(idx)),
                "false_acceptance_rate_with_threshold": float((us[idx] >= thr["threshold"]).mean()),
                "assigned_labels_without_rejection": dict(Counter(names[j] for j in p_utest[idx].argmax(1)).most_common()),
            }

    # calibration diagnostics
    ece_raw, bins_raw = openset.expected_calibration_error(p_test, y_test)
    temperature = openset.fit_temperature(p_val, y_val) if len(y_val) else 1.0
    ece_cal, bins_cal = openset.expected_calibration_error(openset.apply_temperature(p_test, temperature), y_test)

    manifest = load_manifest(project_path(cfg, "image_manifest"))
    attrib = manifest.set_index("image_id")
    mis = test[p_test.argmax(1) != y_test].copy()
    if len(mis):
        mi = mis.index.to_numpy()
        mis["true_species"] = [names[y_test[i]] for i in mi]
        mis["predicted_species"] = [names[p_test[i].argmax()] for i in mi]
        mis["max_softmax"] = p_test[mi].max(1)
        mis["attribution"] = mis["image_id"].map(attrib["attribution"])
        mis["source_record"] = mis["image_id"].map(attrib["occurrence_id"])
        mis[["image_id", "true_species", "predicted_species", "max_softmax", "split_path", "attribution", "source_record"]] \
            .to_csv(out_dir / "misclassified_test_images.csv", index=False)

    history = read_json(run_dir / "history.json")
    plots.confusion_matrix_plot(cm, names, out_dir / "confusion_matrix_counts.png", normalize=False)
    plots.confusion_matrix_plot(cm, names, out_dir / "confusion_matrix_normalized.png", normalize=True)
    plots.training_curves(history["history"], history["phase"], out_dir / "training_curves.png")
    plots.reliability_diagram(bins_raw, bins_cal, out_dir / "reliability_diagram.png", temperature)
    plots.score_histogram(openset.unknown_scores(p_test, kind),
                          openset.unknown_scores(p_utest, kind) if p_utest is not None else None,
                          thr["threshold"], out_dir / "unknown_score_distribution.png", kind)

    metrics = {
        "run_id": run_dir.name, "evaluated": utc_now_iso(), "dataset_version": mapping.get("dataset_version"),
        "classes": names,
        "validation": {k: v for k, v in classification_metrics(y_val, p_val, names, int(ecfg["top_k"])).items() if k != "per_class"},
        "test": test_metrics,
        "confusion_matrix": {"labels": names, "matrix": cm.tolist()},
        "top_confusions": top_confusions(cm, names),
        "error_analysis": error_analysis(y_test, p_test, names),
        "unsupported_species": {
            "threshold": thr, "test": os_test, "per_unknown_species": per_unknown,
            "unknown_val_species": sorted(unk_val["scientific_name"].unique().tolist()) if len(unk_val) else [],
            "unknown_test_species": sorted(unk_test["scientific_name"].unique().tolist()) if len(unk_test) else [],
            "val": openset.open_set_metrics(p_val, y_val, p_uval, thr["threshold"], kind),
        },
        "calibration": {"ece_raw_test": ece_raw, "temperature_fitted_on_val": temperature,
                        "ece_temperature_scaled_test": ece_cal,
                        "note": "Softmax scores are not calibrated identification confidence."},
        "condition_breakdown": condition_breakdown(test, y_test, p_test.argmax(1), manifest),
        "runtime": runtime_profile(model, model_path, size, int(ecfg["timing_warmup"]), int(ecfg["timing_runs"])),
    }
    if ecfg.get("robustness_perturbations") and len(test):
        metrics["robustness_synthetic"] = robustness(model, test["abs_path"].tolist(), y_test, size, n_cls)
    write_json(out_dir / "metrics.json", metrics)
    if write_report:
        from .reporting import write_research_report

        write_research_report(cfg, run_dir, metrics)
    return metrics
