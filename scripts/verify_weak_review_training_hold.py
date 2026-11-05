"""Assert weak-class candidates stay outside the automatic training exporter."""
import csv,sys
from pathlib import Path
from collections import Counter

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from auto_training_worker import approved_staging, manually_reviewed_staging_row
from geoflora_ml.collection.licensing import training_license_eligible

def read_csv(path):
    with path.open(encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))

def main():
    queue=read_csv(ROOT/"docs/weak-class-manual-review-queue-2026-11-01.csv")
    candidate_hashes={r["sha256"] for r in queue}
    exported,_=approved_staging()
    overlap=candidate_hashes & {r["sha256"] for r in exported}
    bad=[r for r in exported if not training_license_eligible(r.get("license"),r.get("attribution"))]
    queues=[]
    for path in (ROOT/"storage/datasets/staging").glob("*_ph/review_queue.csv"):
        queues.extend(read_csv(path))
    unreviewed_hashes={r.get("sha256") for r in queues if not manually_reviewed_staging_row(r)}
    unreviewed_exported=unreviewed_hashes & {r["sha256"] for r in exported}
    assert not overlap, f"Pending review candidates reached exporter: {len(overlap)}"
    assert not bad, f"Training exporter returned license-ineligible photos: {len(bad)}"
    assert not unreviewed_exported, f"Unverified staging images reached exporter: {len(unreviewed_exported)}"
    print({"passed":True,"weak_candidates_pending":len(candidate_hashes),"pending_candidates_exported":len(overlap),"unreviewed_or_rejected_staging_exported":len(unreviewed_exported),"license_ineligible_exported":len(bad),"currently_eligible_staging_export_count":len(exported),"exported_license_counts":dict(Counter(r["license"] for r in exported))})

if __name__=="__main__":main()
