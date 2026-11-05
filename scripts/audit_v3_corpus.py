"""Read-only audit and contact sheets for the frozen three-class v3 corpus.

Run from the repository root with:
  .\\services\\ml\\.venv\\Scripts\\python.exe scripts\\audit_v3_corpus.py

Outputs go to docs/v3-corpus-audit/. The source manifests, reviews, and images are
never modified. Keyword flags are triage hints, not label or image decisions.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageOps, UnidentifiedImageError

from geoflora_ml.datasets.audit import load_current_reviews
from geoflora_ml.datasets.duplicates import group_near_duplicates

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "storage/datasets"
MANIFEST = DATA / "curated/v3/manifest.csv"
DEFAULT_OUTPUT = ROOT / "docs/v3-corpus-audit"
KEYWORDS = re.compile(r"herbarium|botanic|specimen|collection|museum", re.IGNORECASE)
VISUAL_TRIAGE_MANIFEST_SHA256 = "92610540ef74c6944a16567a7029ec88a52406f48ca7694f3376268df3272789"
# Additional contact-sheet observations not caught by the metadata keyword rule.
# These IDs are valid only for the pinned v3 manifest above; they are preliminary
# specimen-sheet screens, not expert label decisions.
VISUAL_SPECIMEN_REVIEW_IDS = {
    "V3-0002", "V3-0071", "V3-0088", "V3-0225",
    "V3-0015", "V3-0017", "V3-0027", "V3-0058", "V3-0089", "V3-0113",
    "V3-0133", "V3-0136", "V3-0166", "V3-0174", "V3-0194", "V3-0203",
    "V3-0164", "V3-0185", "V3-0211", "V3-0227", "V3-0243",
    "V3-0184", "V3-0230",
}
VISUAL_CONTEXT_HOLD_IDS = {"V3-0068"}
DISPLAY = {
    "chromolaena_odorata": "Chromolaena odorata (Hagonoy)",
    "lantana_camara": "Lantana camara (Lantana)",
    "pontederia_crassipes": "Pontederia crassipes (Water Hyacinth)",
}
PAGE_SIZE = 24
COLUMNS = 4
TILE_W, TILE_H, IMAGE_H = 250, 205, 155


def read_rows() -> list[dict[str, str]]:
    with MANIFEST.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    for row in rows:
        row["local_path"] = (DATA / row["local_path"]).resolve().relative_to(DATA.resolve()).as_posix()
    return rows


def audit_images(rows: list[dict[str, str]], reviews: dict[tuple[str, str], dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for index, source in enumerate(rows, start=1):
        row: dict[str, Any] = dict(source)
        row["review_id"] = f"V3-{index:04d}"
        path = DATA / source["local_path"]
        flags: list[str] = []
        try:
            payload = path.read_bytes()
            row["actual_sha256"] = hashlib.sha256(payload).hexdigest()
            if row["actual_sha256"] != source.get("sha256"):
                flags.append("checksum_mismatch")
            with Image.open(path) as im:
                row["width"], row["height"] = im.size
                row["format"] = im.format or "unknown"
                row["mode"] = im.mode
                im.verify()
            if row["width"] < 224 or row["height"] < 224:
                flags.append("small_image_under_224px")
        except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
            row["width"], row["height"], row["format"], row["mode"] = 0, 0, "invalid", "unknown"
            flags.append(f"unreadable_image:{type(exc).__name__}")

        review = reviews.get((str(source.get("source")), str(source.get("source_id"))))
        row["current_review_decision"] = review.get("decision", "no_current_review") if review else "no_current_review"
        row["current_review_rationale"] = review.get("rationale", "") if review else ""
        if review and review.get("decision") not in {"approved", "relabelled"}:
            flags.append("not_currently_approved")
        if KEYWORDS.search(" ".join(str(source.get(k, "")) for k in ("attribution", "image_url", "source_url"))):
            flags.append("source_keywords_need_visual_check")
        row["geography_status"] = "source-filtered; row-level country not independently verified"
        row["triage_flags"] = ";".join(flags)
        row["human_visual_review"] = ""
        row["human_label_review"] = ""
        row["review_notes"] = ""
        output.append(row)
    return output


def add_duplicate_audit(rows: list[dict[str, Any]]) -> dict[str, Any]:
    partitions: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in rows:
        for key in ("sha256", "group_id", "near_duplicate_group_id"):
            partitions[(key, row.get(key, ""))].add(row.get("split", "unknown"))
    cross_split = [
        {"key_type": key, "key": value, "splits": sorted(splits)}
        for (key, value), splits in partitions.items()
        if len(splits) > 1
    ]
    exact = defaultdict(list)
    for row in rows:
        exact[row.get("sha256", "")].append(row["review_id"])
    exact_duplicates = {key: ids for key, ids in exact.items() if key and len(ids) > 1}
    grouped, near_groups = group_near_duplicates(rows, DATA)
    del grouped
    return {
        "cross_split_group_keys": cross_split,
        "exact_duplicate_groups": exact_duplicates,
        "recomputed_near_duplicate_groups": near_groups,
        "recomputed_near_duplicate_group_count": len(near_groups),
    }


def build_candidate_review(rows: list[dict[str, Any]], duplicate_audit: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Create a separate, non-training review manifest; never alter source rows."""
    keyed = {(str(row.get("source")), str(row.get("source_id"))): row for row in rows}
    memberships: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for group in duplicate_audit["recomputed_near_duplicate_groups"]:
        members = [keyed[(str(k["source"]), str(k["source_id"]))] for k in group["record_keys"]]
        for row in members:
            memberships[(str(row.get("source")), str(row.get("source_id")))].extend(m for m in members if m is not row)

    specimen_ids = {row["review_id"] for row in rows if "source_keywords_need_visual_check" in row.get("triage_flags", "")}
    specimen_ids |= VISUAL_SPECIMEN_REVIEW_IDS
    context_hold_ids = VISUAL_CONTEXT_HOLD_IDS
    for row in rows:
        if row["review_id"] in specimen_ids:
            row["assistant_visual_triage"] = "specimen_sheet_preliminary"
            row["assistant_visual_triage_note"] = "Visible herbarium/specimen sheet in contact sheet; preliminary hold only, no source label changed"
        elif row["review_id"] in context_hold_ids:
            row["assistant_visual_triage"] = "context_review_preliminary"
            row["assistant_visual_triage_note"] = "Harvested plant shown outside a natural field setting; hold from field-photo candidate pending scope review"
        else:
            row["assistant_visual_triage"] = "field_photo_preliminary"
            row["assistant_visual_triage_note"] = "Appears to show a live plant in a field-like setting; species and geographic labels not independently verified"
    output: list[dict[str, Any]] = []
    for row in rows:
        key = (str(row.get("source")), str(row.get("source_id")))
        peers = memberships.get(key, [])
        if row["review_id"] in specimen_ids:
            status, reason = "hold_specimen_sheet", "Visible specimen sheet in preliminary contact-sheet review; no source label changed"
        elif row["review_id"] in context_hold_ids:
            status, reason = "hold_context_review", "Harvested plant outside an in-situ field setting; review against intended photo scope"
        elif any(peer["review_id"] in (specimen_ids | context_hold_ids) for peer in peers):
            status, reason = "hold_preliminary_duplicate_group", "Near-duplicate group contains a preliminary visual/context hold"
        elif peers:
            members = [row, *{peer["review_id"]: peer for peer in peers}.values()]
            canonical = min(
                members,
                key=lambda member: (
                    0 if member.get("source") == "inaturalist" else 1,
                    -(int(member.get("width") or 0) * int(member.get("height") or 0)),
                    member["review_id"],
                ),
            )
            if canonical["review_id"] == row["review_id"]:
                status, reason = "preliminary_field_photo_representative", "One representative selected by source preference and resolution; preliminary visual screen only"
            else:
                status, reason = "hold_near_duplicate_copy", f"Near-duplicate copy; retain representative {canonical['review_id']} for review"
        else:
            status, reason = "preliminary_field_photo_singleton", "No near-duplicate partner detected; preliminary visual screen only"
        output.append({**row, "candidate_status": status, "candidate_reason": reason})

    candidates = [row for row in output if row["candidate_status"].startswith("preliminary_field_photo_")]
    observation_groups: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in candidates:
        observation_groups[(row["species_id"], row["split"])].add(str(row.get("group_id") or row.get("source_id")))
    summary = {
        "training_ready": False,
        "purpose": "Assistant-screened field-photo candidate list; pending qualified label/provenance review and not approved for training",
        "source_rows": len(output),
        "preliminary_field_photo_candidates": len(candidates),
        "pending_qualified_label_and_provenance_review": len(candidates),
        "held": len(output) - len(candidates),
        "by_status": dict(Counter(row["candidate_status"] for row in output)),
        "provisional_by_species_and_split": {f"{species}:{split}": count for (species, split), count in Counter((row["species_id"], row["split"]) for row in candidates).items()},
        "provisional_source_observation_groups_by_species_and_split": {f"{species}:{split}": len(groups) for (species, split), groups in observation_groups.items()},
        "provisional_source_observation_groups_total": len({(row["species_id"], str(row.get("group_id") or row.get("source_id"))) for row in candidates}),
        "specimen_sheet_holds": len(specimen_ids),
        "context_review_holds": len(context_hold_ids),
        "keyword_detected_specimen_sheet_holds": sum("source_keywords_need_visual_check" in row.get("triage_flags", "") for row in rows),
        "additional_visual_specimen_sheet_holds": len(VISUAL_SPECIMEN_REVIEW_IDS),
        "source_data_modified": False,
        "approved_labels_modified": False,
        "rule": "Retain one iNaturalist-first representative per recomputed near-duplicate group, unless the group contains a preliminary visual/context hold. Candidate photos look field-like but species and geography are not independently verified.",
    }
    return output, summary


