# GeoFlora client delivery technical summary

Prepared: 2026-11-01 (Asia/Manila)

## Delivery candidate

The current local delivery candidate is `mobilenetv2_v3_seed42`, with the existing three-class mapping:

1. `chromolaena_odorata` — *Chromolaena odorata* (Hagonoy)
2. `lantana_camara` — *Lantana camara* (Lantana)
3. `pontederia_crassipes` — *Pontederia crassipes* (Water Hyacinth)

The active Keras model SHA-256 is `7b092e3209f886a3ade0656b14af68a0d671905646b98e0b6be9a3153742e5d1`, matching the preserved candidate artifact. The active class mapping and activation metadata were unchanged during this stabilization check. No retraining, model replacement, or deployment occurred.

## Working features checked

- Next.js upload reaches the real FastAPI inference route and loaded Keras `model.predict()`; a held-out Water Hyacinth image returned the active model version and matched a fresh local Keras prediction. It was not a verified-reference lookup.
- Upload validation, identified and uncertain result handling, and ML service unavailable/timeout/reset/malformed/crash handling passed `scripts/smoke_identification.py` on isolated local Next instances. The smoke fixture was updated to log into its isolated admin account because current registration requires email verification; production auth behavior was not changed.
- Confidence is displayed as a model score, separately from a reviewed reference match. The active threshold is 0.80, selected on validation data. Below threshold, the API returns `status: uncertain` and `species: null`; the UI presents no assigned species and requires a description before reporting.
- An isolated report-flow check created an identified report and an uncertain/pending-review report, fetched the saved report, and generated a PDF. It used `GEOFLORA_AI_REVIEW=off`, so no external AI reviewer or provider was needed. The four test report rows were removed from the isolated validation database afterward.
- Existing browser smoke evidence covers the identified/uncertain screens, model score and threshold text, and the report/review UI. This stabilization run did not launch a new interactive browser session.
- The public FastAPI health endpoint requires the configured service key; a direct unauthenticated request was rejected. The authorized Next.js proxy health route reports ready with `mobilenetv2_v3_seed42` and three supported species.

## Evaluation evidence and limits

Historical v3 training/validation/test evidence in `docs/model-inference-evaluation-2026-10-31.md` and `docs/part-6-v3-evaluation.json`:

| Measure | Result |
|---|---:|
| Training accuracy | 98.80% (166 images) |
| Validation accuracy | 78.95% (38 images) |
| Historical held-out test accuracy | 87.18% (34/39 images) |
| Test macro F1 | 82.74% |
| Water Hyacinth recall | 50% (4/8 test images) |

Train images / listed observation groups: Hagonoy 64 / 42, Lantana 79 / 55, Water Hyacinth 23 / 19 (166 images total). These are owner-approved dataset records and group metadata, not independent botanical certification.

Test precision / recall / F1: Hagonoy 86.67% / 92.86% / 89.66%; Lantana 85.00% / 100.00% / 91.89%; Water Hyacinth 100.00% / 50.00% / 66.67%. Confusion matrix (actual rows, predicted columns in Hagonoy, Lantana, Water Hyacinth order): `[[13,1,0],[0,17,0],[2,2,4]]`.

The highest-impact observed weakness is Water Hyacinth: four of eight test rows were predicted as another supported species (two Hagonoy and two Lantana). Two wrongly accepted Water Hyacinth rows had scores just over the active 0.80 threshold; two other errors were below threshold and therefore returned uncertain. Repeated/near-duplicate Water Hyacinth close-ups and the small class sample limit interpretation. The 20-point training-to-validation gap is consistent with overfitting; Water Hyacinth has the fewest training images.

The 39-image split was held out from training partitions but has been examined in earlier evaluations; it is not a fresh blind cohort. It contains only 24 recomputed near-duplicate groups. Accordingly, **87.18% is a historical curated-test result, not an independently established estimate of Philippine field-photo accuracy**. The requested 95% accuracy has **not** been independently verified. No supported claim of 100-species capability is made; the trained model supports only three classes.

An exploratory unsupported-image check in the historical evaluation reports 56/151 false acceptances (37.09%) at threshold 0.80, across 78 other species. The sample is not a new blind test, and its false-acceptance rate is not a guaranteed production rate. It shows that a softmax threshold alone cannot reliably reject every unsupported plant.

## Smoke results from this stabilization pass

