"""Stage GRIIS Philippine plant candidates; never enables AI classes.

Run with services/ml/.venv/Scripts/python.exe scripts/build_species_research_pool.py.
Downloads a small public checklist with attribution; preserves its source flags.
"""
import csv
import hashlib
import io
import json
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "storage/species_catalog/research/griis_philippines"
URL = "https://cloud.gbif.org/griis/archive.do?r=griis-philippines"
SOURCE = "https://www.gbif.org/dataset/1b1f1153-f54e-418f-b9c8-3f86a2f680b4"


def main():
    response = requests.get(URL, timeout=30)
    response.raise_for_status()
    archive_bytes = response.content
    archive = zipfile.ZipFile(io.BytesIO(archive_bytes))

    def rows(name):
        return list(csv.DictReader(io.StringIO(archive.read(name).decode("utf-8-sig")), delimiter="\t"))

    taxa = rows("taxon.txt")
    distributions = defaultdict(list)
    profiles = defaultdict(list)
    for row in rows("distribution.txt"):
        distributions[row["id"]].append(row)
    for row in rows("speciesprofile.txt"):
        profiles[row["id"]].append(row)
    previous = json.loads((ROOT / "docs/nationwide-species-availability.json").read_text(encoding="utf-8"))
    historic = {r["scientific_name"] for r in previous["candidates"]}
    historic.add("Eichhornia crassipes")
    candidates = []
    for taxon in taxa:
        if taxon["kingdom"] != "Plantae" or taxon["taxonRank"].upper() != "SPECIES":
            continue
        country = [r for r in distributions[taxon["id"]] if r["countryCode"] == "PH" and r["occurrenceStatus"].lower() == "present"]
        if not country:
            continue
        profile = profiles[taxon["id"]]
        flags = sorted({r["isInvasive"] for r in profile})
        invasive = any(flag.lower() == "invasive" for flag in flags)
        full_name = taxon["acceptedNameUsage"] or taxon["scientificName"]
        search_name = " ".join(full_name.split()[:2])
        candidates.append({
            "source_taxon_id": taxon["id"], "source_scientific_name": taxon["scientificName"],
            "source_accepted_name": taxon["acceptedNameUsage"], "search_name_candidate": search_name,
            "source_taxonomic_status": taxon["taxonomicStatus"], "family": taxon["family"],
            "country_code": "PH", "source_establishment_means": "|".join(sorted({r['establishmentMeans'] for r in country})),
            "source_invasive_flags": "|".join(flags),
            "evidence_bucket": "source_flagged_invasive" if invasive else "introduced_status_review_needed",
            "historical_shortlist_match": search_name in historic,
            "habitat": "|".join(sorted({r['habitat'] for r in profile})),
            "source_url": SOURCE, "source_doi": "10.15468/ribkgo", "source_license": "CC BY 4.0",
            "review_status": "pending_ecological_taxonomic_and_image_feasibility_review",
            "ai_model_supported": False, "image_availability_checked": False,
        })
    names = Counter(r["search_name_candidate"] for r in candidates)
    for row in candidates:
        row["name_collision_requires_review"] = names[row["search_name_candidate"]] > 1
    candidates.sort(key=lambda r: (r["evidence_bucket"] != "source_flagged_invasive", not r["historical_shortlist_match"], r["search_name_candidate"]))
    # Rank source taxa, not deduplicated accepted classes. Never collapse synonym collisions silently.
    selected, seen = [], set()
    for row in candidates:
        if row["name_collision_requires_review"] or row["search_name_candidate"] in seen:
            continue
        selected.append(row)
        seen.add(row["search_name_candidate"])
        if len(selected) == 100:
            break
    BASE.mkdir(parents=True, exist_ok=True)
    (BASE / "source.zip").write_bytes(archive_bytes)
    (BASE / "eml.xml").write_bytes(archive.read("eml.xml"))
    for path, records in [(BASE / "plant_research_pool.csv", candidates), (ROOT / "docs/species_100_research_queue.csv", selected)]:
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(candidates[0]))
            writer.writeheader()
            writer.writerows(records)
    evidence = {
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(), "source_url": SOURCE,
        "download_url": URL, "archive_sha256": hashlib.sha256(archive_bytes).hexdigest(),
        "source_attribution": "Global Register of Introduced and Invasive Species - Philippines; Invasive Species Specialist Group ISSG; DOI 10.15468/ribkgo; CC BY 4.0. Preserve full author/version citation from downloaded eml.xml.",
        "all_taxa": len(taxa), "plant_species_source_rows": len(candidates),
        "all_plant_evidence_buckets": dict(Counter(r["evidence_bucket"] for r in candidates)),
        "research_queue_rows": len(selected), "queue_buckets": dict(Counter(r["evidence_bucket"] for r in selected)),
        "selection": "Source invasive flag first, historical shortlist next, then alphabetical. Excludes unresolved candidate-name collisions. Not a severity ranking.",
        "limitations": ["100 research candidates are not 100 verified invasive species", "Null invasive flag means unknown/not flagged, not proven non-invasive", "Search names are provisional binomials, not independently reconciled taxonomy", "Image counts in this queue have not been probed", "No model classes or ecological database statuses changed"],
    }
    (ROOT / "docs/species-100-source-evidence.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
