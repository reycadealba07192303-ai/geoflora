"""Research evaluation report (Markdown) generated from actual run artifacts only.

Every number in the report is read from files produced by training/evaluation. Sections that
describe proposals are labelled "Proposed future improvements (not yet tested)".
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd
import yaml

from .catalog import by_name, load_catalog
from .config import project_path, project_root
from .manifest import load_manifest
from .utils import read_json, rel_to_root


def _pct(x) -> str:
    return "n/a" if x is None else f"{100 * x:.1f}%"


def _f(x, nd=3) -> str:
    return "n/a" if x is None else f"{x:.{nd}f}"


def write_research_report(cfg: dict, run_dir: Path, metrics: dict) -> Path:
    run_dir = Path(run_dir)
    ev = run_dir / "evaluation"
    run_cfg = yaml.safe_load((run_dir / "run_config.yaml").read_text(encoding="utf-8"))
    tcfg = run_cfg["train"]
    summary = read_json(run_dir / "train_summary.json")
    env = read_json(run_dir / "environment.json")
    mapping = read_json(run_dir / "class_mapping.json")
    catalog = by_name(load_catalog(project_path(cfg, "species_catalog")))
    manifest = load_manifest(project_path(cfg, "image_manifest")).set_index("image_id", drop=False)
    frames = {s: pd.read_csv(run_dir / f"{s}_images.csv", dtype=str, keep_default_na=False) for s in ("train", "val", "test")}
    t = metrics["test"]
    unc = t["uncertainty"]
    os_ = metrics["unsupported_species"]
    rt = metrics["runtime"]
    names = metrics["classes"]

    L: list[str] = []
    add = L.append
    add(f"# Research Evaluation Report - {metrics['run_id']}")
    add("")
    add(f"*Generated {metrics['evaluated']} from run artifacts in `{rel_to_root(run_dir, project_root(cfg))}`. Dataset version "
        f"`{metrics['dataset_version']}`. This model is a research candidate: it has not been deployed or activated in GeoFlora.*")
    add("")
    if run_cfg.get("provisional", {}).get("enabled"):
        add("> **PROVISIONAL PILOT - NOT A RESEARCH RESULT.** Labels are unreviewed identifications from the source "
            "platform (iNaturalist research grade = community agreement), not botanical verification. These figures may "
            "not be reported as GeoFlora model performance, and this run cannot be exported. They only indicate how the "
            "pipeline behaves on real photographs while botanical review is pending.")
        add("")
    add("## 1. Summary of observed results")
    add("")
    add(f"- Classes: {len(names)} ({', '.join(f'*{n}*' for n in names)})")
    add(f"- Independent test images: {t['images']} from {frames['test']['observation_group'].nunique()} observation groups")
    exact = unc.get("accuracy_exact_ci", unc["accuracy_ci"])
    add(f"- Test accuracy: **{_pct(t['accuracy'])}** ({int(100 * unc['confidence_level'])}% exact binomial CI {_pct(exact[0])} - "
        f"{_pct(exact[1])}; observation-group bootstrap CI {_pct(unc['accuracy_ci'][0])} - {_pct(unc['accuracy_ci'][1])})")
    add(f"- Macro F1: **{_f(t['macro_f1'])}** (CI {_f(unc['macro_f1_ci'][0])} - {_f(unc['macro_f1_ci'][1])}); weighted F1: {_f(t['weighted_f1'])}")
    ost = os_["test"]
    if ost.get("unknown_images"):
        add(f"- Unsupported-species false acceptance: 100% without rejection (closed-set softmax); "
            f"**{_pct(ost['unknown_false_acceptance_rate_with_threshold'])}** with the validation-selected threshold, "
            f"at a supported-species acceptance rate of {_pct(ost['known_acceptance_rate'])}. AUROC {_f(ost.get('auroc_known_vs_unknown'))}.")
    else:
        add("- Unsupported-species false acceptance: **not measured** (no reviewed unknown_test images).")
    add(f"- Forward-pass latency (batch 1, median): {rt['batch1_latency_ms_median']:.1f} ms on {rt['device']}; model file {rt['model_file_mb']} MB.")
    add("")
    add("Targets such as a specific accuracy level are only met if the figures above show it on this independent test set.")
    add("")

    add("## 2. Dataset sources and selection criteria")
    add("")
    used = pd.concat(frames.values())
    m = manifest.loc[manifest.index.intersection(used["image_id"])]
    add(f"- Source(s): {', '.join(sorted(set(m['source']) - {''})) or 'n/a'}; source datasets: "
        + "; ".join(f"{k or 'unspecified'} ({v})" for k, v in m["source_dataset_name"].value_counts().head(5).items()))
    add("- Licenses used: " + ", ".join(f"{k}: {v}" for k, v in m["license"].value_counts().items()))
    add("- Country of record (top): " + ", ".join(f"{k or 'unknown'}: {v}" for k, v in m["country_code"].value_counts().head(8).items()))
    add("- Selection criteria: still images with an allowed per-image license, basis of record "
        f"{cfg['download']['basis_of_record']}, at most {cfg['download']['max_images_per_occurrence']} image(s) per occurrence; "
        "quality checks (resolution, blur, exposure, aspect ratio); exact and perceptual duplicate removal; "
        + (f"**{run_cfg.get('review', {}).get('label_basis', 'botanical review approval with a named reviewer')}**."
           if not run_cfg.get("provisional", {}).get("enabled")
           else "**PROVISIONAL: unreviewed source identifications (no botanical review)**."))
    reviewers = m.loc[m["review_status"] == "approved", "reviewer"].value_counts()
    if len(reviewers):
        add("- Label reviewer(s): " + ", ".join(f"{k} ({v} images)" for k, v in reviewers.items()))
    add("- These photographs are external biodiversity records, not GeoFlora field observations.")
    add("")

    add("## 3. Target species and ecological-status evidence")
    add("")
    add("| Index | Species ID | Scientific name | Ecological status | Verification | Evidence |")
    add("|---|---|---|---|---|---|")
    for c in mapping["classes"]:
        sp = catalog.get(c["scientific_name"])
        ev_txt = (sp.status_evidence if sp else "").replace("|", "/") or "none recorded"
        add(f"| {c['index']} | {c['species_id']} | *{c['scientific_name']}* | {c['ecological_status']} | {c['status_verification']} | {ev_txt} |")
    add("")

    add("## 4. Images and independent observation groups per class")
    add("")
    add("| Species | Train imgs / groups | Val imgs / groups | Test imgs / groups |")
    add("|---|---|---|---|")
    for c in mapping["classes"]:
        cells = []
        for s in ("train", "val", "test"):
            f = frames[s][frames[s]["species_id"] == c["species_id"]]
            cells.append(f"{len(f)} / {f['observation_group'].nunique()}")
        add(f"| *{c['scientific_name']}* | " + " | ".join(cells) + " |")
    add("")

    add("## 5. Preprocessing")
    add("")
    add(f"EXIF orientation applied, converted to RGB, re-encoded as JPEG (max side {cfg['split']['normalize_max_side']} px), "
        f"resized to {tcfg['image_size']}x{tcfg['image_size']} (bilinear, aspect ratio not preserved), float32 in [0, 255]; "
        "MobileNetV2 scaling to [-1, 1] inside the model.")
    add(f"Training augmentation: {tcfg['augmentation']}.")
    add("")

    add("## 6. Training configuration and architecture")
    add("")
    pretrained = "ImageNet-pretrained" if tcfg["weights"] == "imagenet" else f"randomly initialised (weights={tcfg['weights']})"
    add(f"- Architecture: MobileNetV2, {pretrained}, alpha={tcfg['alpha']} -> GlobalAveragePooling -> "
        f"Dropout({tcfg['dropout']}) -> Dense({len(names)}, softmax). Parameters: {summary['total_params']:,}.")
    add(f"- Phase 1 (frozen base): up to {tcfg['head_epochs']} epochs, Adam lr={tcfg['head_learning_rate']}.")
    add(f"- Phase 2 (fine-tuning layers >= {tcfg['fine_tune_at_layer']}, BatchNorm frozen): up to {tcfg['fine_tune_epochs']} epochs, "
        f"Adam lr={tcfg['fine_tune_learning_rate']}. Selected phase: **{summary['selected_phase']}** (lowest validation loss).")
    add(f"- Early stopping (patience {tcfg['early_stopping_patience']}), ReduceLROnPlateau, checkpointing on validation loss; "
        f"batch size {tcfg['batch_size']}; seed {run_cfg['project']['seed']}; class weights: {summary['class_weight'] or 'none'}.")
    add(f"- Epochs run: {summary['epochs_run']}; training time {summary['training_seconds']} s.")
    add("")

    add("## 7. Train / validation / test methodology")
    add("")
    add("Images were partitioned by observation group (same occurrence, exact duplicates, perceptual near-duplicates "
        f"[pHash Hamming <= {cfg['validation']['phash_hamming_threshold']}]"
        + (", and same recorder on the same day" if cfg["split"]["group_by_recorder_and_date"] else "")
        + f") with target ratios {cfg['split']['ratios']}. Assignments are sticky across dataset versions so test images never "
        "enter training. Model selection and the unsupported-species threshold used validation data only; the test and "
        "unknown_test sets were used once, for this report.")
    add("")

    add("## 8. Evaluation results (test set)")
    add("")
    add(f"Validation (for reference): accuracy {_pct(metrics['validation']['accuracy'])}, macro F1 {_f(metrics['validation']['macro_f1'])}.")
    add("")
    add("| Species | Precision | Recall | F1 | Support |")
    add("|---|---|---|---|---|")
    for r in t["per_class"]:
        add(f"| *{r['species']}* | {_f(r['precision'])} | {_f(r['recall'])} | {_f(r['f1'])} | {r['support']} |")
    add(f"| **Macro** | {_f(t['macro_precision'])} | {_f(t['macro_recall'])} | {_f(t['macro_f1'])} | {t['images']} |")
    topk = next((k for k in t if k.startswith("top_") and k.endswith("_accuracy")), None)
    if topk:
        add("")
        add(f"{topk.replace('_', ' ').capitalize()}: {_pct(t[topk])}.")
    add("")
    add("![Training curves](training_curves.png)")
    add("")

    add("## 9. Confusion matrix")
    add("")
    add("![Confusion matrix](confusion_matrix_counts.png) ![Normalised](confusion_matrix_normalized.png)")
    add("")
    if metrics["top_confusions"]:
        add("Most frequent confusions (true -> predicted): " +
            "; ".join(f"*{c['true']}* -> *{c['predicted']}* ({c['count']})" for c in metrics["top_confusions"]))
    else:
        add("No confusions were observed on the test set.")
    add("")

    add("## 10. False-positive and false-negative analysis")
    add("")
    add("| Species | TP | FN | FP | FN predicted as | FP true species | Mean score correct / incorrect |")
    add("|---|---|---|---|---|---|---|")
    for e in metrics["error_analysis"]:
        add(f"| *{e['species']}* | {e['true_positives']} | {e['false_negatives']} | {e['false_positives']} | "
            f"{e['false_negatives_predicted_as'] or '-'} | {e['false_positives_true_species'] or '-'} | "
            f"{_f(e['mean_score_correct'])} / {_f(e['mean_score_incorrect'])} |")
    add("")
    add("Misclassified images with attribution: `misclassified_test_images.csv`.")
    add("")

    add("## 11. Unsupported-species evaluation")
    add("")
    thr = os_["threshold"]
    add(f"- Score: `{thr['score_type']}`; threshold strategy `{thr['strategy']}` -> threshold {_f(thr['threshold'], 4)} "
        f"(selected on {thr['selected_on']}).")
    add(f"- unknown_val species (threshold selection): {', '.join(os_['unknown_val_species']) or 'none'}")
    add(f"- unknown_test species (final evaluation): {', '.join(os_['unknown_test_species']) or 'none'}")
    if ost.get("unknown_images"):
        add(f"- Test: supported-species acceptance {_pct(ost['known_acceptance_rate'])}, accuracy on accepted "
            f"{_pct(ost['accuracy_on_accepted_known'])}; unsupported false acceptance {_pct(ost['unknown_false_acceptance_rate_with_threshold'])} "
            f"(n={ost['unknown_images']}); AUROC {_f(ost['auroc_known_vs_unknown'])}.")
        add("")
        add("| Unsupported species | Images | False acceptance (thresholded) | Labels assigned without rejection |")
        add("|---|---|---|---|")
        for sp, d in os_["per_unknown_species"].items():
            add(f"| *{sp}* | {d['images']} | {_pct(d['false_acceptance_rate_with_threshold'])} | {d['assigned_labels_without_rejection']} |")
    else:
        add("- No reviewed unsupported-species test images were available, so false acceptance could not be measured.")
    add("")
    add("![Score distribution](unknown_score_distribution.png)")
    add("")
    cal = metrics["calibration"]
    add(f"Calibration: ECE {_f(cal['ece_raw_test'])} (raw softmax) and {_f(cal['ece_temperature_scaled_test'])} after temperature "
        f"scaling (T={_f(cal['temperature_fitted_on_val'], 2)}, fitted on validation). Softmax scores are model scores, not calibrated "
        "identification confidence.")
    add("")
    add("![Reliability](reliability_diagram.png)")
    add("")

    add("## 12. Robustness and photographic conditions")
    add("")
    if metrics.get("robustness_synthetic"):
        add("Synthetic perturbations of the test images (these approximate, but are not, real lighting/angle/background changes):")
        add("")
        add("| Perturbation | Accuracy | Macro F1 |")
        add("|---|---|---|")
        add(f"| none | {_pct(t['accuracy'])} | {_f(t['macro_f1'])} |")
        for k, v in metrics["robustness_synthetic"].items():
            add(f"| {k} | {_pct(v['accuracy'])} | {_f(v['macro_f1'])} |")
        add("")
    if metrics["condition_breakdown"]:
        add("Accuracy by reviewer-tagged photographic condition:")
        for c, rows in metrics["condition_breakdown"].items():
            add(f"- {c}: " + "; ".join(f"{k} {_pct(v['accuracy'])} (n={v['images']})" for k, v in rows.items()))
    else:
        add("No reviewer condition tags (lighting, background, organ, growth stage) were available, so real-condition breakdowns were not computed.")
    add("")

    add("## 13. Runtime and model size")
    add("")
    add(f"Device {rt['device']}; batch-1 latency median {rt['batch1_latency_ms_median']:.1f} ms (p95 {rt['batch1_latency_ms_p95']:.1f} ms); "
        f"batch-32 throughput {rt['batch32_throughput_images_per_s']:.1f} img/s; {rt['total_params']:,} parameters; "
        f"`.keras` file {rt['model_file_mb']} MB. {rt['note']}")
    add("")

    add("## 14. Model limitations (observed or inherent to this setup)")
    add("")
    lim = [
        "Training and test images come from external biodiversity platforms; their photographers, devices and framing "
        "differ from GeoFlora users' photos, so field performance may differ from the figures above.",
        f"Test-set size ({t['images']} images) bounds precision of the estimates; see the bootstrap confidence intervals.",
        "The model is closed-set: without the rejection threshold every unsupported plant receives a supported label.",
        "Softmax scores are not calibrated probabilities of a correct identification.",
    ]
    ph = (m["country_code"] == "PH").mean() if len(m) else 0
    lim.append(f"{_pct(ph)} of the images used were recorded in the Philippines (country of record per source metadata).")
    unver = [c["scientific_name"] for c in mapping["classes"] if c["status_verification"] != "verified"]
    if unver:
        lim.append("Ecological status is not yet verified with Philippine-specific evidence for: " + ", ".join(f"*{u}*" for u in unver) + ".")
    if len(os_["unknown_test_species"]) < 5:
        lim.append(f"Unsupported-species evaluation covers only {len(os_['unknown_test_species'])} species; false-acceptance rates "
                   "for other plants are unknown.")
    if any(r["support"] < 30 for r in t["per_class"]):
        lim.append("At least one class has fewer than 30 test images; per-class metrics for those classes are highly uncertain.")
    va, ta = metrics["validation"]["accuracy"], t["accuracy"]
    if va is not None and ta is not None and abs(va - ta) >= 0.10:
        lim.append(f"Validation accuracy ({_pct(va)}) and test accuracy ({_pct(ta)}) differ by >= 10 points, which indicates "
                   "high sampling variance at this data size; neither figure alone is a reliable performance estimate.")
    lim.append("Aspect ratio is not preserved during resizing, which may distort plant morphology.")
    for x in lim:
        add(f"- {x}")
    add("")

    add("## 15. Reproducibility")
    add("")
    add(f"- Run directory: `{rel_to_root(run_dir, project_root(cfg))}` (contains run_config.yaml, class_mapping.json, train/val/test image lists, history, logs).")
    add(f"- Dataset version `{metrics['dataset_version']}`; image lists for each split are stored with the run.")
    add(f"- Seed {run_cfg['project']['seed']}; deterministic ops: {tcfg.get('deterministic_ops')}.")
    add(f"- Environment: Python {env.get('python')}, TensorFlow {env.get('tensorflow_version')}, Keras {env.get('keras_version')}, "
        f"{env.get('platform')}, GPUs: {env.get('tf_gpus') or 'none'}.")
    add("- Re-run: `python scripts/train.py --config <run_config.yaml>` then `python scripts/evaluate.py --run <run_dir>`.")
    add("")

    add("## 16. Proposed future improvements (not yet tested)")
    add("")
    recs = []
    weakest = sorted(t["per_class"], key=lambda r: r["f1"])[:3]
    for r in weakest:
        if r["f1"] < 0.9:
            recs.append(f"Collect and review more diverse images of *{r['species']}* (test F1 {_f(r['f1'])}).")
    for c in metrics["top_confusions"][:3]:
        recs.append(f"Add targeted reviewed images that separate *{c['true']}* from *{c['predicted']}* ({c['count']} confusions observed).")
    recs += [
        "Collect GeoFlora-style field photographs from the Philippines (with consent and botanist verification) as an additional held-out test set.",
        "Expand the unsupported-species set with more look-alike and common non-target plants to tighten false-acceptance estimates.",
        "Evaluate alternative rejection methods (e.g. energy scores from logits, feature-space distance) on the same validation protocol.",
        "Ask reviewers to tag photographic conditions so that real-condition robustness can be measured.",
    ]
    for x in recs:
        add(f"- {x}")
    add("")

    text = "\n".join(L) + "\n"
    path = ev / "research_evaluation_report.md"
    path.write_text(text, encoding="utf-8")
    pub = project_path(cfg, "reports") / metrics["run_id"]
    pub.mkdir(parents=True, exist_ok=True)
    for f in ev.iterdir():
        if f.is_file():
            shutil.copy2(f, pub / f.name)
    return path