- Live Next.js → FastAPI → Keras inference: passed; Water Hyacinth top score 0.560237, uncertain, no species assignment, not a reference match.
- Next.js identification endpoint on a held-out Hagonoy image: identified Hagonoy at 0.9016 (API response).
- Next.js identification endpoint on a held-out Water Hyacinth image: uncertain at 0.5602; no species assigned.
- Upload/input failures: unsupported media 415, malformed image 422, too-small image 422, oversize 413, missing file 400, signed-out 401.
- Simulated ML failures: slow 504, unavailable 503, malformed response 502, inference crash 500 with generic response, reset/unreachable 503, unavailable health 503.
- Reporting: saved/read report, uncertain case retained as pending review, identified case PDF generated; passed on an isolated database.
- Active model and class mapping SHA remained unchanged.

### Complete client-demo workflow

The end-to-end run in `docs/client-demo-e2e-smoke-2026-11-01.json` passed against an isolated disposable database. An unsupported water-lily image went through Next.js → FastAPI → the loaded Keras model and returned `uncertain`, confidence 0.4366, threshold 0.80, and no assigned species. The contributor's suggested name and description were saved as an unverified, geotagged pending report; it was absent from verified analytics and not eligible for training. An administrator then explicitly verified it as *Nymphaea pubescens*, role `lookalike`; the original CNN result stayed uncertain, and only then did the verified map/analytics show it. Training consent was false and no job was queued. The disposable database was dropped after the check.

### Research-stage 11-class expansion

The 11-class MobileNetV2 candidate and its data artifacts remain research-only. The frozen-backbone head experiment's validation result was 63.60% accuracy, 1.1944 cross-entropy loss, 61.46% macro F1 (250 validation images / 194 groups), versus 64.80% accuracy and 62.75% macro F1 for the original 11-class checkpoint on the same development validation split. The head candidate modestly improved validation loss but reduced accuracy and macro F1, so it was not promoted. Mikania F1 moved 42.11%→46.81% (recall fell 48%→44%); Coccinia F1 55.56%→61.02% (recall 53.57%→64.29%); Broussonetia F1 16.67%→25.00% (recall remained 16.67%, only six validation images). These are small-sample development metrics, not independent accuracy.

An earlier 11-class candidate scored 73.52% accuracy / 73.53% macro F1 on a 253-image historical test partition that has been inspected and reused; it is not a fresh blind evaluation. The later head candidate was not tested on that partition. Neither expansion artifact is active. The 11-class datasets include research-stage source labels and CC BY-NC material; do not present the candidate as client-ready without rights/use confirmation and independent label review.

### Automatic training boundary

The holdout audit found that older v3/11-class historical test images had appeared in v5 development data (33/39 v3 test hashes and 46/253 11-class test hashes). The worker previously excluded only the v5 benchmark. Its guard now excludes all curated historical test exact hashes and normalized observation identities, then applies perceptual-hash matching (distance ≤6) against historical test images to baseline and consented additions. The audit reports zero remaining exact/group overlap and 24 v5 train/validation rows after exclusions. Staging export now requires a human reviewer and a written rationale; AI-only and research-grade-only records are held for review, leaving zero currently eligible staging rows. The 58 pending weak-review candidates also export zero images. User reports remain gated by contributor training consent plus moderator-approved training candidacy; the complete demo run confirmed a non-consented report creates no training job. No worker process was running and no training run was started during stabilization.

Automatic model promotion is disabled. A candidate must pass its quality and live-comparison gates, then an administrator must review the per-class evaluation and explicitly approve it with a rationale. The worker checks the model, mapping, and evaluation hashes again before activation. Each promotion saves the previous model snapshot and records version, evaluation checksums, and approval details; an operator rollback command preserves the outgoing version and records the from/to versions and reason.

These checks establish that the tested software path responds as intended. They are smoke tests, not a new accuracy evaluation or a guarantee about a remote production deployment.

## Delivery recommendation and blockers

Use the current model only as an **experimental, three-species decision-support feature**. Tell users that the displayed percentage is a model score, not calibrated probability or verified identity; uncertain and unsupported cases need human confirmation. Avoid representing a classifier match as a botanically verified identification unless a human reviewer confirms it.

Do not train v4 before tomorrow's delivery. The currently reviewed development data has a large train/validation gap and only 23 Water Hyacinth train images; the old test has already been inspected and is not a blind promotion gate. There is no fresh, independently reviewed and sealed Philippine field-photo test set. A one-off v4 experiment would therefore add schedule risk without a valid independent success decision. No threshold changes are recommended against the old test set.

Recommended next steps after delivery: collect more diverse, independently reviewed Water Hyacinth field observations; freeze a separate, site/observation-group-aware blind test for all three classes; then approve at most one bounded MobileNetV2 experiment with validation-only selection and explicit rollback. Keep v3 available until a candidate meets a pre-agreed promotion criterion on the sealed test.

Local start instructions, the admin-approved candidate workflow, rollback command, and separate local-demo/production readiness are in the [client handover](client-handover-2026-11-01.md).
