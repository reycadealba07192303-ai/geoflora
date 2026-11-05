"""Unsupported-species (open-set) handling and calibration diagnostics.

A closed-set softmax classifier always outputs one of its known classes, so without a rejection
rule every unsupported plant is falsely accepted. Here a rejection threshold on a score derived
from the softmax output is selected using VALIDATION data only (known val + unknown_val) and then
applied unchanged to the test and unknown_test sets.

Softmax scores are not calibrated probabilities; expected calibration error (ECE) is reported
before and after temperature scaling (temperature fitted on validation data) as a diagnostic.
"""

from __future__ import annotations

import numpy as np
from sklearn.metrics import roc_auc_score

EPS = 1e-12


def unknown_scores(probs: np.ndarray, kind: str = "max_softmax") -> np.ndarray:
    """Higher score = more likely a supported (known) species."""
    p = np.clip(probs, EPS, 1.0)
    if kind == "max_softmax":
        return p.max(axis=1)
    if kind == "margin":
        s = np.sort(p, axis=1)
        return s[:, -1] - s[:, -2]
    if kind == "neg_entropy":
        return (p * np.log(p)).sum(axis=1)
    raise ValueError(f"unknown score type '{kind}'")


def select_threshold(known_val: np.ndarray, unknown_val: np.ndarray | None, strategy: str,
                     known_acceptance_target: float) -> dict:
    """Pick a rejection threshold from validation scores only."""
    if strategy == "youden" and unknown_val is not None and len(unknown_val) > 0:
        cands = np.unique(np.concatenate([known_val, unknown_val]))
        best = None
        for t in cands:
            tpr = float((known_val >= t).mean())
            fpr = float((unknown_val >= t).mean())
            j = tpr - fpr
            if best is None or j > best[0]:
                best = (j, t, tpr, fpr)
        j, t, tpr, fpr = best
        return {"strategy": "youden", "threshold": float(t), "val_known_acceptance": tpr,
                "val_unknown_false_acceptance": fpr, "youden_j": j}
    t = float(np.quantile(known_val, 1.0 - known_acceptance_target)) if len(known_val) else 0.0
    out = {"strategy": "known_acceptance", "threshold": t, "target": known_acceptance_target,
           "val_known_acceptance": float((known_val >= t).mean()) if len(known_val) else None}
    if unknown_val is not None and len(unknown_val):
        out["val_unknown_false_acceptance"] = float((unknown_val >= t).mean())
    if strategy == "youden":
        out["note"] = "No unknown_val images available; fell back to known-acceptance threshold."
    return out


def open_set_metrics(known_probs: np.ndarray, known_labels: np.ndarray, unknown_probs: np.ndarray | None,
                     threshold: float, kind: str) -> dict:
    ks = unknown_scores(known_probs, kind)
    pred = known_probs.argmax(axis=1)
    accepted = ks >= threshold
    out = {
        "known_images": int(len(ks)),
        "known_acceptance_rate": float(accepted.mean()) if len(ks) else None,
        "accuracy_on_accepted_known": float((pred[accepted] == known_labels[accepted]).mean()) if accepted.any() else None,
        "known_correct_and_accepted_rate": float(((pred == known_labels) & accepted).mean()) if len(ks) else None,
    }
    if unknown_probs is not None and len(unknown_probs):
        us = unknown_scores(unknown_probs, kind)
        out.update({
            "unknown_images": int(len(us)),
            "unknown_false_acceptance_rate_without_rejection": 1.0,
            "unknown_false_acceptance_rate_with_threshold": float((us >= threshold).mean()),
            "auroc_known_vs_unknown": float(roc_auc_score(np.r_[np.ones(len(ks)), np.zeros(len(us))], np.r_[ks, us]))
            if len(ks) else None,
        })
    return out


def expected_calibration_error(probs: np.ndarray, labels: np.ndarray, n_bins: int = 15) -> tuple[float, list[dict]]:
    conf = probs.max(axis=1)
    correct = (probs.argmax(axis=1) == labels).astype(float)
    edges = np.linspace(0, 1, n_bins + 1)
    ece, bins = 0.0, []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (conf > lo) & (conf <= hi)
        if m.any():
            gap = abs(correct[m].mean() - conf[m].mean())
            ece += m.mean() * gap
            bins.append({"lo": float(lo), "hi": float(hi), "count": int(m.sum()),
                         "accuracy": float(correct[m].mean()), "confidence": float(conf[m].mean())})
    return float(ece), bins


def apply_temperature(probs: np.ndarray, temperature: float) -> np.ndarray:
    logits = np.log(np.clip(probs, EPS, 1.0)) / temperature
    logits -= logits.max(axis=1, keepdims=True)
    e = np.exp(logits)
    return e / e.sum(axis=1, keepdims=True)


def fit_temperature(probs: np.ndarray, labels: np.ndarray) -> float:
    """Grid-search the temperature minimising validation NLL (log-probabilities equal logits up to a constant)."""
    best_t, best_nll = 1.0, np.inf
    for t in np.exp(np.linspace(np.log(0.05), np.log(20.0), 300)):
        p = apply_temperature(probs, t)
        nll = -np.log(np.clip(p[np.arange(len(labels)), labels], EPS, 1.0)).mean()
        if nll < best_nll:
            best_t, best_nll = float(t), float(nll)
    return best_t
