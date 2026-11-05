"""Training: readiness gate, two-phase transfer learning (frozen head -> controlled fine-tuning)."""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from .config import project_path
from .manifest import load_manifest
from .splitting import load_split_frame
from .utils import environment_info, read_json, utc_now_iso, utc_stamp, write_json
from .validation import training_eligible_mask

log = logging.getLogger(__name__)


class TrainingBlocked(RuntimeError):
    """Raised when the verified-data requirements for training are not met."""


def check_training_readiness(cfg: dict) -> tuple[dict, dict[str, pd.DataFrame]]:
    """Verify, independently of the split step, that every image to be used is approved and consistent."""
    reasons: list[str] = []
    mapping_path = project_path(cfg, "class_mapping")
    if not mapping_path.exists():
        raise TrainingBlocked("metadata/class_mapping.json not found; run scripts/split_dataset.py first")
    mapping = read_json(mapping_path)
    if mapping.get("num_classes", 0) < 2:
        raise TrainingBlocked(f"class mapping has {mapping.get('num_classes', 0)} eligible classes (need >= 2): "
                              "not enough botanically approved images. See reports/split_report.json.")
    version_path = project_path(cfg, "dataset_version")
    if version_path.exists() and read_json(version_path).get("dataset_version") != mapping.get("dataset_version"):
        reasons.append("class_mapping.json and dataset_version.json disagree; re-run split_dataset.py")

    manifest = load_manifest(project_path(cfg, "image_manifest")).set_index("image_id", drop=False)
    eligible_ids = set(manifest.index[training_eligible_mask(manifest, cfg)])
    class_ids = {c["species_id"]: c for c in mapping["classes"]}
    frames = {}
    for split in ("train", "val", "test"):
        f = load_split_frame(cfg, split)
        f = f[f["species_id"].isin(class_ids)].reset_index(drop=True)
        not_ok = sorted(set(f["image_id"]) - eligible_ids)
        if not_ok:
            reasons.append(f"{split}: {len(not_ok)} images are no longer approved/eligible (e.g. {not_ok[:3]}); re-run split")
        missing = [p for p in f["abs_path"] if not os.path.exists(p)]
        if missing:
            reasons.append(f"{split}: {len(missing)} split files missing (e.g. {missing[:2]})")
        bad_folder = f[[Path(p).parent.name != class_ids[s]["folder"] for p, s in zip(f["split_path"], f["species_id"])]]
        if len(bad_folder):
            reasons.append(f"{split}: {len(bad_folder)} files are in a folder that does not match their label")
        for sid, c in class_ids.items():
            n = int((f["species_id"] == sid).sum())
            minimum = cfg["split"]["min_test_images_per_class"] if split == "test" else 1
            if n < minimum:
                reasons.append(f"{split}: {c['scientific_name']} has {n} images (< {minimum})")
        frames[split] = f
    if reasons:
        raise TrainingBlocked("training blocked:\n  " + "\n  ".join(reasons))
    return mapping, frames


def subset_mapping(mapping: dict, species_ids: list[str]) -> dict:
    keep = [c for c in mapping["classes"] if c["species_id"] in set(species_ids)]
    if len(keep) < 2:
        raise TrainingBlocked("class subset must contain at least two eligible classes")
    out = dict(mapping)
    out["classes"] = [dict(c, index=i) for i, c in enumerate(keep)]
    out["num_classes"] = len(keep)
    out["subset_of_dataset_classes"] = True
    return out


def subsample_groups(frame: pd.DataFrame, fraction: float, seed: int) -> pd.DataFrame:
    """Group-aware per-class subsampling of the training set (for data-quantity experiments)."""
    if fraction >= 1.0:
        return frame
    rng = np.random.default_rng(seed)
    parts = []
    for _, g in frame.groupby("species_id"):
        groups = sorted(g["observation_group"].unique())
        k = max(1, int(round(len(groups) * fraction)))
        chosen = set(rng.choice(groups, size=k, replace=False))
        parts.append(g[g["observation_group"].isin(chosen)])
    return pd.concat(parts, ignore_index=True)


def compute_class_weights(labels: np.ndarray, num_classes: int, mode: str) -> dict | None:
    counts = np.bincount(labels, minlength=num_classes).astype(float)
    if mode == "none" or counts.min() == 0:
        return None
    ratio = counts.max() / counts.min()
    if mode == "auto" and ratio <= 1.5:
        return None
    weights = counts.sum() / (num_classes * counts)
    return {i: float(w) for i, w in enumerate(weights)}


