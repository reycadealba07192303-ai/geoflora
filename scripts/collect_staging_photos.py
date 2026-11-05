"""Collect bounded, licensed Philippine field photos into staging for automatic training.

Two kinds of groups:
  * invasive: monitored species (one species per class);
  * lookalike: non-invasive plants people confuse with them (a whole group is one class).

Photos come from research-grade iNaturalist observations in the Philippines (community-agreed identifications; GBIF media
for these taxa are mostly herbarium sheets, so GBIF is not used). The research-grade identification is recorded as the
label basis, and the AI screen (scripts/screen_staging_photos.py) checks photos as its quota allows. Collection defaults
to CC0/CC BY/CC BY-SA; --allow-noncommercial can stage CC BY-NC photos for visual review, but those are excluded from
invasive model training. Every photo keeps its licence and attribution. Nothing here changes the active model.

Usage: python scripts/collect_staging_photos.py [group ...]   (no group: all of them)
"""
import argparse
import csv
import hashlib
import json
import logging
from collections import Counter
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from urllib.parse import quote

from geoflora_ml.collection.inaturalist import INaturalistSource
from geoflora_ml.collection.licensing import normalize_license, training_license_eligible
from geoflora_ml.collection.runner import collect_candidates, image_storage_bytes
from geoflora_ml.config import Species
from geoflora_ml.datasets.duplicates import group_near_duplicates
from geoflora_ml.datasets.manifest import read_jsonl
from geoflora_ml.datasets.review_service import _safe_image_path
from geoflora_ml.env import load_env

ROOT = Path(__file__).resolve().parents[1]
FLAGGED = "Listed as invasive in the Philippines by GRIIS (source-flagged); see docs/species_100_verification_ledger.csv."
REVIEW = "Introduced in the Philippines; invasive status not yet verified in GeoFlora's sources (owner chose to monitor it, October 31, 2026)."


def invasive(species_id, scientific_name, common_name, status):
    return {"role": "invasive", "label": f"{common_name} ({scientific_name})", "status_note": status,
            "class": {"id": species_id, "scientific_name": scientific_name, "common_name": common_name, "role": "invasive", "status": "source_flagged" if status == FLAGGED else "introduced_review"},
            "species": [Species(species_id, scientific_name, common_name)]}


GROUPS = {
    # Monitored species. Ids and names match the frozen v5 classes where they already exist.
    "chromolaena_odorata": invasive("chromolaena_odorata", "Chromolaena odorata", "Hagonoy", FLAGGED),
    "lantana_camara": invasive("lantana_camara", "Lantana camara", "Lantana", FLAGGED),
    "pontederia_crassipes": invasive("pontederia_crassipes", "Pontederia crassipes", "Water Hyacinth", FLAGGED),
    "mikania_micrantha": invasive("mikania_micrantha", "Mikania micrantha", "Mile-a-minute", FLAGGED),
    "pistia_stratiotes": invasive("pistia_stratiotes", "Pistia stratiotes", "Water Lettuce", FLAGGED),
    "broussonetia_papyrifera": invasive("broussonetia_papyrifera", "Broussonetia papyrifera", "Paper mulberry", FLAGGED),
    "leucaena_leucocephala": invasive("leucaena_leucocephala", "Leucaena leucocephala", "Ipil-ipil", REVIEW),
    "spathodea_campanulata": invasive("spathodea_campanulata", "Spathodea campanulata", "African tulip tree", REVIEW),
    "coccinia_grandis": invasive("coccinia_grandis", "Coccinia grandis", "Ivy gourd", REVIEW),
    "antigonon_leptopus": invasive("antigonon_leptopus", "Antigonon leptopus", "Cadena de amor", REVIEW),
    # Look-alikes. The class is the whole group, since photos rarely settle the species.
    "nymphaea": {"role": "lookalike", "label": "Water lily (Nymphaea)", "confused_with": "Pontederia crassipes (water hyacinth)",
                 "status_note": "No GeoFlora source lists these as introduced or invasive in the Philippines; N. nouchali is native.",
                 "class": {"id": "nymphaea", "scientific_name": "Nymphaea", "common_name": "Water lily", "role": "lookalike", "citation": "https://powo.science.kew.org/results?q=Nymphaea"},
                 "species": [Species("nymphaea_rubra", "Nymphaea rubra", "Red water lily"), Species("nymphaea_pubescens", "Nymphaea pubescens", "Hairy water lily"), Species("nymphaea_nouchali", "Nymphaea nouchali", "Blue water lily")]},
}
PER_SPECIES = {"invasive": 150, "lookalike": 40}
PAGES = 3
EXTRA_GB = 0.4
QUEUE_FIELDS = ["species_id", "scientific_name", "common_name", "source", "source_id", "source_url", "license", "attribution", "training_license_eligible", "country_code", "locality", "observed_at", "group_id", "near_duplicate_group_id", "sha256", "local_path", "role", "review_status", "reviewer", "review_rationale"]


