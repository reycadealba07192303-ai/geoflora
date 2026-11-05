"""Resumable, read-only iNaturalist availability check for the research queue.

Run with services/ml/.venv/Scripts/python.exe scripts/check_research_queue.py.
No image collection, approvals or model-class changes.
"""
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from geoflora_ml.collection.inaturalist import BASE_URL, INaturalistSource

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/species-100-availability.json"


def main():
    with (ROOT / "docs/species_100_research_queue.csv").open(encoding="utf-8", newline="") as stream:
        queue = list(csv.DictReader(stream))
    report = json.loads(OUTPUT.read_text(encoding="utf-8")) if OUTPUT.exists() else {
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "unit": "Research-grade observations with >=1 CC0/CC BY/CC BY-SA photo, not approved images",
        "candidates": [],
    }
    completed = {r["source_taxon_id"] for r in report["candidates"] if r["probe_status"] == "completed"}
    client = INaturalistSource(max_retries=1).client
    places = client.get_json(BASE_URL + "/places/autocomplete", {"q": "Philippines"})["results"]
    place_id = next(p["id"] for p in places if p["name"].casefold() == "philippines")
    report["philippines_place_id"] = place_id
    for index, row in enumerate(queue, 1):
        if row["source_taxon_id"] in completed:
            continue
        entry = {"source_taxon_id": row["source_taxon_id"], "search_name_candidate": row["search_name_candidate"],
                 "source_evidence_bucket": row["evidence_bucket"], "checked_at_utc": datetime.now(timezone.utc).isoformat()}
        try:
            taxa = client.get_json(BASE_URL + "/taxa", {"q": row["search_name_candidate"], "rank": "species", "is_active": "true"})["results"]
            exact = next((t for t in taxa if t["name"].casefold() == row["search_name_candidate"].casefold()), None)
            if exact is None:
                entry["probe_status"] = "taxonomy_unresolved"
                entry["returned_names"] = [t["name"] for t in taxa]
            else:
                entry["inaturalist_taxon_id"] = exact["id"]
                params = {"taxon_id": exact["id"], "quality_grade": "research", "photos": "true", "photo_license": "cc0,cc-by,cc-by-sa", "per_page": 1}
                for field, extra in [("ph_observations", {"place_id": place_id}), ("global_observations_including_ph", {})]:
                    result = client.get_json(BASE_URL + "/observations", {**params, **extra})
                    entry[field] = result["total_results"]
                entry["probe_status"] = "completed"
        except Exception as exc:
            entry.update(probe_status="request_failed", error=str(exc))
        report["candidates"] = [r for r in report["candidates"] if r["source_taxon_id"] != entry["source_taxon_id"]] + [entry]
        report["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
        report["status_counts"] = dict(Counter(r["probe_status"] for r in report["candidates"]))
        OUTPUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(index, entry["search_name_candidate"], entry["probe_status"], entry.get("ph_observations"), entry.get("global_observations_including_ph"), flush=True)


if __name__ == "__main__":
    main()
