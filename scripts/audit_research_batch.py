"""Snapshot or final whole-batch audit, preserving every original image/label.

Run with services/ml/.venv/Scripts/python.exe scripts/audit_research_batch.py.
Includes the original corpus and separate Mikania staging in duplicate checks.
"""
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image
from geoflora_ml.collection.licensing import normalize_license
from geoflora_ml.datasets.duplicates import perceptual_hash
from geoflora_ml.datasets.manifest import read_jsonl

ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / "storage/datasets/staging/species_100_ph"
OUTPUT = STAGING / "audit"


def write_csv(path, rows, fields):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "known_synonym_mappings.json").write_text(json.dumps({
        "Eichhornia crassipes": {"accepted_name": "Pontederia crassipes",
        "reference": "https://powo.science.kew.org/taxon/urn%3Alsid%3Aipni.org%3Anames%3A310928-2",
        "use": "Grouping evidence only; no model class or original source name overwritten"}
    }, indent=2), encoding="utf-8")
    with (ROOT / "docs/species_100_research_queue.csv").open(encoding="utf-8", newline="") as stream:
        queue = list(csv.DictReader(stream))
    ecological = json.loads((ROOT / "docs/species-100-ecological-crosscheck.json").read_text())
    eco = {r["source_taxon_id"]: r for r in ecological["candidates"]}
    progress = json.loads((ROOT / "docs/species-100-collection-progress.json").read_text())
    outcomes = {r["source_taxon_id"]: r for r in progress["species"]}
    full_pass = set(outcomes) == {r["source_taxon_id"] for r in queue} and bool(progress.get("pass_finished_at_utc"))
    roots = [("original", ROOT / "storage/datasets"), ("mikania", ROOT / "storage/datasets/staging/mikania_micrantha_ph")]
    roots += [(r["source_taxon_id"], STAGING / r["source_taxon_id"]) for r in queue]
    queue_by_id = {r["source_taxon_id"]: r for r in queue}
    cache_path = OUTPUT / "perceptual_cache.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    entries, failures, manifests = [], [], {}
    rejection_counts = Counter()
    for corpus, base in roots:
        rejected = base / "raw/rejected.jsonl"
        if corpus in queue_by_id and rejected.exists():
            for row in read_jsonl(rejected):
                rejection_counts[row.get("reason", "unspecified")] += 1
        manifest = base / "raw/manifest.jsonl"
        if not manifest.exists():
            continue
        manifests[str(manifest.relative_to(ROOT))] = hashlib.sha256(manifest.read_bytes()).hexdigest()
        for record in read_jsonl(manifest):
            item = {**record, "corpus": corpus, "file": str((base / record["local_path"]).resolve())}
            path = Path(item["file"])
            issues = []
            if not path.is_relative_to(base.resolve()) or not path.is_file():
                issues.append("missing_or_unsafe_path")
            else:
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                if digest != record.get("sha256"):
                    issues.append("checksum_mismatch")
                try:
                    with Image.open(path) as image:
                        item["width"], item["height"] = image.size
                        image.verify()
                    if digest not in cache:
                        cache[digest] = perceptual_hash(path)
                    item["phash"] = cache[digest]
                except (OSError, ValueError, Image.DecompressionBombError) as exc:
                    issues.append("image_decode_failed")
            if not normalize_license(record.get("license")):
                issues.append("license_not_allowed")
            for field in ("attribution", "source_url", "group_id"):
                if not record.get(field):
                    issues.append("missing_" + field)
            item["country_evidence"] = "source_PH_metadata_not_independently_verified" if record.get("country_code") == "PH" else "unresolved"
            if corpus in queue_by_id and record.get("country_code") != "PH":
                issues.append("country_unresolved")
            item["technical_issues"] = "|".join(issues)
            item["canonical_name_candidate"] = record.get("scientific_name", "unknown")
            if item["canonical_name_candidate"] == "Eichhornia crassipes":
                item["canonical_name_candidate"] = "Pontederia crassipes"
            url = record.get("image_url", "")
            item["domain_screen"] = "field_observation_candidate" if "/photos/" in url and "inaturalist" in url else ("herbarium_candidate" if any(host in url for host in ("naturalis.nl", "nmnh.si.edu", "rbge.org.uk", "oxalis", "calacademy")) else "unknown_domain_review")
            # Do not infer coordinates/region from appearance or nearby samples.
            locality = record.get("locality") or ""
            region = next((island for island in ("Luzon", "Visayas", "Mindanao") if island.lower() in locality.lower()), "unknown")
            item["region_screen"] = region + ("_source_text_only" if region != "unknown" else "")
            entries.append(item)
            if issues:
                failures.append({"corpus": corpus, "source": record["source"], "source_id": record["source_id"], "issues": issues})
    cache_path.write_text(json.dumps(cache), encoding="utf-8")
    parent = list(range(len(entries)))

    def find(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left, right):
        parent[find(right)] = find(left)

    owners = {}
    for index, item in enumerate(entries):
        photo = re.search(r"/photos/(\d+)/", item.get("image_url", ""))
        keys = [("sha", item["sha256"]), ("observation", item["group_id"])]
        if photo:
            keys.append(("inaturalist_photo", photo[1]))
        for key in keys:
            if key in owners:
                union(index, owners[key])
            else:
                owners[key] = index
        if "phash" in item:
            for other in range(index):
                if "phash" in entries[other] and (item["phash"] ^ entries[other]["phash"]).bit_count() <= 6:
                    union(index, other)
    components = defaultdict(list)
    for index, item in enumerate(entries):
        components[find(index)].append(index)
    groups = []
    for number, indices in enumerate(components.values(), 1):
        names = {entries[i]["canonical_name_candidate"] for i in indices}
        corpora = {entries[i]["corpus"] for i in indices}
        conflict = len(names) > 1
        group_id = f"audit-component:{number:05d}"
        for i in indices:
            entries[i].update(duplicate_component=group_id, cross_label_conflict_candidate=conflict,
                              cross_corpus_component=len(corpora) > 1)
        if len(indices) > 1:
            groups.append({"id": group_id, "size": len(indices), "names": sorted(names), "corpora": sorted(corpora),
                           "cross_label_conflict_candidate": conflict,
                           "records": [{"corpus": entries[i]["corpus"], "source": entries[i]["source"], "source_id": entries[i]["source_id"]} for i in indices]})
    batch = [r for r in entries if r["corpus"] in queue_by_id]
    for item in batch:
        e = eco[item["corpus"]]
        q = queue_by_id[item["corpus"]]
        reasons = []
        if item["technical_issues"]:
            reasons.append("technical_or_provenance_hold")
        if e["crosscheck_status"] in {"native_status_conflict_hold", "origin_uncertain_hold"}:
            reasons.append(e["crosscheck_status"])
        elif e["crosscheck_status"] != "exact_record_found_context_review_needed":
            reasons.append("taxonomy_or_source_hold")
        elif q["evidence_bucket"] != "source_flagged_invasive":
            reasons.append("invasive_status_not_established")
        if item["cross_label_conflict_candidate"]:
            reasons.append("cross_label_similarity_review")
        if item["domain_screen"] != "field_observation_candidate":
            reasons.append("image_domain_review")
        item["curation_route"] = "|".join(reasons) if reasons else "candidate_for_label_and_location_review"
        item["review_status"] = "pending"
    inventory = []
    for row in queue:
        records = [r for r in batch if r["corpus"] == row["source_taxon_id"]]
        outcome = outcomes.get(row["source_taxon_id"], {})
        inventory.append({"source_taxon_id": row["source_taxon_id"], "name": row["search_name_candidate"],
                          "collection_outcome": outcome.get("status", "not_checkpointed"), "actual_records": len(records),
                          "reported_records": outcome.get("records", ""), "source_counts": json.dumps(dict(Counter(r["source"] for r in records))),
                          "unique_checksums": len({r["sha256"] for r in records}),
                          "component_count_estimate": len({r["duplicate_component"] for r in records}),
                          "technical_issues": sum(bool(r["technical_issues"]) for r in records),
                          "ecology_status": eco[row["source_taxon_id"]]["crosscheck_status"],
                          "domain_counts": json.dumps(dict(Counter(r["domain_screen"] for r in records))),
                          "region_counts": json.dumps(dict(Counter(r["region_screen"] for r in records)))})
    write_csv(OUTPUT / "species_inventory.csv", inventory, list(inventory[0]))
    fields = ["corpus", "scientific_name", "source", "source_id", "source_url", "license", "attribution", "country_code", "locality", "file", "sha256", "duplicate_component", "cross_label_conflict_candidate", "cross_corpus_component", "domain_screen", "region_screen", "country_evidence", "technical_issues", "curation_route", "review_status"]
    write_csv(OUTPUT / "curation_queue.csv", batch, fields)
    (OUTPUT / "duplicate_components.json").write_text(json.dumps(groups, indent=2), encoding="utf-8")
    mismatch = [r for r in inventory if r["reported_records"] != "" and r["actual_records"] != r["reported_records"]]
    changed = [name for name, checksum in manifests.items() if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != checksum]
    summary = {"generated_at_utc": datetime.now(timezone.utc).isoformat(), "final_collection_pass": full_pass,
               "snapshot_changed_during_audit": changed, "collection_outcomes": dict(Counter(r["collection_outcome"] for r in inventory)),
               "queued_species": len(queue), "checkpointed_species": len(outcomes),
               "batch_records": len(batch), "batch_species_with_images": sum(r["actual_records"] > 0 for r in inventory),
               "batch_unique_checksums": len({r["sha256"] for r in batch}),
               "batch_storage_bytes": sum(p.stat().st_size for p in STAGING.glob("*/raw/**/*.jpg")),
               "checkpoint_manifest_mismatches": mismatch, "technical_failures": failures,
               "batch_domain_counts": dict(Counter(r["domain_screen"] for r in batch)),
               "batch_region_counts": dict(Counter(r["region_screen"] for r in batch)),
               "cross_corpus_components": sum(len(g["corpora"]) > 1 for g in groups),
               "cross_label_conflict_components": sum(g["cross_label_conflict_candidate"] for g in groups),
               "download_rejection_reasons": dict(rejection_counts), "source_manifest_checksums": manifests,
               "labels_approved": 0, "notes": ["Similarity components are review candidates, not proof of duplication or label errors", "Domain and region screens are metadata heuristics requiring review", "Source PH metadata is not independent geographic verification", "No images deleted, no active manifests edited, no training or class activation"]}
    (OUTPUT / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (ROOT / "docs/species-100-batch-audit-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k not in {"source_manifest_checksums", "technical_failures", "download_rejection_reasons", "checkpoint_manifest_mismatches"}}, indent=2), flush=True)


if __name__ == "__main__":
    main()
