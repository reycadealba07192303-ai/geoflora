"""Stage 7 - evaluate a trained run on the isolated test and unknown_test sets and write the research report."""

import json
import sys
from pathlib import Path

from _common import latest_dir, parser, setup


def main():
    p = parser(__doc__)
    p.add_argument("--run", default=None, help="run directory (default: most recent in models/checkpoints)")
    args = p.parse_args()
    cfg = setup(args)
    from geoflora_ml.config import project_path
    from geoflora_ml.evaluation import evaluate_run

    run = Path(args.run) if args.run else latest_dir(project_path(cfg, "checkpoints"), "run-")
    if run is None or not (run / "model.keras").exists():
        print("no trained run found (models/checkpoints/run-*/model.keras)", file=sys.stderr)
        sys.exit(2)
    m = evaluate_run(cfg, run)
    t = m["test"]
    print(json.dumps({"run": run.name, "test_images": t["images"], "accuracy": t["accuracy"],
                      "accuracy_ci": t["uncertainty"]["accuracy_ci"], "macro_f1": t["macro_f1"],
                      "weighted_f1": t["weighted_f1"], "unsupported_species": m["unsupported_species"]["test"]}, indent=2))
    print(f"Report: {run / 'evaluation' / 'research_evaluation_report.md'}")


if __name__ == "__main__":
    main()
