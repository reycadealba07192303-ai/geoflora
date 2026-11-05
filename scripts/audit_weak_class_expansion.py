"""Audit targeted weak-class staging against the frozen 11-class dataset.

Read-only: reports eligible metadata, exact/source-observation overlap, grouped
observation counts, and image decode/checksum status. It does not approve labels.
"""
import csv, hashlib, json
from collections import Counter, defaultdict
from pathlib import Path
from PIL import Image
from geoflora_ml.collection.licensing import normalize_license

ROOT = Path(__file__).resolve().parents[1]
FROZEN = ROOT / "storage/datasets/curated/auto_6ae5cd74af23d762feaa0889/manifest.csv"
OUT = ROOT / "docs/weak-class-expansion-audit-2026-11-01.json"
QUEUE = ROOT / "docs/weak-class-manual-review-queue-2026-11-01.csv"
CLASSES = {
    "mikania_micrantha": "invasive_mikania_micrantha_ph",
    "coccinia_grandis": "invasive_coccinia_grandis_ph",
    "broussonetia_papyrifera": "invasive_broussonetia_papyrifera_ph",
}

def read(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def obs_key(row):
    group = row.get("group_id", "") or row.get("observation_id", "")
    return group.split(":observation:")[-1] if ":observation:" in group else group

def main():
    frozen = read(FROZEN)
    frozen_by_class = defaultdict(list)
    review_rows = []
    for row in frozen:
        frozen_by_class[row.get("species_id", "")].append(row)
    result = {"scope": "Metadata/integrity/observation overlap only; research-grade/source-country evidence is not independent expert label or provenance verification.", "classes": {}}
    for species, folder_name in CLASSES.items():
        folder = ROOT / "storage/datasets/staging" / folder_name
        queues = [folder / "review_queue.csv"]
        supplemental = folder / "supplemental_review_queue.csv"
        if supplemental.exists(): queues.append(supplemental)
        rows = [r for p in queues if p.exists() for r in read(p)]
        target = frozen_by_class[species]
        hashes = {r.get("sha256", "") for r in target}
        groups = {obs_key(r) for r in target}
        valid, exact_dup, obs_dup, bad = [], [], [], []
        for row in rows:
            issues=[]
            image=(folder / row.get("local_path", "")).resolve()
            allowed_root=folder.resolve()
            if not image.is_file() and species == "mikania_micrantha":
                # Supplemental gallery files live in the legacy staging root.
                allowed_root=(ROOT / "storage/datasets/staging/mikania_micrantha_ph").resolve()
                image=(allowed_root / row.get("local_path", "")).resolve()
            try:
                if not image.is_relative_to(allowed_root) or not image.is_file(): raise ValueError("missing_or_unsafe")
                digest=hashlib.sha256(image.read_bytes()).hexdigest()
                if digest != row.get("sha256"): raise ValueError("checksum_mismatch")
                with Image.open(image) as im: im.verify()
            except Exception as e:
                issues.append(str(e))
            if row.get("country_code") != "PH": issues.append("country_not_PH")
            if not row.get("source_url") or not row.get("attribution"): issues.append("missing_provenance")
            if not normalize_license(row.get("license")): issues.append("license_not_in_active_training_allowlist")
            if issues:
                bad.append({"source_id": row.get("source_id"), "issues": issues}); continue
            if row.get("sha256") in hashes:
                exact_dup.append(row); continue
            if obs_key(row) in groups:
                obs_dup.append(row); continue
            valid.append(row)
            review_rows.append({"species_id": species, "source": row.get("source", ""), "source_id": row.get("source_id", ""), "group_id": obs_key(row), "source_url": row.get("source_url", ""), "country_code": row.get("country_code", ""), "locality": row.get("locality", ""), "observed_at": row.get("observed_at", ""), "local_image_path": image.relative_to(ROOT).as_posix(), "license": row.get("license", ""), "attribution": row.get("attribution", ""), "sha256": row.get("sha256", ""), "review_status_at_collection": row.get("review_status", ""), "required_human_checks": "visible species identity; field photo suitability; PH locality evidence; duplicate/observation independence", "decision": "pending_human_review", "rationale": ""})
        unique_groups=defaultdict(list)
        for row in valid: unique_groups[obs_key(row)].append(row)
        new_groups=[]
        for group, items in sorted(unique_groups.items()):
            new_groups.append({"group_id": group, "image_count": len(items), "licenses": sorted({r.get("license", "") for r in items}), "sources": sorted({r.get("source", "") for r in items}), "source_ids": [r.get("source_id", "") for r in items], "source_urls": [r.get("source_url", "") for r in items], "sha256": [r.get("sha256", "") for r in items], "review_status": sorted({r.get("review_status", "") for r in items})})
        result["classes"][species]={"staging_rows":len(rows),"staging_groups":len({obs_key(r) for r in rows if obs_key(r)}),"frozen_train_images":sum(r.get("split")=="train" for r in target),"frozen_train_groups":len({obs_key(r) for r in target if r.get("split")=="train"}),"valid_not_in_frozen_images":len(valid),"exact_duplicate_images_excluded":len(exact_dup),"same_observation_images_excluded":len(obs_dup),"integrity_or_metadata_issues":len(bad),"new_observation_groups_pending_review":new_groups,"new_group_count":len(new_groups),"new_image_count":len(valid),"license_counts":dict(Counter(r.get("license", "") for r in valid)),"status_counts":dict(Counter(r.get("review_status", "") for r in valid)),"issues_sample":bad[:20]}
    OUT.write_text(json.dumps(result,indent=2),encoding="utf-8")
    fields=list(review_rows[0]) if review_rows else ["species_id","source","source_id","group_id","source_url","license","attribution","sha256","review_status_at_collection","required_human_checks","decision","rationale"]
    with QUEUE.open("w",encoding="utf-8-sig",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=fields); writer.writeheader(); writer.writerows(review_rows)
    print(json.dumps({k:{x:v[x] for x in ("staging_rows","staging_groups","frozen_train_images","frozen_train_groups","valid_not_in_frozen_images","exact_duplicate_images_excluded","same_observation_images_excluded","integrity_or_metadata_issues","new_group_count","new_image_count","license_counts","status_counts")} for k,v in result["classes"].items()},indent=2))
    print("Wrote",OUT.relative_to(ROOT),"and",QUEUE.relative_to(ROOT))

if __name__ == "__main__": main()
