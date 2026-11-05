"""Restore license-filtered rows from raw manifests without making them trainable."""
import csv,json
from pathlib import Path
from geoflora_ml.collection.licensing import normalize_license
from geoflora_ml.datasets.duplicates import group_near_duplicates
from collect_staging_photos import QUEUE_FIELDS,render_gallery

ROOT=Path(__file__).resolve().parents[1]
GROUPS={"mikania_micrantha":"invasive_mikania_micrantha_ph","coccinia_grandis":"invasive_coccinia_grandis_ph","broussonetia_papyrifera":"invasive_broussonetia_papyrifera_ph"}

def main():
    summary={}
    for species,folder_name in GROUPS.items():
        folder=ROOT/"storage/datasets/staging"/folder_name
        manifest=folder/"raw/manifest.jsonl"; queue=folder/"review_queue.csv"
        if not manifest.exists(): continue
        raw=[json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines() if line.strip()]
        current={}
        if queue.exists():
            with queue.open(encoding="utf-8-sig",newline="") as f: current={r.get("sha256"):r for r in csv.DictReader(f)}
        rows=[]
        for r in raw:
            old=current.get(r.get("sha256"),{})
            eligible=normalize_license(r.get("license")) is not None and (r.get("license")=="cc0" or bool(r.get("attribution"," ").strip()))
            row={**r,"role":"invasive","training_license_eligible":"yes" if eligible else "no","review_status":old.get("review_status","pending"),"reviewer":old.get("reviewer",""),"review_rationale":old.get("review_rationale","")}
            if not eligible and row["review_status"] in {"research_grade","owner_gallery_approved","approved"}:
                row.update(review_status="pending",reviewer="",review_rationale="License is outside the collector's active training allowlist; retained for rights and human review.")
            rows.append(row)
        grouped,_=group_near_duplicates(rows,folder)
        with queue.open("w",encoding="utf-8-sig",newline="") as f:
            writer=csv.DictWriter(f,fieldnames=QUEUE_FIELDS,extrasaction="ignore");writer.writeheader();writer.writerows(grouped)
        meta=json.loads((folder/"group.json").read_text(encoding="utf-8"))
        render_gallery(folder,meta.get("label",species))
        summary[species]={"raw_rows":len(raw),"restored_to_queue":len(rows)-len(current),"pending":sum(r["review_status"]=="pending" for r in grouped),"rights_allowlist_eligible":sum(r["training_license_eligible"]=="yes" for r in grouped)}
    print(json.dumps(summary,indent=2))

if __name__=="__main__":main()
