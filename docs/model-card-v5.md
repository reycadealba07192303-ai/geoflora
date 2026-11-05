# Model card: mobilenetv2_v5_five_seed42 (experimental, not approved)

Evaluated October 27, 2026 (Philippine time). Decision: **not approved for activation**. The live three-species model (v3) is unchanged.

## Model

- Artifact: storage/models/candidates/mobilenetv2_v5_five_seed42/mobilenetv2.keras with class_mapping.json; checksums in checksums.json.
- Architecture: ImageNet MobileNetV2 (frozen) plus a class-balanced softmax head, seed 42. Fine-tuning of the last 20 layers was tried and rejected on validation loss. Training details: [v5 results](training-v5-five-results.md).
- Input: JPEG/PNG/WebP, at least 64x64 pixels, resized to 224x224 RGB through shared `geoflora_ml.inference.preprocess`, with MobileNetV2 scaling outside the model.
- Output, in this class order: chromolaena_odorata, lantana_camara, mikania_micrantha, pistia_stratiotes, pontederia_crassipes.

## Data

Frozen dataset v5_part2_final_five_classes: 211 photos (141 train / 34 validation / 36 test), grouped so that no checksum, observation or near-duplicate group crosses splits. Labels and Philippine location rest on owner attestation and assistant visual screening, not on independent botanical or per-record geographic verification. Mikania has 5/1/1 photos and Pistia 3/2/2.

## Intended use

Research prototype for suggesting which of five Philippine invasive plants a field photo may show. A suggestion goes to human review. It does not verify a species, an ecological status or a location. Not intended for unsupported species, non-plant photos, herbarium sheets, or regulatory or management decisions.

## Results

Full evidence: [part-5-v5-evaluation.json](part-5-v5-evaluation.json). Reproduce with `services/ml/.venv/Scripts/python.exe scripts/evaluate_candidate_part5.py`.

**Held-out test (36 photos):** top-1 accuracy 75.00% and macro F1 49.47%. Per-class recall: Hagonoy 57.14%, Lantana 100%, Mikania 0% (1 photo), Pistia 0% (2 photos), Water Hyacinth 100%. The confusion matrix is in the [v5 results](training-v5-five-results.md).

**Confidence threshold (chosen on validation only).** The rule was the lowest threshold from 0.40 to 0.95 whose validation selective accuracy is at least 90%. This selected **0.90**: 12 of 34 validation photos accepted, 91.67% of them correct. That figure rests on 12 accepted photos and is unstable. The threshold was then applied once to test:

| Test threshold | Coverage | Accepted correct | Selective accuracy |
|---|---:|---:|---:|
| 0.65 (current service default) | 63.89% (23/36) | 18 | 78.26% |
| 0.90 (validation-selected) | 47.22% (17/36) | 15 | 88.24% |

At 0.90 the service would abstain on about half of supported photos. The threshold has not been applied to any running service.

**Errors.** All six Hagonoy errors were predicted as Lantana, two at ≥0.98 confidence that the 0.90 threshold still accepts. The Mikania photo (0.74) and both Pistia photos (0.49, 0.51) were predicted as Hagonoy and fall below the selected threshold. Per-image details are in `test_errors` in the JSON.

**Unsupported species.** 147 Philippine staging photos covered 76 species outside the classes, with synonyms and shared checksums excluded:

- At 0.90, 35.37% (52 photos) were falsely accepted: 34 as Water Hyacinth, 10 as Lantana, 8 as Hagonoy.
- At 0.65, 68.71% were falsely accepted.
- The highest false scores were Bidens pilosa at 99.8% (as Water Hyacinth), Coccinia grandis at 99.4% (as Hagonoy) and Basella alba at 99.2% (as Lantana).

**Synthetic non-plant proxies.** These were 18 solid, noise, gradient, checkerboard and stripe images:

- At 0.90, 1 of 18 was accepted (stripes, as Water Hyacinth, 0.92).
- At 0.65, 10 of 18 were accepted, all as Water Hyacinth.
- No real non-plant photos were available. These proxies do not replace them.

Water Hyacinth acts as a catch-all for unfamiliar inputs, so its 100% test recall overstates how specific it is.

**Blur and lighting.** These perturbations were applied to the 36 test photos and scored at the 0.90 threshold:

| Condition | Top-1 accuracy | Coverage | Selective accuracy |
|---|---:|---:|---:|
| Original | 75.00% | 47.22% | 88.24% |
| Gaussian blur r=2 | 72.22% | 50.00% | 94.44% |
| Gaussian blur r=5 | 69.44% | 47.22% | 94.12% |
| Brightness x0.4 | 52.78% | 36.11% | 84.62% |
| Brightness x1.8 | 36.11% | 33.33% | 100% |
| Contrast x0.5 | 63.89% | 41.67% | 86.67% |

Blur is tolerated. Dark and overexposed photos lose much of their accuracy.

**Latency.** Measured with 36 requests, one at a time, on an Intel Core (family 6, model 186) with 16 logical CPUs, Windows 11, TensorFlow 2.17.1 and default threads:

| Measurement | p50 | p95 | Max |
|---|---:|---:|---:|
| Warm in-process predict | 76.7 ms | 107.1 ms | 107.4 ms |
| FastAPI /predict (ASGI test client) | 83.6 ms | 116.1 ms | 122.3 ms |

Cold model load took 0.51 s, after TensorFlow was already imported. Payloads ranged from 50 KB to 1.6 MB. These figures exclude browser upload, network and the Next.js proxy. Full upload-to-result timing belongs to Part 6.

## Review against Part 1 targets

The Part 1 targets are still proposed and not user-confirmed.

| Target | Result | Met? |
|---|---|---|
| Held-out accuracy ≥ 85% | 75.00% | No |
| Macro F1 ≥ 85% | 49.47% | No |
| Each species recall ≥ 80% | Hagonoy 57%, Mikania 0%, Pistia 0% | No |
| Identification p95 ≤ 5 s | Inference-only p95 0.12 s; end-to-end not yet measured | Inference portion only |
| Unsupported inputs handled clearly | 35% of unsupported-species photos accepted at 0.90 | No (no target was set; this is a material failure) |

**Decision:** not approved for activation. Do not swap it for the live v3 model. The 0.90 threshold and these results stay with this candidate only.

## Limitations and next steps

- The test set is tiny for the new classes, so one photo changes a recall by 100 points. Validation has only 34 photos, so the threshold choice is noisy.
- There is no open-set or "not a target plant" class, and confidence is uncalibrated. High scores are not evidence of correctness.
- The same weaknesses probably apply to the live v3 model, which has not been through this unsupported-input test. Running it is recommended before Part 6.
- To improve: collect distinct, reviewed Philippine field observations for Mikania and Pistia; add more Hagonoy/Lantana examples; consider an explicit unsupported/other class built from the held research archive, or an out-of-distribution score; reserve a fresh test set. Do not tune further against this test set.
