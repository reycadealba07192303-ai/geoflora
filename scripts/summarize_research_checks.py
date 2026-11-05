"""Join completed screening evidence into a review ledger, never approve classes."""
import csv
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    queue_path = ROOT / "docs/species_100_research_queue.csv"
    with queue_path.open(encoding="utf-8", newline="") as stream:
        queue = list(csv.DictReader(stream))
    ecology = json.loads((ROOT / "docs/species-100-ecological-crosscheck.json").read_text())
    availability = json.loads((ROOT / "docs/species-100-availability.json").read_text())
    eco = {r["source_taxon_id"]: r for r in ecology["candidates"]}
    images = {r["source_taxon_id"]: r for r in availability["candidates"]}
    if set(eco) != {r["source_taxon_id"] for r in queue} or set(images) != set(eco):
        raise ValueError("Wait for all 100 attempted checks before summarizing")
    combined = []
    for row in queue:
        e, a = eco[row["source_taxon_id"]], images[row["source_taxon_id"]]
        status = e["crosscheck_status"]
        if status in {"native_status_conflict_hold", "origin_uncertain_hold"}:
            action = "hold_ecological_conflict"
        elif a["probe_status"] != "completed" or status != "exact_record_found_context_review_needed":
            action = "resolve_taxonomy_or_source"
        elif row["evidence_bucket"] == "source_flagged_invasive":
            action = "priority_context_and_image_review" if a["ph_observations"] else "ph_image_gap_context_review"
        else:
            action = "verify_ph_invasive_status_first"
        combined.append({
            "source_taxon_id": row["source_taxon_id"], "scientific_name_candidate": row["search_name_candidate"],
            "griis_evidence_bucket": row["evidence_bucket"], "ecology_screen_status": status,
            "cdfp_annotations": "|".join(e.get("cdfp_annotations", [])), "ecology_reference": e["crosscheck_url"],
            "invasive_term_needs_context_review": e.get("invasive_term_present_needs_context_review", ""),
            "availability_status": a["probe_status"], "ph_photo_observations": a.get("ph_observations", ""),
            "global_photo_observations_including_ph": a.get("global_observations_including_ph", ""),
            "inaturalist_taxon_id": a.get("inaturalist_taxon_id", ""),
            "next_action": action, "ecological_approval": "not_granted", "new_class_activation": False,
        })
        row["image_availability_checked"] = str(a["probe_status"] == "completed")
    output = ROOT / "docs/species_100_verification_ledger.csv"
    with output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(combined[0]))
        writer.writeheader()
        writer.writerows(combined)
    backup = ROOT / "storage/species_catalog/research/griis_philippines/queue_before_verification.csv"
    if not backup.exists():
        backup.write_bytes(queue_path.read_bytes())
    with queue_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(queue[0]))
        writer.writeheader()
        writer.writerows(queue)
    summary = {"queue_rows": len(queue), "ecology_status_counts": dict(Counter(e["crosscheck_status"] for e in eco.values())),
               "availability_status_counts": dict(Counter(a["probe_status"] for a in images.values())),
               "completed_queries_with_ph_results": sum(a["probe_status"] == "completed" and a["ph_observations"] > 0 for a in images.values()),
               "completed_queries_with_zero_ph_results": sum(a["probe_status"] == "completed" and a["ph_observations"] == 0 for a in images.values()),
               "next_action_counts": dict(Counter(r["next_action"] for r in combined)),
               "native_conflict_names": [r["scientific_name_candidate"] for r in combined if r["ecology_screen_status"] == "native_status_conflict_hold"],
               "origin_uncertain_names": [r["scientific_name_candidate"] for r in combined if r["ecology_screen_status"] == "origin_uncertain_hold"],
               "new_classes_approved": 0, "new_images_downloaded": 0}
    (ROOT / "docs/species-100-check-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
