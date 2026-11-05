# Part 6: real photo identification

Completed locally on October 27, 2026 (Philippine time). It uses the owner-authorized experimental v3 model (`mobilenetv2_v3_seed42`, 3 species). No model meets the Part 1 quality targets. The v5 candidate stays unapproved ([model card](model-card-v5.md)).

## Installed model and threshold

- `storage/models/mobilenetv2.keras` and `class_mapping.json` are byte-identical to `storage/models/candidates/mobilenetv2_v3_seed42/` (SHA-256 checked). They load through the existing `PlantPredictor` paths.
- The predictor now reads the owner-maintained `storage/models/active_model.json`. It reports `model_version` as the candidate name (`mobilenetv2_v3_seed42`) instead of the file stem `mobilenetv2`.
- The predictor also takes its confidence threshold from that file. Precedence: explicit argument, then `GEOFLORA_CONFIDENCE_THRESHOLD`, then `active_model.json`, then 0.65.
- **Threshold changed from 0.65 to 0.80.** The rule (from Part 5) is the lowest threshold whose validation selective accuracy is at least 90%. 0.80 met it on the 38 v3 validation photos: 22 accepted, 90.9% correct. Evidence: [part-6-v3-evaluation.json](part-6-v3-evaluation.json).
- To revert, set `confidence_threshold` back to 0.65 in `active_model.json`, or set `GEOFLORA_CONFIDENCE_THRESHOLD`, and restart inference.

Trade-off on the v3 test set, applied once. This test set was already used in the earlier v3 report, so these figures are not a fresh benchmark.

| Threshold | Test coverage | Selective accuracy | Unsupported-species photos accepted (151 photos, 78 species) | Synthetic non-plant proxies accepted (18) |
|---|---:|---:|---:|---:|
| 0.65 (previous) | 87.18% | 94.12% | 62.25% | 9 |
| 0.80 (now) | 69.23% | 92.59% | 37.09% | 2 |

The higher threshold mainly cuts confident answers on photos of plants the model does not know. It still accepts more than a third of them, so the result screen states this limit. Blur and lighting checks are in the JSON. v3 kept at least 79% top-1 accuracy under every perturbation tested.

## Web changes

- **Camera capture.** A *Take a photo* button opens the rear camera on phones (`capture="environment"`); desktops fall back to a file chooser. The preview has *Retake* and *Change photo*. Both inputs accept only JPEG, PNG and WebP, and enforce the 20 MB limit on the client.
- **Result screen.**
  - Every model result shows the model version and suggestion threshold.
  - An uncertain result explains that the top score fell below the threshold.
  - It names the possible causes: an unsupported plant or an unclear photo.
  - It lists the three closest supported species, labeled "not a label". No species is assigned.
- **API errors (`/api/identify`).** The route maps upstream failures to distinct responses:

  | Failure | Status |
  |---|---:|
  | Inference timeout (`GEOFLORA_INFERENCE_TIMEOUT_MS`, default 60 s) | 504 |
  | Unreadable upstream response | 502 |
  | Service unreachable or connection reset | 503 |
  | Identification store failure | 503 |
  | Unexpected upstream error | Upstream status, with a generic message |

  Unexpected upstream error details are no longer forwarded.
- **Client errors.** The client has a 75 s timeout and handles non-JSON responses. A failed request shows a clear message instead of a parse error.

## Verification

- ML unit tests: 31 passed. One new test covers the active-metadata version and threshold precedence.
- Web: `npm run typecheck` and `npm run build` passed. The live services were restarted: inference on 8000 and `next start` on 5173. `/api/identify` reports `ready: true` and `model_version: mobilenetv2_v3_seed42`.
- `scripts/smoke_identification.py` passed and wrote [evidence](part-6-identification-smoke.json). It runs temporary web instances on an isolated `geoflora_identification_validation` database:
  - Real predictions through Next.js and FastAPI: Hagonoy identified at 0.902, Lantana identified at 0.837, and Water Hyacinth uncertain at 0.560. Version and threshold were checked.
  - Upload-to-result latency over 39 held-out photos (53 KB to 1.3 MB, one user, loopback): p50 151 ms, p95 255 ms, max 268 ms. This meets the proposed 5 s p95 target on this machine only.
  - 13 failure cases returned the expected status and a clear message:

    | Case | Status |
    |---|---:|
    | Unsupported type | 415 |
    | Not an image | 422 |
    | Image under 64 px | 422 |
    | Over 20 MB | 413 |
    | Missing file | 400 |
    | Signed out | 401 |
    | Inference timeout | 504 |
    | Model unavailable | 503 |
    | Unreadable response | 502 |
    | Upstream crash | 500 |
    | Connection reset | 503 |
    | Unreachable | 503 |
    | Health check while unreachable | 503 |
- `scripts/smoke_identification_ui.mjs` passed 9 checks in headless Chrome with 390x844 mobile emulation and wrote [evidence](part-6-identification-browser-smoke.json). Checks covered the camera input, and identified and uncertain result screens showing version, threshold and candidates without horizontal overflow. Screenshots are in `storage/logs/ui-preview/identification-mobile-*.png`.
- Identifying a photo still does not save a sighting. Reports remain a separate, confirmed step.
- The active model file was unchanged throughout.

## Limitations

- Camera capture was checked in browser emulation, not on a physical phone. Native camera behavior, especially iOS HEIC conversion, still needs a real-device check.
- Latency is loopback on the development machine (Intel family 6 model 186, 16 logical CPUs). Mobile networks and the deployment host are remeasured in Parts 11–12.
- The threshold rests on 38 validation photos and is not calibration. Unsupported plants can still be accepted, and no real non-plant photos were tested.
- The v3 model's quality limits stand: Water Hyacinth recall was 50% at the old threshold, and the proposed targets are not met.
