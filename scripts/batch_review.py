"""Prepare batch review packets, or apply explicit reviewer decisions.

Run: python scripts/batch_review.py prepare
     python scripts/batch_review.py apply --decisions PATH.csv
This staging workflow never changes active classes or original manifests.
"""
import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "storage/datasets/staging/species_100_ph"
REVIEW = BASE / "review"
FIELDS = ["record_key", "scientific_name", "source", "source_id", "decision", "reviewer", "rationale", "verified_country", "verified_domain"]


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def records():
    rows = read_csv(BASE / "audit/curation_queue.csv")
    for row in rows:
        row["record_key"] = hashlib.sha256(json.dumps([row["corpus"], row["source"], row["source_id"], row["sha256"]]).encode()).hexdigest()
    return rows


def write_csv(path, rows, fields):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def prepare():
    rows = records()
    REVIEW.mkdir(parents=True, exist_ok=True)
    template = REVIEW / "decisions.csv"
    if not template.exists():
        write_csv(template, rows, FIELDS)
    pages, summary = [], []
    inventory = read_csv(BASE / "audit/species_inventory.csv")
    for species in inventory:
        selected = [r for r in rows if r["corpus"] == species["source_taxon_id"]]
        component_counts = Counter(r["duplicate_component"] for r in selected)
        priority = sum(r["curation_route"] == "candidate_for_label_and_location_review" for r in selected)
        summary.append({**species, "priority_label_review_records": priority,
                        "hold_or_domain_review_records": len(selected)-priority,
                        "approved_for_training": False})
        if not selected:
            continue
        cards = []
        for row in selected:
            image_path = Path(row["file"]).resolve()
            if not image_path.is_relative_to(BASE.resolve()):
                raise ValueError("Review image escaped staging root")
            image = quote("../" + image_path.relative_to(BASE).as_posix(), safe="/")
            cards.append(f'<article><a href="{image}"><img src="{image}" loading="lazy" alt="Unverified plant candidate"></a>'
                         f'<h2>{escape(row["scientific_name"])}</h2><p>Key: <code>{row["record_key"]}</code></p>'
                         f'<p>Route: {escape(row["curation_route"])}<br>Domain screen: {escape(row["domain_screen"])}<br>Group: {escape(row["duplicate_component"])}</p>'
                         f'<p>{escape(row["license"])}; {escape(row["attribution"])}</p><p>{escape(row["locality"])}</p>'
                         f'<a href="{escape(row["source_url"], quote=True)}" target="_blank" rel="noopener noreferrer">Original source</a></article>')
        title = escape(species["name"])
        page = '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        page += f'<title>{title} review</title><style>body{{font-family:system-ui;background:#f4f6f3;color:#183029;margin:24px}}main{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px}}article{{padding:16px;background:white;border:1px solid #ccd6cd;overflow-wrap:anywhere}}img{{width:100%;height:260px;object-fit:contain}}</style>'
        page += f'<a href="index.html">All species</a><h1>{title}</h1><p>Pending visual review. Enter decisions by record key in decisions.csv. Approval of a label does not resolve ecological holds or enable a model class.</p><main>' + ''.join(cards) + '</main></html>'
        filename = species["source_taxon_id"] + ".html"
        (REVIEW / filename).write_text(page, encoding="utf-8")
        pages.append(f'<li><a href="{filename}">{title}</a>: {len(selected)} images; {len(component_counts)} component estimates; {priority} priority review records</li>')
    index = '<!doctype html><html lang="en"><meta charset="utf-8"><title>Batch review</title><h1>Batch review packets</h1><p>All new labels remain pending. Inspect full-size images and source observations, then complete decisions.csv. These packets do not save decisions automatically.</p><ul>' + ''.join(pages) + '</ul></html>'
    (REVIEW / "index.html").write_text(index, encoding="utf-8")
    write_csv(REVIEW / "class_selection.csv", summary, list(summary[0]))
    print(f"Prepared {len(rows)} candidate records and {len(pages)} species galleries. Decisions template preserved if already present.")


def apply(path):
    return apply_entries(read_csv(path))


def apply_entries(decisions, *, label_only=False):
    current = {r["record_key"]: r for r in records()}
    pending = []
    seen = set()
    for entry in decisions:
        decision = entry.get("decision", "").strip().lower()
        if not decision:
            continue
        key = entry.get("record_key")
        if key not in current or key in seen:
            raise ValueError("Unknown or duplicated decision key")
        seen.add(key)
        if decision not in {"approved", "rejected", "flagged"}:
            raise ValueError("Decision must be approved/rejected/flagged; flag corrections for taxonomic review")
        if not entry.get("reviewer", "").strip() or not entry.get("rationale", "").strip():
            raise ValueError("Reviewer and rationale required")
        row = current[key]
        if entry.get("scientific_name") != row["scientific_name"]:
            raise ValueError("Do not silently change species labels; flag for correction")
        country, domain = entry.get("verified_country", "").strip(), entry.get("verified_domain", "").strip()
        if decision == "approved":
            if not label_only and (country != "PH" or domain not in {"field", "herbarium"}):
                raise ValueError("Approval requires verified_country PH and verified_domain field/herbarium")
            file = Path(row["file"]).resolve()
            if not file.is_relative_to(BASE.resolve()) or hashlib.sha256(file.read_bytes()).hexdigest() != row["sha256"]:
                raise ValueError("Approved file failed current integrity check")
        pending.append({"record_key": key, "decision": decision, "reviewer": entry["reviewer"].strip(),
                        "rationale": entry["rationale"].strip(), "verified_country": country, "verified_domain": domain,
                        "approval_basis": "owner_label_attestation_only" if label_only else "explicit_record_review",
                        "reviewed_at_utc": datetime.now(timezone.utc).isoformat()})
    REVIEW.mkdir(parents=True, exist_ok=True)
    history_path = REVIEW / "review_events.jsonl"
    history = [json.loads(line) for line in history_path.read_text(encoding="utf-8").splitlines() if line] if history_path.exists() else []
    latest = {r["record_key"]: r for r in history}
    saved = 0
    with history_path.open("a", encoding="utf-8") as stream:
        for event in pending:
            previous = latest.get(event["record_key"], {})
            if all(event[k] == previous.get(k) for k in event if k != "reviewed_at_utc"):
                continue
            stream.write(json.dumps(event) + "\n")
            latest[event["record_key"]] = event
            saved += 1
    approved, held = [], []
    for key, row in current.items():
        review = latest.get(key, {})
        if review.get("decision") != "approved":
            continue
        record = {**row, **review, "review_status": "approved"}
        # A visually confirmed field photo can clear the URL-based domain screen only.
        holds = [reason for reason in row["curation_route"].split("|") if reason not in {"image_domain_review", "candidate_for_label_and_location_review"}]
        file = Path(row["file"]).resolve()
        intact = file.is_relative_to(BASE.resolve()) and file.is_file() and hashlib.sha256(file.read_bytes()).hexdigest() == row["sha256"]
        if review.get("verified_country") != "PH":
            holds.append("country_verification_pending")
        if review.get("verified_domain") != "field":
            holds.append("field_domain_verification_pending")
        if not intact:
            holds.append("current_integrity_failed")
        record["remaining_holds"] = "|".join(holds)
        if holds:
            held.append(record)
        else:
            approved.append(record)
    fields = list(next(iter(current.values()))) + ["decision", "reviewer", "rationale", "verified_country", "verified_domain", "approval_basis", "remaining_holds", "reviewed_at_utc"]
    write_csv(REVIEW / "approved_field_candidates.csv", approved, fields)
    write_csv(REVIEW / "approved_labels_on_hold.csv", held, fields)
    print(f"Saved {saved} review events; field candidates {len(approved)}; approved labels still held {len(held)}. No training or class activation.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "apply"])
    parser.add_argument("--decisions", type=Path)
    args = parser.parse_args()
    if args.action == "prepare":
        prepare()
    elif args.decisions:
        apply(args.decisions)
    else:
        parser.error("apply requires --decisions")
