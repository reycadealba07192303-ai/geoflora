# Weak-class validation errors and follow-up collection

Prepared 1 November 2026 (Asia/Manila). No training, threshold tuning, label changes, or model activation occurred.

## Error gallery

Open the local gallery at [http://127.0.0.1:8770/](http://127.0.0.1:8770/) while the local gallery process is running. It groups the saved 11-class head candidate's errors by error family, recorded class, and observation. The companion [human review queue](http://127.0.0.1:8770/review) shows the only still-actionable rights-eligible observation group and its two source photos. Row-level results and counts are in [validation-error-analysis-2026-11-01.json](validation-error-analysis-2026-11-01.json), [weak-class-followup-available-inventory-2026-11-01.json](weak-class-followup-available-inventory-2026-11-01.json), [weak-class-followup-collection-2026-11-01.json](weak-class-followup-collection-2026-11-01.json), and [weak-class-followup-review-queue-2026-11-01.csv](weak-class-followup-review-queue-2026-11-01.csv).

Predictions were recomputed with the saved 11-class candidate on the frozen dataset's 250-image development validation partition. Historical test image bytes were not opened or predicted. Its manifest checksums and observation IDs were consulted only to exclude duplicate/leaking candidates, not for model evaluation or threshold tuning. There were 91 errors. Priority groups:

| Validation issue | Observed errors |
|---|---:|
| Mikania ↔ Chromolaena | 11 total: Mikania→Chromolaena 8; Chromolaena→Mikania 3 |
| Coccinia involved | 21 total: 10 Coccinia false negatives and 11 false positives |
| Broussonetia involved | 6 total: 5 of its 6 validation images misclassified, plus 1 false positive |

Other weak-class confusion details: Mikania's remaining errors were Coccinia (4), Leucaena (1), and Antigonon (1). Coccinia's ten false negatives went to Antigonon (5), Chromolaena (2), Leucaena (1), Mikania (1), and Spathodea (1). Broussonetia's five false negatives went to Coccinia (2), Leucaena (1), Lantana (1), and Mikania (1). These are prediction patterns, not evidence that source labels are wrong.

Gallery review cues found 11 error images under 320 pixels on their shorter side, 4 with possible exposure clipping, and 13 error images in repeated near-duplicate groups within validation. Thirty of the 91 errors had a top-two prediction margin of at most 0.15; 42 of all 250 validation images met that cue. The gallery asks for visual ambiguity inspection for every error. These score and pixel heuristics do not establish visual ambiguity, poor photography, or a mislabeled specimen. All 91 labels still lack independent expert confirmation; 73 are iNaturalist research-grade/community labels, and the remaining records have owner/source review bases.

## Available weak-class observations

The audit considered strict CC0/CC BY/CC BY-SA records with attribution where required, PH field-photo provenance, valid local images, and exact/checksum or observation overlap against the frozen v3 manifest. CC BY-NC items remain out of the training-eligible count under the current allowlist. The scan includes the main Mikania staging folder and its older supplemental folder.

| Class | Existing staging records | Strict-rights PH field groups seen | Independent groups not in frozen v3 | Current disposition |
|---|---:|---:|---:|---|
| Broussonetia papyrifera | 41 | 0 | 0 | All 41 staging records are CC BY-NC and outside the current training allowlist. |
| Mikania micrantha | 201 | 13 | 0 | No eligible independent group remains outside v3; 40 staging records have exact hashes present in the frozen corpus, 131 are CC BY-NC, and 30 are non-iNaturalist records. |
| Coccinia grandis | 177 | 32 | 2 | Three images across two groups are not in v3. One group (two images) is queued below for independent botanical verification; the other group (one image) has an explicit owner decision of `training_eligible: false` and remains excluded. Fifty-one staging image records match v3 checksums; 123 are CC BY-NC. |

This count is an audit of records already in local staging, not 2 new downloads. A 15-page bounded iNaturalist backfill for each class found **0 new images and 0 new observation groups**. The source queries succeeded. The scan skipped 20 known Mikania and 54 known Coccinia photo IDs; no candidate duplicates were downloaded into the new pool. Broussonetia yielded no strict-license field-photo candidates in the bounded query.

The new isolated pool at `storage/datasets/review_pools/weak_classes_followup_20261101/` contains zero images. It is outside the training worker's staging input. The CSV review queue has two Coccinia photos from one observation: [iNaturalist observation 260239376](https://www.inaturalist.org/observations/260239376). Both are CC BY with photographer attribution. Their source label is community research-grade; the prior owner visual approval explicitly still needs independent taxonomic citation/verification and has no explicit training-eligibility approval. Automated image checks report 225×500 pixels for both (small-image flag by the repository's 320-pixel heuristic), Laplacian variances 2976.68 and 3311.30, and negligible clipped pixels (0.003 and 0.000). These checks do not establish botanical identity or image suitability.

The other out-of-v3 group, iNaturalist observation 360175357, is explicitly marked training-ineligible in the saved owner decision and is excluded from the review queue for training. No decision was changed. The exact records, source/license fields, and saved rationale for observation 260239376 are in the CSV and gallery.

## Independent evaluation set

There are **zero** newly collected, independently botanically verified groups for any of the three classes. The one Coccinia group awaiting expert verification cannot form a balanced three-class test set and was not reserved, scored, or used for training/validation. No historical test image was repurposed as a fresh blind example. Independent field-photo accuracy remains unestablished.

## Model safety and checks

- Active model remains `mobilenetv2_v3_seed42`; model SHA-256 is `7b092e3209f886a3ade0656b14af68a0d671905646b98e0b6be9a3153742e5d1` and mapping SHA-256 is `097e40e340422b06fda4ec1faca7512207a0c57b98e2ec1db59919f8acbdd452`, matching the recorded active baseline.
- No training ran, no confidence threshold changed, and no model artifact was promoted or overwritten.
- Gallery smoke: `/`, `/review`, and `/api/review` returned HTTP 200; an error-gallery image and a queued Coccinia image returned HTTP 200 with JPEG content.
- Python syntax compilation passed for the collection, inventory-audit, and gallery-server scripts.

## Human decision required

An independent botanist or qualified reviewer must verify the visible species identity and Philippine observation evidence for Coccinia observation 260239376, and a separate explicit training-eligibility decision must be recorded before any use. Until then, its two images remain review-only. Further training should wait for meaningful newly reviewed, diverse observations; this pass did not add any.
