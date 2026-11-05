"""Stage 5 - leakage-safe, observation-group-aware train/val/test (+ unknown_val/unknown_test) partitions.
Writes metadata/class_mapping.json, metadata/split_assignments.csv, metadata/dataset_version.json,
reports/split_report.json and rebuilds dataset/{train,val,test,unknown_val,unknown_test}/<species>/."""

import json
import sys

from _common import parser, setup


def main():
    p = parser(__doc__)
    p.add_argument("--no-materialize", action="store_true", help="compute assignments without writing image folders")
    args = p.parse_args()
    cfg = setup(args)
    from geoflora_ml.splitting import SplitError, prepare_splits

    try:
        report = prepare_splits(cfg, materialize=not args.no_materialize)
    except SplitError as exc:
        print(f"split failed: {exc}", file=sys.stderr)
        sys.exit(2)
    print(json.dumps(report, indent=2))
    if not report["ready_for_training"]:
        print("\nNOT READY FOR TRAINING - see class_readiness above.", file=sys.stderr)


if __name__ == "__main__":
    main()
