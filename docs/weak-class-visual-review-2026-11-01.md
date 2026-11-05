# Weak-class visual review package

Prepared 1 November 2026. Open the review interface at **http://127.0.0.1:8768/** while the local review service is running. It is bound to loopback only. Review decisions save separately to `docs/weak-class-human-decisions-2026-11-01.json`; no review choice automatically alters a dataset or starts training.

## Automated review results

- Gallery includes all **58 candidate files in 40 source-observation cards**: 31 Mikania / 23 source groups and 27 Coccinia / 17 groups.
- All files decode and match their recorded SHA-256. All have source URL, attribution, and CC BY or CC0 rights metadata. No CC BY-NC images are in the gallery.
- The automatic visual features are resolution, exposure, green-pixel fraction, and edge variance. These are triage cues only. The software does not verify visible species identity; an AI or source community identification is not expert botanical review.
- **19 Mikania files across 12 source groups** have perceptual hash distance 0 to frozen 11-class images. They match historical training, validation, and test sources. Three match the historical test source images 191462732, 114266128, and 171377650. Hold out all 12 groups from any new training split.
- One more candidate image is duplicated across iNaturalist observation 18554448 and GBIF occurrence 1945468596 (photo ID 28386564; pHash distance 0). Prefer the direct iNaturalist record and do not count the GBIF copy as a separate image/group.
- Three Coccinia images are 225Ã—500 across two observations; one Mikania image has a possible exposure concern. These remain visible for a human decision rather than being automatically rejected.

| Gallery triage | Groups | Records | Human action |
|---|---:|---:|---|
| Suitable for human botanical review | 15 | 24 | Review the Coccinia label and visible plant features |
| Field-photo check | 8 | 8 | Confirm these Mikania GBIF images show live field plants, not herbarium specimens |
| Questionable quality | 3 | 5 | Inspect the three low-resolution Coccinia photos and the exposure-flagged Mikania observation (two files) |
| Cross-source alias | 2 | 2 | Confirm which record to retain; use only one copy |
| Match to frozen dataset | 12 | 19 | Excluded from a new split to prevent test/training leakage |

After excluding all 19 frozen-match files and one GBIF alias, the 38 remaining files were pre-screened with the inactive 11-class candidate. Top predictions were Coccinia 13, Mikania 10, and other supported classes 15. These are non-binding triage scores, not label evidence or accuracy; historical test images were not re-inferred. Remove the duplicate GBIF copy and keep the direct iNaturalist record; at most **38 images across 27 observation groups** remain for a new dataset. Of these, 24 Coccinia images in 15 groups have no automated quality flags; the remaining Mikania groups need field-photo review (plus one direct iNaturalist record retained from the alias pair), and three groups have quality flags. No group has been approved yet. Gallery choices are owner visual-review decisions only, recorded with training_eligible false; they do not assert independent expert verification and cannot trigger training. The machine-readable details, including exact SHA-256 values, matching frozen source IDs and split, are in [weak-class-visual-audit-2026-11-01.json](weak-class-visual-audit-2026-11-01.json) and [weak-class-manual-review-queue-2026-11-01.csv](weak-class-manual-review-queue-2026-11-01.csv).

## License hold

The October 31 owner note permits CC BY-NC for non-commercial research. Since the clientâ€™s permitted downstream use has not been documented, the November 1 direction holds CC BY-NC files out of training. There are **295** such staged records: Mikania 131, Coccinia 123, Broussonetia 41. They remain pending with their original provenance. The 11-class artifact was trained on a broader corpus that included CC BY-NC material; keep it out of client delivery until the use is confirmed. The new 58-photo review gallery itself is only CC BY and CC0.

The worker now enforces the strict CC0/CC BY/CC BY-SA allowlist (plus attributed owner photos) instead of relying on `review_status`. Verification passed: none of the 58 pending candidates entered the automatic training export and none of the exported staging images failed the license check. The licensing tests passed 4/4. No dataset freeze or training ran because human decisions are still pending. The live three-class model and the inactive 11-class candidate remain unchanged.
