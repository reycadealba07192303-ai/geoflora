# Weak-class review and controlled training results - 1 November 2026

## Review decisions and eligibility

- The saved interface has **40 observation groups**: 39 approved, 1 rejected, 0 uncertain, and 0 undecided. The 58 image files resolve to **57 approved images** and one rejected image; group-level choices apply to all files in an observation.
- All approvals share the same generic rationale (one unique rationale): "The visible leaf shape, arrangement, and overall plant structure appear consistent with the proposed species identification." This is owner visual review, not independent expert botanical verification.
- Thirty-seven newer approve records have `training_eligible: false`; three earlier approvals predate that field. To honor the explicit request in this turn, these saved approve decisions were used only for this isolated experimental run. This did not change any saved decision, expert-verification status, or automatic-training policy.
- The approved files contain source IDs/URLs, attribution, locality/country, checksums, and CC BY or CC0 license metadata. New images are rights-eligible under the current CC0/CC BY/CC BY-SA rule. No CC BY-NC additions were included.
- Eligibility filters excluded: 18 approved images perceptually matching the frozen dataset (the 19th frozen match belongs to the rejected group), one GBIF copy of the iNaturalist photo, three originals below 320 px on the short side, and one severe-exposure-flagged image. The 4-photo Coccinia observation was approved after the first freeze; the final snapshot includes its image(s) that pass quality checks.
- Final additions: **34 images / 25 observation groups**: Coccinia 24/15 groups; Mikania 10/10 groups; Broussonetia 0/0. All frozen-match records, including historical test overlaps, remain excluded from additions.

## Frozen dataset

- Immutable version: `storage/datasets/curated/auto_6ae5cd74af23d762feaa0889_weakreview_v3_20261101`. Manifest SHA-256: `ab5cd2da63f4eb7f2232634e7d2b0d354de37fbea2ae8d5bed451f22c45d77b9`. It preserves the exact 11-class mapping from `storage\datasets\curated\auto_6ae5cd74af23d762feaa0889`.
- The historical test rows were preserved exactly and not used in training or checkpoint selection. The prior train/validation manifest contained 65 redundant exact-hash rows; these were removed from development partitions (same-partition repeats only).
- New observation groups use a stable SHA-256 group assignment: approximately 80% train, 20% validation. No new test examples were created. New additions: Coccinia 19 train images / 11 train groups and 5 validation images / 4 validation groups; Mikania 8/8 train and 2/2 validation.
- Cross-partition checks for image hash, observation group, and near-duplicate group passed. Every manifest path and SHA-256 matched. Historical test remains 253 image rows.
- Group counts here represent recorded observation/near-duplicate groups, not independent expert-reviewed botanical observations. The historical test has 253 rows, 235 unique file hashes, and 219 such groups; repeated views limit its effective sample size.

| Class | Train images/groups | Validation images/groups | Historical test images/groups | New approved images/groups |
|---|---:|---:|---:|---:|
| antigonon_leptopus | 104/103 | 23/23 | 23/23 | 0/0 |
| broussonetia_papyrifera | 29/28 | 6/6 | 6/6 | 0/0 |
| chromolaena_odorata | 140/113 | 31/26 | 35/20 | 0/0 |
| coccinia_grandis | 123/115 | 28/27 | 23/23 | 24/15 |
| lantana_camara | 125/103 | 34/30 | 31/19 | 0/0 |
| leucaena_leucocephala | 103/103 | 24/23 | 23/23 | 0/0 |
| mikania_micrantha | 110/110 | 25/25 | 25/24 | 10/10 |
| nymphaea | 56/54 | 13/13 | 12/12 | 0/0 |
| pistia_stratiotes | 106/102 | 22/21 | 24/23 | 0/0 |
| pontederia_crassipes | 91/81 | 21/19 | 28/23 | 0/0 |
| spathodea_campanulata | 104/104 | 23/23 | 23/23 | 0/0 |

The frozen v3 dataset contains **1594 rows** after development duplicate-row cleanup, including all 253 historical test rows. New additions account for 34 images in 25 groups. The full per-source review snapshot is in `reviews_snapshot.json`.

## Fine-tuning result

- Candidate saved separately: `storage/models/candidates/mobilenetv2_11class_weakreview_v3_20261101`. The first run (`...weakreview_v2...`) captured the earlier review snapshot; the final v3 run used the subsequently approved Coccinia observation. Both used the same bounded settings and did not improve validation.
- The earlier v2 snapshot had 30 additions / 24 groups; validation loss was 1.20516 initially, then 1.30349 and 1.26549, so its checkpoint also stayed at the source weights. The later v3 pass used 34 additions / 25 groups. This was a data-snapshot update after a new human decision, not a hyperparameter search.
- Initialization: saved 11-class candidate checkpoint; last 20 MobileNetV2 layers unfrozen except BatchNormalization; Adam 1e-5; maximum 8 epochs, patience 2; batch 16; shared conservative train-only augmentation (original, mirror, +10-degree rotation at 0.9 brightness); square-root inverse-frequency class weights clipped to 0.5 to 2.0.
- Final run stopped after 2 epochs. Validation cross-entropy was 1.20516 before, then 1.26617 and 1.27392. The checkpoint-selection rule retained the exact initial weights.

| Validation metric | Before | Selected candidate |
|---|---:|---:|
| Accuracy | 64.80% | 64.80% |
| Macro precision | 62.81% | 62.81% |
| Macro recall | 63.54% | 63.54% |
| Macro F1 | 62.75% | 62.75% |

## Historical held-out comparison

No new blind test set exists. The 253-row historical test partition (235 unique file hashes / 219 groups) was kept out of this fine-tune and used only once after validation-based selection for comparison. It was previously examined and contains repeated images/views, so this is not a fresh independent accuracy claim.

