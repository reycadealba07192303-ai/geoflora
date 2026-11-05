# GeoFlora client-demo readiness — 1 November 2026

## Demo-safe scope

- The live local model is `mobilenetv2_v3_seed42`, serving only Hagonoy (*Chromolaena odorata*), Lantana (*Lantana camara*), and Water Hyacinth (*Pontederia crassipes*). The threshold remains 0.80; model, mapping, and activation metadata checksums were unchanged.
- The complete upload → real CNN inference → uncertain result → user-provided name/description → geotagged pending report → administrator verification → map/analytics flow passed on a disposable database. A water-lily photo remained unassigned by the CNN; after an administrator verified it as a look-alike, the map showed the human-confirmed record. The original prediction remained unchanged.
- Pending or unverified reports are not shown in verified analytics and do not enter training. The worker requires contributor training consent and an approved training candidate; the demo report had neither and created no job. Historical test hashes/groups and perceptual near-duplicates are now explicitly held out from future automatic training.
- The 11-class candidate is research-stage and inactive. Its original 73.52% / 73.53% accuracy/macro F1 came from a previously inspected 253-image test partition. A subsequent head-only experiment was weaker overall on development validation (63.60% accuracy, 61.46% macro F1) than its checkpoint baseline (64.80%, 62.75%). Neither result supports a 95% claim.
- The auto-training worker process was not running at the time of the final process check. No training job was created by this demo.

## Genuine blockers by intended use

### Local client demonstration

- No blocking software issue was found in the tested upload/report/review/map route.
- Use photo upload as the demonstrated capture route. Physical-device camera capture was not exercised in this pass; perform that check on the actual phone/browser if live camera capture is required.
- Describe confidence as a model score, not a calibrated probability or confirmed identification. The model may accept unsupported plants; all reported sightings still require review.
- Use only the three supported classes for CNN identification. Present any other name as a user suggestion until a human reviewer verifies it.

### Production deployment

- Part 12 is not complete: HTTPS and production secret handling, backups/recovery, deployment health/logging, and a full staging upload → identify → report → review → map check remain outstanding.
- Current model quality remains limited: historical v3 accuracy is 87.18% (34/39), Water Hyacinth recall 50% (4/8), and the test set is small and already inspected. Independent field accuracy and the requested 95% are unverified.
- The holdout audit leaves 24 v5 train/validation rows before additions. The current staging export yields **zero images** because no staged record has the required human reviewer and written rationale; AI-screened and research-grade records remain in review storage. Consented, verified user reports can still progress through the training pipeline.
- The worker process was not running during this check. Promotion now requires an eligible candidate, explicit administrator approval with a rationale, and worker-side revalidation. Keep the worker stopped during the demo unless intentionally processing a reviewed training batch.
- Production promotion requires an assigned administrator and an available training worker to process approved candidates. The previous automatic promotion behavior is removed.
- Confirm CC BY-NC use against the actual client delivery terms before distributing research-stage expanded artifacts. The 11-class candidate is not deployed and must not be represented as the supported production model.

## Evidence and checks

- Full demo workflow: [client demo E2E evidence](client-demo-e2e-smoke-2026-11-01.json)
- Historical-test holdout audit: [holdout boundary evidence](training-holdout-boundary-audit-2026-11-01.json)
- Pending review/export guard: `scripts/verify_weak_review_training_hold.py` passed (58 pending candidate hashes exported 0; unreviewed/rejected staging exported 0; license-ineligible staging exported 0; current eligible staging export count 0).
- Promotion safety and licensing regression tests passed 15/15; web typecheck and production build passed. Active model artifacts were hash-checked after the changes.
- Detailed model results and limitations: [client technical summary](client-delivery-technical-summary-2026-11-01.md)

No model training, retraining, promotion, dataset rewrite, collection scan, or review-decision changes were made for this readiness pass. The demo's disposable database was removed after verification. Promotion is no longer automatic: the worker saves eligible models as candidates until an administrator explicitly approves them.
