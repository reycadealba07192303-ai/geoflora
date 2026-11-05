# Weak-class data and delivery check

Prepared 1 November 2026 (Asia/Manila). This records one bounded collection pass and workflow checks. No model was trained or activated in this pass.

## Current model status

- Serving locally: `mobilenetv2_v3_seed42`, 3 classes, confidence threshold 0.80. Active model and mapping SHA-256 remained `7b092e3209f886a3ade0656b14af68a0d671905646b98e0b6be9a3153742e5d1` and `097e40e340422b06fda4ec1faca7512207a0c57b98e2ec1db59919f8acbdd452`.
- Expanded experiment: `auto_6ae5cd74af23d762feaa0889`, 11 classes, 73.52% historical test accuracy / 73.53% macro F1 on 253 images. It remains an unpromoted candidate.
- Fine-tuning experiment: `mobilenetv2_11class_finetune_v1_20261101`, unpromoted. Validation-loss selection restored the original checkpoint; selected validation accuracy/F1/loss stayed 65.73% / 63.33% / 1.1920. The already-used 253-image historical test scored 73.52% / 73.53% once after selection; this is not an independent or blind result.

## Frozen 11-class data and evaluation

The candidate manifest has 1,625 images (1,124 train, 248 validation, 253 historical test). Existing grouped split audit found no exact image, observation, or near-duplicate key shared across partitions. It does not establish independent sites or expert botanical truth. Train counts below are frozen manifest image counts / source observation groups as recorded in the reconciliation report.

| Class | Train images / groups | Historical test precision | Recall | F1 | Test support |
|---|---:|---:|---:|---:|---:|
| Antigonon leptopus | 104 / 54 | 68.00% | 73.91% | 70.83% | 23 |
| Broussonetia papyrifera | 29 / 24 | 80.00% | 66.67% | 72.73% | 6 |
| Chromolaena odorata | 153 / 119 | 72.22% | 74.29% | 73.24% | 35 |
| Coccinia grandis | 104 / 72 | 72.22% | 56.52% | 63.41% | 23 |
| Lantana camara | 145 / 110 | 81.08% | 96.77% | 88.24% | 31 |
| Leucaena leucocephala | 103 / 71 | 62.96% | 73.91% | 68.00% | 23 |
| Mikania micrantha | 107 / 74 | 47.37% | 36.00% | 40.91% | 25 |
| Nymphaea (look-alike class) | 56 / 48 | 100.00% | 91.67% | 95.65% | 12 |
| Pistia stratiotes | 112 / 97 | 68.97% | 83.33% | 75.47% | 24 |
| Pontederia crassipes | 103 / 71 | 77.42% | 85.71% | 81.36% | 28 |
| Spathodea campanulata | 108 / 81 | 100.00% | 65.22% | 78.95% | 23 |

The weak-class confusion evidence is limited by small support. In the historical test, Mikania was predicted as Chromolaena 5 times and Coccinia 4 times (9/25 correct). Coccinia was confused most with Leucaena (3), Antigonon (2), Chromolaena (2), and Mikania (2) (13/23 correct). Broussonetia had only six test photos; two were wrong, one predicted Antigonon and one Chromolaena. These are observed confusion patterns, not proof of botanical mislabels. The training labels are mostly iNaturalist community research-grade records; the dataset has not had independent expert review of every label or locality.

Train imbalance remains material: Broussonetia has 29 train images versus 153 Chromolaena (5.3:1). Even the larger weak classes have just 104 Coccinia and 107 Mikania train images. Their validation supports were 6 Broussonetia, 23 Coccinia, and 23 Mikania; such validation estimates are noisy. Coccinia and Mikania also visually overlap as climbing vines; the saved predictions show confusions, while image-level causal attribution still needs reviewer inspection.

## Targeted collection and review queue

Ran `scripts/collect_staging_photos.py mikania_micrantha coccinia_grandis broussonetia_papyrifera --skip-registry-sync` with the existing strict CC0/CC BY/CC BY-SA allowlist and three-page bound:

