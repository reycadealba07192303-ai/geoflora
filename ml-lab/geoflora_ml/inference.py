"""Prediction with a trained run or an exported bundle. Output follows prediction_output_spec.json.

The model produces species identifiers and scores only. It does not produce or infer GPS
coordinates or occurrence records - the GeoFlora application attaches the observation's location.
"""

from __future__ import annotations

import io
import time
from pathlib import Path

import numpy as np

from .imaging import open_rgb
from .utils import read_json, sha256_file, utc_now_iso

DISCLAIMER = ("softmax_score is an uncalibrated model score, not the probability that the identification is correct. "
              "Predictions are AI-assisted suggestions that require expert verification.")


def preprocess_image(path: str | Path, image_size: int) -> np.ndarray:
    """Preprocessing contract: EXIF-correct RGB -> JPEG round-trip -> bilinear resize -> float32 [0, 255]."""
    import tensorflow as tf

    im = open_rgb(path)
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=95)  # matches the JPEG-normalised training data
    arr = tf.io.decode_jpeg(buf.getvalue(), channels=3)
    arr = tf.image.resize(arr, (image_size, image_size), method="bilinear")
    return tf.cast(arr, tf.float32).numpy()


class Predictor:
    def __init__(self, model_dir: str | Path):
        from tensorflow import keras

        self.dir = Path(model_dir)
        self.mapping = read_json(self.dir / "class_mapping.json")
        meta_path = self.dir / "model_metadata.json"
        self.meta = read_json(meta_path) if meta_path.exists() else {}
        pre_path = self.dir / "preprocessing.json"
        if pre_path.exists():
            self.image_size = int(read_json(pre_path)["input_size"][0])
        else:  # a training run directory
            import yaml

            self.image_size = int(yaml.safe_load((self.dir / "run_config.yaml").read_text(encoding="utf-8"))["train"]["image_size"])
        self.threshold = self.meta.get("unknown_handling", {}).get("threshold")
        self.score_type = self.meta.get("unknown_handling", {}).get("score_type", "max_softmax")
        if self.threshold is None:
            metrics_path = self.dir / "evaluation" / "metrics.json"
            if metrics_path.exists():
                thr = read_json(metrics_path)["unsupported_species"]["threshold"]
                self.threshold, self.score_type = thr["threshold"], thr["score_type"]
        desc_path = self.dir / "species_descriptions.json"
        self.descriptions = read_json(desc_path) if desc_path.exists() else {}
        self.model = keras.models.load_model(self.dir / "model.keras")
        self.model_version = self.meta.get("model_version", self.dir.name)
        self.provisional = bool(self.mapping.get("provisional"))

    def predict(self, path: str | Path, top_k: int = 3) -> dict:
        from .openset import unknown_scores

        t0 = time.perf_counter()
        x = preprocess_image(path, self.image_size)[None]
        probs = self.model(x, training=False).numpy()[0]
        ms = (time.perf_counter() - t0) * 1000
        order = np.argsort(-probs)
        classes = self.mapping["classes"]
        best = classes[int(order[0])]
        score = float(unknown_scores(probs[None], self.score_type)[0])
        decision = None
        if self.threshold is not None:
            decision = "supported_species" if score >= self.threshold else "unsupported_or_uncertain"
        return {
            "model_version": self.model_version,
            "dataset_version": self.mapping.get("dataset_version"),
            "image": {"filename": Path(path).name, "sha256": sha256_file(path)},
            "prediction": {
                "species_id": best["species_id"], "scientific_name": best["scientific_name"],
                "common_name": best.get("common_name", ""), "gbif_taxon_key": best.get("gbif_taxon_key"),
                "ecological_status": best.get("ecological_status"),
                "status_verification": best.get("status_verification"),
                "is_target_invasive": best.get("is_target_invasive"),
                "softmax_score": float(probs[order[0]]),
                "description": self.descriptions.get(best["species_id"]),
            },
            "top_k": [{"rank": r + 1, "species_id": classes[int(i)]["species_id"],
                       "scientific_name": classes[int(i)]["scientific_name"], "softmax_score": float(probs[i])}
                      for r, i in enumerate(order[:top_k])],
            "unknown_handling": {"score_type": self.score_type, "score": score, "threshold": self.threshold,
                                 "decision": decision},
            "inference_ms": round(ms, 2),
            "timestamp": utc_now_iso(),
            "disclaimer": DISCLAIMER,
            **({"provisional_model": True, "provisional_note": "Trained on unreviewed labels - pilot only, not for use."}
               if self.provisional else {}),
        }
