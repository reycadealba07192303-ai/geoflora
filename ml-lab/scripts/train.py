"""Stage 6 - train a MobileNetV2 transfer-learning candidate. Refuses to start unless every class has
enough botanically approved, leakage-checked data (see geoflora_ml.training.check_training_readiness)."""

import sys

from _common import parser, setup


def main():
    p = parser(__doc__)
    p.add_argument("--run-name", default=None)
    p.add_argument("--train-fraction", type=float, default=1.0, help="group-aware fraction of training data (experiments)")
    p.add_argument("--classes", nargs="*", help="subset of species_ids (class-expansion experiments)")
    p.add_argument("--check-only", action="store_true", help="only run the readiness gate")
    args = p.parse_args()
    cfg = setup(args)
    from geoflora_ml.training import TrainingBlocked, check_training_readiness, train

    try:
        if args.check_only:
            mapping, frames = check_training_readiness(cfg)
            print(f"READY: {mapping['num_classes']} classes; " + ", ".join(f"{k}={len(v)}" for k, v in frames.items()))
            return
        run_dir = train(cfg, args.run_name, args.train_fraction, args.classes)
    except TrainingBlocked as exc:
        print(f"TRAINING NOT STARTED: {exc}", file=sys.stderr)
        sys.exit(2)
    print(f"Run saved to {run_dir}\nNext: python scripts/evaluate.py --run \"{run_dir}\"")


if __name__ == "__main__":
    main()
