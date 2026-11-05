"""Stage 9 - export an evaluated run to models/exported/<model_version>/ for future GeoFlora integration.
Does not deploy or activate anything."""

import sys
from pathlib import Path

from _common import latest_dir, parser, setup


def main():
    p = parser(__doc__)
    p.add_argument("--run", default=None, help="run directory (default: most recent)")
    p.add_argument("--model-version", default=None)
    p.add_argument("--savedmodel", action="store_true", help="also write a TensorFlow SavedModel")
    args = p.parse_args()
    cfg = setup(args)
    from geoflora_ml.config import project_path
    from geoflora_ml.export import ExportBlocked, export_run

    run = Path(args.run) if args.run else latest_dir(project_path(cfg, "checkpoints"), "run-")
    if run is None:
        print("no run found", file=sys.stderr)
        sys.exit(2)
    try:
        out = export_run(cfg, run, args.model_version, args.savedmodel)
    except ExportBlocked as exc:
        print(f"EXPORT BLOCKED: {exc}", file=sys.stderr)
        sys.exit(2)
    print(f"Exported candidate (NOT activated): {out}")


if __name__ == "__main__":
    main()