def folder(group_id):
    return ROOT / f"storage/datasets/staging/{GROUPS[group_id]['role']}_{group_id}_ph"


def write_review_queue(data, rows, role):
    """Preserve source records; only allowlisted rights may retain a training-usable review status."""
    path = data / "review_queue.csv"
    decided = {}
    if path.exists():
        with path.open(encoding="utf-8", newline="") as stream:
            decided = {row["sha256"]: row for row in csv.DictReader(stream) if row.get("review_status") not in (None, "", "pending")}
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=QUEUE_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            previous = decided.get(row["sha256"], {})
            initial = "research_grade" if row["source"] == "inaturalist" else "pending"
            eligible = training_license_eligible(row.get("license"), row.get("attribution"))
            status = previous.get("review_status", initial) if eligible else "pending"
            writer.writerow({**row, "role": role, "training_license_eligible": "yes" if eligible else "no", "review_status": status,
                             "reviewer": previous.get("reviewer", "") if eligible else "",
                             "review_rationale": previous.get("review_rationale", "") if eligible else "License is outside the active training allowlist; retained for rights review."})


def render_gallery(data, title):
    with (data / "review_queue.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    cards = "".join(
        f'<article><a href="{quote(row["local_path"], safe="/")}"><img loading="lazy" src="{quote(row["local_path"], safe="/")}" alt="Candidate photo"></a>'
        f'<h2><i>{escape(row["scientific_name"])}</i></h2><p>{escape(row["source"])}: {escape(row["source_id"])} · {escape(row["review_status"])}</p>'
        f'<p>Invasive model training: {"eligible" if row.get("training_license_eligible") == "yes" else "excluded by license"}</p>'
        f'<p>{escape(row["license"])} · {escape(row["attribution"])}</p><a href="{escape(row["source_url"], quote=True)}" target="_blank" rel="noopener noreferrer">Source observation</a></article>'
        for row in rows)
    page = f'<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(title)} staging</title>'
    page += '<style>body{font-family:system-ui;margin:24px;background:#eef1ea;color:#0d2618}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}article{background:white;border-radius:20px;padding:12px}img{width:100%;height:220px;object-fit:cover;border-radius:14px}h2{font-size:15px}p{font-size:12px;color:#5f6b62}</style>'
    page += f'<h1>{escape(title)}: staging photos</h1><p>{len(rows)} photos with their review status.</p><main>{cards}</main></html>'
    (data / "review_gallery.html").write_text(page, encoding="utf-8")


