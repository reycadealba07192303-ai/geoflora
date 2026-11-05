# Water Hyacinth Wikimedia Commons review pilot

Audit date: 2026-11-01 (Asia/Manila)

## Result

- Wikimedia Commons category checked: [Pontederia crassipes in the Philippines](https://commons.wikimedia.org/wiki/Category:Pontederia_crassipes_in_the_Philippines), 153 file pages at audit time.
- 73 files had an explicit CC0, CC BY 2.0, CC BY-SA 3.0, or CC BY-SA 4.0 license. All had a photographer/artist field. The license URL and individual source page are retained in the review CSV.
- 80 files marked Public domain were excluded because the current GeoFlora dataset policy for this pilot accepts CC0/CC BY/CC BY-SA. This is a project-scope exclusion, not a legal conclusion that public-domain material cannot be used. Missing or unclear licenses are never treated as permission.
- The 73 provisionally rights-eligible files are heavily concentrated in a few numbered photo sequences and locations. To avoid representing sequential frames as independent observations, the manual queue contains one representative from each of 14 apparent Commons title/location series. This is a review shortlist, not 14 confirmed observations.
- All 73 rights-eligible Commons thumbnails were compared with the 36 Water Hyacinth v3 images using perceptual hashes. None was within 12 bits of a v3 hash. This screen found zero likely cross-dataset near-duplicates; it does not prove there are no crops, edited versions, or exact source matches. Five pairs within the Commons candidate pool were within 12 bits of one another (four at distances 10–12 and one at distance 8); these are from the same Pulilan numbered sequence and are kept together for manual sequence/group review.
- The 14-item visual queue keeps one representative from each apparent Commons title/location sequence; the other 59 rights-eligible image files are documented in the audit CSV but were not added to the queue as separate candidate observations. This is a lightweight review shortlist, not duplicate-based exclusion.
- Zero labels, field-photo status, Philippine provenance, or observation groups have been approved. Accordingly, there are **zero confirmed new independent observation groups** and zero additions to the approved training dataset.
- The current MobileNetV2 v3 model and curated v3 manifest were not changed. No v4 training was started.

## Manual review files

- `../storage/datasets/staging/water_hyacinth_commons_pilot_20261101/review_gallery.html` — local visual queue with links to original Commons pages.
- `../storage/datasets/staging/water_hyacinth_commons_pilot_20261101/review_queue.csv` — source IDs and URLs, photographer attribution, license and license URL, source description/date, uploader, available GPS metadata, preview hash, duplicate screen, and pending human-review fields.
- `../storage/datasets/staging/water_hyacinth_commons_pilot_20261101/commons_license_counts.csv` — category license counts and the pilot's inclusion decision.
- `../storage/datasets/staging/water_hyacinth_commons_pilot_20261101/commons_candidate_duplicate_audit.csv` — source/license metadata and perceptual-hash comparison for all 73 provisionally rights-eligible files.

Review each original file page, image, license terms, and attribution before reuse. Commons' [reuse guidance](https://commons.wikimedia.org/wiki/Commons:REUSE) notes that reusers need to check the individual file's copyright and license information. The 49 CC BY-SA files retain share-alike terms; confirm those terms are acceptable for the intended dataset/model distribution before including them in any training release. Commons category membership, image text, and embedded coordinates do not independently verify the species or Philippine field provenance. Do not mark a candidate approved until a reviewer verifies the taxon and records the evidence. Treat images from one sequence/site/date as one group unless evidence supports distinct observations.

## Collection and blind-test recommendation

For development data, use the 14 queued previews to decide whether a candidate is genuinely a field photo of *Pontederia crassipes* and whether its location and source are usable. Request permission or rely only on the file's explicit license; retain the original source ID, URL, photographer, license, attribution, and observation-group evidence. A second reviewer should adjudicate uncertain labels. Keep rejected files and reasons in the queue rather than deleting originals.

For a fresh blind test across Hagonoy, Lantana, and Water Hyacinth, collect new photos directly from Philippine field sites with permission, using phones/cameras already available and a small number of local partners or volunteers. Ask contributors to submit original photos with date, general location, photographer consent, and one observation/event ID; avoid uploading private exact coordinates. Have two reviewers independently label each observation and group burst photos from the same plant/site/time together. Freeze the grouped test manifest and file hashes before training or tuning; keep it out of all development folders and do not inspect test predictions during model selection. Existing v3 test images are historical and should not be recycled as the fresh blind set.

## Decision

This pilot is **not ready for a v4 experiment**. It has a small, rights-screened manual queue, but no approved new Water Hyacinth labels and no confirmed independent observation groups. First complete human review and collect/approve development observations. Separately collect and freeze a fresh, independently labeled test set for all three classes. Only then prepare a v4 configuration for approval; keep the current v3 model available and unchanged.

## Scope and reproducibility

The queue preparation helper is `../scripts/prepare_water_hyacinth_commons_pilot.py`. It queries Commons file metadata, accepts only the four explicit CC license labels above, and keeps labels/provenance/grouping pending. The downloaded previews are 640-pixel Commons thumbnails for review and duplicate screening, not training assets. The script does not approve, curate into v3, or train a model.
