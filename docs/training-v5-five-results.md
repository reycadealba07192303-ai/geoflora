# Five-species v5 experimental training results

Completed October 27, 2026 (Philippine time). Candidate trained, saved and verified in isolation; the live three-species model remains active.

Classes (frozen v5 order): Chromolaena odorata (Hagonoy), Lantana camara (Lantana), Mikania micrantha (Mile-a-minute), Pistia stratiotes (Water Lettuce), Pontederia crassipes (Water Hyacinth). Caladium bicolor is excluded; see [Part 2 finalization](part-2-finalization.md).

## Data and method

Frozen dataset: storage/datasets/curated/v5_part2_final_five_classes (211 unique photos: 141 training, 34 validation, 36 test). Manifest and review-snapshot hashes were rechecked before training, every image checksum matched, and recomputed checksum/observation/near-duplicate groups do not cross partitions.

- Frozen ImageNet MobileNetV2 feature extractor with a new class-balanced softmax head, seed 42, batch 16, Adam 0.001, dropout 0.2.
- Shared preprocessing (`geoflora_ml.inference.preprocess`): Pillow 224x224 RGB, then MobileNetV2 scaling outside the saved model. The inference decoder produces the same tensor as the training original view (unit-tested).
- Train-only augmentation: original, horizontal mirror, +10 degree rotation with brightness x0.9. Validation, test and live inference use the original view only. Augmented views do not add independent photos.
- Checkpoint selection by minimum validation cross entropy: epoch 13 selected; early stopping (patience 8) ended at epoch 21.
- Fine-tuning requested (last 20 backbone layers, learning rate 1e-5, patience 3). Validation loss went 0.9551, 0.9538, 0.9574 against the frozen-head best of 0.9487, so fine-tuning was **not applied** and the frozen-head weights were restored.
- No test-set selection or threshold tuning.

## Held-out results

Top-1 accuracy: **27/36 = 75.00%**. Macro F1: **49.47%**. These scores precede the 65% inference abstention threshold.

| Species | Train / validation / test | Precision | Recall | F1 |
|---|---|---:|---:|---:|
| Chromolaena odorata | 57 / 14 / 14 | 72.73% | 57.14% | 64.00% |
| Lantana camara | 55 / 12 / 15 | 71.43% | 100.00% | 83.33% |
| Mikania micrantha | 5 / 1 / 1 | 0.00% | 0.00% | 0.00% |
| Pistia stratiotes | 3 / 2 / 2 | 0.00% | 0.00% | 0.00% |
| Pontederia crassipes | 21 / 5 / 4 | 100.00% | 100.00% | 100.00% |

Confusion matrix (rows = expected, columns = predicted, same class order):

```text
[[ 8,  6, 0, 0, 0],
 [ 0, 15, 0, 0, 0],
 [ 1,  0, 0, 0, 0],
 [ 2,  0, 0, 0, 0],
 [ 0,  0, 0, 0, 4]]
```

Six Hagonoy photos were predicted as Lantana; the Mikania and both Pistia test photos were predicted as Hagonoy. One to two test images per new class cannot establish dependable performance. The candidate fails the proposed 85% accuracy, 85% macro F1 and 80% per-class recall targets and is **not promoted**. Scores are on a different split from v3 and are not a direct model comparison. Unsupported plants/non-plants can still receive high scores.

## Saved artifacts and checks

- Candidate: storage/models/candidates/mobilenetv2_v5_five_seed42/ with mobilenetv2.keras, class_mapping.json, evaluation.json, test_predictions.json, inference_smoke.json and checksums.json.
- Status: docs/training-v5-status.json (stage completed, reload equivalence passed, activated false).
- Train: `services/ml/.venv/Scripts/python.exe scripts/train_expanded.py --frozen-dataset storage/datasets/curated/v5_part2_final_five_classes --output storage/models/candidates/mobilenetv2_v5_five_seed42 --status docs/training-v5-status.json --fine-tune`. Existing outputs are protected from overwrite.
- Verify: `services/ml/.venv/Scripts/python.exe scripts/verify_expanded_candidate.py` passed: artifact checksums, all frozen image checksums, recomputed split isolation, five real FastAPI photo requests and unchanged active model. Smoke predictions: Hagonoy, Lantana and Water Hyacinth identified correctly; the Mikania photo was identified as Hagonoy (73.9%); the Pistia photo was uncertain (48.7%).
- Loading the model logs a Keras warning about skipped optimizer variables (the saved file carries the unused fine-tune optimizer state). Inference weights are unaffected; reload equivalence passed.
- ML unit tests: 30 passed, including shared-preprocessing and train-only augmentation tests.

Next improvement needs distinct, reviewed Philippine field observations for Mikania and Pistia and better Hagonoy/Lantana separation, plus a fresh evaluation set. Do not repeatedly tune this candidate against the reported test results.
