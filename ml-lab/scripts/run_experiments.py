"""Research experiments built on the same gated training/evaluation pipeline.

  learning_curve   : train on group-aware fractions of the training data (RQ6: data quantity)
  class_expansion  : train with the first k eligible classes, k = 2..N (RQ5: adding species)

Each configuration is a full training run evaluated on its classes' isolated test images.
Results: reports/experiments/<type>_<timestamp>.{json,md}

  python scripts/run_experiments.py learning_curve --fractions 0.25 0.5 1.0
  python scripts/run_experiments.py class_expansion
"""

import sys

from _common import parser, setup


def main():
    p = parser(__doc__)
    p.add_argument("experiment", choices=["learning_curve", "class_expansion"])
    p.add_argument("--fractions", nargs="*", type=float, default=[0.25, 0.5, 1.0])
    args = p.parse_args()
    cfg = setup(args)
    from geoflora_ml.config import project_path
    from geoflora_ml.evaluation import evaluate_run
    from geoflora_ml.training import TrainingBlocked, check_training_readiness, train
    from geoflora_ml.utils import read_json, utc_stamp, write_json

    try:
        mapping, _ = check_training_readiness(cfg)
    except TrainingBlocked as exc:
        print(f"EXPERIMENT NOT STARTED: {exc}", file=sys.stderr)
        sys.exit(2)

    configs = []
    if args.experiment == "learning_curve":
        configs = [{"label": f"fraction={f}", "train_fraction": f, "classes": None} for f in sorted(args.fractions)]
    else:
        ids = [c["species_id"] for c in mapping["classes"]]
        configs = [{"label": f"classes={k}", "train_fraction": 1.0, "classes": ids[:k]} for k in range(2, len(ids) + 1)]

    rows = []
    for c in configs:
        run = train(cfg, run_name=f"{args.experiment}-{c['label'].replace('=', '')}",
                    train_fraction=c["train_fraction"], class_subset=c["classes"])
        m = evaluate_run(cfg, run, write_report=False)
        rows.append({**c, "run": run.name, "train_images": read_json(run / "train_summary.json")["images"]["train"],
                     "test_images": m["test"]["images"], "accuracy": m["test"]["accuracy"],
                     "accuracy_ci": m["test"]["uncertainty"].get("accuracy_exact_ci", m["test"]["uncertainty"]["accuracy_ci"]), "macro_f1": m["test"]["macro_f1"],
                     "macro_f1_ci": m["test"]["uncertainty"]["macro_f1_ci"],
                     "unknown_far": m["unsupported_species"]["test"].get("unknown_false_acceptance_rate_with_threshold")})

    out = project_path(cfg, "reports") / "experiments"
    stamp = utc_stamp()
    write_json(out / f"{args.experiment}_{stamp}.json", rows)
    lines = [f"# Experiment: {args.experiment} ({stamp})", ""]
    if cfg.get("provisional", {}).get("enabled"):
        lines += ["> **PROVISIONAL PILOT - NOT A RESEARCH RESULT.** Trained on unreviewed source identifications; "
                  "do not report these figures as GeoFlora model performance.", ""]
    lines += [f"Dataset version: {mapping['dataset_version']}", "",
              "Accuracy CI: exact binomial 95%. Macro F1 CI: observation-group bootstrap 95%.", "",
              "| Config | Train imgs | Test imgs | Accuracy (CI) | Macro F1 (CI) | Unknown FAR |", "|---|---|---|---|---|---|"]
    for r in rows:
        far = "n/a" if r["unknown_far"] is None else f"{r['unknown_far']:.3f}"
        lines.append(f"| {r['label']} | {r['train_images']} | {r['test_images']} | {r['accuracy']:.3f} "
                     f"({r['accuracy_ci'][0]:.3f}-{r['accuracy_ci'][1]:.3f}) | {r['macro_f1']:.3f} "
                     f"({r['macro_f1_ci'][0]:.3f}-{r['macro_f1_ci'][1]:.3f}) | {far} |")
    lines += ["", "Each row is an independent training run; class-expansion rows are evaluated only on their own classes."]
    (out / f"{args.experiment}_{stamp}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