def collect(group_id, allow_noncommercial=False, rescan_licensed=False):
    group, data = GROUPS[group_id], folder(group_id)
    data.mkdir(parents=True, exist_ok=True)
    (data / "group.json").write_text(json.dumps({**group["class"], "label": group["label"], "status_note": group["status_note"], **({"confused_with": group["confused_with"]} if "confused_with" in group else {})}, indent=2), encoding="utf-8")
    active = ROOT / "storage/datasets/raw/manifest.jsonl"
    active_hash = hashlib.sha256(active.read_bytes()).hexdigest()
    manifest = data / "raw/manifest.jsonl"
    before = read_jsonl(manifest) if manifest.exists() else []
    id_above_by_species = {}
    for row in before:
        observation_id = str(row.get("observation_id", ""))
        species_id = row.get("species_id", "")
        if observation_id.isdigit():
            id_above_by_species[species_id] = max(int(observation_id), id_above_by_species.get(species_id, 0))
    initial_bytes = image_storage_bytes(data)
    report_path = ROOT / f"docs/staging-{group_id}-evidence.json"
    page_limit = 30 if rescan_licensed else PAGES
    report = {"started_at_utc": datetime.now(timezone.utc).isoformat(), "group": group["label"], "role": group["role"], "status_note": group["status_note"], "country_filter": "PH",
              "bounds": {"new_unique_images_per_species": PER_SPECIES[group["role"]], "api_pages": page_limit, "additional_gb": EXTRA_GB},
              "licensing_filter": "CC0/CC BY/CC BY-SA only" if not allow_noncommercial else "CC0/CC BY/CC BY-SA/CC BY-NC only",
              "pagination": {"strategy": "rescan from earliest observation" if rescan_licensed else "continue after highest existing iNaturalist observation id for each species", "id_above_by_species": {}},
              "label_basis": "iNaturalist research grade (community-agreed identification); AI screen as quota allows", "runs": []}
    try:
        for species in group["species"]:
            id_above = None if rescan_licensed else id_above_by_species.get(species.id)
            report["pagination"]["id_above_by_species"][species.id] = id_above
            source = INaturalistSource(max_retries=1, allow_noncommercial=allow_noncommercial)
            logging.info("Collecting %s", species.scientific_name)
            result = {"species": species.scientific_name, "source": "inaturalist"}
            try:
                count, rejected = collect_candidates(source.candidates(species, limit=None, pages=page_limit, id_above=id_above), data, max_images=PER_SPECIES[group["role"]], source_name="inaturalist",
                                                     max_storage_bytes=initial_bytes + int(EXTRA_GB * 1024**3), minimum_interval=source.client.minimum_interval, max_retries=1, allow_noncommercial=allow_noncommercial)
                result.update(status="completed", new_unique_images=count, download_rejections=rejected)
            except Exception as exc:
                logging.exception("Source failed")
                result.update(status="failed", error=str(exc)[:300])
            report["runs"].append(result)
            report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    finally:
        rows = read_jsonl(manifest) if manifest.exists() else []
        valid, reviewable, invalid = [], [], []
        for row in rows:
            image_ok = _safe_image_path(row, data.resolve()) is not None
            provenance_ok = bool(row.get("source_url") and row.get("group_id"))
            if image_ok and row.get("country_code") == "PH" and provenance_ok:
                reviewable.append(row)
            issues = [issue for issue, failed in [
                ("image_integrity_failed", not image_ok),
                ("rights_metadata_ineligible", not normalize_license(row.get("license"), allow_noncommercial=allow_noncommercial) or not row.get("attribution")),
                ("country_unresolved", row.get("country_code") != "PH"),
                ("missing_provenance", not row.get("source_url") or not row.get("group_id")),
            ] if failed]
            (invalid.append({"source": row["source"], "source_id": row["source_id"], "issues": issues}) if issues else valid.append(row))
        grouped, near_groups = group_near_duplicates(reviewable, data) if reviewable else ([], [])
        write_review_queue(data, grouped, group["role"])
        render_gallery(data, group["label"])
        assert hashlib.sha256(active.read_bytes()).hexdigest() == active_hash, "Active raw manifest changed during staging run"
        report.update(finished_at_utc=datetime.now(timezone.utc).isoformat(), new_records=len(rows) - len(before), valid_records=len(valid), review_queue_records=len(reviewable), invalid_records=invalid,
                      licences=dict(Counter(r["license"] for r in valid)), observation_groups=len({r["group_id"] for r in valid}), near_duplicate_groups=len(near_groups),
                      additional_image_bytes=image_storage_bytes(data) - initial_bytes, review_queue=str((data / "review_queue.csv").relative_to(ROOT)), gallery=str((data / "review_gallery.html").relative_to(ROOT)))
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps({"group": group_id, "valid_records": len(valid), "new_records": report["new_records"], "licences": report["licences"]}), flush=True)


def main():
    load_env()
    parser = argparse.ArgumentParser()
    parser.add_argument("groups", nargs="*", help="any of: " + ", ".join(sorted(GROUPS)))
    parser.add_argument("--skip-registry-sync", action="store_true", help="keep collection limited to local staging files")
    parser.add_argument("--allow-noncommercial", action="store_true", help="include CC BY-NC images in staging; these are not eligible for invasive model training")
    parser.add_argument("--rescan-licensed", action="store_true", help="rescan early source pages for eligible licensed images; existing photos are deduplicated")
    args = parser.parse_args()
    groups = args.groups or list(GROUPS)
    if unknown := sorted(set(groups) - set(GROUPS)):
        parser.error(f"unknown group(s): {', '.join(unknown)}")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    for group_id in groups:
        collect(group_id, allow_noncommercial=args.allow_noncommercial, rescan_licensed=args.rescan_licensed)
    if not args.skip_registry_sync:
        try:
            from species_registry import sync_now
            print(f"Species classes in the database: {sync_now()}", flush=True)
        except Exception as error:  # The training worker syncs again on its next pass.
            print(f"Species list not synced to the database: {error}", flush=True)


if __name__ == "__main__":
    main()
