from __future__ import annotations

"""Build evidence and image-review queues without approving records."""

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path
from html import escape
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/ml/src"))
sys.path.insert(0, str(ROOT / "scripts"))
EXPERIMENT = ROOT / "storage/datasets/experiments/geoflora_mobilenetv2_up_to_50_20261101"
ROSTER = EXPERIMENT / "proposed_50_species_roster.csv"
LEDGER = ROOT / "docs/species_100_verification_ledger.csv"
STAGING = ROOT / "storage/datasets/staging"
DOCS = ROOT / "docs"
from auto_training_worker import benchmark_lookalike_filter  # noqa: E402


def read_csv(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def write_csv(path: Path, rows, fields):
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main():
    roster = read_csv(ROSTER)
    ledger = {row["scientific_name_candidate"].casefold(): row for row in read_csv(LEDGER)}
    ecological = []
    for item in roster:
        if item.get("role") == "existing_invasive_baseline":
            continue
        ev = ledger.get(item["scientific_name"].casefold(), {})
        ecological.append({
            "scientific_name": item["scientific_name"], "source_taxon_id": ev.get("source_taxon_id", ""),
            "source_evidence_bucket": ev.get("griis_evidence_bucket", item.get("source_evidence_bucket", "")),
            "source_status_claim": "GRIIS/source flag only; not GeoFlora approval" if ev.get("griis_evidence_bucket") == "source_flagged_invasive" else "Introduced/source candidate; invasive status not established",
            "ecology_screen_status": ev.get("ecology_screen_status", item.get("ecology_screen_status", "")),
            "flora_annotations": ev.get("cdfp_annotations", ""), "citation_url": ev.get("ecology_reference", item.get("source_url", "")),
            "source_catalog_citation": "https://www.gbif.org/dataset/1b1f1153-f54e-418f-b9c8-3f86a2f680b4 (GRIIS Philippines checklist; DOI 10.15468/ribkgo; source flag is not an independent status decision)" if ev.get("griis_evidence_bucket") == "source_flagged_invasive" else "",
            "ecological_approval": ev.get("ecological_approval", item.get("ecological_approval", "not_granted")),
            "conflict_or_review_flag": "; ".join(filter(None, [ev.get("invasive_term_needs_context_review", ""), ev.get("ecology_screen_status", "")])),
            "required_human_action": "Review accepted name, source context, Philippine alien/invasive evidence and intended class role; record decision and rationale",
        })
    ecological.sort(key=lambda row: (row["source_evidence_bucket"] != "source_flagged_invasive", row["scientific_name"].casefold()))
    ecology_path = DOCS / "mobilenetv2-expansion-ecological-review-queue-2026-11-01.csv"
    write_csv(ecology_path, ecological, list(ecological[0]))

    test_hashes, test_groups = set(), set()
    for path in (ROOT / "storage/datasets/curated").glob("*/manifest.csv"):
        for row in read_csv(path):
            if row.get("split", "").casefold() == "test":
                if row.get("sha256"):
                    test_hashes.add(row["sha256"].casefold())
                for field in ("group_id", "observation_id"):
                    value = str(row.get(field) or "").strip()
                    if value:
                        parts = value.split(":")
                        test_groups.add(value.casefold())
                        test_groups.update(":".join(parts[index:]).casefold() for index in range(1, len(parts)))
                        test_groups.add(parts[-1].casefold())
    near_historical_test, save_phashes = benchmark_lookalike_filter()

    candidate_names = {row["scientific_name"].casefold(): row for row in roster}
    staged = []
    for manifest in STAGING.glob("**/raw/manifest.jsonl"):
        for line in manifest.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            name = str(row.get("scientific_name") or "").casefold()
            if name not in candidate_names:
                continue
            species = candidate_names[name]
            base = manifest.parent.parent
            path = (base / str(row.get("local_path", ""))).resolve()
            try:
                rel_image = path.relative_to(ROOT).as_posix()
            except ValueError:
                rel_image = ""
            group = str(row.get("group_id") or row.get("observation_id") or "")
            observation_keys = {group.casefold()} if group else set()
            if group:
                parts = group.split(":")
                observation_keys.update(":".join(parts[index:]).casefold() for index in range(1, len(parts)))
                observation_keys.add(parts[-1].casefold())
            sha = str(row.get("sha256") or "").casefold()
            duplicate_group = str(row.get("near_duplicate_group_id") or "")
            exact_test = sha in test_hashes if sha else False
            group_test = bool(observation_keys & test_groups)
            perceptual_test = bool(sha and path.is_file() and near_historical_test(sha, path))
            license_ok = str(row.get("license", "")).casefold() in {"cc0", "cc-by", "cc-by-sa"} and bool(row.get("attribution"))
            status = str(row.get("review_status") or "pending")
            staged.append({
                "scientific_name": species["scientific_name"], "role_or_status": species.get("role", "research_candidate"),
                "source": row.get("source", ""), "source_id": row.get("source_id", ""), "source_url": row.get("source_url", ""),
                "photographer_attribution": row.get("attribution", ""), "license": row.get("license", ""),
                "license_screen": "eligible license, attribution present" if license_ok else "ineligible/unclear; rights review required",
                "country_code": row.get("country_code", ""), "locality": row.get("locality", ""), "observed_at": row.get("observed_at", ""),
                "observation_group": group, "near_duplicate_group": duplicate_group, "sha256": sha,
                "duplicate_warning": "historical-test exact/group/perceptual overlap; exclude from development" if exact_test or group_test or perceptual_test else ("same-source duplicate group; inspect grouping" if duplicate_group else "none detected by stored or perceptual checks"),
                "recorded_label_basis": "community/research-grade or source record; not independent botanical verification",
                "botanical_evidence_status": "No independent botanical verification recorded; inspect diagnostic characters and record reviewer evidence",
                "review_status": status, "reviewer": row.get("reviewer", ""), "review_rationale": row.get("review_rationale", ""),
                "human_decision_required": "yes; verify visible diagnostic features and label; ecological decision separate",
                "local_image": rel_image if path.is_file() else "",
            })
    save_phashes()
    staged.sort(key=lambda row: (row["scientific_name"].casefold(), row["observation_group"], row["source_id"]))
    image_path = DOCS / "mobilenetv2-expansion-image-review-queue-2026-11-01.csv"
    write_csv(image_path, staged, list(staged[0]) if staged else ["scientific_name"])

    # Static, read-only image gallery. It records no decisions and adds no labels.
    cards = []
    for row in staged:
        if not row["local_image"]:
            continue
        image_url = "../" + quote(row["local_image"], safe="/")
        cards.append(f'<article><a href="{image_url}"><img loading="lazy" src="{image_url}" alt="Unreviewed candidate image"></a>'
                     f'<h2>{escape(row["scientific_name"])}</h2><p>{escape(row["source"])} · {escape(row["source_id"])} · {escape(row["review_status"])}</p>'
                     f'<p>{escape(row["license"])} · {escape(row["photographer_attribution"])}</p><p>{escape(row["observation_group"])} · {escape(row["duplicate_warning"])}</p>'
                     f'<p>Candidate label needs human visual review; this is not independent botanical verification.</p>'
                     f'<a href="{escape(row["source_url"], quote=True)}" target="_blank" rel="noopener">Source record</a></article>')
    gallery = DOCS / "mobilenetv2-expansion-image-review-2026-11-01.html"
    gallery.write_text('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Expansion image review queue</title>'
        '<style>body{font:15px system-ui;margin:24px;background:#eef1ea;color:#10291d}main{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:14px}article{background:white;padding:12px;border-radius:16px}img{width:100%;height:210px;object-fit:contain;background:#f5f5f0}p{font-size:12px;overflow-wrap:anywhere}</style>'
        f'<h1>Image-label review queue</h1><p>{len(staged)} staged candidate records. Read-only gallery: no approvals are recorded. Confirm label and visible diagnostic features independently; assess ecological role separately.</p><main>{"".join(cards)}</main></html>', encoding="utf-8")
    summary = {}
    for name in sorted({row["scientific_name"] for row in staged}):
        subset = [row for row in staged if row["scientific_name"] == name]
        unique = {row["sha256"]: row for row in subset if row["sha256"]}
        eligible = [row for row in unique.values() if row["license_screen"].startswith("eligible") and "historical-test" not in row["duplicate_warning"]]
        summary[name] = {
            "records": len(subset), "exact_unique_images": len(unique),
            "unique_groups_after_exact_test_exclusion": len({row["observation_group"] for row in eligible if row["observation_group"]}),
            "license_eligible_unique_images_after_exact_test_exclusion": len(eligible),
            "explicit_human_approvals": sum(bool(row["reviewer"] and row["review_rationale"] and row["review_status"].casefold() in {"approved", "owner_visual_review_approved"}) for row in subset),
        }
    summary_path = DOCS / "mobilenetv2-expansion-review-queue-summary-2026-11-01.json"
    summary_path.write_text(json.dumps({"generated_from": "existing staging manifests; no approval changes", "historical_test_hashes": len(test_hashes), "historical_test_group_keys": len(test_groups), "species": summary}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ecology_rows": len(ecological), "image_review_rows": len(staged), "gallery_images": len(cards), "historical_test_hashes": len(test_hashes), "historical_test_groups": len(test_groups), "ecology_csv": str(ecology_path.relative_to(ROOT)), "image_csv": str(image_path.relative_to(ROOT)), "gallery": str(gallery.relative_to(ROOT)), "summary": str(summary_path.relative_to(ROOT))}, indent=2))


if __name__ == "__main__":
    main()
