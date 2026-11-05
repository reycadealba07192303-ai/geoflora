"""Stage 4 - validate readability, quality, licenses, labels, duplicates and observation groups;
write reports/validation_summary.json and reports/dataset_inventory.md."""

import json

from _common import parser, setup


def main():
    p = parser(__doc__)
    p.add_argument("--no-recheck", action="store_true", help="reuse stored image metrics where available")
    args = p.parse_args()
    cfg = setup(args)
    from geoflora_ml.validation import validate_manifest

    s = validate_manifest(cfg, recheck_images=not args.no_recheck)
    brief = {k: v for k, v in s.items() if k != "per_species"}
    print(json.dumps(brief, indent=2))
    print("\nInventory: reports/dataset_inventory.md")


if __name__ == "__main__":
    main()
