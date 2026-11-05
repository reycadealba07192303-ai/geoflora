# MobileNetV2 expansion up to 50 species — readiness snapshot

Date: 2026-11-01. This snapshot reuses the existing GeoFlora catalog, review, licensing, split, training, evaluation, and promotion pipeline. No model was trained, modified, or promoted.

## Deliverables

- [Folder-based dataset export](../storage/datasets/experiments/geoflora_mobilenetv2_up_to_50_20261101/README.md)
- [Training configuration](../storage/datasets/experiments/geoflora_mobilenetv2_up_to_50_20261101/training_config.json)
- [50-slot candidate roster and per-species inventory](../storage/datasets/experiments/geoflora_mobilenetv2_up_to_50_20261101/proposed_50_species_roster.csv)
- [Prepared baseline manifest](../storage/datasets/experiments/geoflora_mobilenetv2_up_to_50_20261101/source_manifest.csv)
- [Images excluded from development](../storage/datasets/experiments/geoflora_mobilenetv2_up_to_50_20261101/excluded_from_development.csv)
- [Machine-readable readiness summary](../storage/datasets/experiments/geoflora_mobilenetv2_up_to_50_20261101/dataset_readiness.json)
- Rebuild with `services/ml/.venv/Scripts/python.exe scripts/species_catalog/prepare_mobilenetv2_50_readiness.py`.

## Actual class readiness

The folder export uses the frozen v3 class mapping, in the same neuron order as the preserved v3 model:

1. Chromolaena odorata
2. Lantana camara
3. Pontederia crassipes (water hyacinth)

The 50-slot research roster contains these three baseline entries and 47 proposed additions. The additions comprise **6 GRIIS source-flagged invasive candidates still awaiting project ecological approval** and **41 introduced-species candidates whose invasive status is unverified**. The source queue contains 75 candidates after active-name and known-conflict exclusions; the chosen 47 are for evidence/review prioritization only. They are not classes in `class_mapping.json`.

Across the 47 proposed additions, existing PH staging contains 1,007 candidate records, 954 exact-unique class images, and 730 observation groups (per-class sums). The current strict training-license screen passes for 467 images after exact historical-test exclusion. **Human-approved labels: 0; ecological approvals: 0; eligible new training classes: 0.** Community/research-grade identifications and source invasive flags do not satisfy these gates. The per-species counts, source IDs, citations, licenses, review state, ecological evidence, and next action are in the roster CSV.

Known conflicts are excluded from this proposed target roster, including native-status/origin holds and unresolved exact-name records. Coccinia grandis is held for its documented cryptogenic-status conflict. Nymphaea remains a separate non-target look-alike research group; it is not an accepted species label or an invasive target class in this roster.

## Folder dataset and split safety

The source v3 corpus has 243 owner-attested images: 166 train, 38 validation, and 39 historical test. The prepared `train/`, `val/`, and `test/` folders contain only development data that avoids every curated historical test hash, observation key, and perceptual near-match. Historical test photos are not copied into the new `test/`; those folders are empty pending a fresh blind set.

| Existing class | Safe train | Safe validation | Fresh test |
|---|---:|---:|---:|
| Chromolaena odorata | 9 | 4 | 0 |
| Lantana camara | 28 | 6 | 0 |
| Pontederia crassipes | 11 | 0 | 0 |

The strict all-history boundary held out 413 unique historical test hashes and 1,043 normalized observation-group keys. It excluded 138 exact-overlap baseline train/validation rows, 8 perceptual near-duplicates, and reserved the 39 original v3 test rows. This explains why the export is not trainable: Pontederia has no safe validation image, and there is no untouched independent test set. The old v3 test partition remains preserved at its original path and was not re-evaluated.

New-source candidates are not copied into folders unless review and project ecological approval pass. That prevents research-grade community labels, introduced-only records, license-ineligible images, and conflict-held taxa from becoming class labels by their directory names.

## Reused training configuration

The existing `scripts/train_expanded.py` implements ImageNet-pretrained MobileNetV2 with 224×224 inputs, the shared inference preprocessing, train-only augmentation, class-weighted batches, minimum-validation-loss checkpoint selection, early stopping, and optional validation-gated backbone fine-tuning. Its head is `Dense(len(classes), softmax)`, so the actual class mapping determines the neuron count; the 50-class ceiling does not force 50 outputs.

The prepared config has `maximum_classes=50`, actual mapping size **3**, and `training_enabled=false`. It would produce a new candidate under `storage/models/candidates/` only after a new frozen dataset has approved class labels, appropriate group-aware train/validation partitions, and an untouched independent Philippine test set. Look-alike classes require a separate role and ecological/diagnostic rationale.

## Model status and reason training did not run

- Active model: `mobilenetv2_v3_seed42`, three classes, threshold 0.80. Its model artifact and mapping remain unchanged.
- Proposed additions passing all gates: **0 of 47**.
- Trainable safe baseline data for a new candidate: 48 images, but only 2 classes appear in validation.
- Fresh independent test images: 0.
- New training run: **not justified, not started**. A three-output rerun would not expand species coverage and would lack valid splits.
- Model evaluation metrics: none for this preparation snapshot. Existing historical v3 test accuracy remains 87.18% on 39 images; it is not a new or independent result for this proposed expansion.

The live v3 model has previously accepted unsupported-species photos at a material rate, including a 37% acceptance rate in its earlier validation-threshold unsupported-input probe. Softmax confidence is not treated as species verification; result presentation remains tentative and admin review remains separate.

## Next gating data

Each addition needs accepted-name/taxonomic reconciliation, a reviewed Philippine invasive-status citation (or a separately justified look-alike role), individual image rights and attribution, human visual label review, distinct observation groups, holdout/near-duplicate clearance, enough reviewed records for each split, and fresh blind Philippine test observations. The current project has candidates to review, but it does not yet have a scientifically approved 50-class training corpus.
