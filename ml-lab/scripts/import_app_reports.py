"""Add photos from GeoFlora app reports to the lab dataset, so the next training run learns from them.

A report is imported when an administrator approved or corrected it in the app (status "verified",
trainingCandidateStatus "approved") and the contributor allowed training use. The app marks a report for training only
when the AI did not get it right (not sure, disputed by the contributor, or corrected by the administrator). The
administrator's species becomes the label (review_status "approved", reviewer = that administrator). Reports whose
species is not in the lab catalog stay in the app until the species is added to the catalog.

  python scripts/import_app_reports.py                # import into the manifest and dataset/raw/
  python scripts/import_app_reports.py --dry-run      # show what would be imported
The Mongo URI comes from --mongo-uri, GEOFLORA_MONGODB_URI, or mongodb://127.0.0.1:27017/geoflora.
"""
import io
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from _common import parser, setup


def main():
    p = parser(__doc__)
    p.add_argument("--mongo-uri", default=os.environ.get("GEOFLORA_MONGODB_URI", "mongodb://127.0.0.1:27017/geoflora"))
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    cfg = setup(args)
    from PIL import Image
    from pymongo import MongoClient
    from geoflora_ml.catalog import by_name, load_catalog
    from geoflora_ml.config import project_path, project_root
    from geoflora_ml.imaging import inspect_image, quality_flags, save_normalized_jpeg
    from geoflora_ml.manifest import append_rows, load_manifest, save_manifest
    from geoflora_ml.utils import rel_to_root, sha256_file, species_folder_name

    root = project_root(cfg)
    client = MongoClient(args.mongo_uri, serverSelectionTimeoutMS=8000)
    db = client.get_default_database()
    sightings = db["sightings"]
    names = {key.lower(): sp for key, sp in by_name(load_catalog(project_path(cfg, "species_catalog"))).items()}
    manifest_path = project_path(cfg, "image_manifest")
    manifest = load_manifest(manifest_path)
    have = set(manifest["image_id"])
    query = {"status": "verified", "trainingConsent": True, "trainingCandidateStatus": "approved", "labImport": {"$exists": False}}
    rows, done, skipped = [], [], []
    for report in sightings.find(query).sort("_id", 1):
        rid = str(report["_id"])
        image_id = f"app-{rid}"
        name = (report.get("verifiedScientificName") or "").strip()
        sp = names.get(name.lower()) or names.get(" ".join(name.split()[:2]).lower())
        if sp is None:
            skipped.append((rid, name or "?", "species not in the lab catalog yet"))
            continue
        if image_id in have or not report.get("photo"):
            skipped.append((rid, name, "already imported" if image_id in have else "photo missing"))
            continue
        review = (report.get("reviewHistory") or [{}])[-1]
        target = root / "dataset" / "raw" / species_folder_name(sp.scientific_name) / f"{image_id}.jpg"
        if not args.dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_suffix(".src")
            Image.open(io.BytesIO(bytes(report["photo"]))).save(tmp, format="JPEG", quality=95)
            save_normalized_jpeg(tmp, target)
            tmp.unlink(missing_ok=True)
            info = inspect_image(target)
            flags = quality_flags(info, cfg["validation"])
        else:
            info, flags = None, []
        predicted = ((report.get("prediction") or {}).get("species") or {}).get("scientific_name") or "not sure"
        observed = report.get("observedAt")
        rows.append({
            "image_id": image_id, "species_id": sp.species_id, "scientific_name": sp.scientific_name,
            "accepted_taxon_key": str(sp.gbif_taxon_key or ""), "verbatim_scientific_name": name, "ecological_role": sp.role,
            "source": "GeoFlora app", "source_dataset_key": "geoflora-app-reports", "source_dataset_name": "GeoFlora field reports",
            "publisher": "GeoFlora", "observation_id": f"geoflora:{rid}", "occurrence_id": rid,
            "license_raw": "GeoFlora contributor training consent", "license": "GEOFLORA-CONTRIBUTOR",
            "attribution": "GeoFlora contributor (training use allowed in the app)", "basis_of_record": "HUMAN_OBSERVATION",
            "country_code": "PH", "event_date": observed.isoformat() if hasattr(observed, "isoformat") else str(observed or ""),
            "recorded_by": f"geoflora-user-{str(report.get('ownerId') or '')[-6:]}",
            "download_timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "is_geoflora_field_observation": "true",
            "local_path": rel_to_root(target, root), "file_sha256": "" if args.dry_run else sha256_file(target),
            "phash": info.phash if info else "", "width": str(info.width) if info else "", "height": str(info.height) if info else "",
            "file_bytes": str(target.stat().st_size) if not args.dry_run else "", "image_format": "jpg",
            "readable": "true" if (info is None or info.readable) else "false", "quality_flags": ";".join(flags),
            "quality_pass": "false" if flags else "true", "license_eligible": "true",
            "observation_group": f"grp-app-{rid[-10:]}", "label_conflict": "false",
            "review_status": "approved", "reviewer": review.get("reviewer") or "GeoFlora administrator",
            "review_date": (review.get("reviewedAt") or datetime.now(timezone.utc)).strftime("%Y-%m-%d") if hasattr(review.get("reviewedAt"), "strftime") else datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "review_notes": f"GeoFlora admin {'corrected' if review.get('action') == 'correct_identification' else 'approved'} this report (AI said: {predicted}). {review.get('rationale') or ''}".strip(),
            "split": "",
        })
        done.append((rid, sp.scientific_name))
    if rows and not args.dry_run:
        save_manifest(append_rows(manifest, rows), manifest_path)
        now = datetime.now(timezone.utc)
        for rid, _ in done:
            from bson import ObjectId
            sightings.update_one({"_id": ObjectId(rid)}, {"$set": {"labImport": {"imageId": f"app-{rid}", "importedAt": now}, "trainingJobId": "ml-lab"}})
    print(f"{'Would import' if args.dry_run else 'Imported'} {len(done)} report photo(s); skipped {len(skipped)}.")
    for rid, name in done:
        print(f"  + {rid}  {name}")
    for rid, name, why in skipped:
        print(f"  - {rid}  {name}: {why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
