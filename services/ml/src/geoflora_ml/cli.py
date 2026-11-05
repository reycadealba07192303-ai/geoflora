from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from geoflora_ml.datasets.audit import record_review, write_audit_report
from geoflora_ml.datasets.review_app import run_review_app
from geoflora_ml.collection.gbif import GBIFSource
from geoflora_ml.collection.inaturalist import INaturalistSource
from geoflora_ml.collection.kaggle import KaggleManifestSource
from geoflora_ml.collection.runner import collect_candidates, image_storage_bytes
from geoflora_ml.config import data_dir_from_environment, load_species
from geoflora_ml.datasets.prepare import prepare_dataset
from geoflora_ml.logging_config import configure_logging

LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="geoflora-ml")
    commands = parser.add_subparsers(dest="command", required=True)

    collect = commands.add_parser("collect", help="Collect licensed images from data sources")
    collect.add_argument(
        "--source", choices=("inaturalist", "gbif", "kaggle", "all"), required=True
    )
    limits = collect.add_mutually_exclusive_group()
    limits.add_argument("--limit-per-species", type=_positive_int, default=100)
    limits.add_argument(
        "--all-available",
        action="store_true",
        help="Follow source pagination until eligible records are exhausted",
    )
    collect.add_argument("--data-dir", type=Path, default=data_dir_from_environment())
    collect.add_argument(
        "--max-download-gb",
        type=_positive_float,
        default=5.0,
        help="Maximum additional normalized image storage for this run (default: 5 GB)",
    )
    collect.add_argument(
        "--request-interval",
        type=_nonnegative_float,
        help="Minimum seconds between source API/image requests (source default if omitted)",
    )
    collect.add_argument(
        "--max-retries",
        type=_positive_int,
        default=4,
        help="Maximum transient HTTP retries per request (default: 4)",
    )
    collect.add_argument(
        "--max-pages",
        type=_positive_int,
        help="Optional page cap per species/source for bounded collection runs",
    )
    collect.add_argument(
        "--kaggle-manifest",
        type=Path,
        help="CSV manifest for an already-downloaded Kaggle dataset",
    )

    prepare = commands.add_parser(
        "prepare", help="Deduplicate and create leakage-resistant dataset splits"
    )
    prepare.add_argument("--data-dir", type=Path, default=data_dir_from_environment())
    prepare.add_argument(
        "--manifest", type=Path, help="Input JSONL manifest (defaults to raw/manifest.jsonl)"
    )
    prepare.add_argument(
        "--output-dir", type=Path, help="Defaults to <data-dir>/curated/v1"
    )
    prepare.add_argument("--seed", type=int, default=42)

    audit = commands.add_parser("audit", help="Write dataset quality and target progress report")
    audit.add_argument("--data-dir", type=Path, default=data_dir_from_environment())
    audit.add_argument("--target-per-species", type=_positive_int, default=1000)

    review = commands.add_parser("review", help="Approve or reject a species label")
    review.add_argument("--data-dir", type=Path, default=data_dir_from_environment())
    review.add_argument("--source", required=True)
    review.add_argument("--source-id", required=True)
    review.add_argument(
        "--decision",
        choices=("approved", "rejected", "flagged", "relabelled"),
        required=True,
    )
    review.add_argument("--reviewer", required=True)
    review.add_argument("--reason", required=True)
    review.add_argument("--relabel-to")

    review_app = commands.add_parser(
        "review-ui", help="Launch the local browser-based dataset review tool"
    )
    review_app.add_argument("--data-dir", type=Path, default=data_dir_from_environment())
    review_app.add_argument("--port", type=_port_number, default=8765)
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    args = build_parser().parse_args(argv)
    try:
        if args.command == "collect":
            return _collect(args)
        if args.command == "prepare":
            return _prepare(args)
        if args.command == "audit":
            return _audit(args)
        if args.command == "review":
            return _review(args)
        if args.command == "review-ui":
            run_review_app(args.data_dir.expanduser().resolve(), args.port)
            return 0
    except (OSError, ValueError, RuntimeError, requests.RequestException) as exc:
        LOGGER.error("%s", exc)
        return 1
    return 2


