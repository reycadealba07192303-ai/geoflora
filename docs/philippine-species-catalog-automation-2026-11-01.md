# Philippine species catalog and image readiness — 2026-11-01

## Result

Built a provenance-preserving catalog export and a read-only image-readiness inventory from GeoFlora's existing staged sources. No CNN training, model promotion, or image approval occurred. One bounded incremental Broussonetia iNaturalist request completed but yielded zero new eligible downloads. The existing resumable collectors and saved checkpoints were reused rather than restarting broad collection jobs.

The export contains **16,042 source taxon candidates across 15,500 normalized binomial names**. There are **451 canonical-name groups with multiple taxon IDs** (542 excess records in those groups); these are flagged for taxonomy review rather than merged by guesswork. Of the 18,718 already staged source rows, **254 source usages could not be safely joined** to a unique accepted taxon and are kept in a separate unresolved-usages file.

The GBIF full-download processed unresolved file has **6,897 rows**: 5,640 are non-species ranks and 1,257 are species-rank usages; those 1,257 use 1,051 normalized binomial strings. The earlier staging sidecar says 6,872 because it predates 25 accepted-name collisions across taxon keys; the processed CSV and audit include those rows. Counts are source usages, not species missing from the Philippines.

## Generated files

- [Master catalog CSV](../storage/species_catalog/exports/philippine_plant_species_master.csv)
- [Master catalog JSON](../storage/species_catalog/exports/philippine_plant_species_master.json)
- [Catalog source/status summary](../storage/species_catalog/exports/philippine_plant_species_summary.json)
- [Unresolved source usages](../storage/species_catalog/exports/philippine_plant_unresolved_source_usages.json)
- [Image dataset readiness inventory](../storage/species_catalog/exports/image_dataset_readiness.json)
- Rebuild catalog: `services/ml/.venv/Scripts/python.exe scripts/species_catalog/build_master_catalog.py`
- Rebuild readiness: `services/ml/.venv/Scripts/python.exe scripts/species_catalog/build_image_readiness.py`

Catalog fields preserve accepted-name candidates, normalized binomial, family/genus, source IDs, source rows, synonyms/source usages, source license/citation/version metadata, and an unverified ecological evidence bucket. Every export row stays pending source/taxonomy/ecology review and has `ai_model_supported=false`.

## Source coverage and licensing

| Source | Existing staged rows | Coverage and limits |
|---|---:|---|
| GBIF Philippines Plantae occurrence Species List, DOI `10.15468/dl.r3a2uq` | 15,958 accepted-taxon candidates from 32,472 source usages | Occurrence-derived, not a national flora checklist; 6,897 processed usages are retained in the unresolved audit. |
| GRIIS Philippines v1.3, DOI `10.15468/ribkgo` | 353 plant usages; 341 joined in the composite export | Dataset is CC BY 4.0. The extracted species API view does not carry the exact introduced-versus-invasive assertion per record; membership is not labeled as confirmed invasive. |
| GBIF regional flora checklists | 1,868 checklist usages; 1,813 joined | Partial regional coverage, not a national flora. Individual datasets carry their own licenses, including CC BY-NC; attribution and restrictions are retained. |
| MalNAF v1 Philippines subset | 539 records; 495 joined | Alien/naturalized flora evidence, not an invasive-species census. Source claims conflict for some taxa; supplement is marked CC BY 4.0 but source-level restrictions need review. |
| Co's Digital Flora of the Philippines | Linked for manual verification; no bulk rows copied | Its terms do not allow reproducing substantial portions of its accepted-name lists. |

No evidence is assigned to a taxon merely because it is missing from an invasive checklist. The current export has 66 conflicting source-claim records, 140 GRIIS-membership records whose specific status is unresolved in this extraction, 403 records with introduced/naturalized source claims, and 15,433 with insufficient ecological evidence. Separately, 66 records carry an unverified invasive source claim and 469 carry an unverified introduced/naturalized claim; these claim counts overlap. **Zero are marked ecologically verified by this export.** Native and endemic status remain unknown unless an included source explicitly supports a claim; the current sources do not support a national native/endemic breakdown.

GBIF source attribution is preserved in each taxon's evidence. GBIF's individual image licenses are not inferred from these taxon-list licenses; each image must pass its own rights check before use.

