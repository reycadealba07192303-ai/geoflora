# Active local identification model

**Update October 27, 2026:** the suggestion threshold for this model is now 0.80 (validation-selected), recorded in `storage/models/active_model.json`, and the service reports `model_version: mobilenetv2_v3_seed42`. The 0.65 figures below are historical. See [Part 6 identification](part-6-identification.md).

Activated at the owner's explicit request on October 23, 2026 (Asia/Manila).

The trained candidate mobilenetv2_v3_seed42 was checksum-verified, loaded successfully, and installed at storage/models/mobilenetv2.keras with its matching class_mapping.json. The candidate files are preserved. storage/models/active_model.json identifies this local experimental activation.

The inference service is running on http://127.0.0.1:8000; the web proxy at http://127.0.0.1:5173/api/identify reports ready=true. Open the app, select **Identify a plant**, upload a JPEG/PNG/WebP photo and submit it. Refresh or reopen the identification view if it still shows an old unavailable state.

Supported classes: Chromolaena odorata (Hagonoy), Lantana camara, and Pontederia crassipes (Water Hyacinth). Mikania and Pistia are selection candidates only and are not supported by this model.

Real web-proxy upload checks returned HTTP 200 for three previously evaluated test images: Hagonoy identified at 0.902, Lantana identified at 0.837, and Water Hyacinth uncertain at 0.560 under the unchanged 0.65 confidence cutoff. The uncertain result is intentional. Evidence: docs/active-model-web-smoke.json. These are integration smoke checks, not new accuracy or latency benchmarks.

This is an experimental local activation despite unmet proposed quality targets: historical test accuracy 87.18%, macro F1 82.74%, Water Hyacinth recall 50% on a small test set. Confidence is not calibrated accuracy. No nationwide validation or reliable unknown-species rejection is claimed. The owner authorized local use; the earlier non-activation status in training reports is historical.

Startup from the repository root if needed:

```powershell
.\services\ml\.venv\Scripts\python.exe -m geoflora_ml.inference
```

Run the web app separately from apps/web with npm run dev (or npm run start after a build). Inference PID and logs are under storage/logs/inference.pid and inference-active-stderr.log. Identification currently displays predictions without automatically saving a sighting; the separate sighting form remains available.
