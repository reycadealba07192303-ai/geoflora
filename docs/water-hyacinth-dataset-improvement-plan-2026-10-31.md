# Water Hyacinth data improvement and training plan

Status: proposal for owner approval. No source images, labels, splits, or model artifacts were changed for this plan; no training was started.

## Current usable data

The active v3 corpus has 243 owner-approved rows: 93 Hagonoy, 114 Lantana, and 36 Water Hyacinth. The review is owner attestation, not independent botanical or per-row Philippine provenance verification.

### Water Hyacinth counts

| Inventory | Rows/images | Distinct observation groups | Rights/review status |
|---|---:|---:|---|
| Active v3 total | 36 | 28 | Owner-approved class gallery; not expert-certified |
| v3 train | 23 | 19 | 8 rows / 6 groups appear field-like after preliminary visual triage |
| v3 validation | 5 | 5 | 3 rows / 3 preliminary field-like groups |
| Old v3 test | 8 | 4 | 4 rows / 2 preliminary field-like groups; already inspected, not reusable as a fresh blind test |
| Existing iNaturalist staging | 129 | 87 | Owner confirmed gallery class labels; rows remain `research_grade` |
| Staging under current invasive-training license allowlist | 14 | 11 | 11 CC BY, 1 CC BY-SA, 2 CC0; all 14 source IDs/checksums already occur in v3, so zero new independent development images |
| Staging excluded by current policy | 115 | — | CC BY-NC; retain in staging/review only, exclude from invasive classifier training |

The full v3 manifest's source-group counts (which include items later held by the visual audit) are:

| Class | Train groups | Validation groups | Old test groups |
|---|---:|---:|---:|
| Hagonoy | 42 | 11 | 14 |
| Lantana | 55 | 14 | 13 |
| Water Hyacinth | 19 | 5 | 4 |

The field-like subset's preliminary group counts are lower: Hagonoy 19/5/7, Lantana 16/5/6, and Water Hyacinth 6/3/2 (train/validation/old test). These are assistant visual triage counts, not human botanical approvals. A fresh blind test set currently has **zero** groups in every class.

## Existing quality issues

- The v3 visual review held 46 of 243 images as specimen sheets: 8 Hagonoy, 32 Lantana, and 6 Water Hyacinth. One additional Hagonoy record was held for context review. These stay on disk; a new dataset snapshot should exclude held rows without deleting originals.
- The v3 audit found 93 near-duplicate copies across classes. There was no detected cross-partition leakage, but duplicates within a partition inflate image counts; the old test has only 31 observation IDs and 24 recomputed near-duplicate groups across 39 rows.
- For Water Hyacinth, the visual triage classified 15/36 rows as preliminary field-like (14 representatives and one singleton) across 11 groups; 14 near-duplicate copies and 6 specimen sheets were held, plus one context hold. This does not prove the other 21 are mislabeled; it means they need qualified review or should be held from a field-photo benchmark.
- No v3 label is confirmed mislabeled by an independent botanist. The source labels and owner gallery confirmation are not enough to claim that none are wrong. Qualified review is needed for uncertain lookalikes and provenance.
- Staging integrity checks decoded all 129 Water Hyacinth files. The staging audit found four exact-duplicate groups (eight rows) and two additional near-duplicate groups for this class. Duplicate members remain preserved with their source IDs.
- Four 223×500 low-width images were found in Hagonoy staging; no Water Hyacinth resolution failure was reported. The Water Hyacinth v3 non-field/specimen holds remain the main image-quality issue.

## New source candidates

