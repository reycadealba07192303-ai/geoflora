from __future__ import annotations

"""Build a conservative, provenance-preserving Philippine plant catalog export.

This consumes already acquired/staged sources only. It never downloads data,
approves taxonomy/ecology, or changes the live catalog/model.
"""

import argparse
import csv
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
STAGING = ROOT / "storage/species_catalog/staging"
OUTPUT = ROOT / "storage/species_catalog/exports"
sys.path.insert(0, str(ROOT / "services/ml/src"))

SOURCES = [
    ("gbif_philippines_plantae_full_0038372-260928105237408", "gbif_species_list"),
    ("griis_philippines_plant", "griis"),
    ("gbif_philippine_regional_flora", "regional_checklists"),
    ("malnaf_v1_philippines", "malnaf"),
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return [dict(row) for row in csv.DictReader(stream)]


def clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def canonical_name(value: str) -> str:
    """Normalize a botanical string to its leading genus + specific epithet."""
    value = unicodedata.normalize("NFKD", clean(value))
    tokens = re.findall(r"[A-Za-z][A-Za-z.-]*", value)
    if len(tokens) < 2:
        return clean(value).casefold()
    return f"{tokens[0]} {tokens[1]}".casefold()


def parse_json_list(value: Any) -> list[Any]:
    try:
        result = json.loads(value) if isinstance(value, str) else value
    except (json.JSONDecodeError, TypeError):
        return []
    return result if isinstance(result, list) else []


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_sources() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    metadata: dict[str, Any] = {}
    source_rows: list[dict[str, Any]] = []
    for stem, source_kind in SOURCES:
        csv_path = STAGING / f"{stem}_staging.csv"
        json_path = STAGING / f"{stem}_provenance.json"
        if not csv_path.is_file() or not json_path.is_file():
            raise FileNotFoundError(f"Required staged source/provenance missing: {stem}")
        provenance = json.loads(json_path.read_text(encoding="utf-8"))
        actual_hash = sha256(csv_path)
        expected_hash = provenance.get("staging_csv_sha256")
        if expected_hash and actual_hash != expected_hash:
            raise ValueError(f"Staging checksum differs from provenance: {csv_path}")
        rows = read_csv(csv_path)
        metadata[stem] = {
            "kind": source_kind,
            "file": str(csv_path.relative_to(ROOT)),
            "sha256": actual_hash,
            "row_count": len(rows),
            "provenance": provenance,
        }
        for row in rows:
            source_rows.append({"kind": source_kind, "stem": stem, "row": row})
    return source_rows, metadata


def row_taxon(row: dict[str, str], kind: str) -> tuple[str, str, list[str], str, str]:
    if kind == "gbif_species_list":
        name = clean(row.get("accepted_scientific_name"))
        key = clean(row.get("accepted_taxon_key"))
        aliases = parse_json_list(row.get("source_scientific_names"))
        return key, name, [clean(item) for item in aliases if clean(item)], clean(row.get("family")), clean(row.get("genus"))
    if kind == "griis":
        name = clean(row.get("accepted_name")) or clean(row.get("canonical_name")) or clean(row.get("scientific_name"))
        key = clean(row.get("gbif_backbone_key")) or clean(row.get("source_taxon_id"))
        aliases = [clean(row.get("scientific_name")), clean(row.get("canonical_name")), name]
        return key, name, list(dict.fromkeys(x for x in aliases if x)), clean(row.get("family")), clean(row.get("genus"))
    if kind == "regional_checklists":
        name = clean(row.get("canonical_name")) or clean(row.get("scientific_name"))
        key = clean(row.get("species_key")) or clean(row.get("gbif_usage_key"))
        aliases = [clean(row.get("scientific_name")), name]
        return key, name, list(dict.fromkeys(x for x in aliases if x)), clean(row.get("family")), clean(row.get("genus"))
    name = clean(row.get("accepted_binomial")) or clean(row.get("accepted_name"))
    key = clean(row.get("taxonomic_identifier")) or clean(row.get("staging_id"))
    aliases = [name, *[clean(x) for x in parse_json_list(row.get("synonyms_or_source_names"))]]
    return key, name, list(dict.fromkeys(x for x in aliases if x)), clean(row.get("family")), clean(row.get("genus"))


def ecological_bucket(records: list[dict[str, Any]]) -> tuple[str, list[str]]:
    claims: set[str] = set()
    has_griis = False
    for item in records:
        kind, row = item["source_kind"], item["record"]
        if kind == "griis":
            has_griis = True
        if kind == "malnaf":
            vals = parse_json_list(row.get("original_source_statuses"))
            vals.extend(parse_json_list(row.get("source_taxonomic_statuses")))
            vals.extend([row.get("ecological_status", "")])
            for val in vals:
                normalized = clean(val).casefold()
                if normalized in {"invasive", "invasive alien"}:
                    claims.add("invasive")
                elif normalized in {"introduced", "alien", "naturalized", "naturalised"}:
                    claims.add("introduced_or_naturalized")
                elif normalized == "native":
                    claims.add("native")
                elif normalized == "endemic":
                    claims.add("endemic")
    if len(claims) > 1:
        return "conflicting_source_claims_review_required", sorted(claims)
    if claims == {"invasive"}:
        return "invasive_reported_by_source_unverified", sorted(claims)
    if claims == {"introduced_or_naturalized"}:
        return "introduced_or_naturalized_reported_unverified", sorted(claims)
    if claims == {"native"}:
        return "native_reported_by_source_unverified", sorted(claims)
    if claims == {"endemic"}:
        return "endemic_reported_by_source_unverified", sorted(claims)
    if has_griis:
        return "griis_introduced_or_invasive_membership_status_unspecified", []
    return "unknown_or_insufficiently_documented", []


def build_catalog(source_rows: list[dict[str, Any]], unresolved_rows: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    unresolved_rows = unresolved_rows if unresolved_rows is not None else []
    taxa: dict[str, dict[str, Any]] = {}
    by_name: dict[str, str | None] = {}

    def register_alias(alias: str, catalog_key: str) -> None:
        normalized = canonical_name(alias)
        previous = by_name.get(normalized, "__missing__")
        if previous == "__missing__":
            by_name[normalized] = catalog_key
        elif previous != catalog_key:
            # A canonical binomial attached to multiple GBIF keys is
            # ambiguous; never let later sources pick one arbitrarily.
            by_name[normalized] = None

    # Seed with the broad occurrence-derived GBIF list, whose accepted taxon
    # identifiers are stable within the GBIF backbone snapshot.
    for item in source_rows:
        if item["kind"] != "gbif_species_list":
            continue
        key, name, aliases, family, genus = row_taxon(item["row"], item["kind"])
        if not name:
            continue
        catalog_key = f"gbif:{key}" if key else f"name:{canonical_name(name)}"
        record = taxa.setdefault(catalog_key, {
            "catalog_id": catalog_key,
            "accepted_scientific_name": name,
            "canonical_name": canonical_name(name),
            "family": family,
            "genus": genus,
            "synonyms_and_source_names": set(),
            "source_records": [],
        })
        record["synonyms_and_source_names"].update(aliases)
        record["source_records"].append({"source": item["stem"], "source_kind": item["kind"], "record": item["row"]})
        for alias in [name, *aliases]:
            register_alias(alias, catalog_key)

    # Enrich GBIF taxa with source checklists; add accepted taxa absent from
    # that snapshot without attempting fuzzy or author-string name matching.
    for item in source_rows:
        if item["kind"] == "gbif_species_list":
            continue
        row = item["row"]
        key, name, aliases, family, genus = row_taxon(row, item["kind"])
        if not name:
            continue
        normalized = canonical_name(name)
        match_key = by_name.get(normalized)
        if normalized in by_name and match_key is None:
            unresolved_rows.append({"source": item["stem"], "source_kind": item["kind"], "reason": "ambiguous_canonical_name_matches_multiple_gbif_taxon_keys", "record": row})
            continue
        if match_key is None:
            # Nonaccepted checklist usages are retained as evidence only when
            # their accepted name is unavailable, avoiding false extra taxa.
            taxonomic_status = clean(row.get("taxonomic_status") or row.get("source_taxonomic_statuses")).casefold()
            if taxonomic_status and taxonomic_status not in {"accepted", "provisionally_accepted"}:
                unresolved_rows.append({"source": item["stem"], "source_kind": item["kind"], "reason": "nonaccepted_usage_not_resolved_to_accepted_taxon", "record": row})
                continue
            match_key = f"{item['kind']}:{key or canonical_name(name)}"
            taxa[match_key] = {
                "catalog_id": match_key,
                "accepted_scientific_name": name,
                "canonical_name": canonical_name(name),
                "family": family,
                "genus": genus,
                "synonyms_and_source_names": set(),
                "source_records": [],
            }
            register_alias(name, match_key)
        record = taxa[match_key]
        record["synonyms_and_source_names"].update(aliases)
        if not record["family"]:
            record["family"] = family
        if not record["genus"]:
            record["genus"] = genus
        record["source_records"].append({"source": item["stem"], "source_kind": item["kind"], "record": row})
        for alias in aliases:
            register_alias(alias, match_key)

    output = []
    for record in taxa.values():
        bucket, claims = ecological_bucket(record["source_records"])
        record["synonyms_and_source_names"] = sorted(record["synonyms_and_source_names"], key=str.casefold)
        record["source_ids"] = sorted({
            clean(entry["record"].get(field))
            for entry in record["source_records"]
            for field in ("source_taxon_id", "accepted_taxon_key", "gbif_usage_key", "species_key", "taxonomic_identifier", "source_dataset_key")
            if clean(entry["record"].get(field))
        })
        record["ecological_status_bucket"] = bucket
        record["ecological_status_source_claims"] = claims
        record["ecological_status_verified"] = False
        record["catalog_review_status"] = "pending_source_taxonomy_and_ecological_review"
        record["ai_model_supported"] = False
        record["source_count"] = len(record["source_records"])
        output.append(record)
    return sorted(output, key=lambda item: item["accepted_scientific_name"].casefold())


def write_exports(catalog: list[dict[str, Any]], metadata: dict[str, Any], unresolved_rows: list[dict[str, Any]]) -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    generated = datetime.now(timezone.utc).isoformat()
    json_path = OUTPUT / "philippine_plant_species_master.json"
    csv_path = OUTPUT / "philippine_plant_species_master.csv"
    summary_path = OUTPUT / "philippine_plant_species_summary.json"
    unresolved_path = OUTPUT / "philippine_plant_unresolved_source_usages.json"
    payload = {
        "title": "GeoFlora Philippine plant species research catalog",
        "generated_at_utc": generated,
        "catalog_scope_note": "Source-derived candidate catalog, not a complete or taxonomically verified national flora inventory.",
        "ecological_status_note": "Source claims are preserved as unverified evidence. Absence from an invasive checklist is not evidence of non-invasiveness. GRIIS membership alone does not distinguish introduced from invasive in this GBIF API extraction.",
        "linked_authoritative_reference": {
            "title": "Co's Digital Flora of the Philippines",
            "url": "https://www.philippineplants.org/",
            "terms_url": "https://www.philippineplants.org/General/Copyright.html",
            "bulk_checklist_reproduced": False,
            "reason": "CDFP terms restrict reproducing substantial portions of accepted-name lists; use as a linked human taxonomic verification source.",
        },
        "sources": metadata,
        "species_count": len(catalog),
        "unique_normalized_binomial_names": len({item["canonical_name"] for item in catalog}),
        "unresolved_source_usage_count": len(unresolved_rows),
        "unresolved_source_usages_file": str(unresolved_path.relative_to(ROOT)),
        "species": catalog,
        "unresolved_source_usages": unresolved_rows,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    unresolved_path.write_text(json.dumps({"generated_at_utc": generated, "record_count": len(unresolved_rows), "records": unresolved_rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    fields = ["catalog_id", "accepted_scientific_name", "canonical_name", "family", "genus", "synonyms_and_source_names", "source_ids", "source_count", "ecological_status_bucket", "ecological_status_source_claims", "ecological_status_verified", "catalog_review_status", "ai_model_supported", "source_records"]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for record in catalog:
            writer.writerow({key: json.dumps(record[key], ensure_ascii=False) if isinstance(record[key], (list, dict)) else record[key] for key in fields})
    buckets = Counter(item["ecological_status_bucket"] for item in catalog)
    by_source = Counter(entry["source_kind"] for item in catalog for entry in item["source_records"])
    claim_counts = Counter(claim for item in catalog for claim in item["ecological_status_source_claims"])
    names_to_ids: dict[str, set[str]] = defaultdict(set)
    for item in catalog:
        names_to_ids[item["canonical_name"]].add(item["catalog_id"])
    collision_groups = {name: sorted(ids) for name, ids in names_to_ids.items() if len(ids) > 1}
    raw_unresolved_path = ROOT / "storage/datasets/taxonomy/gbif_philippines/processed/gbif_philippines_plantae_full_0038372-260928105237408_unresolved.csv"
    raw_unresolved = read_csv(raw_unresolved_path) if raw_unresolved_path.is_file() else []
    unresolved_species_rows = [row for row in raw_unresolved if clean(row.get("taxonrank")).upper() == "SPECIES"]
    unique_unresolved_species_names = {canonical_name(row.get("scientificname", "")) for row in unresolved_species_rows if row.get("scientificname")}
    summary = {
        "generated_at_utc": generated,
        "species_records": len(catalog),
        "unique_normalized_binomial_names": len({item["canonical_name"] for item in catalog}),
        "canonical_name_collision_groups_requiring_review": len(collision_groups),
        "excess_taxon_records_in_collision_groups": sum(len(ids) - 1 for ids in collision_groups.values()),
        "source_record_joins": dict(sorted(by_source.items())),
        "ecological_status_breakdown": dict(sorted(buckets.items())),
        "ecological_source_claim_taxon_counts_unverified": dict(sorted(claim_counts.items())),
        "pending_taxonomy_and_ecology_review_count": len(catalog),
        "unresolved_source_usage_count": len(unresolved_rows),
        "gbif_initial_staging_provenance_unresolved_rows": metadata["gbif_philippines_plantae_full_0038372-260928105237408"]["provenance"].get("unresolved_rows", 0),
        "gbif_initial_staging_count_note": "The earlier staged sidecar count differs from the processed unresolved export, which also records 25 accepted-name collisions across taxon keys.",
        "gbif_full_processed_unresolved_file": str(raw_unresolved_path.relative_to(ROOT)) if raw_unresolved_path.is_file() else None,
        "gbif_full_processed_unresolved_rows": len(raw_unresolved),
        "gbif_full_processed_unresolved_non_species_rank_rows": len(raw_unresolved) - len(unresolved_species_rows),
        "gbif_full_processed_unresolved_species_rank_rows": len(unresolved_species_rows),
        "gbif_full_processed_unresolved_unique_species_binomials": len(unique_unresolved_species_names),
        "taxonomic_name_collision_groups": collision_groups,
        "source_coverage": {name: {"rows": info["row_count"], "sha256": info["sha256"], "file": info["file"]} for name, info in metadata.items()},
        "coverage_limitations": [
            "GBIF Species List is occurrence-derived and is not a national flora checklist.",
            "Regional inventories cover only their stated areas and carry source-specific licensing.",
            "GRIIS API extraction preserves checklist membership but not per-record introduced-versus-invasive status.",
            "MalNAF source claims may conflict and do not by themselves prove national invasiveness.",
            "Co's Digital Flora is linked as a verification resource; bulk reproduction is excluded under its stated terms.",
            "No source absence is interpreted as evidence that a taxon is non-invasive.",
        ],
        "linked_reference_policy": "Co's Digital Flora is linked for human taxonomic verification; no substantial portion of its checklist was copied into this export.",
        "exports": {"json": str(json_path.relative_to(ROOT)), "csv": str(csv_path.relative_to(ROOT)), "unresolved_source_usages": str(unresolved_path.relative_to(ROOT))},
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true", help="Validate staged inputs and print counts without writing exports")
    args = parser.parse_args()
    rows, metadata = load_sources()
    unresolved_rows: list[dict[str, Any]] = []
    catalog = build_catalog(rows, unresolved_rows)
    print(json.dumps({"source_rows": len(rows), "species_records": len(catalog), "unresolved_source_usages": len(unresolved_rows), "gbif_source_unresolved_rows": metadata["gbif_philippines_plantae_full_0038372-260928105237408"]["provenance"].get("unresolved_rows", 0), "sources": {key: value["row_count"] for key, value in metadata.items()}}, indent=2))
    if not args.check_only:
        write_exports(catalog, metadata, unresolved_rows)
        print(f"Wrote exports under {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
