# 11-class model candidate reconciliation

Prepared: 2026-11-01 (Asia/Manila)

## Artifact status

The 11-class experiment was not a plan-only item. Its frozen dataset and candidate still exist:

- Dataset: `storage/datasets/curated/auto_6ae5cd74af23d762feaa0889/` (manifest, metadata, review snapshot, mapping, species registry; 1,625 manifest records).
- Original candidate: `storage/models/candidates/auto_6ae5cd74af23d762feaa0889/` (Keras model, 11-class mapping, species list, evaluation, predictions and checksums).
- Fine-tuning attempt from this reconciliation: `storage/models/candidates/mobilenetv2_11class_finetune_v1_20261101/` (new isolated output, mapping, evaluation and checksums). It was not activated.
- Machine-readable experiment status: `storage/models/candidates/mobilenetv2_11class_finetune_v1_20261101/evaluation.json` and `docs/11class-finetune-status-2026-11-01.json`.

Active local serving remains `mobilenetv2_v3_seed42`, three classes, threshold 0.80. Active model SHA-256 remains `7b092e3209f886a3ade0656b14af68a0d671905646b98e0b6be9a3153742e5d1`; active mapping SHA-256 remains `097e40e340422b06fda4ec1faca7512207a0c57b98e2ec1db59919f8acbdd452`.

The previous delivery stabilization summary focused on what was active and smoke-tested for tomorrow's delivery. It should also have mentioned the inactive 11-class artifact; omitting it made the account incomplete. The candidate was excluded from delivery because it was never promoted, scored 73.52% accuracy / 73.53% macro F1 (below its 85% quality gates), and did not beat v3 on the fixed three-class comparison. The broader model's existence does not change the deployed model.

## Frozen data counts

The collection report records 1,463 newly usable Philippine-source field-photo records. The frozen 11-class manifest contains 1,625 total records after combining them with existing images and two approved user reports. It partitions them into 1,124 training, 248 validation, and 253 test images. “Approved” here means the dataset's recorded review/source-label policy, not independent expert botanical certification for every image. The 1,419 iNaturalist research-grade records are community-agreed IDs; provenance uses source-country filters and selected owner attestations.

Counts below are manifest images and distinct `group_id` values per split. These IDs group source observations (for iNaturalist, usually observation IDs); they do not establish independent sites, photographers, or botanical verification.

| Class | Train images / groups | Validation images / groups | Test images / groups | Test recall |
|---|---:|---:|---:|---:|
| *Antigonon leptopus* | 104 / 54 | 23 / 13 | 23 / 17 | 73.91% |
| *Broussonetia papyrifera* | 29 / 24 | 6 / 6 | 6 / 5 | 66.67% |
| *Chromolaena odorata* | 153 / 119 | 33 / 29 | 35 / 21 | 74.29% |
| *Coccinia grandis* | 104 / 72 | 23 / 16 | 23 / 14 | 56.52% |
| *Lantana camara* | 145 / 110 | 34 / 22 | 31 / 22 | 96.77% |
| *Leucaena leucocephala* | 103 / 71 | 24 / 21 | 23 / 19 | 73.91% |
| *Mikania micrantha* | 107 / 74 | 23 / 16 | 25 / 17 | 36.00% |
| *Nymphaea* spp. (look-alike class) | 56 / 48 | 13 / 12 | 12 / 8 | 91.67% |
| *Pistia stratiotes* | 112 / 97 | 24 / 23 | 24 / 22 | 83.33% |
| *Pontederia crassipes* | 103 / 71 | 22 / 16 | 28 / 16 | 85.71% |
| *Spathodea campanulata* | 108 / 81 | 23 / 19 | 23 / 20 | 65.22% |
| **Total** | **1,124 / 821** | **248 / 193** | **253 / 181** | — |

The frozen split metadata reports zero cross-partition exact-image, observation-group, or near-duplicate-group keys. It remains a source-observation split; it does not prove geographical/site independence.

## Original head-only evaluation

The 11-class model was trained with an ImageNet MobileNetV2 backbone frozen, a dropout plus softmax head, class weights and train-only augmentation. Best head epoch was 4 by minimum validation cross-entropy. Its previous single evaluation reported 73.52% test accuracy and 73.53% macro F1 on 253 images. Test recall was lowest for Mikania 36.00%, Coccinia 56.52%, and Broussonetia 66.67%; Water Hyacinth recall was 85.71% (24/28).

Validation performance recomputed from the preserved model before fine-tuning was 65.73% accuracy, 63.33% macro F1, and 1.1920 cross-entropy. Lowest validation recalls included Broussonetia 16.67% (1/6), Mikania 52.17% (12/23), Chromolaena 54.55% (18/33), and Coccinia 56.52% (13/23). The validation split was used in head training and is not an independent performance estimate.

