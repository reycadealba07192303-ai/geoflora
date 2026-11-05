"""Wait for the batch pass, run the final audit, and reconcile plan status.

Run once alongside the collector. Checkpoint/collection errors stay explicit.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROGRESS = ROOT / "docs/species-100-collection-progress.json"
STATE = ROOT / "docs/part-2ab-job-status.json"


def main():
    deadline = time.monotonic() + 6 * 3600
    STATE.write_text(json.dumps({"status": "waiting_for_full_collection_pass", "next": "Final audit and plan reconciliation"}, indent=2), encoding="utf-8")
    while time.monotonic() < deadline:
        try:
            report = json.loads(PROGRESS.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            time.sleep(10)
            continue
        if report.get("pass_finished_at_utc") and report.get("attempted_species") == 100:
            break
        time.sleep(10)
    else:
        STATE.write_text(json.dumps({"status": "collection_incomplete_after_wait_budget", "action": "Inspect worker and resume collection; no completion claimed"}, indent=2), encoding="utf-8")
        return
    STATE.write_text(json.dumps({"status": "running_final_audit"}, indent=2), encoding="utf-8")
    subprocess.run([sys.executable, "scripts/audit_research_batch.py"], cwd=ROOT, check=True)
    audit = json.loads((ROOT / "docs/species-100-batch-audit-summary.json").read_text())
    if not audit["final_collection_pass"] or audit["snapshot_changed_during_audit"] or audit["checkpoint_manifest_mismatches"]:
        raise RuntimeError("Final pass is inconsistent; inspect audit before marking complete")
    lines = ["# Parts 2A and 2B — final batch outcomes", "",
             "Collection pass and technical organization completed. Label approval and final ecological/geographic decisions remain Part 2C.", "",
             f"- Queue entries with documented outcomes: {audit['checkpointed_species']}/100.",
             f"- Species folders with images: {audit['batch_species_with_images']}.",
             f"- Batch records: {audit['batch_records']}; distinct checksums: {audit['batch_unique_checksums']}.",
             f"- Staging image bytes: {audit['batch_storage_bytes']}.",
             f"- Technical/provenance issue records across audited corpora: {len(audit['technical_failures'])}.",
             f"- Cross-corpus observation/similarity components: {audit['cross_corpus_components']}.",
             f"- Cross-label similarity components requiring review: {audit['cross_label_conflict_components']}.", "",
             "Collection outcomes: " + json.dumps(audit["collection_outcomes"]), "",
             "Domain screening: " + json.dumps(audit["batch_domain_counts"]), "",
             "Region screening: " + json.dumps(audit["batch_region_counts"]), "",
             "## Outputs", "",
             "- storage/datasets/staging/species_100_ph/audit/species_inventory.csv",
             "- storage/datasets/staging/species_100_ph/audit/curation_queue.csv",
             "- storage/datasets/staging/species_100_ph/audit/duplicate_components.json",
             "- docs/species-100-batch-audit-summary.json", "",
             "All originals were preserved. Candidate domain/region screens require review. Source country PH is not independent location verification. Unknown names, native/cryptogenic conflicts, introduced-only statuses, technical issues and cross-label similarity are explicitly held/routed in the curation queue. Similarity grouping is not an automatic deletion or species verdict. Existing approved data and model classes are not expanded.", "",
             "The next step is Part 2C: contextual review, domain verification, label decisions and supported-class selection. A complete pass means all outcomes are accounted for, not that all 100 species yielded images or are fit for training."]
    (ROOT / "docs/part-2ab-results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    plan = ROOT / "plan.md"
    text = plan.read_text(encoding="utf-8")
    for section, end in [("### Part 2A", "### Part 2B"), ("### Part 2B", "### Part 2C")]:
        left, right = text.index(section), text.index(end)
        text = text[:left] + text[left:right].replace("- [ ]", "- [x]") + text[right:]
    text = text.replace("**Active phase: Part 2A — batch collection for the full research queue.**", "**Active phase: Part 2C — review and class selection. Parts 2A/2B collection and technical organization are complete; unresolved evidence is held in the curation queue.**")
    text = text.replace("Status: In progress at Part 2A.", "Status: Parts 2A/2B complete with explicit holds; Part 2C pending.")
    text = text.replace("- [ ] Finish the bounded pass across all 100 queue entries, including documented unresolved names and source failures.", "- [x] Finish the bounded pass across all 100 queue entries, including documented unresolved names and source failures.")
    text += f"\n| 2026-10-23 | Parts 2A/2B | Full 100-entry pass reconciled: {audit['batch_records']} records across {audit['batch_species_with_images']} species folders; integrity/provenance, grouping and routing reports generated | See docs/part-2ab-results.md. Labels and unresolved ecological/geographic evidence require Part 2C review. |\n"
    plan.write_text(text, encoding="utf-8")
    STATE.write_text(json.dumps({"status": "parts_2a_2b_complete_with_explicit_review_holds", "results": "docs/part-2ab-results.md", "next": "Part 2C: review and class selection"}, indent=2), encoding="utf-8")
    print("Final audit and plan reconciliation complete", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        STATE.write_text(json.dumps({"status": "finalization_failed", "error": str(exc), "completion_claimed": False}, indent=2), encoding="utf-8")
        raise
