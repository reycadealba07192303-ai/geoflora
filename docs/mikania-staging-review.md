# Mikania micrantha — collection and review handoff

Date: October 23, 2026 (Asia/Manila). Status: collected, technically checked, pending visual/provenance review. No species class was activated.

## Result

| Measure | Count |
|---|---:|
| New candidate records / distinct normalized checksums | 50 |
| iNaturalist records | 20 |
| GBIF records | 30 |
| Passed image integrity / basic rights metadata checks | 50 |
| Download candidate rejections | 6 |
| Stored source observation groups | 35 |
| Perceptual near-duplicate groups | 20 |
| Connected observation/similarity components | 22 |
| Approved labels | 0 |

The connected-component count combines source observation IDs, perceptual groups and exact hashes. It is a grouping estimate, not proof of 22 independent field observations. GBIF includes higher-resolution copies of iNaturalist photos and herbarium specimens. Different-resolution copies may have different checksums, so 50 checksums do not mean 50 independent scenes.

Both sources completed a bounded PH-filtered collection with at most three API pages per source, 50 new unique images per source and a shared 0.1 GB additional-storage cap. The pass stored 38,335,630 bytes (about 36.6 MiB). No attempt was made to force 100 photos by relaxing rights, image limits or country criteria.

All stored records have PH source country codes, source URLs, attribution and allow-listed photo licenses. These are source metadata checks, not independent confirmation of every location or plant identity. SHA-256 and image decoding checks passed. Six download candidates failed the existing safety/format limits; failures are retained in the staging rejected.jsonl. No raw records were deleted.

## Review artifacts

Open storage/datasets/staging/mikania_micrantha_ph/review_gallery.html for a local read-only gallery with full-size image links, source observations, attribution and similarity groups. It does not save decisions.

The companion review_queue.csv contains all 50 pending candidates. Record qualified visual/provenance decisions separately before integration. Inspect diagnostic evidence at full size; flag ambiguous labels, mixed subjects, unclear location evidence or images unsuitable for field-photo classification. Inspect herbarium images as a separate domain; they should not dominate training or serve as a substitute for a field-photo test set.

Do not copy labels from the original owner's approval of the existing 243 images. That approval did not review these new candidates. Do not use the current default approved-export workflow for this proposed class before extending the class registry and review/export support together. This staging gallery and queue deliberately require no class activation.

## Isolation and verification

- Staging root: storage/datasets/staging/mikania_micrantha_ph.
- Source manifest: raw/manifest.jsonl under that root; all labels pending.
- Evidence: docs/mikania-staging-evidence.json.
- Existing main raw manifest SHA-256 remained 556b9384476b104874f0f24f146bb3266e44de4305e048c234b6e282e2a40e43.
- Validated 50 unique source IDs, 50 gallery cards, existing image paths and pending PH-source records.
- Existing 243-image corpus, species.yaml, v3 splits and trained candidate were preserved. No training occurred.

Reusable collector: scripts/collect_mikania_staging.py. It resumes source IDs and regenerates the review queue/gallery; the generated queue is not an authoritative review-decision ledger. It may report fewer additions on subsequent runs. This collection result does not establish that all available Mikania images have been exhausted.

Next: qualified image/provenance review, then decide if local independent coverage is sufficient to register Mikania as a new training class. Acquire more independent Philippine field photos or a separately tracked supplemental corpus if coverage remains too small.
