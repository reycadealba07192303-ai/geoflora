"""Build a review-only gallery for licensed Mikania photos outside the approved gallery."""
from __future__ import annotations

import csv
import argparse
import hashlib
import html
import json
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/ml/src"))
from geoflora_ml.collection.licensing import normalize_license

STAGING = ROOT / "storage/datasets/staging"
APPROVED_GALLERY = STAGING / "invasive_mikania_micrantha_ph"
SUPPLEMENT = STAGING / "mikania_micrantha_ph"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner-approved", action="store_true", help="record owner approval of all supplemental gallery photos")
    args = parser.parse_args()
    with (APPROVED_GALLERY / "review_queue.csv").open(encoding="utf-8", newline="") as stream:
        approved_rows = list(csv.DictReader(stream))
    known_hashes = {row["sha256"] for row in approved_rows}

    with (SUPPLEMENT / "review_queue.csv").open(encoding="utf-8", newline="") as stream:
        candidates = list(csv.DictReader(stream))

    rows = []
    for row in candidates:
        if row["sha256"] in known_hashes:
            continue
        if row.get("country_code") != "PH" or not normalize_license(row.get("license")):
            continue
        if row.get("license") != "cc0" and not row.get("attribution", "").strip():
            continue
        image = (SUPPLEMENT / row["local_path"]).resolve()
        if not image.is_relative_to(SUPPLEMENT.resolve()) or not image.is_file():
            raise ValueError(f"Unsafe or missing staged photo: {row['source_id']}")
        if hashlib.sha256(image.read_bytes()).hexdigest() != row["sha256"]:
            raise ValueError(f"Staged photo checksum mismatch: {row['source_id']}")
        rows.append({**row,
                     "owner_photo_review": "approved" if args.owner_approved else "pending",
                     "review_status": "owner_gallery_approved" if args.owner_approved else "pending",
                     "reviewer": "owner" if args.owner_approved else "",
                     "review_rationale": "Owner confirmed these 30 supplemental Mikania photos on 2026-10-31" if args.owner_approved else ""})

    queue = APPROVED_GALLERY / "supplemental_review_queue.csv"
    fields = sorted(set().union(*(row.keys() for row in rows))) if rows else ["source", "source_id", "sha256"]
    with queue.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    cards = []
    for row in rows:
        image_url = "../mikania_micrantha_ph/" + quote(row["local_path"], safe="/")
        source_url = html.escape(row["source_url"], quote=True)
        cards.append(
            f'<article><a href="{image_url}"><img loading="lazy" src="{image_url}" alt="Mikania candidate photo"></a>'
            f'<h2>{html.escape(row.get("scientific_name", "Mikania micrantha"))}</h2>'
            f'<p>{"Owner approved as Mikania candidate" if args.owner_approved else "Pending owner photo review"} · {html.escape(row["license"])} · {html.escape(row.get("attribution", ""))}</p>'
            f'<p>{html.escape(row.get("locality", ""))}<br>Group: {html.escape(row.get("group_id", ""))}</p>'
            f'<a href="{source_url}" target="_blank" rel="noopener noreferrer">Source record</a></article>'
        )
    page = '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
    page += '<title>Mikania supplemental review</title><style>body{font:16px system-ui;margin:24px;background:#eef1ea;color:#10291d}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px}article{background:white;padding:12px;border-radius:16px;overflow-wrap:anywhere}img{width:100%;height:230px;object-fit:contain}h2{font-size:16px}p{font-size:12px;color:#56645a}</style>'
    page += f'<h1>Mikania micrantha: {len(rows)} supplemental candidates</h1>'
    page += ('<p>Owner approved these CC0/CC BY photos as Mikania candidates. Source identifications remain community-sourced, and near-duplicate groups are kept together when splitting.</p>' if args.owner_approved else '<p>These CC0/CC BY images are not in the gallery already approved by the owner. They are pending photo review and are not included in training yet. Review duplicates, visible plant identity, and source context.</p>')
    page += '<main>' + "".join(cards) + '</main></html>'
    (APPROVED_GALLERY / "supplemental_review_gallery.html").write_text(page, encoding="utf-8")

    report = {
        "species": "Mikania micrantha",
        "images": len(rows),
        "source_groups": len({row["group_id"] for row in rows}),
        "licenses": dict(Counter(row["license"] for row in rows)),
        "owner_photo_review": "approved" if args.owner_approved else "pending",
        "owner_approval_date": "2026-10-31" if args.owner_approved else None,
        "overlap_rule": "Exact SHA-256 checksums already in the owner-approved invasive Mikania gallery were excluded.",
        "queue": queue.relative_to(ROOT).as_posix(),
        "gallery": (APPROVED_GALLERY / "supplemental_review_gallery.html").relative_to(ROOT).as_posix(),
    }
    report_path = ROOT / "docs/mikania-supplemental-review-evidence.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