Observed error patterns in the saved test confusion matrix/report:

- Mikania was confused with Chromolaena (5), Coccinia (4), and other classes. The source review attributes this to overlapping white flower-head/foliage appearance and climbing-vine views; the metric alone cannot prove visual cause.
- Pistia and Water Hyacinth were confused with each other (4 Pistia images predicted Water Hyacinth; 2 Water Hyacinth images predicted Pistia).
- Small and uneven class support is material: training count ranges from 29 Broussonetia images to 153 Chromolaena images, a 5.3× difference. The training code used class weighting, but weighting cannot create visual diversity or label certainty.
- 1,419 of 1,625 records use community research-grade labels; 164 are existing owner approvals, 29 AI-screened staging labels, 11 owner-batch approvals, and 2 AI-reviewer/classifier-agreement reports. Label provenance is mixed and is not equivalent to expert verification.

## One bounded fine-tuning attempt

The original 11-class artifact's `fine_tune` metadata says `requested: false`, `applied: false`; the October 31 run was head-only. During this reconciliation, one new pass started from the saved head-only 11-class Keras artifact and the frozen manifest. It unfreezed the final 20 MobileNetV2 layers with BatchNormalization layers frozen, learning rate `1e-5`, maximum 8 epochs, patience 3, and batch size 16. Checkpoint selection was fixed to minimum validation cross-entropy. The test partition was not loaded until checkpoint selection ended.

| Selected checkpoint | Validation accuracy | Macro F1 | Cross-entropy |
|---|---:|---:|---:|
| Before fine-tuning | 65.73% | 63.33% | 1.1920 |
| After selected checkpoint | 65.73% | 63.33% | 1.1920 |

Fine-tuning epochs 1–3 produced cross-entropy 1.2650, 1.3244, and 1.4041, all worse than the starting checkpoint. Epoch 2 did raise validation accuracy/macro F1 to 69.76% / 68.48%, but increased cross-entropy to 1.3244. Because minimum cross-entropy was the prespecified selection rule and loss worsened at each epoch, the original checkpoint weights were restored. Fine-tuning was genuinely attempted but **not retained as an improvement**.

After selection, the model was scored once on the already-used 253-image historical test split: 73.52% accuracy / 73.53% macro F1, unchanged because the source checkpoint was restored. This is a repeated score on a previously inspected split, **not a fresh independent test or a blind result**. No model selection was based on this score. Do not interpret it as evidence of independent Philippine field accuracy.

## Fine-tuning code correction

Review found the reusable `scripts/train_expanded.py --fine-tune` path set child MobileNetV2 layers trainable while the parent backbone remained `trainable=False`. Keras therefore would not expose those backbone weights as trainable. That path is now corrected to enable the parent, freeze all layers, unfreeze only the last 20 non-BatchNormalization layers, and restore the frozen parent if validation loss fails to improve. The actual experiment used the same corrected trainability policy. No new training was run after this one-shot experiment.

## Unknown-plant review/training workflow

`scripts/smoke_unknown_plant_review.py` exercised the current Next.js and active v3 model with a disposable MongoDB database:

1. Real Water Hyacinth CNN output was uncertain (score 0.560237; threshold 0.80; species `null`).
2. Contributor supplied a description/name suggestion. The saved report stayed `unknown`, pending review, and training candidate `pending_review`.
3. Another contributor could not access the report; contributor could not use the admin review endpoint.
4. Admin fixture approved a supported label with rationale/citation. The record became `verified` and consented candidate `approved`.
5. The report entered a queued training job. The disposable database was dropped after the check; the worker was deliberately not run so the single approved fine-tuning attempt was not followed by a second training run.

The independent worker-path smoke already present in `docs/roles-training-smoke.json` documents a synthetic, isolated report approval that was exported, trained, evaluated, and kept from activation. That earlier test confirms the worker can train from eligible records; it is synthetic pipeline evidence, not botanical evidence. Automatic training will not make a new class usable from one isolated photo: class split eligibility requires at least three independent source/near-duplicate groups.

## Test results and delivery

- `services/ml/tests`: **37 passed**.
- Python syntax check for fine-tuning, unknown-workflow smoke, and reusable training entry point: passed.
- Unknown-plant web/database workflow smoke: passed; queued training job, not executed.
- Active v3 model, active class mapping, and activation metadata hashes stayed unchanged.

For tomorrow, safely deliver the existing three-class v3 service only, as experimental decision support, with its honest historical 87.18%/39-image result and Water Hyacinth recall limitation. Do not deliver or activate the 11-class candidate as a production model. The 11-class model is a useful research candidate but misses the 85% promotion thresholds, has weak Mikania/Coccinia performance, and lacks a fresh blind Philippine test. A new experiment would need better reviewed samples and a sealed new test set before promotion decisions.
