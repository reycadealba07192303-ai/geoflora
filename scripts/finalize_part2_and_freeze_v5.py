"""Finalize the documented Part 2 selection and freeze its Part 3 dataset.

The input is the preserved six-class v4 experiment.  This script deliberately
does *not* promote v4: Caladium bicolor is excluded because the project has no
adequate Philippine invasive-status evidence for it.  The resulting v5 is a
five-class, owner-attested *experimental* dataset.  It is reproducible and
auditable, but its limitations (especially the two small new classes) remain
part of the artifact rather than being hidden by a version number.

Run from the repository root:
  services/ml/.venv/Scripts/python.exe scripts/finalize_part2_and_freeze_v5.py
"""
from __future__ import annotations

import csv
import argparse
import hashlib
import json
import shutil
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from geoflora_ml.collection.licensing import normalize_license


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "storage" / "datasets"
SOURCE = DATA / "curated" / "v4_six_classes"
TARGET = DATA / "curated" / "v5_part2_final_five_classes"
DOCS = ROOT / "docs"

EXCLUDED_CLASS = "caladium_bicolor"
ECOLOGY_REFERENCES = {
    "chromolaena_odorata": "https://www.philchm.ph/wp-content/uploads/2019/03/NISSAP-Philippines-2016_final-draft.pdf",
    "lantana_camara": "https://www.cbd.int/doc/world/ph/ph-nr-04-en.pdf#page=23",
    "mikania_micrantha": "https://www.cbd.int/doc/world/ph/ph-nr-04-en.pdf#page=23",
    "pistia_stratiotes": "https://www.philippineplants.org/Families/Araceae.html",
    "pontederia_crassipes": "https://www.philchm.ph/wp-content/uploads/2019/03/NISSAP-Philippines-2016_final-draft.pdf",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(path)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def write_csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def validate(rows: list[dict[str, str]], class_ids: set[str]) -> dict[str, object]:
    if not rows or {row["species_id"] for row in rows} != class_ids:
        raise ValueError("The selected rows and class mapping disagree")
    seen_checksums: set[str] = set()
    partition_keys: dict[tuple[str, str], set[str]] = defaultdict(set)
    image_issues: list[str] = []
    for row in rows:
        photo = (ROOT / row["local_path"]).resolve()
        if not photo.is_relative_to(DATA.resolve()) or not photo.is_file():
            image_issues.append(f"unsafe or missing path: {row['local_path']}")
            continue
        if digest(photo) != row["sha256"]:
            image_issues.append(f"checksum mismatch: {row['local_path']}")
        try:
            with Image.open(photo) as image:
                image.verify()
        except (OSError, ValueError, Image.DecompressionBombError) as error:
            image_issues.append(f"unreadable image {row['local_path']}: {error}")
        if row["sha256"] in seen_checksums:
            image_issues.append(f"duplicate checksum: {row['sha256']}")
        seen_checksums.add(row["sha256"])
        if not normalize_license(row.get("license")) or not row.get("attribution"):
            image_issues.append(f"rights metadata incomplete: {row['local_path']}")
        for key in ("sha256", "group_id", "near_duplicate_group_id"):
            partition_keys[(key, row[key])].add(row["split"])
    leakage = {f"{kind}:{value}": sorted(splits) for (kind, value), splits in partition_keys.items() if len(splits) > 1}
    if image_issues or leakage:
        raise ValueError(json.dumps({"image_issues": image_issues, "cross_split_keys": leakage}, indent=2))
    per_class = {}
    for class_id in sorted(class_ids):
        class_rows = [row for row in rows if row["species_id"] == class_id]
        per_class[class_id] = {
            split: {
                "images": sum(row["split"] == split for row in class_rows),
                "independent_groups": len({row["group_id"] for row in class_rows if row["split"] == split}),
                "near_duplicate_groups": len({row["near_duplicate_group_id"] for row in class_rows if row["split"] == split}),
            }
            for split in ("train", "validation", "test")
        }
    return {
        "images": len(rows),
        "classes": len(class_ids),
        "unique_checksums": len(seen_checksums),
        "cross_split_keys": 0,
        "per_class": per_class,
        "source_counts": dict(sorted(Counter(row["source"] for row in rows).items())),
    }


def verify_existing() -> None:
    required = [
        "manifest.csv", "class_mapping.json", "species.yaml", "reviews_snapshot.json",
        "part2_decision_ledger.csv", "dataset_metadata.json", "checksums.json",
    ]
    if any(not (TARGET / name).is_file() for name in required):
        raise FileNotFoundError("v5 is incomplete")
    metadata = json.loads((TARGET / "dataset_metadata.json").read_text(encoding="utf-8"))
    if digest(TARGET / "manifest.csv") != metadata["manifest_sha256"]:
        raise ValueError("v5 manifest checksum mismatch")
    if digest(TARGET / "reviews_snapshot.json") != metadata["reviews_snapshot_sha256"]:
        raise ValueError("v5 review snapshot checksum mismatch")
    if digest(TARGET / "part2_decision_ledger.csv") != metadata["decision_ledger_sha256"]:
        raise ValueError("v5 decision ledger checksum mismatch")
    checksums = json.loads((TARGET / "checksums.json").read_text(encoding="utf-8"))
    mismatches = [name for name, expected in checksums.items() if not (TARGET / name).is_file() or digest(TARGET / name) != expected]
    if mismatches:
        raise ValueError(f"v5 artifact checksum mismatch: {mismatches}")
    classes = json.loads((TARGET / "class_mapping.json").read_text(encoding="utf-8"))["classes"]
    audit = validate(read_csv(TARGET / "manifest.csv"), {item["id"] for item in classes})
    ledger = read_csv(TARGET / "part2_decision_ledger.csv")
    if len(ledger) != audit["images"] or {item["species_id"] for item in ledger} != {item["id"] for item in classes}:
        raise ValueError("v5 decision ledger does not cover the manifest")
    print(json.dumps({"verification": "passed", "dataset": str(TARGET.relative_to(ROOT)), "audit": audit}, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true", help="verify an already-frozen v5 without changing it")
    args = parser.parse_args()
    if args.verify:
        verify_existing()
        return
    if TARGET.exists():
        raise ValueError(f"Refusing to overwrite immutable dataset: {TARGET}")
    needed = [SOURCE / name for name in ("manifest.csv", "class_mapping.json", "reviews_snapshot.json", "dataset_metadata.json")]
    if any(not path.is_file() for path in needed):
        raise FileNotFoundError("The preserved v4 source dataset is incomplete")
    source_metadata = json.loads((SOURCE / "dataset_metadata.json").read_text(encoding="utf-8"))
    if digest(SOURCE / "manifest.csv") != source_metadata["manifest_sha256"]:
        raise ValueError("v4 manifest checksum does not match its metadata")
    rows = [row for row in read_csv(SOURCE / "manifest.csv") if row["species_id"] != EXCLUDED_CLASS]
    source_classes = json.loads((SOURCE / "class_mapping.json").read_text(encoding="utf-8"))["classes"]
    classes = [item for item in source_classes if item["id"] != EXCLUDED_CLASS]
    class_ids = {item["id"] for item in classes}
    audit = validate(rows, class_ids)

    TARGET.mkdir(parents=True)
    source_fields = list(rows[0])
    write_csv(TARGET / "manifest.csv", rows, source_fields)
    write_json(TARGET / "class_mapping.json", {"classes": classes})
    write_json(TARGET / "species.yaml", {"species": classes})
    selected_keys = {(row["source"], row["source_id"]) for row in rows}
    all_reviews = json.loads((SOURCE / "reviews_snapshot.json").read_text(encoding="utf-8"))
    reviews = [entry for entry in all_reviews if (entry["source"], entry["source_id"]) in selected_keys]
    write_json(TARGET / "reviews_snapshot.json", reviews)

    ledger_fields = [
        "species_id", "scientific_name", "source", "source_id", "sha256", "split", "group_id",
        "near_duplicate_group_id", "label_decision", "label_basis", "country_decision", "country_basis",
        "domain_decision", "domain_basis", "ecological_reference", "scope", "rationale",
    ]
    ledger = []
    for row in rows:
        new_class = row["species_id"] in {"mikania_micrantha", "pistia_stratiotes"}
        ledger.append({
            "species_id": row["species_id"], "scientific_name": row["scientific_name"],
            "source": row["source"], "source_id": row["source_id"], "sha256": row["sha256"],
            "split": row["split"], "group_id": row["group_id"], "near_duplicate_group_id": row["near_duplicate_group_id"],
            "label_decision": "accepted_for_experimental_dataset", "label_basis": row["label_basis"],
            "country_decision": "PH_owner_attested", "country_basis": row["country_basis"],
            "domain_decision": "field_photo_candidate", "domain_basis": row["domain_basis"],
            "ecological_reference": ECOLOGY_REFERENCES[row["species_id"]],
            "scope": "experimental_only", "rationale": (
                "Owner label/location attestation and preserved source review evidence; no independent botanical or per-record geographic verification."
                if not new_class else
                "Owner label/location attestation plus recorded assistant visual field-photo screen; no independent botanical or per-record geographic verification."
            ),
        })
    write_csv(TARGET / "part2_decision_ledger.csv", ledger, ledger_fields)
    generated_at = datetime.now(timezone.utc).isoformat()
    metadata = {
        "dataset_id": "v5_part2_final_five_classes",
        "generated_at_utc": generated_at,
        "preparation_seed": 42,
        "source_dataset": "curated/v4_six_classes",
        "source_manifest_sha256": digest(SOURCE / "manifest.csv"),
        "images": audit["images"], "classes": classes, "split_audit": audit,
        "ecology_references": ECOLOGY_REFERENCES,
        "exclusions": [{
            "species_id": EXCLUDED_CLASS, "scientific_name": "Caladium bicolor",
            "reason": "No adequate Philippine invasive-status evidence was established for this project; preserved only in unactivated v4 exploratory history.",
        }],
        "scope": "Owner-attested, experimental five-class dataset. It is not a nationwide accuracy claim or an independently expert-verified botanical corpus.",
        "limitations": [
            "Mikania micrantha and Pistia stratiotes have very small partitions and must not be promoted on this evidence.",
            "Owner label/location attestation and source metadata are not independent per-record botanical/geographic verification.",
            "No external/global photos were mixed into Philippine evaluation partitions.",
            "Pretraining weights are separately tracked by training runs and are not dataset records.",
        ],
    }
    metadata["manifest_sha256"] = digest(TARGET / "manifest.csv")
    metadata["reviews_snapshot_sha256"] = digest(TARGET / "reviews_snapshot.json")
    metadata["decision_ledger_sha256"] = digest(TARGET / "part2_decision_ledger.csv")
    write_json(TARGET / "dataset_metadata.json", metadata)
    write_json(TARGET / "checksums.json", {
        name: digest(TARGET / name)
        for name in ("manifest.csv", "class_mapping.json", "species.yaml", "reviews_snapshot.json", "part2_decision_ledger.csv", "dataset_metadata.json")
    })
    (TARGET / "README.md").write_text(
        "# GeoFlora curated v5\n\n"
        "Part 3 frozen, five-class experimental dataset generated from the documented Part 2 review decision. "
        "The manifest references original files by path and protects them with SHA-256 checksums; it does not duplicate images. "
        "Caladium bicolor was deliberately excluded because its invasive status was not established for this project. "
        "See `dataset_metadata.json`, `part2_decision_ledger.csv`, and `docs/part-2-finalization.md`.\n",
        encoding="utf-8",
    )
    finalization = {
        "generated_at_utc": generated_at,
        "part_2_scope": "Full 100-species collection remains a research staging archive; only five evidence-backed classes are selected for the experimental dataset.",
        "batch_outcome": {"records": 674, "species_with_images": 80, "owner_label_approvals": 674, "owner_country_attestations": 674},
        "selected_dataset": {"path": str(TARGET.relative_to(ROOT)).replace("\\", "/"), **audit},
        "included_classes": [{**item, "ecological_reference": ECOLOGY_REFERENCES[item["id"]]} for item in classes],
        "held_or_excluded": [
            {"category": "Caladium bicolor", "decision": "excluded", "reason": "Invasive status not established for this project."},
            {"category": "Mikania/Pistia supplemental staging", "decision": "held", "reason": "Separate 50-image Mikania corpus lacks its own label approval; it was not silently merged."},
            {"category": "Other research-queue taxa", "decision": "held", "reason": "Their audit/review evidence or independent field coverage is insufficient for this experimental freeze."},
        ],
        "supplementation_outcome": "No weak, unreviewed, or global images were added just to raise counts. Existing separate Mikania staging is retained for future review.",
        "part_3_readiness": "Technical split, integrity, license/attribution, checksum, and leakage checks pass. Statistical/model-promotion readiness does not pass for Mikania or Pistia.",
    }
    write_json(DOCS / "part-2-finalization.json", finalization)
    report = """# Part 2 finalization\n\n""" + (
        "Completed: the 100-species collection is retained as a research archive, while the supported experimental subset is explicitly limited to five classes. "
        "This does not convert all collected taxa into invasive-model labels.\n\n"
        "## Decision\n\n"
        "- Included in `curated/v5_part2_final_five_classes`: Chromolaena odorata, Lantana camara, Pontederia crassipes, Mikania micrantha, and Pistia stratiotes.\n"
        "- Excluded: Caladium bicolor. The earlier v4 exploratory experiment is preserved but unactivated; its inclusion is not sufficient evidence that the species is an invasive target.\n"
        "- Held: 660 other batch records and the separate 50-image Mikania staging corpus. Neither has been silently promoted.\n\n"
        "## What the decisions mean\n\n"
        "All included records retain their exact source, checksum, license/attribution, group/similarity IDs, split, reviewer evidence and rationale in the [v5 decision ledger](../storage/datasets/curated/v5_part2_final_five_classes/part2_decision_ledger.csv). "
        "Label/location evidence is owner attestation; Mikania and Pistia additionally have the recorded visual field-photo screen. These are not independent botanical or per-record geographic certifications.\n\n"
        "The inclusion references are recorded in the dataset metadata and point to the Philippine [NISSAP draft](https://www.philchm.ph/wp-content/uploads/2019/03/NISSAP-Philippines-2016_final-draft.pdf), the [CBD national report](https://www.cbd.int/doc/world/ph/ph-nr-04-en.pdf#page=23), and [CDFP Araceae](https://www.philippineplants.org/Families/Araceae.html). They support research inclusion, not a claim that every photographed site is invaded.\n\n"
        "## Supplementation result\n\n"
        "No new unreviewed or non-Philippine images were added merely to increase class counts. The Mikania/Pistia counts remain too small for promotion; the separate Mikania candidate corpus remains available for a distinct approval pass.\n\n"
        "## Hand-off to Part 3\n\n"
        "Part 3 is frozen as [curated v5](../storage/datasets/curated/v5_part2_final_five_classes/README.md): image paths and SHA-256 checksums resolve, every image decodes, rights metadata is present, and checksum/observation/similarity groups do not cross splits. Per-class image and independent-group counts are in `dataset_metadata.json`. Pretraining weights, if used later, are not data records and must remain outside Philippine evaluation partitions.\n"
    )
    (DOCS / "part-2-finalization.md").write_text(report, encoding="utf-8")
    print(json.dumps({"dataset": str(TARGET.relative_to(ROOT)), "audit": audit, "excluded": EXCLUDED_CLASS}, indent=2))


if __name__ == "__main__":
    main()
