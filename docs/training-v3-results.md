# MobileNetV2 v3 baseline results

Training completed October 23, 2026 (Asia/Manila). Candidate only; not activated.

- 243 owner-approved images: 166 train, 38 validation, 39 test.
- Seed 42; frozen ImageNet backbone; weighted classifier head.
- 22 epochs run; epoch 17 selected using minimum validation loss.
- No detected cross-partition checksum, observation, or recomputed near-duplicate group leakage.
- Top-1 test accuracy: 34/39 = 87.18%. This excludes abstention/threshold decisions.

| Species | Precision | Recall | F1 | Test images |
|---|---:|---:|---:|---:|
| chromolaena_odorata | 86.67% | 92.86% | 89.66% | 14 |
| lantana_camara | 85.00% | 100.00% | 91.89% | 17 |
| pontederia_crassipes | 100.00% | 50.00% | 66.67% | 8 |

Macro F1: 82.74%. Weighted F1: 85.91%.

Confusion matrix (rows = actual, columns = predicted; class order as above):

```text
13  1  0
 0 17  0
 2  2  4
```

## Validation and limits

Saved model reload equivalence passed. Existing PlantPredictor accepted the model and mapping; a real FastAPI in-process photo request returned HTTP 200. The sampled water-hyacinth photo ranked correctly but was uncertain (0.5602, default threshold 0.65), demonstrating that top-1 accuracy is not the same as accepted-result accuracy. One request took about 0.77 seconds; this is not an end-to-end latency benchmark. All 27 ML tests and pip check passed after installing TensorFlow 2.17.1.

The proposed accuracy target (>=85%) was met, but macro F1 (>=85%) and each-class recall (>=80%) were not: water-hyacinth recall is 50% on eight test images. The candidate does not meet the proposed model-quality criteria and was not promoted to default inference paths. Do not claim deployment readiness or tune repeatedly against these test results.

Labels were approved from owner attestation, not independent botanical verification. Per-record Philippine provenance remains unverified. Unsupported/non-plant inputs, calibration, threshold tuning, augmented/fine-tuned training and intended-user evaluation are outstanding. More diverse independently reviewed water-hyacinth observations and a fresh prospective evaluation set are recommended before final validation.

## Artifacts

- storage/models/candidates/mobilenetv2_v3_seed42/mobilenetv2.keras
- class_mapping.json, evaluation.json, inference_smoke.json, environment.txt, checksums.json beside the model
- storage/datasets/curated/v3/manifest.csv, dataset_metadata.json, reviews_snapshot.jsonl
- scripts/train_baseline.py and docs/training-baseline.md for the reproducible entry point

The model expects MobileNetV2-preprocessed 224x224 RGB inputs, matching existing inference. Nothing was copied into the default active model location.

## Later local activation

The owner subsequently explicitly requested that the model work in the local application. It was activated for experimental local use; this supersedes the historical non-activation status above without changing evaluation results or quality limits. See active-local-model.md and active-model-web-smoke.json.
