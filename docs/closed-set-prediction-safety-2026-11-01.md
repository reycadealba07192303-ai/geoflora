# Closed-set prediction safety check

Date: November 1, 2026 (Asia/Manila)

## Finding on the reported 82.4% result

The identification record written by the live `/api/identify` flow at 3:12:15 PM PHT contains:

- `method: model`, `status: identified`
- `mobilenetv2_v3_seed42`, threshold `0.80`
- Lantana camara: `0.8241089`; Chromolaena odorata: `0.1649488`; Pontederia crassipes: `0.0109422`

The active mapping file has these output indices: Chromolaena odorata, Lantana camara, Pontederia crassipes. `PlantPredictor` checks that the saved model has three outputs and calls Keras `model.predict()` on a 224 x 224 RGB image after TensorFlow MobileNetV2 preprocessing. The mapping is consistent with the saved model shape and reported class. The record is not a verified-reference match. The stored response and matching live inference code confirm this was the real CNN path.

The original uploaded bytes are not retained in the temporary identification record: GeoFlora stores source/normalized photo hashes and the result for 24 hours. The screenshot is not the original image file, so the exact image could not be replayed independently. Uvicorn logs record successful `/predict` requests but do not carry an identification ID to associate one request line with this record. Re-upload the original photo to reproduce its raw model output. This limitation does not change the recorded result.

## Actual image probes

These were inference behavior probes, not an accuracy evaluation. HTTP results through Next.js `/api/identify` matched fresh `PlantPredictor.predict()` outputs for each image. No reference match occurred. Lantana probes used owner-approved v3 **training** images, not a held-out test set. The Tawa-tawa candidates remain pending and their Commons captions are not expert label verification.

| Image / label basis | CNN output | Interpretation |
|---|---|---|
| Lantana, owner-approved v3 training image, group 1 | Lantana, 80.55% | Supported-class workflow probe only |
| Lantana, owner-approved v3 training image, different group | Lantana, 96.34% | Supported-class workflow probe only |
| Mikania, owner-gallery-approved source label; outside active v3 classes | Uncertain, top score Lantana 55.58% | Unknown handling worked on this sample |
| Commons Euphorbia hirta candidate by Bim24; locality/label unverified | Uncertain, top score Hagonoy 71.30% | Below display threshold; does not validate the Tawa-tawa label |
| Commons Euphorbia hirta candidate by Judgefloro; Philippine capture metadata, label unverified | Water Hyacinth, 86.81% | Closed-set risk example, not a confirmed false-positive count |

The user-reported Tawa-like image remains a plausible CNN false identification based on the user's visual comparison, but its botanical identity has not been independently confirmed. Therefore no numeric false-positive rate or unknown-detection accuracy is claimed.

## Changes made

- Every above-threshold CNN output is now labeled a **tentative, unverified suggestion**. The score is described as a model score, not probability of correctness. The UI explains that the classifier knows only three species and that unsupported plants can score highly.
- Species information shown beside a CNN result is explicitly information about the suggested class, not established facts about the uploaded plant. CNN species descriptions and citations are no longer copied into the report as facts about the observation.
- Added **This does not match my plant**. It opens the unknown-report form for a free-text species suggestion or blank/unknown, requires a plant description, and submits the report as `unknown` and pending. The original CNN output remains attached for reviewer context. Reports flagged this way bypass automatic AI verification and remain in the human queue.
- Pending CNN suggestions remain out of verified occurrence counts. Training/reference permissions remain separate and no image is approved by this control.
- With eligible indexed references, the identify API now attaches image-similarity suggestions to either uncertain or identified CNN responses without changing the CNN class, status, or score. Similarities remain uncalibrated and cannot verify a report. The active index currently has zero references, so this optional branch has not been exercised with real references.
- No calibrated OOD detector or new threshold was added because there is no independently labeled, grouped unknown-species evaluation set to calibrate one against.

## Checks

- Next.js typecheck: passed.
- Next.js production build: passed.
- `scripts/smoke_unknown_plant_review.py`: passed in a disposable MongoDB database. It checked uncertain reporting, user mismatch for a real Lantana photo, preservation of the CNN result, pending/admin-review status, omission of predicted-species facts from the report, no training consent, and four actual-image HTTP-vs-Keras parity probes.
- The same smoke confirmed `mobilenetv2_v3_seed42`, active model and class-mapping hashes, and threshold `0.80` remained unchanged.
- Live web and ML health checks: HTTP 200; active model ready with the same three classes.

Full machine-readable smoke results: [unknown-plant workflow smoke](unknown-plant-workflow-smoke-2026-11-01.json).
