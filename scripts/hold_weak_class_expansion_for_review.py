"""Move newly collected weak-class records to pending until a person reviews them."""
import csv, json
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
QUEUE=ROOT/"docs/weak-class-manual-review-queue-2026-11-01.csv"
GROUPS={"mikania_micrantha":"invasive_mikania_micrantha_ph","coccinia_grandis":"invasive_coccinia_grandis_ph","broussonetia_papyrifera":"invasive_broussonetia_papyrifera_ph"}
AUDIT=ROOT/"docs/weak-class-review-status-changes-2026-11-01.json"

def main():
    with QUEUE.open(encoding="utf-8-sig",newline="") as f: requested={r["sha256"]:r for r in csv.DictReader(f)}
    changed=[]
    for species,folder_name in GROUPS.items():
        path=ROOT/"storage/datasets/staging"/folder_name/"review_queue.csv"
        if not path.exists(): continue
        with path.open(encoding="utf-8-sig",newline="") as f: reader=csv.DictReader(f); fields=reader.fieldnames; rows=list(reader)
        dirty=False
        for row in rows:
            candidate=requested.get(row.get("sha256",""))
            if candidate and row.get("review_status")=="research_grade":
                previous=row["review_status"]
                row.update(review_status="pending",reviewer="",review_rationale="Targeted expansion; awaiting manual visual, field-photo and provenance review before training.")
                changed.append({"species_id":species,"sha256":row["sha256"],"source_id":row["source_id"],"group_id":row["group_id"],"previous_status":previous,"new_status":"pending"})
                dirty=True
        if dirty:
            with path.open("w",encoding="utf-8-sig",newline="") as f: writer=csv.DictWriter(f,fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    result={"generated_at_utc":datetime.now(timezone.utc).isoformat(),"purpose":"Prevent newly collected weak-class candidates from entering automatic training before human review.","changed_count":len(changed),"changes":changed}
    AUDIT.write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps({"changed_count":len(changed),"by_class":{species:sum(x["species_id"]==species for x in changed) for species in GROUPS}},indent=2))

if __name__=="__main__":main()
