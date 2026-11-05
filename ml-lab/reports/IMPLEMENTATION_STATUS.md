# GeoFlora-ML-Lab: Implementation Status Against the Project Specification

Status as of 2026-11-05.

**Status labels**

| Label | Meaning |
|---|---|
| **Done** | Implemented and executed on real data |
| **Built** | Implemented and covered by tests, but not yet executed on verified data |
| **Pilot** | Executed only in provisional mode, on unreviewed labels. Not a research result. |
| **Blocked** | Cannot run until the listed resource exists |

## Summary

| Area | Status |
|---|---|
| Stage 1: project structure and environment | **Done**. Python 3.11 venv, TensorFlow 2.20, Keras 3.15 |
| Stage 2: download, validation and provenance tools | **Done** |
| Stage 3: bounded acquisition | **Done**. 1,620 GBIF images across 16 species (expanded 2026-11-04: 150 per target and look-alike species) |
| Stage 4: inventory and review requirements | **Done**. See `reports/dataset_inventory.md` and 32 review sheets |
| Stage 5: leakage-safe partitions | **Done**. Reviewed data: 3 classes, 435 images (302 / 67 / 66), 0 leakage violations. |
| Stage 6: training | **Done** on reviewed labels. Current: `run-20261104T093016Z-reviewed-v2` (3 classes, about 2 min on CPU). |
| Stage 7: evaluation | **Done**. Test accuracy 97.0% (64/66; 95% CI 89.5–99.6%), macro F1 0.969. Unsupported species (620 images from 7 species, including 4 look-alikes): false acceptance 19.2% at the validation-selected threshold, but only 71.2% of supported-species photos are accepted at that threshold. AUROC 0.844. |
| Stage 8: expansion experiments | **Done** on reviewed labels (2026-11-04). Learning curve (3 classes): 25% / 50% / 100% of training data gave test accuracy 90.9% / 95.5% / 97.0%. Class expansion (3 targets plus 7 look-alikes, about 100 training photos per class): accuracy fell from 95.5% (3 classes) to 75.3% (10 classes), and *Chromolaena* recall fell to 59%. At the developer's request, a dedicated 10-class model was then trained with one pre-chosen longer fine-tuning configuration (`configs/tenclass_v1.yaml`). It was selected over the experiment run on validation accuracy (78.8% vs 71.4%). Test results: accuracy 79.5% (95% CI 73.5-84.7%), macro F1 0.794; recall *Chromolaena* 82%, *Lantana camara* 96%, water hyacinth 71%. It is exported as `geoflora-mnv2-10cls-v1` (candidate, not activated). The 3-class model (97.0%) remains the recommended candidate for detecting target invasive species. See `reports/experiments/` and `reports/expansion/experiments/`. |
| Stage 9: export | **Done**. `models/exported/geoflora-mnv2-3cls-v1/` (status `candidate_not_activated`); predict.py smoke-tested. |
| Demo web app | **Done** (2026-11-04). `scripts/demo_server.py` has three tabs: pipeline flow, identification with species descriptions, and sighting reports with date, time and location on a map (stored locally in `demo_data/`). This scope was added at the developer's request; the original plan left maps to GeoFlora. |
| Executable tests | **Done**. 35 tests pass. |

## Section-by-section

### §5 Project structure
**Done.** Every folder and file in the spec exists. Additions to the spec:
- `dataset/unknown_val/`, used only for threshold selection
- `scripts/review_images.py`, `scripts/export_model.py` and `scripts/run_experiments.py`
- the `geoflora_ml/` library
- `tests/`

Class folders use scientific names (for example, `Pontederia_crassipes`). Label identity comes from `species_id` in `class_mapping.json` and is carried unchanged through the split folders, the run directories and the export bundle.

### §4 Species scope
**Done.** `metadata/species_catalog.csv` lists 28 species, with GBIF backbone keys resolved live:

| Role | Species |
|---|---|
| Baseline targets | 3 |
| Look-alikes | 7 |
| Unsupported-species test set | 6 |
| Expansion candidates | 12 |

The four ecological-status categories are kept separate. Only the 3 client-scope species are marked `target_invasive`, and every status is `unverified`. Synonym handling follows the GBIF backbone:
- *Monochoria vaginalis* is catalogued as *Pontederia vaginalis*.
- *Clidemia hirta* is catalogued as *Miconia crenata*.

### §6 Acquisition
**Done** for GBIF, through the official occurrence and species APIs. The following are recorded for every image:
- scientific name and accepted taxon key
- original and fetched URL
- source dataset
- creator and rights holder
- per-image license and attribution
- observation ID
- the full original occurrence JSON
- download timestamp
- review status (`pending`)
- `is_geoflora_field_observation = false`

Downloads use rate limiting, retry with backoff, per-species limits, a storage cap and resume support.

*Not implemented:*
- GBIF's asynchronous Darwin Core Archive downloads, which require a GBIF account and credentials.
- Other source APIs. GBIF already aggregates iNaturalist and herbarium datasets.

### §7 Dataset preparation
**Done.** Validation covers:
- readability, resolution, blur, exposure and aspect ratio
- license allow-list
- label and folder consistency
- review status
- SHA-256 exact duplicates and pHash near-duplicates

