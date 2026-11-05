"""Stage 2/3 - bounded, resumable image acquisition from GBIF (official API).

Examples
  python scripts/download_dataset.py --dry-run
  python scripts/download_dataset.py --roles target --max-per-species 80
  python scripts/download_dataset.py --species "Lantana camara" --max-per-species 20 --max-total-mb 50
"""

import json

from _common import parser, setup


def main():
    p = parser(__doc__)
    p.add_argument("--species", nargs="*", help="species_id or scientific name (default: all download_enabled)")
    p.add_argument("--roles", nargs="*", choices=["target", "lookalike", "unknown_eval", "expansion_candidate"])
    p.add_argument("--max-per-species", type=int, default=None, help="total images per species incl. already downloaded")
    p.add_argument("--max-total-mb", type=float, default=None, help="storage cap for this session")
    p.add_argument("--dry-run", action="store_true", help="show the plan without contacting GBIF")
    args = p.parse_args()
    cfg = setup(args)
    from geoflora_ml.acquisition import run_download

    summary = run_download(cfg, args.species, args.roles, args.max_per_species, args.max_total_mb, args.dry_run)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
