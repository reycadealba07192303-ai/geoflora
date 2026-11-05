# Active MobileNetV2 inference and evaluation

Updated: October 31, 2026

## Scope and status

Evaluated the locally active `mobilenetv2_v3_seed42` artifact without retraining, replacing, or promoting a model. The file `storage/models/mobilenetv2.keras` has the same SHA-256 as the preserved candidate artifact. The active Keras file and class mapping were not changed.

## Live inference integration

`scripts/test_live_cnn_integration.py` submitted a held-out v3 Water Hyacinth test photo through the live Next.js `/api/identify` route. The response was `method: model`, `model_version: mobilenetv2_v3_seed42`, `status: uncertain`, confidence `0.560237`, and no species suggestion. The test rejects verified-reference results and compared the response score and species with a fresh prediction from the locally loaded active Keras artifact; both matched. A temporary local test account, session, and identification record were removed in cleanup. This is an integration check, not an accuracy sample.

The inference implementation calls the loaded Keras model's `predict()` on MobileNetV2-preprocessed input. The reference-photo lookup remains a separate early-return path and was not counted in evaluation.

## Split metrics

Training and validation accuracy were recomputed from the saved active model and the frozen v3 manifest; those accuracy values were not stored in the original training history. The historical evaluation artifact stores the test metrics. The selected checkpoint was epoch 17 by minimum validation loss (0.4782); training stopped after 22 epochs.

| Split | Images | Recomputed top-1 accuracy |
|---|---:|---:|
| Train | 166 | 98.80% |
| Validation | 38 | 78.95% |
| Held-out v3 test | 39 | 87.18% (34/39) |
| Test, one representative per recomputed near-duplicate group | 24 | 87.50% (21/24) |

The 39-row test split is held out from training and tuning partitions in the manifest, but has been inspected in earlier evaluations and is not a fresh blind cohort. Its labels were owner-approved rather than independently botanically certified, row-level Philippine provenance is not independently verified, and visual review found specimen-sheet images in the corpus. Therefore **87.18% is the measured accuracy on this historical curated split; current real-world Philippine field-photo accuracy is not established**. The 24-group figure is a sensitivity check after near-duplicate deduplication, not a replacement benchmark.

### Per-species test results

| Species | Test images | Precision | Recall | F1 |
|---|---:|---:|---:|---:|
| Chromolaena odorata (Hagonoy) | 14 | 86.67% | 92.86% | 89.66% |
| Lantana camara | 17 | 85.00% | 100.00% | 91.89% |
| Pontederia crassipes (Water Hyacinth) | 8 | 100.00% | 50.00% | 66.67% |

Confusion matrix, rows = actual and columns = predicted, in the order above:

```text
13  1  0
 0 17  0
 2  2  4
```

Owner-approved train images and source observation groups:

| Species | Train images | Observation groups |
|---|---:|---:|
| Hagonoy | 64 | 42 |
| Lantana | 79 | 55 |
| Water Hyacinth | 23 | 19 |

These are owner-approved labels, **not independent botanical verification**.

## Split isolation and duplicate structure

The v3 audit found zero cross-partition exact-hash, observation-group, stored near-duplicate-group, or recomputed near-duplicate-group keys. That means no detected train/validation/test leakage across partitions. However, there are repeated rows inside each partition: train has 50 extra rows from repeated observation groups and 62 extra near-duplicate rows; validation has 8 and 16; test has 8 and 15. The test has 31 distinct observation IDs and 24 recomputed near-duplicate groups across 39 rows, so its effective independent support is smaller than 39 photos.

## Error and unsupported-input review

The main closed-set weakness is Water Hyacinth: 4 of 8 test rows were assigned to another supported class (2 Hagonoy, 2 Lantana). Visual inspection showed duplicated/near-duplicate water-hyacinth close-ups among these errors. One Hagonoy test error was a pressed herbarium specimen. This suggests both limited class coverage and an evaluation mix that does not consistently match field uploads; the images do not establish a single definitive visual cause for every error.

For an exploratory open-set check, 8 held-out owner-approved non-target photos were run separately (7 Mikania, 1 Pistia/Water Lettuce). The model always had one of its three classes as its top candidate; at the active 0.80 threshold, 2/8 were accepted as a supported species (one Mikania as Lantana and one Pistia as Water Hyacinth), while 6/8 were marked uncertain. This sample is far too small to estimate a reliable false-accept rate, but confirms that the classifier can mistake unsupported plants for a supported class.

## Interpretation and recommendations

The 20-point train-to-validation gap (98.80% vs 78.95%) is strong evidence of overfitting. Training counts are imbalanced (64 / 79 / 23) and Water Hyacinth has the fewest images and weakest recall, though the original run did apply inverse-frequency class weights. The test errors also show Hagonoy/Lantana confusion and unsupported plants receiving confident scores.

At least 95% is **not supported or realistically demonstrated by the current dataset**. The next evaluation-quality gains should come from independently reviewed, diverse field observations—especially Water Hyacinth—plus removal of specimen/duplicate records and a newly frozen blind test cohort. Do not tune against the historical test results. No architecture or training change was made in this evaluation.

## Health error sanitization

FastAPI `/health` now returns a generic public reason when the model is unavailable. Detailed loader exceptions and missing artifact paths remain in server logs; public `/predict` errors also use a generic unavailable message. The inference unit tests verify health sanitization and all 11 tests passed. The already-running local FastAPI process must be restarted before it serves this code change; no model deployment or model replacement was performed.
