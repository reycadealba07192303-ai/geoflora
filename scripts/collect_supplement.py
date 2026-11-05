"""Bounded PH image collection: water hyacinth first, new records pending.

Run with services/ml/.venv/Scripts/python.exe scripts/collect_supplement.py.
Resumes through the existing source-ID manifest. No review decisions change.
"""
from __future__ import annotations

import json
import argparse
import logging
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from geoflora_ml.collection.gbif import GBIFSource
from geoflora_ml.collection.inaturalist import INaturalistSource
from geoflora_ml.collection.runner import collect_candidates, image_storage_bytes
from geoflora_ml.config import load_species
from geoflora_ml.datasets.manifest import read_jsonl

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "storage/datasets"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--species", choices=[entry.id for entry in load_species()])
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    before = read_jsonl(DATA / "raw/manifest.jsonl")
    before_keys = {(r["source"], r["source_id"]) for r in before}
    initial_bytes = image_storage_bytes(DATA)
    cap = initial_bytes + int(0.1 * 1024**3)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report = {"started_at": run_id, "additional_storage_cap_gb": 0.1,
              "max_pages_per_species_source": 3, "sources": [], "approvals_changed": False}
    output = DATA / f"reports/supplement_{run_id}.json"
    output.parent.mkdir(exist_ok=True)
    species = sorted(load_species(), key=lambda s: (s.id != "pontederia_crassipes", s.id))
    if args.species:
        species = [entry for entry in species if entry.id == args.species]
    try:
        for entry in species:
            limit = 20 if entry.id == "pontederia_crassipes" else 10
            for name, source in [("inaturalist", INaturalistSource(max_retries=1)), ("gbif", GBIFSource(max_retries=1))]:
                progress = {"species_id": entry.id, "source": name, "new_image_limit": limit}
                logging.info("Collecting %s from %s limit=%s", entry.id, name, limit)
                try:
                    downloaded, rejected = collect_candidates(
                        source.candidates(entry, limit=None, pages=3), DATA,
                        max_images=limit, source_name=name, max_storage_bytes=cap,
                        minimum_interval=source.client.minimum_interval, max_retries=1,
                    )
                    progress.update(status="completed", new_unique_images=downloaded, rejected=rejected)
                except Exception as exc:
                    progress.update(status="failed", error=str(exc))
                    logging.exception("Source failed; continuing other bounded sources")
                report["sources"].append(progress)
                output.write_text(json.dumps(report, indent=2), encoding="utf-8")
                logging.info("Result %s", progress)
    finally:
        after = read_jsonl(DATA / "raw/manifest.jsonl")
        added = [r for r in after if (r["source"], r["source_id"]) not in before_keys]
        report.update(
            finished_at=datetime.now(timezone.utc).isoformat(),
            before_records=len(before), after_records=len(after), new_records=len(added),
            new_by_species=dict(Counter(r["species_id"] for r in added)),
            additional_image_bytes=image_storage_bytes(DATA) - initial_bytes,
            new_record_keys=[{"source": r["source"], "source_id": r["source_id"]} for r in added],
        )
        output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print("Run report:", output, flush=True)


if __name__ == "__main__":
    main()