def _collect(args: argparse.Namespace) -> int:
    if args.source == "kaggle":
        if args.kaggle_manifest is None:
            raise ValueError("--kaggle-manifest is required for the kaggle source")
        sources = [("kaggle", KaggleManifestSource(args.kaggle_manifest))]
    elif args.source == "all":
        sources = [
            (
                "inaturalist",
                INaturalistSource(
                    args.request_interval if args.request_interval is not None else 1.0,
                    args.max_retries,
                ),
            ),
            (
                "gbif",
                GBIFSource(
                    args.request_interval if args.request_interval is not None else 0.25,
                    args.max_retries,
                ),
            ),
        ]
    elif args.source == "inaturalist":
        sources = [
            (
                "inaturalist",
                INaturalistSource(
                    args.request_interval if args.request_interval is not None else 1.0,
                    args.max_retries,
                ),
            )
        ]
    else:
        sources = [
            (
                "gbif",
                GBIFSource(
                    args.request_interval if args.request_interval is not None else 0.25,
                    args.max_retries,
                ),
            )
        ]

    total_downloaded = 0
    total_rejected = 0
    data_dir = args.data_dir.expanduser().resolve()
    max_storage_bytes = image_storage_bytes(data_dir) + int(
        args.max_download_gb * 1024**3
    )
    for species in load_species():
        limit = None if args.all_available else args.limit_per_species
        for source_name, source in sources:
            LOGGER.info(
                "Collecting species=%s source=%s",
                species.scientific_name,
                source_name,
            )
            try:
                candidates = source.candidates(
                    species, limit=None, pages=args.max_pages
                )
                request_interval = (
                    args.request_interval
                    if args.request_interval is not None
                    else source.client.minimum_interval
                )
                downloaded, rejected = collect_candidates(
                    candidates,
                    data_dir=data_dir,
                    max_images=limit,
                    source_name=source_name,
                    max_storage_bytes=max_storage_bytes,
                    minimum_interval=request_interval,
                    max_retries=args.max_retries,
                )
            except (OSError, ValueError, RuntimeError, requests.RequestException) as exc:
                _append_progress(
                    data_dir,
                    {
                        "species_id": species.id,
                        "source": source_name,
                        "status": "failed",
                        "error": str(exc),
                        "completed_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
                raise
            total_downloaded += downloaded
            total_rejected += rejected
            _append_progress(
                data_dir,
                {
                    "species_id": species.id,
                    "source": source_name,
                    "status": "completed",
                    "new_valid_images": downloaded,
                    "download_rejections": rejected,
                    "run_limit": limit,
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                },
            )
    LOGGER.info(
        "Collection complete downloaded=%s rejected=%s",
        total_downloaded,
        total_rejected,
    )
    return 0


def _prepare(args: argparse.Namespace) -> int:
    data_dir = args.data_dir.expanduser().resolve()
    manifest_path = (
        args.manifest.expanduser().resolve()
        if args.manifest
        else data_dir / "raw" / "manifest.jsonl"
    )
    output_dir = (
        args.output_dir.expanduser().resolve()
        if args.output_dir
        else data_dir / "curated" / "v1"
    )
    count, duplicates = prepare_dataset(
        manifest_path=manifest_path,
        data_dir=data_dir,
        output_dir=output_dir,
        seed=args.seed,
    )
    LOGGER.info(
        "Dataset prepared images=%s duplicates_removed=%s manifest=%s",
        count,
        duplicates,
        output_dir / "manifest.csv",
    )
    return 0


def _audit(args: argparse.Namespace) -> int:
    data_dir = args.data_dir.expanduser().resolve()
    output_path = write_audit_report(data_dir, args.target_per_species)
    LOGGER.info("Dataset audit report written to %s", output_path)
    report = json.loads(output_path.read_text(encoding="utf-8"))
    for species_id, details in report["species"].items():
        LOGGER.info(
            "Audit species=%s valid=%s approved=%s pending=%s remaining=%s",
            species_id,
            details["valid_images"],
            details["approved_images"],
            details["pending_review"],
            details["remaining_to_verified_target"],
        )
    return 0


def _review(args: argparse.Namespace) -> int:
    record_review(
        data_dir=args.data_dir.expanduser().resolve(),
        source=args.source,
        source_id=args.source_id,
        decision=args.decision,
        reviewer=args.reviewer,
        rationale=args.reason,
        relabel_to=args.relabel_to,
    )
    LOGGER.info(
        "Review recorded source=%s source_id=%s decision=%s",
        args.source,
        args.source_id,
        args.decision,
    )
    return 0


def _append_progress(data_dir: Path, event: dict[str, object]) -> None:
    progress_path = data_dir / "reports" / "collection_progress.jsonl"
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    with progress_path.open("a", encoding="utf-8") as progress_file:
        progress_file.write(json.dumps(event, ensure_ascii=False) + "\n")


def _positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("value must be a positive integer") from exc
    if number <= 0:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return number


def _positive_float(value: str) -> float:
    try:
        number = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("value must be a positive number") from exc
    if not 0 < number < float("inf"):
        raise argparse.ArgumentTypeError("value must be a positive number")
    return number


def _nonnegative_float(value: str) -> float:
    try:
        number = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("value must be a non-negative number") from exc
    if not 0 <= number < float("inf"):
        raise argparse.ArgumentTypeError("value must be a non-negative number")
    return number


def _port_number(value: str) -> int:
    number = _positive_int(value)
    if number > 65535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")
    return number


if __name__ == "__main__":
    sys.exit(main())
