# Initial verification of the 100-species research queue

Date: October 23, 2026 (Asia/Manila). This is desktop source screening and live image feasibility checking, not ecological approval of 100 invasive species.

## Work performed

Cross-checked all 100 source taxa against exact species entries in Co's Digital Flora of the Philippines (CDFP), using 41 family pages. Saved source URLs, page hashes, annotations and match status. Queried iNaturalist for exact active species matches and research-grade observations with CC0, CC BY or CC BY-SA photos, separately for the Philippines and globally. A global count includes Philippine observations. Counts refer to observations, not approved photos or independent image groups.

Results are in:

- species_100_verification_ledger.csv: combined source screening, image counts and next action per entry.
- species-100-check-summary.json: aggregate results.
- species-100-ecological-crosscheck.json: 100 source cross-checks and source links.
- species-100-availability.json: attempted live image queries with timestamps and any unresolved taxonomic names.

The original source flags are retained. Only completed image probes mark image_availability_checked as True in species_100_research_queue.csv. A pre-update copy is preserved under storage/species_catalog/research/griis_philippines. No new images, image approvals, model classes or database ecological flags were created.

## Final image-screening counts

All 100 candidates were attempted: 92 exact taxon queries completed and eight names remain unresolved. Of the completed queries, 48 returned at least one Philippine qualifying observation and 44 returned zero. No request failures were recorded. These counts do not imply 48 training-ready species.

## Important ecological conflicts

CDFP exact-record screening found 77 records requiring contextual review, 12 unresolved exact-record matches, seven native-status conflicts and four uncertain-origin records. These are automated screening categories. Missing records may reflect synonyms, family changes or page structure and do not establish absence from the Philippines.

Manually inspected examples:

- **Hiptage benghalensis:** CDFP identifies it as native. Hold its invasive-alien inclusion despite the GRIIS source flag. [Malpighiaceae](https://www.philippineplants.org/Families/Malpighiaceae.html).
- **Imperata cylindrica:** CDFP treats its origin as cryptogenic. Do not automatically classify it as an alien plant. [Poaceae](https://www.philippineplants.org/Families/Poaceae.html).
- **Coccinia grandis:** also cryptogenic in CDFP. Its earlier proposed collection priority is on hold for invasive-alien class inclusion until the conflict is resolved. [Cucurbitaceae](https://www.philippineplants.org/Families/Cucurbitaceae.html).

The other native annotation conflicts are Abrus precatorius, Alternanthera sessilis, Alysicarpus vaginalis, Areca catechu, Biophytum sensitivum and Chloris barbata. The other uncertain-origin records are Aleurites moluccanus and Basella alba. Consult each ledger row's flora URL and review context before making an ecological decision. This is not a management/removal recommendation.

## Documented candidates worth further review

CDFP gives explicit invasion notes for these candidates, alongside Philippine entries:

| Candidate | Evidence | Image concern from this probe |
|---|---|---|
| Broussonetia papyrifera | [Moraceae](https://www.philippineplants.org/Families/Moraceae.html) notes Philippine invasiveness | Zero PH observations under the selected filters; local acquisition needed |
| Pachystachys coccinea | [Acanthaceae](https://www.philippineplants.org/Families/Acanthaceae.html) describes naturalized/invasive status | Only one PH qualifying observation |
| Piper aduncum | [Piperaceae](https://www.philippineplants.org/Families/Piperaceae.html) notes invasive naturalization | Only one PH qualifying observation |
| Pistia stratiotes | [Araceae](https://www.philippineplants.org/Families/Araceae.html) includes an invasion note | Six PH qualifying observations |
| Salvinia molesta | [Salviniaceae](https://www.philippineplants.org/Families/Salviniaceae.html) includes an invasion note | Zero PH observations under the selected filters |

Mikania micrantha retains GRIIS source-flag evidence and the historical national-report reference from the earlier shortlist; this probe found 13 PH qualifying observations. It is a practical next candidate for bounded feasibility collection, conditional on taxonomic and label/provenance review. Do not treat a keyword hit as a final ecological approval. The 88 introduced-only source entries need independent Philippine invasion/impact evidence; availability of images is insufficient.

## Taxonomic limits

Queries deliberately require an exact active species match and leave mismatches unresolved. For example, the queue's Eichhornia crassipes needs a synonym crosswalk: Kew accepts Pontederia crassipes and lists Eichhornia crassipes as a synonym. [Kew taxonomy record](https://powo.science.kew.org/taxon/urn%3Alsid%3Aipni.org%3Anames%3A310928-2). The earlier shortlist already probed Pontederia; do not count these names as separate model classes. Other mismatches remain unresolved rather than taking a fuzzy match automatically.

## Next actions

1. Resolve or exclude native/uncertain-origin conflicts for the invasive-alien scope. Retain original evidence and rationale in a review ledger.
2. Reconcile unresolved names, family placements and synonym collisions before collection.
3. Prioritize independently documented candidates with real PH image coverage; acquire additional local photos for poorly covered classes.
4. Keep non-PH supplemental training images separate and protect Philippine holdouts from observation/duplicate leakage.
5. Train the next expansion only after sufficient rights/provenance and label review. Neither 100 records nor large global counts establish readiness for a 100-class model.

## Reproduction

Run with the project ML virtual environment:

```powershell
.\services\ml\.venv\Scripts\python.exe scripts/check_ecological_evidence.py
.\services\ml\.venv\Scripts\python.exe scripts/check_research_queue.py
.\services\ml\.venv\Scripts\python.exe scripts/summarize_research_checks.py
```

The availability probe checkpoints every attempted species and skips previously completed records when resumed. Unresolved/failed entries are retried. Source pages and counts can change, so use saved timestamps/hashes when reporting this run. Annotation extraction and invasive-word detection are conservative research aids; contextual review and qualified domain decisions remain outstanding.
