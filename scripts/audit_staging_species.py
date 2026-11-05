"""Read-only integrity and provenance audit for the three active-species staging queues."""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from geoflora_ml.collection.licensing import normalize_license

ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / "storage/datasets/staging"
OUTPUT = ROOT / "docs/staging-quality-audit-2026-10-31.json"
GROUPS = {
    "chromolaena_odorata": "invasive_chromolaena_odorata_ph",
    "lantana_camara": "invasive_lantana_camara_ph",
    "pontederia_crassipes": "invasive_pontederia_crassipes_ph",
}


def audit_class(species_id: str, folder_name: str) -> dict:
    folder = STAGING / folder_name
    with (folder / "review_queue.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    issues: list[dict] = []
    exact: dict[str, list[str]] = {}
    for row in rows:
        key = f"{row.get('source')}:{row.get('source_id')}"
        sha = row.get("sha256", "")
        exact.setdefault(sha, []).append(key)
        path = (folder / row.get("local_path", "")).resolve()
        try:
            if not path.is_relative_to(folder.resolve()) or not path.is_file():
                raise ValueError("unsafe_or_missing_file")
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != sha:
                raise ValueError("checksum_mismatch")
            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                width, height = image.size
        except (OSError, ValueError) as error:
            issues.append({"record": key, "issue": str(error) or type(error).__name__})
            continue
        checks = {
            "wrong_species_id": row.get("species_id") != species_id,
            "country_not_ph": row.get("country_code") != "PH",
            "missing_locality": not row.get("locality", "").strip(),
            "missing_observation_date": not row.get("observed_at", "").strip(),
            "missing_source_url": not row.get("source_url", "").startswith("https://"),
            "missing_attribution": not row.get("attribution", "").strip(),
            "ineligible_license": not bool(normalize_license(row.get("license"), allow_noncommercial=True)),
            "missing_group_id": not row.get("group_id", "").strip(),
        }
        issues.extend({"record": key, "issue": name} for name, failed in checks.items() if failed)
        if width < 224 or height < 224:
            issues.append({"record": key, "issue": "below_224px", "dimensions": [width, height]})
    duplicates = {sha: keys for sha, keys in exact.items() if sha and len(keys) > 1}
    for sha, keys in duplicates.items():
        issues.extend({"record": key, "issue": "exact_duplicate_group_member", "sha256": sha} for key in keys)
    near_members: dict[str, set[str]] = {}
    for row in rows:
        group_id = row.get("near_duplicate_group_id", "")
        if group_id.startswith("near-duplicate:"):
            near_members.setdefault(group_id, set()).add(row.get("sha256", ""))
    return {
        "species_id": species_id,
        "images": len(rows),
        "observation_groups": len({row.get("group_id") for row in rows if row.get("group_id")}),
        "near_duplicate_groups": sum(len(hashes) > 1 for hashes in near_members.values()),
        "exact_duplicate_groups": duplicates,
        "review_status_counts": dict(Counter(row.get("review_status", "") for row in rows)),
        "source_counts": dict(Counter(row.get("source", "") for row in rows)),
        "issue_counts": dict(Counter(row["issue"] for row in issues)),
        "issues": issues,
    }


def main() -> None:
    classes = {species: audit_class(species, folder) for species, folder in GROUPS.items()}
    result = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Read-only integrity, metadata, source, and resolution checks for staging queues; does not verify visible taxonomic identity or field-photo suitability.",
        "classes": classes,
    }
    OUTPUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({species: {k: value[k] for k in ("images", "observation_groups", "near_duplicate_groups", "issue_counts", "review_status_counts")} for species, value in classes.items()}, indent=2))
    print("Report:", OUTPUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
