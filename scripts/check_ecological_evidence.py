"""Conservative automated CDFP cross-check; does not approve ecological status.

Parses exact species records only. Missing/changed taxonomy remains unresolved.
"""
import csv
import hashlib
import html
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]


def main():
    with (ROOT / "docs/species_100_research_queue.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    pages, results = {}, []
    session = requests.Session()
    session.headers["User-Agent"] = "GeoFlora/0.1 (bounded botanical evidence check)"
    for row in rows:
        family = row["family"]
        url = f"https://www.philippineplants.org/Families/{family}.html"
        if family not in pages:
            time.sleep(0.5)
            try:
                response = session.get(url, timeout=(10, 20))
                response.raise_for_status()
                pages[family] = {"html": response.content.decode("utf-8", errors="replace"), "sha256": hashlib.sha256(response.content).hexdigest()}
            except requests.RequestException as exc:
                pages[family] = {"error": str(exc)}
        page = pages[family]
        item = {"source_taxon_id": row["source_taxon_id"], "search_name_candidate": row["search_name_candidate"],
                "griis_evidence_bucket": row["evidence_bucket"], "crosscheck_url": url,
                "crosscheck_method": "Automated exact species-record match; requires contextual review",
                "ai_model_supported": False}
        if "html" not in page:
            item.update(crosscheck_status="source_request_failed", error=page["error"])
        else:
            item["page_sha256"] = page["sha256"]
            blocks = re.findall(r'<li\b[^>]*class=["\']species_record["\'][^>]*>(.*?)</li>', page["html"], re.S | re.I)
            exact = []
            for block in blocks:
                match = re.search(r'<b>\s*<i>(.*?)</i>\s*</b>', block, re.S | re.I)
                if match and html.unescape(re.sub('<[^>]+>', '', match[1])).strip().casefold() == row["search_name_candidate"].casefold():
                    exact.append(block)
            if len(exact) != 1:
                item.update(crosscheck_status="exact_record_unresolved", matching_records=len(exact))
            else:
                block = exact[0]
                annotations = re.findall(r'<span\b[^>]*class=["\']annotation\s+([^"\']+)["\'][^>]*>(.*?)</span>', block, re.S | re.I)
                item["cdfp_annotations"] = [html.unescape(re.sub('<[^>]+>', '', value)).strip() for _, value in annotations]
                text = html.unescape(re.sub('<[^>]+>', ' ', block))
                item["invasive_term_present_needs_context_review"] = bool(re.search(r'\binvasive\b', text, re.I))
                annotation_text = " ".join(item["cdfp_annotations"]).lower()
                if re.search(r'\bnative\b', annotation_text) and 'not native' not in annotation_text:
                    item["crosscheck_status"] = "native_status_conflict_hold"
                elif 'cryptogenic' in annotation_text:
                    item["crosscheck_status"] = "origin_uncertain_hold"
                else:
                    item["crosscheck_status"] = "exact_record_found_context_review_needed"
        results.append(item)
        print(row["search_name_candidate"], item["crosscheck_status"], flush=True)
    report = {"checked_at_utc": datetime.now(timezone.utc).isoformat(), "candidates": results,
              "method_limit": "Annotations and keyword detection do not establish invasion impact. Missing matches do not establish absence. Family names and synonyms may need reconciliation."}
    (ROOT / "docs/species-100-ecological-crosscheck.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