| Class | Newly collected in this pass | New eligible observation groups | Result |
|---|---:|---:|---|
| Mikania | 0 | 0 | No additional eligible records in the bounded source pages |
| Coccinia | 27 | 17 | 27 field-photo records, all iNaturalist research-grade; 13 CC BY and 14 CC0 |
| Broussonetia | 0 | 0 | No eligible records in the bounded source pages |

Compared with the frozen 11-class set, staging has 31 Mikania photos across 23 observation groups and 27 Coccinia photos across 17 groups that are not exact-checksum or observation matches to the frozen set. The Mikania 31 includes the previously collected 30-image supplemental gallery (not newly downloaded today) and one pre-existing main-queue record. Altogether, the audit found 58 candidate photos across 40 source observation groups; all require additional review before a new training freeze. No exact checksum duplicate was retained against the frozen set: 19 Mikania and 27 Coccinia staging files duplicated a frozen image and were excluded from the new-candidate count. No observation overlap was found among the remaining 58.

The manual queue is [weak-class-manual-review-queue-2026-11-01.csv](weak-class-manual-review-queue-2026-11-01.csv). It retains source URLs, IDs, attribution, license, checksum and group. The 28 new iNaturalist rows (1 Mikania, 27 Coccinia) were changed from `research_grade` to `pending`, so the automatic training worker cannot consume them before a person reviews them. No species, field-domain or PH-provenance decisions were automatically approved.

The raw staging manifests also contain 295 CC BY-NC records (131 Mikania, 123 Coccinia, 41 Broussonetia). They were restored to their review queues as pending, with original source/license metadata intact. The collector's executable training allowlist excludes CC BY-NC even though a previous project note records owner permission for non-commercial research; resolve that policy discrepancy before treating those records as training-eligible. All original image files remain in staging.

The audit and reversible queue-status record are [weak-class-expansion-audit-2026-11-01.json](weak-class-expansion-audit-2026-11-01.json) and [weak-class-review-status-changes-2026-11-01.json](weak-class-review-status-changes-2026-11-01.json). No new approved training images resulted from this pass. Do not train on the pending records.

## Unknown-plant learning and delivery smokes

The isolated unknown-plant workflow passed again: the active CNN returned uncertain for the Water Hyacinth photo (0.5602 below 0.80, no species assigned); contributor name/description stayed unverified and the report pending; unauthorized review was denied; administrator review approved the label; consented photo entered a queued training job. The job was deliberately not executed. Evidence: [unknown-plant-workflow-smoke-2026-11-01.json](unknown-plant-workflow-smoke-2026-11-01.json).

Delivery checks passed against isolated databases and the live local inference service:

- Identify through Next.js to the real model: three target photos produced two correct class results and one appropriate uncertain result; 13 invalid-file, unavailable-service, timeout and malformed-response cases had expected errors. Identification p95 was 199 ms. See [Part 6 smoke](part-6-identification-smoke.json).
- Report creation, geotag/map pin, prediction snapshot, editing/withdrawal and photo deletion: 39 Part 8 checks passed.
- Admin/reviewer verification, original prediction preservation, consented training eligibility and catalog/map indicators: 34 Part 9 checks passed.
- Geotagged occurrence map, access scopes, filters, Philippine date boundaries and generalized analytics: 23 Part 10 checks passed.

The first Part 8/9/10 reruns exposed stale smoke fixtures that used the old signup form and omitted currently required review citation/class registry data. The isolated test helper now seeds legacy-style verified accounts directly (it does not send real email), and the fixtures contain the active classes and review evidence required by the current API. The production app was not changed for these smoke fixes.

## Delivery decision

For tomorrow, deliver only the current three-class v3 service as experimental decision support. Its historical three-class result is 87.18% (34/39), macro F1 82.74%, with Water Hyacinth recall 50% (4/8); the 11-class candidate is a separate research artifact at 73.52% on its reused 253-image historical test. Neither demonstrates the requested 95% on a fresh blind, independent Philippine field-photo set. A broader hundred-species claim is not supported. Keep the current active model and class mapping; next step is human review of the staged weak-class queue followed by a separately frozen grouped development set and a new blind test, before any further training run.