Observation groups link images that share an occurrence, exact duplicate, near-duplicate, or the same recorder on the same day. Partitions are sticky, so test images never move into training, and `locked_test_groups.txt` preserves historical test isolation. Class balance is reported.

*Observed on the downloaded data:* water hyacinth had 2 exact-duplicate photos posted under different observations, and 6 images in near-duplicate clusters. All are now grouped together. One image failed on resolution.

### §8 Architecture
**Built and exercised in the pilot.** The model is an ImageNet-pretrained MobileNetV2 followed by `Dense(num_classes, softmax)`, where `num_classes` equals the number of eligible classes. Training includes:
- augmentation
- automatic class weights
- early stopping
- checkpoints
- ReduceLROnPlateau
- a fixed seed
- CSV logs and history

Training runs in two phases: the head on a frozen base, then fine-tuning with BatchNorm frozen. The pilot trained in 71 s on a laptop CPU.

### §9 Evaluation
**Built and exercised in the pilot.** All 11 required outputs are produced, plus:
- an exact binomial and an observation-group bootstrap confidence interval
- calibration (ECE, temperature scaling)
- synthetic robustness perturbations
- breakdowns by photo condition (once reviewers tag them)

Unsupported-species thresholds are selected on `val` + `unknown_val` only. The two unknown sets are species-disjoint.

### §10 Documentation
**Built and exercised in the pilot.** The report is generated automatically with every required section. "Observed results" and "Proposed future improvements (not yet tested)" are kept separate, and pilot reports carry a PROVISIONAL banner.

### §11 Integration readiness
**Built.** The export bundle contains:
- `model.keras`
- `class_mapping.json`, `preprocessing.json`, `model_metadata.json` (version, dataset version, SHA-256, threshold, status `candidate_not_activated`) and `supported_species.json`
- `prediction_output_spec.json` (JSON Schema)
- the evaluation report
- `SHA256SUMS.txt`

Nothing is deployed or activated. Predictions contain species IDs and scores only, with no coordinates.

## Pilot findings (PROVISIONAL: unreviewed labels, not reportable as model performance)

| Metric | Value |
|---|---|
| Test accuracy | 36/36 = 100%, 95% exact CI 90.3–100% |
| Validation accuracy | 86.1% (the samples are small and the estimates vary widely) |
| Unsupported-species false acceptance, no rejection | 100% |
| Unsupported-species false acceptance, validation-selected threshold | 27.2% |
| Known species kept at that threshold | 86.1% |
| Known-vs-unknown separation (AUROC) | 0.865 |

**Look-alike confusion without rejection**

| Look-alike | Labelled as | Count |
|---|---|---|
| *Ageratum conyzoides* | *Chromolaena* | 27 of 30 |
| *Pontederia vaginalis* | water hyacinth | 22 of 30 |
| *Mikania micrantha* | *Chromolaena* | 25 of 30 |

With the threshold applied, 43% of *Mikania* images were still accepted.

**Runtime:** 18 ms per image (batch 1, CPU); 24 MB model file.

Experiment tables for Stage 8 are in `reports/provisional/experiments/`.

## Still needed

1. **Label review.** Decided 2026-11-04: the developer, a named non-botanist reviewer, screens each photo against its iNaturalist research-grade identification using the interactive review pages. `review.label_basis` records this, and the thesis must report it as a limitation, not as expert botanical verification. Each class needs at least 60 approved images from at least 30 independent observations. This is the only blocker for Stages 6, 7 and 9.
2. **Philippine ecological-status evidence** for each species, with a citation, verifier and date in the catalog.
3. **More images.** Download more per baseline species (`--max-per-species 150`) to leave room for review rejections. Add more approved look-alike images so the look-alikes can become trainable classes, which addresses research question 2 directly.
4. **Optional:**
   - GeoFlora-style field photos from the Philippines as an extra held-out test set
   - reviewer condition tags, needed for research question 8
   - a decision on CC BY-NC licensing if commercial use is planned

## Update 2026-11-04/05: more data, NISSAP species, 21-class model

**Data and status changes**
- Photos: 9,150 across 32 catalogued species. Review batches 2-4 used the AI-assisted pre-screen, with the reviewer's acceptance.
- Ecological status: 13 species are now `target_invasive`. Each is verified by the developer against the DENR-BMB NISSAP 2020-2030 (citation recorded per species; located and quoted by an AI assistant). *Eucalyptus deglupta* and *Acacia auriculiformis* stay unresolved.

**Models (all exported as `candidate_not_activated`)**

| Bundle | Classes | Test images | Accuracy (95% CI) | Macro F1 |
|---|---|---|---|---|
| geoflora-mnv2-3cls-v2 | 3 | 152 | 97.4% | 0.974 |
| geoflora-mnv2-10cls-v2 | 10 | 485 | 86.4% | 0.868 |
| geoflora-mnv2-21cls-v1 | 21 | 931 | 82.5% (79.9-84.9%) | 0.830 |

*Chromolaena odorata* recall in each model: 96.5% (3-class), 73.7% (10-class), 64.9% (21-class).

The 21-class model's most frequent confusions:
- *Mikania* → *Broussonetia*
- *A. auriculiformis* → *A. mangium*
- *Chromolaena* → *Mikania* / *Ageratum*
