"""Collect bounded PH Mikania candidates outside the active ML corpus."""
import csv
import hashlib
import json
import logging
from html import escape
from urllib.parse import quote
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from geoflora_ml.collection.gbif import GBIFSource
from geoflora_ml.collection.inaturalist import INaturalistSource
from geoflora_ml.collection.licensing import normalize_license
from geoflora_ml.collection.runner import collect_candidates, image_storage_bytes
from geoflora_ml.config import Species
from geoflora_ml.datasets.duplicates import group_near_duplicates
from geoflora_ml.datasets.manifest import read_jsonl
from geoflora_ml.datasets.review_service import _safe_image_path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "storage/datasets/staging/mikania_micrantha_ph"


def render_gallery():
    """Local read-only report; decisions remain in the separate review workflow."""
    with (DATA / "review_queue.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    cards = []
    for row in rows:
        image = quote(row["local_path"], safe="/")
        source = escape(row["source_url"], quote=True)
        cards.append(f'<article><a href="{image}"><img loading="lazy" src="{image}" alt="Unverified Mikania candidate"></a>'
                     f'<h2>{escape(row["source"])}: {escape(row["source_id"])}</h2>'
                     f'<p>Pending review | {escape(row["license"])} | {escape(row["attribution"])}</p>'
                     f'<p>Observation: {escape(row["group_id"])}<br>Similarity group: {escape(row["near_duplicate_group_id"])}</p>'
                     f'<p>{escape(row["locality"])} | Source country: {escape(row["country_code"])}</p>'
                     f'<a href="{source}" target="_blank" rel="noopener noreferrer">Source observation</a></article>')
    page = '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
    page += '<title>Mikania staging review</title><style>body{font-family:system-ui;margin:24px;background:#f4f6f3;color:#183029}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px}article{background:white;padding:16px;border:1px solid #bcc9be;border-radius:8px;overflow-wrap:anywhere}img{width:100%;height:260px;object-fit:contain}h2{font-size:16px}</style>'
    page += f'<h1>Mikania micrantha: {len(rows)} staging candidates</h1><p>Read-only visual review report. All labels are pending; this page does not save decisions. Open images at full size and compare source observations, field/herbarium context and duplicate groups. No model support is enabled.</p><main>'
    (DATA / "review_gallery.html").write_text(page + ''.join(cards) + '</main></html>', encoding="utf-8")


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    DATA.mkdir(parents=True, exist_ok=True)
    original = ROOT / "storage/datasets/raw/manifest.jsonl"
    original_hash = hashlib.sha256(original.read_bytes()).hexdigest()
    manifest = DATA / "raw/manifest.jsonl"
    before = read_jsonl(manifest) if manifest.exists() else []
    initial_bytes = image_storage_bytes(DATA)
    report = {"started_at_utc": datetime.now(timezone.utc).isoformat(),
              "species": "Mikania micrantha", "country_filter": "PH", "status": "pending_review",
              "bounds": {"new_unique_images_per_source": 50, "api_pages_per_source": 3, "additional_gb": 0.1},
              "label_evidence": "Source labels only; not visually verified", "sources": []}
    species = Species("mikania_micrantha", "Mikania micrantha", "Mile-a-minute")
    report_path = ROOT / "docs/mikania-staging-evidence.json"
    try:
        for name, source in [("inaturalist", INaturalistSource(max_retries=1)), ("gbif", GBIFSource(max_retries=1))]:
            logging.info("Collecting Mikania from %s", name)
            result = {"source": name}
            try:
                count, rejected = collect_candidates(
                    source.candidates(species, limit=None, pages=3), DATA,
                    max_images=50, source_name=name,
                    max_storage_bytes=initial_bytes + int(0.1 * 1024**3),
                    minimum_interval=source.client.minimum_interval, max_retries=1,
                )
                result.update(status="completed", new_unique_images=count, download_rejections=rejected)
            except Exception as exc:
                logging.exception("Source failed")
                result.update(status="failed", error=str(exc))
            report["sources"].append(result)
            report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    finally:
        rows = read_jsonl(manifest) if manifest.exists() else []
        valid, invalid = [], []
        for row in rows:
            issues = []
            if _safe_image_path(row, DATA.resolve()) is None:
                issues.append("image_integrity_failed")
            if not normalize_license(row.get("license")) or not row.get("attribution"):
                issues.append("rights_metadata_ineligible")
            if row.get("country_code") != "PH":
                issues.append("country_unresolved")
            if not row.get("source_url") or not row.get("group_id"):
                issues.append("missing_provenance")
            if issues:
                invalid.append({"source": row["source"], "source_id": row["source_id"], "issues": issues})
            else:
                valid.append(row)
        grouped, near_groups = group_near_duplicates(valid, DATA) if valid else ([], [])
        fields = ["species_id", "source", "source_id", "source_url", "license", "attribution", "country_code", "locality", "observed_at", "group_id", "near_duplicate_group_id", "sha256", "local_path", "review_status"]
        with (DATA / "review_queue.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows({**row, "review_status": "pending"} for row in grouped)
        render_gallery()
        current_hash = hashlib.sha256(original.read_bytes()).hexdigest()
        assert current_hash == original_hash, "Active raw manifest changed during staging run"
        report.update(
            finished_at_utc=datetime.now(timezone.utc).isoformat(), before_records=len(before), total_records=len(rows),
            new_records=len(rows) - len(before), valid_records=len(valid), invalid_records=invalid,
            unique_checksums=len({r["sha256"] for r in valid}),
            stored_observation_groups=len({r["group_id"] for r in valid}),
            near_duplicate_groups=len(near_groups), source_counts=dict(Counter(r["source"] for r in rows)),
            additional_image_bytes=image_storage_bytes(DATA)-initial_bytes,
            active_manifest_unchanged=True, active_manifest_sha256=current_hash,
            review_queue=str((DATA / "review_queue.csv").relative_to(ROOT)),
            note="Stored source groups are not cross-provider independent counts. No labels approved, no training, no active classes changed.",
        )
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
