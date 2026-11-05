"""Read-only image-availability probe for proposed Philippine target classes.

Run with services/ml/.venv/Scripts/python.exe scripts/check_species_shortlist.py.
Counts observations, not usable photos. Downloads no images; changes no classes.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from geoflora_ml.collection.inaturalist import INaturalistSource, BASE_URL

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "https://www.cbd.int/doc/world/ph/ph-nr-04-en.pdf#page=23"
CANDIDATES = [
    ("Chromolaena odorata", "Hagonoy", True),
    ("Lantana camara", "Lantana / coronitas", True),
    ("Pontederia crassipes", "Water hyacinth", True),
    ("Leucaena leucocephala", "Ipil-ipil", False),
    ("Mikania micrantha", "Mile-a-minute", False),
    ("Broussonetia papyrifera", "Paper mulberry", False),
    ("Coccinia grandis", "Ivy gourd", False),
    ("Swietenia macrophylla", "Big-leaf mahogany", False),
    ("Acacia mangium", "Mangium", False),
    ("Acacia auriculiformis", "Auri", False),
]


def main():
    client = INaturalistSource(max_retries=1).client
    places = client.get_json(BASE_URL + "/places/autocomplete", {"q": "Philippines"})["results"]
    place = next(p for p in places if p["name"].casefold() == "philippines")
    report = {"checked_at_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "Nationwide Philippines; proposed classes, not deployed support",
              "count_unit": "research-grade observations with at least one CC0/CC BY/CC BY-SA photo; NOT approved independent images",
              "philippines_place_id": place["id"], "candidates": []}
    output = ROOT / "docs/nationwide-species-availability.json"
    for name, common, existing in CANDIDATES:
        entry = {"scientific_name": name, "common_name": common,
                 "existing_class": existing, "proposed_only": not existing,
                 "ph_status_evidence": SOURCE, "evidence_year": 2009,
                 "ecological_review_required": True}
        if name == "Pontederia crassipes":
            entry["source_name_note"] = "Source lists water hyacinth as Eichornia crassipes; current project uses Pontederia crassipes. Taxonomic reconciliation must be recorded."
        try:
            taxa = client.get_json(BASE_URL + "/taxa", {"q": name, "rank": "species", "is_active": "true"})["results"]
            exact = next((t for t in taxa if t["name"].casefold() == name.casefold()), None)
            if exact is None:
                raise ValueError("No exact active species match; resolve taxonomy before collection")
            entry["inaturalist_taxon_id"] = exact["id"]
            entry["taxon_url"] = f"https://www.inaturalist.org/taxa/{exact['id']}"
            params = {"taxon_id": exact["id"], "quality_grade": "research", "photos": "true",
                      "photo_license": "cc0,cc-by,cc-by-sa", "per_page": 1}
            for label, extra in [("ph_observations", {"place_id": place["id"]}), ("global_observations_including_ph", {})]:
                entry[label] = client.get_json(BASE_URL + "/observations", {**params, **extra})["total_results"]
            entry["probe_status"] = "completed"
        except Exception as exc:
            entry.update(probe_status="failed", error=str(exc))
        report["candidates"].append(entry)
        output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(name, entry.get("ph_observations"), entry.get("global_observations_including_ph"), entry["probe_status"], flush=True)


if __name__ == "__main__":
    main()
