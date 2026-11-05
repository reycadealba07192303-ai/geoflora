"""Resumable PH-only collection for all 100 research candidates, never approves.

Default: up to 10 distinct image checksums per species, 1 API page per provider,
40 candidate attempts per provider, and a 1 GiB total staging image budget.
Run with services/ml/.venv/Scripts/python.exe scripts/collect_research_batch.py.
"""
import csv
import hashlib
import itertools
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from geoflora_ml.collection.gbif import GBIFSource
from geoflora_ml.collection.inaturalist import INaturalistSource
from geoflora_ml.collection.runner import collect_candidates, image_storage_bytes
from geoflora_ml.config import Species
from geoflora_ml.datasets.manifest import read_jsonl

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "storage/datasets/staging/species_100_ph"
REPORT = ROOT / "docs/species-100-collection-progress.json"


def batch_storage_bytes():
    # Each taxon has its own raw directory, rather than DATA/raw.
    return sum(path.stat().st_size for path in DATA.rglob("*.jpg"))


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    with (ROOT / "docs/species_100_research_queue.csv").open(encoding="utf-8", newline="") as stream:
        queue = list(csv.DictReader(stream))
    availability = json.loads((ROOT / "docs/species-100-availability.json").read_text())
    probes = {r["source_taxon_id"]: r for r in availability["candidates"]}
    active = ROOT / "storage/datasets/raw/manifest.jsonl"
    active_hash = hashlib.sha256(active.read_bytes()).hexdigest()
    DATA.mkdir(parents=True, exist_ok=True)
    report = json.loads(REPORT.read_text()) if REPORT.exists() else {
        "started_at_utc": datetime.now(timezone.utc).isoformat(), "species": [],
        "scope": "PH research candidates; ecological approval NOT granted",
        "bounds": {"target_unique_images_per_species": 10, "pages_per_source": 1,
                   "candidate_attempts_per_source": 40, "total_staging_gib": 1},
    }
    done = {r["source_taxon_id"] for r in report["species"] if r["status"] in {"collected", "no_eligible_images", "taxonomy_unresolved"}}
    # A resumed pass must not expose the old finished marker to the finalizer.
    report.pop("pass_finished_at_utc", None)
    report["resumed_at_utc"] = datetime.now(timezone.utc).isoformat()
    report["run_status"] = "running"
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    for index, row in enumerate(queue, 1):
        if row["source_taxon_id"] in done:
            continue
        folder = DATA / row["source_taxon_id"]
        manifest = folder / "raw/manifest.jsonl"
        records = read_jsonl(manifest) if manifest.exists() else []
        progress = {"source_taxon_id": row["source_taxon_id"], "name": row["search_name_candidate"],
                    "ecological_evidence_bucket": row["evidence_bucket"], "review_status": "pending",
                    "sources": [], "status": "running"}
        probe = probes.get(row["source_taxon_id"], {})
        species = Species("research_" + row["source_taxon_id"], row["search_name_candidate"], row["search_name_candidate"])
        logging.info("SPECIES %s/100 %s", index, species.scientific_name)
        # Do not guess unresolved names in either provider. They remain in the batch report.
        if probe.get("probe_status") == "taxonomy_unresolved":
            progress["status"] = "taxonomy_unresolved"
        else:
            for name, source in [("inaturalist", INaturalistSource(max_retries=1)), ("gbif", GBIFSource(max_retries=1))]:
                remaining = 10 - len({r["sha256"] for r in records})
                if remaining <= 0:
                    break
                remaining_bytes = 1024**3 - batch_storage_bytes()
                if remaining_bytes < 20 * 1024**2:
                    progress["status"] = "storage_cap_reached"
                    break
                if name == "inaturalist" and probe.get("ph_observations") == 0:
                    progress["sources"].append({"source": name, "status": "skipped_recent_zero_ph_probe"})
                    continue
                try:
                    candidates = itertools.islice(source.candidates(species, limit=None, pages=1), 40)
                    downloaded, rejected = collect_candidates(
                        candidates, folder, max_images=remaining, source_name=name,
                        max_storage_bytes=image_storage_bytes(folder) + remaining_bytes,
                        minimum_interval=source.client.minimum_interval, max_retries=1,
                    )
                    progress["sources"].append({"source": name, "status": "completed", "new_unique_images": downloaded, "rejected": rejected})
                except Exception as exc:
                    progress["sources"].append({"source": name, "status": "failed", "error": str(exc)})
                records = read_jsonl(manifest) if manifest.exists() else []
            if progress["status"] == "running":
                progress["status"] = "source_error" if any(r["status"] == "failed" for r in progress["sources"]) else ("collected" if records else "no_eligible_images")
        progress.update(records=len(records), unique_checksums=len({r["sha256"] for r in records}),
                        finished_at_utc=datetime.now(timezone.utc).isoformat())
        report["species"] = [r for r in report["species"] if r["source_taxon_id"] != row["source_taxon_id"]] + [progress]
        report.update(updated_at_utc=datetime.now(timezone.utc).isoformat(),
                      attempted_species=len(report["species"]),
                      species_with_images=sum(r["records"] > 0 for r in report["species"]),
                      total_records=sum(r["records"] for r in report["species"]),
                      active_manifest_unchanged=hashlib.sha256(active.read_bytes()).hexdigest() == active_hash)
        REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
        logging.info("RESULT %s records=%s status=%s", species.scientific_name, len(records), progress["status"])
    report["pass_finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    report["run_status"] = "pass_finished"
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("BATCH PASS FINISHED", report["attempted_species"], report["species_with_images"], report["total_records"], flush=True)


if __name__ == "__main__":
    main()