def draw_contact_sheets(rows: list[dict[str, Any]], output_dir: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    font = ImageFont.load_default()
    for species_id in DISPLAY:
        selected = [row for row in rows if row["species_id"] == species_id]
        pages = (len(selected) + PAGE_SIZE - 1) // PAGE_SIZE
        counts[species_id] = len(selected)
        for page_index in range(pages):
            page = selected[page_index * PAGE_SIZE : (page_index + 1) * PAGE_SIZE]
            page_rows = (len(page) + COLUMNS - 1) // COLUMNS
            sheet = Image.new("RGB", (COLUMNS * TILE_W, page_rows * TILE_H + 54), "#eef1ea")
            draw = ImageDraw.Draw(sheet)
            draw.text((16, 15), f"{DISPLAY[species_id]} — page {page_index + 1}/{pages}", fill="#0d2618", font=font)
            for tile_index, row in enumerate(page):
                x = (tile_index % COLUMNS) * TILE_W
                y = 48 + (tile_index // COLUMNS) * TILE_H
                draw.rounded_rectangle((x + 5, y + 4, x + TILE_W - 5, y + TILE_H - 4), radius=12, fill="white", outline="#dbe4d7")
                image_path = DATA / row["local_path"]
                try:
                    with Image.open(image_path) as source:
                        image = ImageOps.contain(source.convert("RGB"), (TILE_W - 24, IMAGE_H - 8))
                    px = x + (TILE_W - image.width) // 2
                    py = y + 8 + (IMAGE_H - image.height) // 2
                    sheet.paste(image, (px, py))
                except (OSError, ValueError, UnidentifiedImageError):
                    draw.text((x + 18, y + 65), "IMAGE UNREADABLE", fill="#a53e2a", font=font)
                label = f"{row['review_id']} · {row['split']} · {row['source']}"
                draw.text((x + 12, y + IMAGE_H + 6), label[:42], fill="#23382b", font=font)
                flags = row.get("triage_flags", "") or "No metadata flag"
                draw.text((x + 12, y + IMAGE_H + 23), flags[:40], fill="#7b4d1f" if row.get("triage_flags") else "#68736a", font=font)
            filename = output_dir / f"{species_id}-{page_index + 1:02d}-of-{pages:02d}.jpg"
            sheet.save(filename, quality=88, optimize=True)
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output_dir = args.output.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = read_rows()
    manifest_sha256 = hashlib.sha256(MANIFEST.read_bytes()).hexdigest()
    if manifest_sha256 != VISUAL_TRIAGE_MANIFEST_SHA256:
        raise SystemExit("The v3 manifest changed. Reconfirm review IDs before reusing the visual-triage list.")
    reviews = load_current_reviews(DATA)
    audited = audit_images(rows, reviews)
    duplicate_audit = add_duplicate_audit(audited)
    candidate_rows, candidate_summary = build_candidate_review(audited, duplicate_audit)
    visual_counts = draw_contact_sheets(audited, output_dir)

    review_fields = [
        "review_id", "species_id", "scientific_name", "split", "source", "source_id", "source_url",
        "attribution", "license", "local_path", "group_id", "near_duplicate_group_id", "observed_at",
        "width", "height", "format", "sha256", "actual_sha256",
        "current_review_decision", "current_review_rationale", "geography_status", "triage_flags",
        "human_visual_review", "human_label_review", "review_notes",
        "assistant_visual_triage", "assistant_visual_triage_note",
    ]
    with (output_dir / "review.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=review_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(audited)

    candidate_fields = review_fields + ["candidate_status", "candidate_reason"]
    with (output_dir / "candidate-review-manifest.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=candidate_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(candidate_rows)
    provisional = [row for row in candidate_rows if row["candidate_status"].startswith("preliminary_field_photo_")]
    provisional_contact_dir = output_dir / "provisional-contact-sheets"
    provisional_contact_dir.mkdir(parents=True, exist_ok=True)
    provisional_contact_counts = draw_contact_sheets(provisional, provisional_contact_dir)
    candidate_summary["provisional_contact_sheet_counts"] = provisional_contact_counts
    with (output_dir / "provisional-representatives.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=candidate_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(provisional)
    with (output_dir / "preliminary-field-photos.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=candidate_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(provisional)
    (output_dir / "candidate-summary.json").write_text(json.dumps(candidate_summary, indent=2), encoding="utf-8")

    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_manifest": str(MANIFEST.relative_to(ROOT)),
        "source_manifest_sha256": hashlib.sha256(MANIFEST.read_bytes()).hexdigest(),
        "source_files_modified": False,
        "label_or_review_decisions_modified": False,
        "total_rows": len(audited),
        "by_species": dict(Counter(row["species_id"] for row in audited)),
        "by_species_and_split": {f"{species}:{split}": count for (species, split), count in Counter((row["species_id"], row["split"]) for row in audited).items()},
        "by_source": dict(Counter(row["source"] for row in audited)),
        "by_license": dict(Counter(row["license"] for row in audited)),
        "by_current_review": dict(Counter(row["current_review_decision"] for row in audited)),
        "image_readability_or_checksum_flags": dict(Counter(flag.split(":", 1)[0] for row in audited for flag in row["triage_flags"].split(";") if flag and not flag.startswith("source_keywords"))),
        "metadata_keyword_visual_triage_count": sum("source_keywords_need_visual_check" in row["triage_flags"] for row in audited),
        "geographic_limitation": "PH-filtered sources; row-level country and field context are not independently verified",
        "visual_contact_sheet_counts": visual_counts,
        "provisional_candidate_manifest": "candidate-review-manifest.csv",
        "provisional_candidate_summary": candidate_summary,
        **duplicate_audit,
        "review_instructions": [
            "Open the species contact sheets and enter field_photo, specimen, unclear, or unreadable in human_visual_review.",
            "Enter confirmed, incorrect, or uncertain in human_label_review only when qualified evidence is available.",
            "Source keyword flags are prompts for review, not automatic exclusions or label changes.",
            "Do not use the old test split as a fresh blind test; its performance has already been inspected.",
        ],
    }
    (output_dir / "audit-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output_dir), "rows": len(audited), "contact_sheets": visual_counts, "cross_split_keys": len(duplicate_audit["cross_split_group_keys"]), "recomputed_near_duplicate_groups": len(duplicate_audit["recomputed_near_duplicate_groups"]), "preliminary_field_photo_candidates": len(provisional), "provisional_contact_sheets": provisional_contact_counts}))


if __name__ == "__main__":
    main()
