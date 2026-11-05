# Model-accuracy data collection update

Date: October 31, 2026

## Bounded iNaturalist staging run

Collected Philippines-filtered, research-grade iNaturalist image candidates for the three active classes. This wrote only to staging; it did not change the raw/curated training manifests, review history, active model, or species registry. Each downloaded record retains source, attribution, license, country, and observation-group metadata.

| Class | New images | Current valid staged images | Observation groups | Queue status |
|---|---:|---:|---:|---|
| *Chromolaena odorata* | 150 | 302 | 217 | 302 research-grade; 0 AI screened |
| *Lantana camara* | 150 | 300 | 209 | 300 research-grade; 0 AI screened |
| *Pontederia crassipes* | 0 | 129 | 87 | 129 research-grade; 0 AI screened |

No download rejections or integrity/provenance validation failures were reported. The two successful downloads added about 26 MB. Water hyacinth's bounded query returned no new unique images, so its existing staging corpus remains unchanged.

The AI image-screening script was tried once with a five-image limit. The shared OpenRouter free daily allowance was already exhausted, so it screened zero images and stopped without changing queue decisions. The tool reported reset at 2026-11-01 08:00 local time. Avoid relying on it for ground-truth labels even after it becomes available: it only screens visible field-photo suitability. Its AI verdicts do not replace botanical or per-image geographic review.

## Owner label review

On October 31, 2026, the owner reviewed and accepted the Water Lettuce gallery as candidate images for that class, and confirmed the class labels in the *Lantana camara*, *Chromolaena odorata* (Hagonoy), and *Pontederia crassipes* (Water Hyacinth) galleries. This is owner gallery review, not independent botanical certification or confirmation of each image's exact Philippine locality, license, or duplicate status. The source `review_status` values therefore remain unchanged; in particular, `research_grade` remains distinguishable from an AI-screened field-photo approval.

## Water Lettuce expansion decision

The Water Lettuce gallery has 168 PH images across 148 observation groups. Of these, 161 use CC BY-NC, 5 use CC BY and 2 use CC0. Only the 7 CC BY/CC0 images across 6 groups meet the invasive-model license allowlist. A bounded re-scan with that allowlist found no additional Water Lettuce photos. CC BY-NC images remain visible in the gallery for owner review, and the queue marks them as excluded from invasive model training.

An existing experimental 11-class model includes Water Lettuce but is not releasable: 73.52% test accuracy and 73.53% macro F1; Water Lettuce recall is 83.33% on 24 test images. On the fixed benchmark for the three active classes, it scores 63.64% accuracy / 71.43% macro recall versus the active model's 90.91% / 92.86%. The candidate fails both the quality and promotion comparisons. Details: [Water Lettuce expansion status](model-expansion-status-2026-10-31.md).

The owner has approved the main Mikania gallery and its 30-photo supplement. The main gallery has 151 PH research-grade photos, including 20 CC BY/CC0 images across 13 groups; the supplement adds 30 CC BY/CC0 images across 22 source groups. A new five-class candidate used these and the other owner-approved galleries, after checksum, duplicate and benchmark-overlap filtering. It scored 39.13% accuracy / 35.24% macro F1 on a 23-photo test split, and 54.55% accuracy / 64.76% macro recall on the fixed benchmark for the active classes. It failed the promotion gates, so the active model remains unchanged. Verification passed and confirmed the active model was unchanged. The [supplemental gallery](http://127.0.0.1:8767/invasive_mikania_micrantha_ph/supplemental_review_gallery.html) now records owner approval. See [model expansion status](model-expansion-status-2026-10-31.md).

## Follow-up source and quality checks

The iNaturalist collector now resumes using the highest already-staged observation ID (`id_above`) so repeated runs do not keep scanning only the first pages. This follows iNaturalist's [API recommended practices](https://www.inaturalist.org/pages/api%2Brecommended%2Bpractices). A bounded continuation for *Pontederia crassipes* after observation ID `404648725` returned no new licensed research-grade photos. A small GBIF sample returned two media candidates, both already represented by the same iNaturalist photo ID in the staging queue; no additional image was imported.

The reproducible [staging quality audit](../scripts/audit_staging_species.py) rechecked all 731 staged files: all opened and matched checksums; all had license/attribution metadata, PH source filter, observation link, and group metadata. The license check allowed CC BY-NC for staging review. Under the invasive-model training policy, CC BY-NC is excluded; CC0/CC BY/CC BY-SA remain eligible. The audit found 6 exact-duplicate groups (2 Hagonoy, 4 Water Hyacinth; 12 rows total) and 7 additional near-duplicate groups (4 Hagonoy, 1 Lantana, 2 Water Hyacinth). Keep each group together when splitting and retain only one copy of exact duplicates when freezing training data. The automatic training worker now removes exact duplicates and errors on cross-class checksum conflicts. Four Hagonoy images are 223×500 pixels; these remain flagged for judgment, not automatically removed. See the [full audit report](staging-quality-audit-2026-10-31.json). This automated audit does not verify visible field suitability or prove the exact locality.

## Review galleries and source reports

- [Hagonoy review gallery](../storage/datasets/staging/invasive_chromolaena_odorata_ph/review_gallery.html) · [collection evidence](staging-chromolaena_odorata-evidence.json)
- [Lantana review gallery](../storage/datasets/staging/invasive_lantana_camara_ph/review_gallery.html) · [collection evidence](staging-lantana_camara-evidence.json)
- [Water hyacinth review gallery](../storage/datasets/staging/invasive_pontederia_crassipes_ph/review_gallery.html) · [collection evidence](staging-pontederia_crassipes-evidence.json)

## Next step

Water hyacinth remains the data bottleneck: the current iNaturalist query is exhausted through its latest eligible record, and the sampled GBIF media added nothing new. New *Pontederia crassipes* field photos now need to come from direct collection or a genuinely new dataset with usable licenses and Philippine provenance. The owner has confirmed the three gallery class labels as recorded above. Review the four low-resolution Hagonoy photos if they are intended for training, then create a fresh independent blind-test cohort before tuning or reporting a new accuracy estimate. The old v3 test split remains used and cannot serve as a new blind benchmark. No training or model promotion was performed in these data-check steps.