def train(cfg: dict, run_name: str | None = None, train_fraction: float = 1.0,
          class_subset: list[str] | None = None, frames_override: dict | None = None,
          mapping_override: dict | None = None) -> Path:
    import tensorflow as tf
    from tensorflow import keras

    from .data import make_dataset
    from .model import build_model, unfreeze_top

    tcfg = cfg["train"]
    seed = int(cfg["project"]["seed"])
    if frames_override is not None:
        mapping, frames = mapping_override, frames_override
    else:
        mapping, frames = check_training_readiness(cfg)
    if class_subset:
        mapping = subset_mapping(mapping, class_subset)
    index_of = {c["species_id"]: c["index"] for c in mapping["classes"]}
    frames = {k: v[v["species_id"].isin(index_of)].reset_index(drop=True) for k, v in frames.items()}
    frames["train"] = subsample_groups(frames["train"], train_fraction, seed)

    keras.utils.set_random_seed(seed)
    if tcfg.get("deterministic_ops"):
        tf.config.experimental.enable_op_determinism()

    run_id = f"run-{utc_stamp()}" + (f"-{run_name}" if run_name else "")
    run_dir = project_path(cfg, "checkpoints") / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    write_json(run_dir / "class_mapping.json", mapping)
    (run_dir / "run_config.yaml").write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    write_json(run_dir / "environment.json", environment_info())
    for split, f in frames.items():
        f[["image_id", "species_id", "observation_group", "split_path"]].to_csv(run_dir / f"{split}_images.csv", index=False)

    n_cls = mapping["num_classes"]
    size, bs = int(tcfg["image_size"]), int(tcfg["batch_size"])
    y_train = frames["train"]["species_id"].map(index_of).to_numpy()
    y_val = frames["val"]["species_id"].map(index_of).to_numpy()
    ds_train = make_dataset(frames["train"]["abs_path"].tolist(), y_train.tolist(), n_cls, size, bs, training=True,
                            augment_cfg=tcfg.get("augmentation"), seed=seed, shuffle_buffer=int(tcfg["shuffle_buffer"]))
    ds_val = make_dataset(frames["val"]["abs_path"].tolist(), y_val.tolist(), n_cls, size, bs)
    class_weight = compute_class_weights(y_train, n_cls, str(tcfg.get("class_weight", "auto")))

    model, base = build_model(n_cls, size, float(tcfg["alpha"]), tcfg.get("weights"), float(tcfg["dropout"]))
    loss = keras.losses.CategoricalCrossentropy(label_smoothing=float(tcfg.get("label_smoothing", 0.0)))

    def callbacks(phase: str):
        return [
            keras.callbacks.EarlyStopping(monitor="val_loss", patience=int(tcfg["early_stopping_patience"]),
                                          restore_best_weights=True, verbose=1),
            keras.callbacks.ModelCheckpoint(str(run_dir / f"{phase}_best.keras"), monitor="val_loss", save_best_only=True),
            keras.callbacks.ReduceLROnPlateau(monitor="val_loss", factor=float(tcfg["reduce_lr_factor"]),
                                              patience=int(tcfg["reduce_lr_patience"]),
                                              min_lr=float(tcfg["min_learning_rate"]), verbose=1),
            keras.callbacks.CSVLogger(str(run_dir / "training_log.csv"), append=True),
            keras.callbacks.TerminateOnNaN(),
        ]

    started = time.time()
    history: dict[str, list] = {}
    phase_of_epoch: list[str] = []

    def record(h, phase):
        for k, v in h.history.items():
            history.setdefault(k, []).extend(float(x) for x in v)
        phase_of_epoch.extend([phase] * len(h.history.get("loss", [])))

    model.compile(optimizer=keras.optimizers.Adam(float(tcfg["head_learning_rate"])), loss=loss, metrics=["accuracy"])
    h1 = model.fit(ds_train, validation_data=ds_val, epochs=int(tcfg["head_epochs"]), class_weight=class_weight,
                   callbacks=callbacks("head"), verbose=2)
    record(h1, "head")
    best = {"phase": "head", "val_loss": float(min(h1.history["val_loss"]))}

    n_trainable = 0
    if int(tcfg.get("fine_tune_epochs", 0)) > 0:
        model.save(run_dir / "head_final.keras")  # best head-phase weights (EarlyStopping restored them)
        n_trainable = unfreeze_top(base, int(tcfg["fine_tune_at_layer"]))
        model.compile(optimizer=keras.optimizers.Adam(float(tcfg["fine_tune_learning_rate"])), loss=loss, metrics=["accuracy"])
        h2 = model.fit(ds_train, validation_data=ds_val, epochs=int(tcfg["fine_tune_epochs"]), class_weight=class_weight,
                       callbacks=callbacks("finetune"), verbose=2)
        record(h2, "finetune")
        ft_best = float(min(h2.history["val_loss"]))
        if ft_best < best["val_loss"]:
            best = {"phase": "finetune", "val_loss": ft_best}
        else:  # fine-tuning did not improve validation loss: keep the head-phase model
            model = keras.models.load_model(run_dir / "head_final.keras")
    model.save(run_dir / "model.keras")

    write_json(run_dir / "history.json", {"history": history, "phase": phase_of_epoch})
    write_json(run_dir / "train_summary.json", {
        "run_id": run_id, "finished": utc_now_iso(), "training_seconds": round(time.time() - started, 1),
        "dataset_version": mapping.get("dataset_version"), "num_classes": n_cls,
        "classes": [c["scientific_name"] for c in mapping["classes"]],
        "train_fraction": train_fraction, "class_subset": class_subset,
        "images": {k: int(len(v)) for k, v in frames.items()},
        "observation_groups": {k: int(v["observation_group"].nunique()) for k, v in frames.items()},
        "train_images_per_class": {c["scientific_name"]: int((y_train == c["index"]).sum()) for c in mapping["classes"]},
        "class_weight": class_weight, "selected_phase": best["phase"], "best_val_loss": best["val_loss"],
        "fine_tune_trainable_layers": n_trainable, "epochs_run": len(phase_of_epoch),
        "total_params": int(model.count_params()),
        "selection_note": "Model selected on validation loss only; the test set was not used during training.",
        "label_source": ("PROVISIONAL: unreviewed source-community identifications" if cfg.get("provisional", {}).get("enabled")
                         else cfg.get("review", {}).get("label_basis", "botanical review (approved, named reviewer)")),
    })
    log.info("training complete: %s", run_dir)
    return run_dir