1. **Direct Philippine field collection with contributors, local universities, LGUs, and aquatic-plant/river-lake groups.** Prioritize this source. Capture multiple sites, seasons, plants, distances, growth stages, and phones; obtain written photo and model-training permission, date, coarse locality, source/photographer ID, and a license that the current policy accepts. Keep names and precise coordinates private where needed.
2. **iNaturalist Research Grade, Philippines, filtered by each photo's license.** Continue only as a bounded availability check after a genuinely different query or new observations are expected. The project already has 129 staged rows; its 14 CC0/CC BY/CC BY-SA images overlap v3, and previous bounded runs found no new eligible Water Hyacinth photos. iNaturalist documents a distinct `photo_license` filter and recommends rate-limited, filtered API use. [API search parameters](https://www.inaturalist.org/api), [API recommended practices](https://www.inaturalist.org/pages/api%2Brecommended%2Bpractices).
3. **Wikimedia Commons Philippines category: discovery only, currently on rights hold.** The category lists 153 files, but the audit of file metadata found 50 marked “Public domain” and 103 with no license short name. Many filenames are numbered photo sequences, so file count is not observation count. The current project allowlist is CC0/CC BY/CC BY-SA; verify each individual file's license, attribution, field suitability, locality, and observation grouping before any import. Commons itself advises checking each file's copyright status. [Philippines category](https://commons.wikimedia.org/wiki/Category:Pontederia_crassipes_in_the_Philippines), [Commons reuse guidance](https://commons.wikimedia.org/wiki/Commons:REUSE).
4. **GBIF: low priority for this class.** Earlier bounded checks added no new independent photo; two media records duplicated iNaturalist images. Any future media needs a field-photo check and image-specific rights check because GBIF warns occurrence media may have more restrictive terms than occurrence records. [GBIF image API guidance](https://techdocs.gbif.org/en/openapi/images).

No new licensed, non-overlapping image was found in the inspected existing staging/source records. The current [Water Hyacinth review gallery](../storage/datasets/staging/invasive_pontederia_crassipes_ph/review_gallery.html) is available, but it contains the existing 129 images, not a new review batch. New contributors or a rights-cleared new source are needed to populate one.

## Initial collection and review target

Use **100–200 independently reviewed Water Hyacinth observation groups** as the initial development milestone, with one to a few useful views per group. Count groups, not files. The preliminary v3 field-like development pool has only 9 groups (6 train + 3 validation), so the gap is approximately **91–191 new eligible groups**, subject to qualified review and duplicate filtering. Do not count old v3 test groups toward the fresh blind test.

For each candidate, retain source ID/URL, license identifier and URL, attribution, date, locality/provenance basis, photographer/observation group, image checksum, review status, reviewer, and rationale. New candidates start `pending`; owner/gallery or AI review never changes that status automatically. Review decisions: `approved`, `relabelled`, `hold`, or `rejected`; preserve every original file and decision history.

## Fresh test set and isolation

- Collect a new cohort from different observation groups, preferably different sites/photographers from the development pool. A small initial pilot target is 30–50 independent groups per species; this can reveal major weaknesses but cannot substantiate a 95% claim. A stronger 95% statement needs a larger sample and confidence interval.
- A qualified reviewer verifies test labels and Philippine field provenance. A custodian freezes the manifest and hashes before training; the training process receives no test images or labels.
- Split by connected components of observation/plant, source IDs, exact checksum, perceptual near-duplicate group, and available photographer/site/date bursts. No component may cross train, validation, and blind test.
- Current fresh-test group counts are **0 Hagonoy, 0 Lantana, 0 Water Hyacinth**. The old v3 test (14/13/4 source groups by class, 24 recomputed near-duplicate groups total) is historical only.

## Draft training configuration

The reproducible, unexecuted draft is [mobilenetv2-v4-wh-improvement-config.json](mobilenetv2-v4-wh-improvement-config.json). It keeps MobileNetV2/ImageNet and the existing 224×224 RGB preprocessing. Proposed generalization changes are:

- Train on the reviewed development snapshot only; deduplicate exact copies and apply observation-group-aware sample weights so observations with many photos do not dominate.
- Use the existing conservative train-only views (original, horizontal mirror, +10° rotation with brightness ×0.9); validation and test use original images only.
- Raise head dropout from 0.20 to 0.35, add L2 weight decay `1e-4`, and lower the frozen-head Adam learning rate from `1e-3` to `3e-4`. Keep batch size 16, seed 42, maximum 60 epochs, and early stop after 8 validation-loss epochs without improvement.
- Optionally fine-tune only the last 20 MobileNetV2 layers at `1e-5` after the head stage; keep BatchNormalization frozen and retain fine-tuning only if grouped validation loss improves. Do not tune using the blind test.
- Save histories, exact manifest hash, class mapping, code/dependency versions, checkpoints, per-class metrics, confusion matrix, non-target false-accept results, and calibration data with a distinct candidate name. Do not write to the active model path.

## Exact gates before any training

1. Acquire new Water Hyacinth groups and enough new Hagonoy/Lantana field observations for a representative three-class evaluation; keep provenance and license metadata.
2. Complete qualified per-image label/provenance review. Separate specimen sheets, low-quality/ambiguous images, and any unresolved rights records into holds; do not delete originals.
3. Freeze a versioned development snapshot plus a separately sealed fresh test cohort. Run automated checksum, group, and near-duplicate leakage checks; publish unique observation counts by class and split.
4. Owner approves the review queue, dataset snapshot, blind-test isolation plan, and this training config. Only then start candidate training.
5. Evaluate the candidate on the blind set once. Report top-1 accuracy, per-class precision/recall/F1, confusion, non-target false acceptance, confidence calibration, supports, and intervals. Keep `mobilenetv2_v3_seed42` and its rollback artifact unchanged unless a later promotion is explicitly approved.

Within the ₱15,000 scope, keep collection to existing free source APIs plus local contributor/partner photos, use a phone camera and the existing review gallery/CSV flow, and avoid paid labeling APIs, dashboards, architecture changes, or new hosting services.
