# GeoFlora-ML-Lab integration (5 November 2026)

This document records how the model trained in GeoFlora-ML-Lab became the live GeoFlora model, and how to repeat or undo the change.

## What changed

**1. The ML lab now lives in `ml-lab/`.**
- It contains the full standalone research workspace: code, configs, 9,150 photos with per-image provenance and review decisions, splits, trained runs, exported bundles, evaluation reports and the lab demo.
- See `ml-lab/README.md` and `ml-lab/reports/IMPLEMENTATION_STATUS.md`.
- The lab's own `.gitignore` excludes photos and model weights. Its `.venv` is local.

**2. The live model is `geoflora-mnv2-21cls-v1`.** The developer chose it on 5 November 2026. It recognises 21 species:
- **13 target invasive species**, each verified against DENR-BMB NISSAP 2020-2030:
  - *Chromolaena odorata*, *Lantana camara*, *Pontederia crassipes*
  - *Mikania micrantha*, *Imperata cylindrica*
  - *Leucaena leucocephala*, *Spathodea campanulata*, *Piper aduncum*, *Salvinia molesta*
  - *Broussonetia papyrifera*, *Acacia mangium*, *Swietenia macrophylla*, *Gmelina arborea*
- **8 non-target classes**, used to tell the targets apart:
  - Look-alikes: *Ageratum conyzoides*, *Lantana montevidensis*, *Duranta erecta*, *Pistia stratiotes*, *Pontederia vaginalis*, *Limnocharis flava*
  - Reforestation trees whose Philippine status is unresolved: *Eucalyptus deglupta*, *Acacia auriculiformis*

**3. The web app shows information for all 21 species.**
- `apps/web/src/features/identification/species-information.ts` is now generated from `ml-lab/metadata/species_descriptions.json` and the species catalog. It includes identifying features, look-alikes, NISSAP status and references.
- The Identify page lists the live model's species from the health endpoint.
- The result screen shows a **Target invasive** or **Not a GeoFlora target species** label. For non-target classes it no longer claims the plant is non-invasive.
- The result screen lists other possibilities. The hard-coded "three species" text is gone.

## Evaluation (independent lab test split; threshold chosen on validation only)

**Overall:**

| Measure | Value |
|---|---|
| Test photos | 931, from 861 observation groups |
| Accuracy | **82.5%** (95% CI 79.9-84.9%) |
| Accuracy re-scored through `services/ml` `PlantPredictor` | 83.1% |
| Macro F1 | 0.830 |
| Suggestion threshold | 0.686 (max softmax, Youden on validation) |
| Test photos above the threshold | 60.4% |
| Unsupported species accepted at the threshold | 22.8% (408 photos, 5 species) |

**Per-class recall:** 100% *Imperata*, 98% *Piper*, 95% *Eucalyptus*, 96% *Spathodea*, 94% *Lantana camara*, 88% *Pontederia crassipes*, 86% *Swietenia*, 85% *A. mangium*, 84% *Leucaena*, 83% *Gmelina*, 80% *Salvinia*, 69% *Mikania* and *Broussonetia*, **65% *Chromolaena***.

**The model does not meet `model_promotion.py`'s automatic gates** (accuracy ≥85%, macro F1 ≥85%, every class recall ≥80%). The developer approved the installation anyway, and `storage/models/active_model.json → quality_gate_override` records each gate that was not met, together with the approver and rationale.

**Known behaviour:**
- Plants outside the 21 classes can still be accepted. For example, a red hibiscus (gumamela) photo was suggested as African tulip tree with a score of 72.5%.
- *Chromolaena* is often confused with *Mikania* and *Ageratum*.
- Every report still needs administrator review.

## Labels and status: what they are based on

- **Labels:** iNaturalist research-grade photos from GBIF. Each one was screened photo by photo and approved by a named non-botanist reviewer (Reyca de Alba), assisted by an AI pre-screen. This is not expert botanical verification.
- **Target status:** the developer verified it from the NISSAP citation; an AI assistant located and quoted the citation.
- **Species descriptions:** drafts that a botanist has not yet checked.

## How to repeat with a new lab model

```powershell
# 1. In ml-lab: train, evaluate and export (see ml-lab/README.md), then package for GeoFlora
cd ml-lab
.\.venv\Scripts\python.exe scripts\package_for_geoflora.py --bundle models\exported\<version> --geoflora ..
.\.venv\Scripts\python.exe scripts\export_species_information.py --candidate ..\storage\models\candidates\<version> --out ..\apps\web\src\features\identification\species-information.ts

# 2. In the project root: install with a backup, then restart the inference service
cd ..
.\services\ml\.venv\Scripts\python.exe scripts\install_lab_model.py --candidate storage\models\candidates\<version> --approved-by "Name" --rationale "Why"
```

- `package_for_geoflora.py` removes the lab model's internal Rescaling layer, because `services/ml` already applies MobileNetV2 `preprocess_input`. It also checks that the adapted model matches the lab model (maximum difference below 1e-4).

## How to undo

The model that was live before (`mobilenetv2_v3_seed42`) is saved in `storage/models/previous/20261104T172339Z/`. To restore it:

```powershell
.\services\ml\.venv\Scripts\python.exe scripts\model_promotion.py --rollback-to storage\models\previous\20261104T172339Z --reason "..."
```

A copy of the pre-integration source code is in `C:\Users\reyca\geoflora-backups\geoflora-src-before-ml-lab-transfer-20261105.zip`.

## Checks run

- `services/ml` tests: 53 passed. The active-model embedding test now checks the active model against `active_model.json` instead of a hard-coded v3 version.
- `apps/web` typecheck: passed.
- Browser check on an isolated copy of the web app (port 5174) with a disposable database, which was dropped afterwards:
  - start page
  - *Lantana* result (target)
  - *Mikania* result (target)
  - *Ageratum* result (uncertain, AI-suggestion path)
  - hibiscus result (false acceptance, noted above)

## Follow-up fixes (same day)

- **Reference re-indexing with the new model's embedding version failed** with "Updating the path '_id' would create a conflict at '_id'". The cause was a latent bug in `apps/web/src/lib/verified-references.ts`: the upsert listed `_id` in both `$set` and `$setOnInsert`. `_id` is now written only on insert.
- **One live report submission returned 503 (`ValidationError`).** It could not be reproduced: identified and uncertain reports both saved on the isolated test app, and a later live report saved normally. The sightings route now logs the names of the failing fields (never their values), so a repeat can be diagnosed.
