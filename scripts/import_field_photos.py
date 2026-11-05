"""Import the owner's own field photos of a look-alike plant into its staging queue (pending the AI screen).

The owner attests that they took the photos in the Philippines and that they show the group's plant. Photos are
converted to JPEG, de-duplicated by checksum and by near-duplicate grouping, and added to
storage/datasets/staging/<role>_<group>_ph/review_queue.csv as pending. Run scripts/screen_staging_photos.py next;
approved photos are picked up by the automatic training worker.

Usage: python scripts/import_field_photos.py <group> C:/path/to/photos --photographer "Your name" --attest
"""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path

from PIL import Image, ImageOps
from geoflora_ml.datasets.duplicates import group_near_duplicates

ROOT = Path(__file__).resolve().parents[1]
SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def taken_at(image):
    exif = image.getexif()
    value = exif.get_ifd(0x8769).get(0x9003) or exif.get(0x0132)  # DateTimeOriginal, else DateTime
    return str(value).replace(":", "-", 2).replace(" ", "T") if value else ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("group")
    parser.add_argument("folder", type=Path)
    parser.add_argument("--photographer", required=True)
    parser.add_argument("--attest", action="store_true", help="I took these photos in the Philippines and they show this group's plant")
    args = parser.parse_args()
    if not args.attest:
        raise SystemExit("Add --attest to confirm you took these photos in the Philippines and that they show this plant.")
    data = next((ROOT / "storage/datasets/staging").glob(f"*_{args.group}_ph"), None)
    if data is None:
        raise SystemExit(f"No staging group {args.group}; collect it first with scripts/collect_staging_photos.py")
    group = json.loads((data / "group.json").read_text(encoding="utf-8"))
    queue = data / "review_queue.csv"
    with queue.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        fields, rows = reader.fieldnames, list(reader)
    known = {row["sha256"] for row in rows}
    folder = data / "raw/owner"
    folder.mkdir(parents=True, exist_ok=True)
    added, skipped = [], []
    for path in sorted(p for p in args.folder.iterdir() if p.suffix.lower() in SUFFIXES):
        try:
            with Image.open(path) as image:
                when = taken_at(image)
                image = ImageOps.exif_transpose(image).convert("RGB")
                if min(image.size) < 224:
                    skipped.append((path.name, "smaller than 224 px")); continue
                buffer = io.BytesIO()
                image.save(buffer, "JPEG", quality=92)
        except OSError as error:
            skipped.append((path.name, f"not a readable image: {error}")); continue
        sha = hashlib.sha256(buffer.getvalue()).hexdigest()
        if sha in known:
            skipped.append((path.name, "already imported")); continue
        local = f"raw/owner/{sha}.jpg"
        (data / local).write_bytes(buffer.getvalue())
        known.add(sha)
        added.append({"species_id": group["id"], "scientific_name": group["scientific_name"], "common_name": group["common_name"], "source": "owner_field_photo", "source_id": sha[:16], "source_url": "",
                      "license": "owner_own_photo", "attribution": args.photographer, "country_code": "PH", "locality": "", "observed_at": when, "group_id": f"owner:{sha[:16]}",
                      "sha256": sha, "local_path": local, "role": group["role"], "review_status": "pending", "reviewer": "", "review_rationale": f"Owner attested: taken by {args.photographer} in the Philippines"})
    if added:
        # Group the new photos with everything already queued so near-identical shots never split across train/test.
        grouped, _ = group_near_duplicates(rows + added, data)
        with queue.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(grouped)
    print(json.dumps({"added": len(added), "skipped": skipped, "next": f"python scripts/screen_staging_photos.py {args.group}"}, indent=2))


if __name__ == "__main__":
    main()
