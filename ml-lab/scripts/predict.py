"""Predict species for one or more images with an exported bundle or a training run directory.

  python scripts/predict.py photo1.jpg photo2.jpg --model models/exported/<model_version>
"""

import json
import sys
from pathlib import Path

from _common import latest_dir, parser, setup


def main():
    p = parser(__doc__)
    p.add_argument("images", nargs="+")
    p.add_argument("--model", default=None, help="exported bundle or run dir (default: latest export)")
    p.add_argument("--top-k", type=int, default=3)
    p.add_argument("--output", default=None, help="write results to this JSON file")
    args = p.parse_args()
    cfg = setup(args)
    from geoflora_ml.config import project_path
    from geoflora_ml.inference import Predictor

    model_dir = Path(args.model) if args.model else latest_dir(project_path(cfg, "exported"))
    if model_dir is None or not (model_dir / "model.keras").exists():
        print("no model found; pass --model <exported bundle or run dir>", file=sys.stderr)
        sys.exit(2)
    pred = Predictor(model_dir)
    results = [pred.predict(img, args.top_k) for img in args.images]
    text = json.dumps(results if len(results) > 1 else results[0], indent=2)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
