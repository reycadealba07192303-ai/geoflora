# ML inside Next.js (6 November 2026)

GeoFlora's plant classifier now runs **inside the Next.js server** with ONNX Runtime (`onnxruntime-node`). The app no longer needs the separate Python inference service (`services/ml`) or a Hugging Face Space. One process (`npm run dev` / `npm start`) serves the frontend, the API and identification. MongoDB is still the database.

## How it works

| Piece | Where |
|---|---|
| Models (ONNX, about 9 MB each) | `apps/web/models/<version>/model.onnx` + `class_mapping.json` |
| Which models are used | `apps/web/models/ensemble.json` |
| Inference code | `apps/web/src/lib/classifier.ts` (preprocessing: RGB, 224x224, x / 127.5 - 1, the same as training) |
| HTTP shape kept for callers | `apps/web/src/lib/ml.ts` → `mlFetch("/health" \| "/predict" \| "/embed")` |
| Old Python service (optional) | set `GEOFLORA_ML_MODE=remote` to use `GEOFLORA_ML_API_URL` again |

**Ensemble (chosen 2026-11-06):**
- **`geoflora-mnv2-21cls-v1` and `geoflora-mnv2-21cls-v2`:** their 21-class probabilities are averaged. The result counts as "sure" from 0.69, the Youden threshold on validation.
- **`geoflora-mnv2-3cls-v2`:** when the ensemble is not sure but its top guess is Hagonoy, Lantana or water hyacinth, this model confirms it if it names the same species with a score of at least 0.968, its own validation threshold.
- **Embeddings** for verified-reference search come from v1's 1280-wide feature layer. They keep the same `embedding_version`, so existing references stay valid.

**Evaluation**

All options were scored on the same lab test split (931 photos) plus unknown_test (408). Thresholds were chosen on validation only.

| Option | Top-1 | Sure | Accuracy when sure | Hagonoy/Lantana/hyacinth found | False "TARGET" |
|---|---|---|---|---|---|
| v1 | 82.3% | 58.2% | 96.7% | 86/152 | 6 |
| v2 | 82.9% | 61.4% | 96.0% | 96/152 | 7 |
| v1+v2 | 83.2% | 59.7% | 97.8% | 92/152 | 4 |
| **v1+v2 + 3cls confirm** (live, plus the 0.60 floor below) | **83.2%** | **63.5%** | **96.4%** | **118/152** | **16** |

**Confirm floor (added after the first Next.js run).** Unknown plants were confirmed as Hagonoy or water hyacinth by the 3-class model from ensemble scores as low as 0.23. Now the 3-class model may only confirm when the ensemble's top score is at least **0.60**. This floor was chosen on validation only (val vs unknown_val). In the lab evaluation it gives 97.7% accuracy when sure, 99/152 targets found and 21.8% unknown accepted.

**Measured through the Next.js API** (`/api/identify`, in-process ONNX, sharp cubic resize, the same resize family as the old Python service):

| Set | Result |
|---|---|
| Lab test (931) | top-1 **85.8%**, sure 62.8%, **97.4% accuracy when sure**, Hagonoy/Lantana/hyacinth found 100/152 |
| unknown_test (408) | 25.5% wrongly sure |
| Independent Kaggle photos (`Downloads/GeoFlora-Kaggle-Test`) | Lantana 16/25, water hyacinth 16/25 (7/13 of the no-license photos), Pistia 21/25, plants not in the model 49/50 "Not sure" |
| Speed | about 0.16 s per photo, for three models on CPU |

A validation recalibration of the main threshold for the Next.js resize suggested 0.65, which is lower and would accept more unknown plants. The threshold was therefore kept at 0.69, and the test set was not used to tune it.

v2 is the same MobileNetV2 trained deeper: fine-tuning from layer 30 instead of 80, 45 fine-tune epochs, and stronger augmentation (`ml-lab/configs/expansion_nissap_v2.yaml`). Its test result is 83.2% top-1 and macro F1 0.839, against v1's 82.5% and 0.830.

**ONNX conversion check** (`ml-lab/scripts/export_onnx.py`, run in `ml-lab/.venv-onnx`): on 156 test photos per model, the ONNX top-1 matches Keras 100% of the time. The largest probability difference is about 4e-6. Results are in `models/<version>/onnx_check.json`.

## New models from auto-training

`ml-lab/scripts/app_training_worker.py` retrains with the v2 config after 20 new approved or corrected report photos. When an administrator approves the new model under Review & training, the worker:
1. converts it to ONNX and checks it against Keras;
2. makes it the newest member of `ensemble.json`, after saving `ensemble.before-<version>.json`. v1 stays as the stable member.

Next.js notices the changed `ensemble.json` and reloads the models by itself. To roll back, copy the saved `ensemble.before-*.json` over `ensemble.json`.

## Deployment notes

- `next.config.ts` marks `onnxruntime-node` as a server external package and includes `models/**` in the API routes' file tracing.
- `onnxruntime-node` ships binaries for every platform (about 294 MB in `node_modules`). Before deploying to Vercel (250 MB function limit), exclude the non-Linux binaries in `outputFileTracingExcludes` and test a preview deployment.

## Update 2026-11-07: v3 replaces v2

v3 uses the v2 recipe and adds 546 newly reviewed Hagonoy and Ageratum photos (`docs/HANDOVER-GeoFlora-2026-11-07.md`). The ensemble is now **v1 + v3 (+ 3cls confirm)**, and the thresholds are unchanged.

| Test set | Ensemble | Top-1 | Accuracy when sure | Hagonoy recall | Ageratum recall |
|---|---|---|---|---|---|
| Old test (931 photos) | v1+v2 | 83.2% | 98.0% | 73.7% | 67.3% |
| Old test (931 photos) | **v1+v3** | **84.2%** | **98.4%** | **77.2%** | 67.3% |
| Larger test (1,013 photos) | v1+v2 | 81.4% | 97.0% | 61.0% | 72.3% |
| Larger test (1,013 photos) | **v1+v3** | **82.8%** | **97.3%** | **66.0%** | **74.5%** |

- Measured in the lab (bilinear resize, 3-class confirm not included).
- Mikania recall fell slightly, from 68.6% to 66.7% on the old test.
- ONNX check for v3: 169 photos, 100% top-1 agreement.
- Rollback: `models/ensemble.before-geoflora-mnv2-21cls-v3.json`.
