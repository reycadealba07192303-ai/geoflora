# Expansion toward 100 Philippine target species

Date: October 23, 2026 (Asia/Manila). Owner-approved direction: nationwide Philippines, up to 100 evidence-backed plant classes. Current configured classes remain three. The existing candidate model does not support the research queue.

## Source-backed research pool

Retrieved the public [GRIIS Philippines checklist](https://www.gbif.org/dataset/1b1f1153-f54e-418f-b9c8-3f86a2f680b4), DOI [10.15468/ribkgo](https://doi.org/10.15468/ribkgo), published by the Invasive Species Specialist Group under CC BY 4.0. It includes introduced as well as invasive species, so membership alone does not establish invasiveness. Full metadata/citation is preserved in the source EML.

Snapshot processing results:

| Item | Count |
|---|---:|
| All source taxon rows, across kingdoms | 453 |
| Plant species rows with Philippine presence | 352 |
| Plant rows explicitly flagged invasive in this source | 13 |
| Plant rows without that explicit flag | 339 |
| Selected research candidates | 100 |
| Source-flagged invasive candidates in selected queue | 12 |
| Other introduced candidates requiring status evidence | 88 |

These are source rows/provisional search names, not a fully reconciled count of accepted species. The queue omits candidate-name collisions instead of silently merging them; one source-flagged row is therefore not selected. Null/absent invasive flags mean no explicit invasive flag in this snapshot, not proof of ecological safety. This checklist alone does not support a claim of 100 confirmed invasive Philippine plant species.

## Deliverables

- docs/species_100_research_queue.csv: 100 provisional candidates, original names, source status flags, references, and pending review status.
- docs/species-100-source-evidence.json: source checksum, processing counts, selection logic and limitations.
- storage/species_catalog/research/griis_philippines/source.zip and eml.xml: preserved source archive and metadata.
- storage/species_catalog/research/griis_philippines/plant_research_pool.csv: complete 352-row pool for research, including excluded collisions.
- scripts/build_species_research_pool.py: reproducible download and staging entry point.

Selection puts source-flagged invasive records first, then the prior historical shortlist, then other introduced records alphabetically. This is a research workload ordering, not an ecological risk ranking. Provisional search names use the first two words of the source accepted name or original name; resolve taxonomy against an authoritative source before assigning a permanent class ID. Preserve original author strings and synonym evidence.

## Phased implementation

1. **3 → 10:** finish ecological and image feasibility review of the existing ten-species shortlist. Collect images only for candidates that pass; keep new records pending review.
2. **10 → 25:** cross-check source-flagged taxa and find independent Philippine invasion/impact evidence for additional candidates. Resolve synonyms and name collisions first.
3. **25 → 50:** expand only where rights, class balance, independent observations and local evaluation coverage can be supported.
4. **50 → up to 100:** proceed if evidence and data support the classes. Do not fill the target with introduced-only plants or claim nationwide validation without regional evidence.

For every candidate, require: reconciled accepted taxon and ID; Philippine invasive/impact reference with context and date; image-license/provenance inventory; visual label review; independent observation/group counts; PH regional coverage; and documented inclusion decision. Keep decisions in a separate review ledger; generated source snapshots are not the decision authority.

## Image and model requirements

- Start with a bounded feasibility target of 100 unique candidate images per eligible species, not 100 automatically approved labels. Up to 100 classes would mean up to 10,000 candidate images at that initial target; actual needs depend on diversity and validation.
- Philippine validation/test partitions must use eligible independent local observations. Track non-PH supplemental training images separately and check cross-source duplication against every holdout.
- Protect v3 and the original test history. New classes require a new dataset version, matching class mapping, retraining and per-class evaluation.
- Each phase must evaluate per-class precision/recall/F1, confusion, unsupported inputs and latency. Update advertised model support only after activation.
- Do not begin a 100-class training run using this research queue. It contains no approved image corpus for the proposed additions.

## Current completion

- [x] Updated the long-term scope to up to 100 evidence-backed species.
- [x] Retrieved and preserved a source-attributed Philippine checklist snapshot.
- [x] Separated explicit invasive flags from introduced/unknown status.
- [x] Generated a 100-entry research queue with collision exclusions.
- [ ] Reconcile taxonomy and verify current Philippine invasive evidence for prospective classes.
- [ ] Probe image feasibility for the additional candidates; only the earlier ten have availability checks.
- [ ] Acquire/review images and train the next supported expansion phase.

No ecological flags in MongoDB, configured species YAML, existing model mapping, image approvals or model artifacts were changed by this investigation.