| Metric | Previous 11-class candidate | New candidate |
|---|---:|---:|
| Accuracy | 73.52% | 73.52% |
| Macro precision | 75.48% | 75.48% |
| Macro recall | 73.09% | 73.09% |
| Macro F1 | 73.53% | 73.53% |

### Per-class historical test results

| Class | n | Precision before -> after | Recall before -> after | F1 before -> after |
|---|---:|---:|---:|---:|
| antigonon_leptopus | 23 | 68.00% -> 68.00% | 73.91% -> 73.91% | 70.83% -> 70.83% |
| broussonetia_papyrifera | 6 | 80.00% -> 80.00% | 66.67% -> 66.67% | 72.73% -> 72.73% |
| chromolaena_odorata | 35 | 72.22% -> 72.22% | 74.29% -> 74.29% | 73.24% -> 73.24% |
| coccinia_grandis | 23 | 72.22% -> 72.22% | 56.52% -> 56.52% | 63.41% -> 63.41% |
| lantana_camara | 31 | 81.08% -> 81.08% | 96.77% -> 96.77% | 88.24% -> 88.24% |
| leucaena_leucocephala | 23 | 62.96% -> 62.96% | 73.91% -> 73.91% | 68.00% -> 68.00% |
| mikania_micrantha | 25 | 47.37% -> 47.37% | 36.00% -> 36.00% | 40.91% -> 40.91% |
| nymphaea | 12 | 100.00% -> 100.00% | 91.67% -> 91.67% | 95.65% -> 95.65% |
| pistia_stratiotes | 24 | 68.97% -> 68.97% | 83.33% -> 83.33% | 75.47% -> 75.47% |
| pontederia_crassipes | 28 | 77.42% -> 77.42% | 85.71% -> 85.71% | 81.36% -> 81.36% |
| spathodea_campanulata | 23 | 100.00% -> 100.00% | 65.22% -> 65.22% | 78.95% -> 78.95% |

The three priority classes were unchanged: Mikania precision/recall/F1 **47.37/36.00/40.91%** (n=25); Coccinia **72.22/56.52/63.41%** (n=23); Broussonetia **80.00/66.67/72.73%** (n=6). No new Broussonetia photos were collected in this review set.

Confusion matrix for the new candidate (rows = true class, columns = predicted class; identical to the prior checkpoint):

| | Ant | Brou | Chro | Cocc | Lant | Leuc | Mik | Nym | Pist | Pont | Spath |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Ant | 17 | 0 | 0 | 0 | 2 | 1 | 3 | 0 | 0 | 0 | 0 |
| Brou | 1 | 4 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Chro | 0 | 1 | 26 | 1 | 2 | 0 | 5 | 0 | 0 | 0 | 0 |
| Cocc | 2 | 0 | 2 | 13 | 0 | 3 | 2 | 0 | 1 | 0 | 0 |
| Lant | 0 | 0 | 0 | 0 | 30 | 0 | 0 | 0 | 1 | 0 | 0 |
| Leuc | 1 | 0 | 2 | 0 | 0 | 17 | 0 | 0 | 2 | 1 | 0 |
| Mik | 2 | 0 | 5 | 4 | 0 | 2 | 9 | 0 | 1 | 2 | 0 |
| Nym | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 11 | 0 | 0 | 0 |
| Pist | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 20 | 4 | 0 |
| Pont | 0 | 0 | 0 | 0 | 0 | 2 | 0 | 0 | 2 | 24 | 0 |
| Spath | 1 | 0 | 0 | 0 | 3 | 2 | 0 | 0 | 2 | 0 | 15 |

## System checks and limitations

- `smoke_identification.py` passed through Next.js -> FastAPI -> active v3 model: Chromolaena and Lantana returned identified species with confidence (0.902 and 0.837); Water Hyacinth returned uncertain (0.560, threshold 0.80). Upload validation, outages, timeout, malformed response, and proxy-failure cases returned expected errors. End-to-end p95 was 222.6 ms in this local run.
- `smoke_unknown_plant_review.py` passed: uncertain result -> user suggestion/description stays unverified -> pending owner report -> unauthorized action denied -> admin verification -> consented training job queued but not run. Active model hash remained unchanged.
- Targeted ML checks: 7 passed (license and preprocessing). New scripts passed `py_compile`. Dataset integrity: 1,594 rows, unchanged 253 historical test rows, all checksums passed, zero cross-split image/group/near-duplicate keys. Candidate artifacts: 4 checksums passed.
- Active model remains `mobilenetv2_v3_seed42`, three classes, test figure 87.18% on 39 rows; no model or mapping was activated from this work. The new candidate retained the previous 11-class weights because validation did not improve; accuracy did not improve.
- Active artifact hashes are unchanged: model `7b092e3209f886a3ade0656b14af68a0d671905646b98e0b6be9a3153742e5d1`, mapping `097e40e340422b06fda4ec1faca7512207a0c57b98e2ec1db59919f8acbdd452`. The saved final experimental model is `5fba153db608440bb2f5f611b1ecf961d5c71f9a4574b2644df4791156a56485`.
- Fine-tuning reused the saved checkpoint and the original development train rows, whose corpus includes CC BY-NC records under the prior non-commercial research approval; the 34 new additions themselves were CC BY/CC0. Keep the resulting candidate local/research-only until permitted client use is confirmed. The 95% target is not independently verified.

## Next action

Do not promote either weak-review candidate. Seek a botanical reviewer to validate species and field context (especially the repeated generic rationales), add independently reviewed Mikania/Coccinia observations and new Broussonetia images, then run future experiments against grouped validation. Obtain a genuinely new blind Philippine test set before making a delivery accuracy claim.
