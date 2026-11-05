"""Build a traceable five-class experimental selection, never activate/train."""
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

from geoflora_ml.datasets.audit import load_current_reviews
from geoflora_ml.datasets.manifest import read_jsonl
from geoflora_ml.datasets.duplicates import group_near_duplicates
from geoflora_ml.datasets.split import assign_group_splits

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "storage/datasets/selection/pilot_five_classes"
CLASSES = {
    "Chromolaena odorata": "Hagonoy", "Lantana camara": "Lantana",
    "Pontederia crassipes": "Water Hyacinth", "Mikania micrantha": "Mile-a-minute",
    "Pistia stratiotes": "Water Lettuce",
}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    screen = json.loads((OUT / "visual_screening.json").read_text())
    included_files = {r["file"] for group in screen.values() for r in group if r["include"]}
    data = ROOT / "storage/datasets"
    reviews = load_current_reviews(data)
    candidates = []
    for record in read_jsonl(data / "raw/manifest.jsonl"):
        review = reviews.get((record["source"], record["source_id"]), {})
        if review.get("decision") not in {"approved", "relabelled"}:
            continue
        if record["scientific_name"] not in CLASSES:
            continue
        # Preserve legacy review basis; these images are not newly visually rechecked.
        url = record.get("image_url", "")
        if "inaturalist" not in url or "/photos/" not in url:
            continue
        candidates.append({**record, "file": str((data / record["local_path"]).resolve()),
                           "domain_basis": "legacy_photo_source_heuristic_not_new_visual_review", "label_basis": "existing_owner_approval"})
    import batch_review
    history = batch_review.REVIEW / "review_events.jsonl"
    latest = {r["record_key"]: r for r in read_jsonl(history)}
    for row in batch_review.records():
        if row["file"] not in included_files:
            continue
        review = latest.get(row["record_key"], {})
        if review.get("decision") != "approved" or review.get("verified_country") != "PH" or review.get("verified_domain") != "field":
            raise ValueError("Selected new record lacks approval/PH/domain evidence")
        candidates.append({**row, "group_id": next(r["group_id"] for r in read_jsonl(batch_review.BASE / row["corpus"] / "raw/manifest.jsonl") if r["source"] == row["source"] and r["source_id"] == row["source_id"]),
                           "domain_basis": "assistant_visual_field_screen", "label_basis": "owner_batch_approval"})
    unique, seen = [], set()
    for row in candidates:
        file = Path(row["file"])
        if hashlib.sha256(file.read_bytes()).hexdigest() != row["sha256"]:
            raise ValueError("Selected image integrity failed")
        if row["sha256"] in seen:
            continue
        seen.add(row["sha256"])
        name = row["scientific_name"]
        unique.append({**row, "species_id": name.lower().replace(" ", "_"),
                       "local_path": file.relative_to(ROOT).as_posix(), "country_code": "PH",
                       "country_basis": "owner_PH_location_confirmation; source PH filters", "selection_status": "experimental_only"})
    grouped, _ = group_near_duplicates(unique, ROOT)
    # This dry feasibility assignment checks group constraints but is not the final evaluation split.
    feasibility = assign_group_splits(grouped, seed=42)
    class_counts = {}
    for name in CLASSES:
        selected = [r for r in feasibility if r["scientific_name"] == name]
        if len(selected) < 6:
            raise ValueError("Pilot floor: at least six images per class; not a quality guarantee")
        class_counts[name] = {"images": len(selected), "feasibility_split_counts": dict(Counter(r["split"] for r in selected))}
    fields = ["species_id", "scientific_name", "source", "source_id", "source_url", "license", "attribution", "sha256", "local_path", "group_id", "near_duplicate_group_id", "country_code", "country_basis", "domain_basis", "label_basis", "selection_status"]
    with (OUT / "selected_candidates.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader(); writer.writerows(grouped)
    config = {"scope": "experimental five-class selection; active registry unchanged",
              "classes": [{"id": n.lower().replace(" ", "_"), "scientific_name": n, "common_name": common} for n, common in CLASSES.items()],
              "counts": class_counts, "total_unique_images": len(unique),
              "invasive_evidence": {
                  "Chromolaena odorata": "https://www.philchm.ph/wp-content/uploads/2019/03/NISSAP-Philippines-2016_final-draft.pdf",
                  "Lantana camara": "https://www.cbd.int/doc/world/ph/ph-nr-04-en.pdf#page=23",
                  "Pontederia crassipes": "https://www.philchm.ph/wp-content/uploads/2019/03/NISSAP-Philippines-2016_final-draft.pdf",
                  "Mikania micrantha": "https://www.cbd.int/doc/world/ph/ph-nr-04-en.pdf#page=23",
                  "Pistia stratiotes": "https://www.philippineplants.org/Families/Araceae.html"},
              "limitations": ["New classes have very small independent samples", "Original three-class images retain previous owner/source-based review; not newly visually verified", "No claim of nationwide accuracy", "No final split/model activation performed"]}
    (OUT / "selected_classes.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    print(json.dumps(config, indent=2))


if __name__ == "__main__":
    main()
