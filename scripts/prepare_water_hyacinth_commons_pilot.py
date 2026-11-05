"""Create a rights-screened Commons manual-review queue (no label approval)."""
from __future__ import annotations

import csv
import hashlib
import html
import re
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "storage/datasets/staging/water_hyacinth_commons_pilot_20261101"
ALLOWED = {"CC0", "CC BY 2.0", "CC BY-SA 3.0", "CC BY-SA 4.0"}


def clean(value: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", value or "")).replace("\xa0", " ").strip()


def api(session: requests.Session, params: dict) -> dict:
    response = session.get("https://commons.wikimedia.org/w/api.php", params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers["User-Agent"] = "GeoFloraDatasetAudit/1.0 (manual dataset review)"
    listing = api(session, {"action": "query", "generator": "categorymembers", "gcmtitle": "Category:Pontederia crassipes in the Philippines", "gcmtype": "file", "gcmlimit": 500, "format": "json"})
    titles = [page["title"] for page in listing.get("query", {}).get("pages", {}).values()]
    pages = []
    for offset in range(0, len(titles), 40):
        result = api(session, {"action": "query", "titles": "|".join(titles[offset:offset + 40]), "prop": "imageinfo", "iiprop": "url|size|extmetadata|user|timestamp", "iiurlwidth": 640, "format": "json"})
        pages.extend(page for page in result.get("query", {}).get("pages", {}).values() if page.get("imageinfo"))

    eligible = []
    license_counts: dict[str, int] = {}
    for page in pages:
        info = page["imageinfo"][0]
        meta = info.get("extmetadata", {})
        license_name = clean(meta.get("LicenseShortName", {}).get("value", ""))
        license_counts[license_name] = license_counts.get(license_name, 0) + 1
        if license_name not in ALLOWED:
            continue
        eligible.append((page, info, meta, license_name))

    # Conservatively select one file per Commons title series/location sequence.
    # These are only candidate groups; a reviewer must confirm observation identity.
    patterns = [
        r"09060jfPulilan Riverbanks Dampol 4 ",
        r"2Victoria, Laguna Roads Barangays 21\.jpg$",
        r"9924Photos taken during 2020 coronavirus pandemic Meycauayan, Bulacan 03\.jpg$",
        r"Eichhornia crassipes by Netan\.jpg$",
        r"Eichhornia crassipes in the Philippines\.jpg$",
        r"Flowering Pontederia crassipes Mart\. in the Philippines\.jpg$",
        r"FvfApalitBC0177 11\.JPG$",
        r"FvfMexicoPmpanga1575 24\.JPG$",
        r"FvfSanMiguelCal9619 01\.JPG$",
        r"JfWaterLily0122Philippinesfvf 01\.JPG$",
        r"Mainit Water Lily\.jpg$",
        r"SMiguel,Calumpit,Bulacan9602 11\.JPG$",
        r"Typhoon Khanun \(2023\).* E911a 07\.jpg$",
        r"Xyz waterplant in the philippines 2\.jpg$",
    ]
    selected = []
    for pattern in patterns:
        matches = [entry for entry in eligible if re.search(pattern, entry[0]["title"].removeprefix("File:"), re.I)]
        if matches:
            selected.append(matches[0])

    rows = []
    for index, (page, info, meta, license_name) in enumerate(selected, 1):
        title = page["title"]
        filename = re.sub(r"[^A-Za-z0-9._-]+", "_", title.removeprefix("File:"))
        image_path = OUT / filename
        thumb = info.get("thumburl")
        error = ""
        if thumb and not image_path.exists():
            try:
                response = session.get(thumb, timeout=30)
                response.raise_for_status()
                image_path.write_bytes(response.content)
            except Exception as exc:  # retain metadata row even if a preview fails
                error = str(exc)
        artist = clean(meta.get("Artist", {}).get("value", ""))
        rows.append({
            "candidate_id": f"WHC-{index:03d}",
            "source": "Wikimedia Commons",
            "source_id": title,
            "source_url": info.get("descriptionurl", ""),
            "photographer_attribution": artist,
            "license": license_name,
            "license_url": clean(meta.get("LicenseUrl", {}).get("value", "")),
            "attribution_required": "yes" if license_name != "CC0" else "no (credit retained)",
            "source_description": clean(meta.get("ImageDescription", {}).get("value", "")),
            "source_date": clean(meta.get("DateTime", {}).get("value", "")),
            "uploader": info.get("user", ""),
            "gps_lat": clean(meta.get("GPSLatitude", {}).get("value", "")),
            "gps_lon": clean(meta.get("GPSLongitude", {}).get("value", "")),
            "candidate_group": "pending manual grouping",
            "preview_file": image_path.name if image_path.exists() else "",
            "preview_sha256": hashlib.sha256(image_path.read_bytes()).hexdigest() if image_path.exists() else "",
            "species_label_review": "pending; not approved",
            "philippine_provenance_review": "pending; not approved",
            "field_photo_review": "pending",
            "independent_observation_review": "pending",
            "duplicate_review_against_v3": "pending",
            "download_error": error,
        })
        print(f"preview {index}/{len(selected)} {title}", flush=True)

    fields = list(rows[0]) if rows else []
    with (OUT / "review_queue.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    with (OUT / "commons_license_counts.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["license", "file_count", "pilot_decision"])
        for name, count in sorted(license_counts.items()):
            writer.writerow([name or "missing", count, "eligible under current policy" if name in ALLOWED else "excluded; do not infer permission"])
    print(f"category_files={len(pages)} eligible_files={len(eligible)} selected_candidate_series={len(rows)} licenses={license_counts}", flush=True)


if __name__ == "__main__":
    main()
