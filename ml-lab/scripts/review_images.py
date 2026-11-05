"""Botanical review workflow.

  python scripts/review_images.py export [--species GF-SP-0001 ...]
      -> reports/review_sheets/<species>.csv (fill the `decision` column) + <species>.html (photo gallery)
  python scripts/review_images.py import reports/review_sheets/GF-SP-0001_Chromolaena_odorata.csv --reviewer "Full Name"
      -> applies approved / rejected / uncertain decisions to metadata/image_manifest.csv
"""

import json
import sys

from _common import parser, setup


def main():
    p = parser(__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export")
    e.add_argument("--species", nargs="*")
    e.add_argument("--include-reviewed", action="store_true")
    e.add_argument("--include-quality-failures", action="store_true")
    i = sub.add_parser("import")
    i.add_argument("sheet")
    i.add_argument("--reviewer", required=True, help="full name of the person who made the decisions")
    i.add_argument("--date", default=None, help="review date YYYY-MM-DD (default today)")
    args = p.parse_args()
    cfg = setup(args)
    from geoflora_ml.review import export_review_sheets, import_review_sheet

    if args.cmd == "export":
        for path in export_review_sheets(cfg, args.species, args.include_reviewed, args.include_quality_failures):
            print(path)
    else:
        try:
            print(json.dumps(import_review_sheet(cfg, args.sheet, args.reviewer, args.date), indent=2))
        except ValueError as exc:
            print(exc, file=sys.stderr)
            sys.exit(2)
        print("Re-run scripts/validate_images.py and scripts/split_dataset.py to update the partitions.")


if __name__ == "__main__":
    main()