## Existing image collection and readiness

The read-only scan found 92 manifest files, 2,542 staged image records, and 86 taxa across existing staging. The bounded Broussonetia request checked three incremental iNaturalist pages after the saved highest observation ID; the provider returned zero new CC0/CC BY/CC BY-SA candidates. Its 41 class-folder records are all CC BY-NC and stay outside invasive training eligibility. The separate PH research batch contains ten license-screen-eligible Broussonetia photos; they remain pending review. The earlier resumable 100-taxon pass is already complete (674 records across 80 taxa, about 282 MB of image payload); a separate existing staging collection holds additional monitored-species images. Files in staging remain candidate data, not contributor sightings or verified labels.

| Priority species | Candidate records | Exact unique images | Observation groups | License-screen eligible, excluding exact test overlaps | Exact historical-test overlaps | Human-approved staged images |
|---|---:|---:|---:|---:|---:|---:|
| *Mikania micrantha* | 211 | 181 | 128 | 33 | 38 | 0 |
| *Coccinia grandis* | 187 | 178 | 120 | 50 | 23 | 0 |
| *Broussonetia papyrifera* | 51 | 51 | 45 | 10 | 6 | 0 |
| *Chromolaena odorata* | 312 | 300 | 215 | 7 | 54 | 0 |
| *Lantana camara* | 310 | 300 | 209 | 4 | 51 | 0 |
| *Pontederia crassipes* | 129 | 125 | 85 | 3 | 34 | 0 |

License-screen eligible means the current strict CC0/CC BY/CC BY-SA plus attribution allowlist passed; it is not human approval. Exact matches to any curated historical test partition are counted separately and excluded from new development use. The readiness JSON also includes every staged taxon, duplicate groups, review-state counts, and exact test-hash checks. The existing collector/audit reports retain the previous perceptual near-duplicate grouping; this run did not repeat that image-heavy pass.

The preserved 11-class development dataset (`auto_6ae5cd74af23d762feaa0889_weakreview_v3_20261101`) contains 1,594 images. Weak classes:

| Class | Images | Observation groups | Train / validation / test | Owner visual review approved | License-screen eligible | Reviewed + eligible train images |
|---|---:|---:|---:|---:|---:|---:|
| Mikania | 160 | 116 | 110 / 25 / 25 | 10 | 30 | 8 |
| Coccinia | 174 | 117 | 123 / 28 / 23 | 24 | 51 | 19 |
| Broussonetia | 41 | 35 | 29 / 6 / 6 | 0 | 0 | 0 |

Owner visual review is not independent botanical expert verification. These counts do not certify the labels or clear every source-specific term. The frozen test partitions remain untouched and were not used for training or selection here.

## Local MongoDB reconciliation

The existing importer passed dry-run validation for all 15,958 GBIF rows. Import was idempotent: **0 inserted, 15,958 already present** in local `species_catalog_staging`. Those records were approved previously by an owner-attestation batch; this import did not set or change that status. Current local DB check: 15,958 records have `ecological_status_is_verified=false` and `ai_model_supported=false`. The exported master catalog remains pending review; it does not mark them invasive or enable them in the CNN.

## Model and collection safety

- Active model remains `mobilenetv2_v3_seed42`, three classes, confidence threshold `0.80`; no model or mapping files were modified.
- Existing 11-class development candidate remains experimental and unchanged.
- No newly downloaded or unverified image was added to training.
- `scripts/collect_research_batch.py` is the resumable, rate/storage-bounded 100-taxon worker; `scripts/collect_staging_photos.py` is the targeted per-species collector with source/license metadata and review queues. Existing collection coverage is broad enough that this run did not launch redundant downloads.
- New images remain separate from contributor consent and sightings. License eligibility does not establish species label correctness or Philippine location.

## Verification

- Species catalog mapping, ambiguity, and conservative ecological-status tests: 4 pass.
- Existing GBIF download/staging and taxonomy tests: 10 pass.
- Mongo staging import validation/idempotency/local-host safeguards: 4 pass.
- Total `scripts/species_catalog` tests: 18 pass.

Remaining work requires human taxonomic/ecological review, source-specific rights decisions for restricted images, and suitable independently verified field photos. This export is a multi-source research catalog, **not a complete Philippine flora inventory** and not a declaration that all listed taxa are invasive.
