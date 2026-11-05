# Frozen-backbone classification-head experiment - 1 November 2026

## Why this run was distinct

The two earlier weak-review experiments made the classification head trainable together with the last 20 MobileNetV2 layers. Validation loss did not improve and the original checkpoint weights were restored. There was no saved head-only run. This experiment reset the Dense classification head, froze the complete MobileNetV2 backbone, and selected the head using the final dataset development validation partition.

## Protocol

- Dataset: `storage/datasets/curated/auto_6ae5cd74af23d762feaa0889_weakreview_v3_20261101` (34 approved additions: Coccinia 24/15 groups, Mikania 10/10 groups; no new Broussonetia).
- Training: 1,064 existing train images plus 27 approved additions; 3,273 train-only views after conservative augmentation. Validation: 250 images / 194 groups.
- The MobileNetV2 backbone remained frozen. A fresh Dropout(0.2) + Dense(11, softmax) head used Adam at 1e-3, batch size 16, square-root inverse-frequency class weights clipped to 0.5-2.0, up to 60 epochs, and patience 8. Selected checkpoint: minimum validation cross-entropy.
- Historical test rows were checked only in manifest metadata for split isolation (253 rows); test image files were not opened. No test metrics or thresholds were calculated.

## Development validation result

| Metric | Original 11-class checkpoint | Fresh head candidate | Change |
|---|---:|---:|---:|
| Accuracy | 64.80% | 63.60% | -1.20 pp |
| Cross-entropy loss | 1.2052 | 1.1944 | -0.0108 |
| Macro precision | 62.81% | 64.47% | +1.66 pp |
| Macro recall | 63.54% | 61.39% | -2.14 pp |
| Macro F1 | 62.75% | 61.46% | -1.29 pp |

The selected head reached its lowest validation loss at epoch 3 (1.19439); after eight consecutive non-improving epochs, early stopping ended at epoch 11. Accuracy and macro F1 declined, so evidence is mixed and does not support further backbone fine-tuning.

### Per-class validation scores

| Class | n | Precision baseline -> head | Recall baseline -> head | F1 baseline -> head |
|---|---:|---:|---:|---:|
| antigonon_leptopus | 23 | 68.18% -> 59.26% | 65.22% -> 69.57% | 66.67% -> 64.00% |
| broussonetia_papyrifera | 6 | 16.67% -> 50.00% | 16.67% -> 16.67% | 16.67% -> 25.00% |
| chromolaena_odorata | 31 | 65.38% -> 46.51% | 54.84% -> 64.52% | 59.65% -> 54.05% |
| coccinia_grandis | 28 | 57.69% -> 58.06% | 53.57% -> 64.29% | 55.56% -> 61.02% |
| lantana_camara | 34 | 85.19% -> 88.46% | 67.65% -> 67.65% | 75.41% -> 76.67% |
| leucaena_leucocephala | 24 | 67.74% -> 67.74% | 87.50% -> 87.50% | 76.36% -> 76.36% |
| mikania_micrantha | 25 | 37.50% -> 50.00% | 48.00% -> 44.00% | 42.11% -> 46.81% |
| nymphaea | 13 | 81.25% -> 80.00% | 100.00% -> 92.31% | 89.66% -> 85.71% |
| pistia_stratiotes | 22 | 63.64% -> 68.75% | 63.64% -> 50.00% | 63.64% -> 57.89% |
| pontederia_crassipes | 21 | 80.95% -> 73.68% | 80.95% -> 66.67% | 80.95% -> 70.00% |
| spathodea_campanulata | 23 | 66.67% -> 66.67% | 60.87% -> 52.17% | 63.64% -> 58.54% |

Priority classes: Mikania F1 **42.11% -> 46.81%** (recall 48.00% -> 44.00%, n=25); Coccinia **55.56% -> 61.02%** (recall 53.57% -> 64.29%, n=28); Broussonetia **16.67% -> 25.00%** (recall unchanged at 16.67%, n=6). These are validation-only changes; Broussonetia has just six validation examples, so its apparent gain is highly uncertain.

## Conclusion

- Saved the candidate separately as `storage/models/candidates/mobilenetv2_11class_head_weakreview_v1_20261101`. Model SHA-256: `b7942b4ecace07d7beb1b7dbdc25bb8704e7521efce35fd1ed29721d02a19ff0`.
- The head-only model slightly improved validation loss but reduced accuracy by 1.20 percentage points and macro F1 by 1.29 points. It was not promoted. No backbone fine-tuning followed.
- The 95% target and independent test accuracy remain unverified. The existing 253-row test set was not touched; a new blind test set is still required for an independent claim.
- Active model remains `mobilenetv2_v3_seed42` with unchanged model SHA-256 `7b092e3209f886a3ade0656b14af68a0d671905646b98e0b6be9a3153742e5d1` and mapping SHA-256 `097e40e340422b06fda4ec1faca7512207a0c57b98e2ec1db59919f8acbdd452`.
- Stop further retraining until the weak-class data improve: seek botanical review of current generic rationales, collect independently verified Mikania/Coccinia field groups and Broussonetia photos, and build a larger grouped validation set. The original development corpus contains CC BY-NC material; this candidate remains local/research-only pending client-use confirmation.
