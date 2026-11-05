# Water Lettuce model expansion status

Updated: October 31, 2026

## Owner review

The owner reviewed and accepted the Water Lettuce staging gallery as candidate images of the class. Record this as owner gallery approval, not independent botanical certification or per-photo proof of Philippine locality. The source observations remain community-identified as iNaturalist research grade.

## Data and license gate

The Philippine gallery contains 168 images across 148 observation groups. Its license counts are 161 CC BY-NC, 5 CC BY and 2 CC0. Under the invasive-model training policy, only CC0/CC BY/CC BY-SA records are eligible, so this leaves 7 unique images across 6 observation groups. A bounded rescan of the Philippine iNaturalist records using only eligible licenses found no additional Water Lettuce photos. The 161 CC BY-NC images remain in the review gallery with their attribution, but they are excluded from invasive model training.

The updated collector marks each gallery row's training-license eligibility. Collection now defaults to the license allowlist; `--allow-noncommercial` is an explicit option for staging CC BY-NC images for visual review only.

## Existing candidate and promotion check

The existing experimental 11-class candidate includes Pistia, but its evaluation is below release gates:

- 73.52% top-1 accuracy and 73.53% macro F1 on its 253-image test split.
- Pistia recall is 83.33% (20/24); this split is an exploratory benchmark, not a new blind Philippine test.
- Its Pistia training corpus contains 149 CC BY-NC images among 160 records, so it does not satisfy the invasive training-license policy.
- On the fixed benchmark restricted to the three currently active species, this candidate scores 63.64% accuracy and 71.43% macro recall (33 images); the live model scores 90.91% accuracy and 92.86% macro recall on those same rows.

It therefore fails both the training quality gate and fixed-benchmark comparison. The active three-class model and species mapping remain unchanged; Water Lettuce is not activated.

## Mikania addition and candidate gate

The owner approved both the main Mikania gallery and the 30 supplemental photos. The 151-photo main gallery has 20 unique CC BY/CC0 photos across 13 groups; the supplemental set contributes 30 more CC BY/CC0 photos from 22 groups. After checksum deduplication, v3/v5 benchmark exclusion, and perceptual grouping, the new five-class snapshot contains 124 images; Mikania has 28 train, 12 validation and 7 test images, while Pistia still has only 4/1/1. The candidate scored 39.13% accuracy and 35.24% macro F1 on 23 test images. On the fixed benchmark for the three active species, it scored 54.55% accuracy / 64.76% macro recall versus the live model's 90.91% / 92.86%. It fails the quality and promotion gates, so it was not activated. Verification passed artifact/checksum checks, split isolation, five FastAPI photo predictions, and confirmed the live model was unchanged. See the [new frozen dataset metadata](../storage/datasets/curated/owner_approved_five_class_plus_mikania_supplement_20261031/dataset_metadata.json), [candidate evaluation](../storage/models/candidates/mobilenetv2_owner_approved_five_plus_mikania_supp_20261031/evaluation.json), and [training status](owner-approved-five-plus-mikania-supp-training-status-20261031.json).

The 30 supplemental photos are now recorded as owner-approved candidate images. Approval is still not expert botanical verification; source labels remain community-sourced. View the [supplemental gallery](http://127.0.0.1:8767/invasive_mikania_micrantha_ph/supplemental_review_gallery.html) and the main [approved gallery](http://127.0.0.1:8767/invasive_mikania_micrantha_ph/review_gallery.html).

The three-class recovery experiment reused the 84 preliminary field-like v3 train/validation photos plus eligible staging, while excluding v3/v5 test groups and duplicates. The frozen snapshot retained 75 images (train: 21 Hagonoy, 21 Lantana, 5 Water Hyacinth). Its candidate scored 63.64% accuracy / 46.67% macro F1 on only 11 test photos. On the fixed benchmark it scored 78.79% accuracy / 83.33% macro recall, below the live model's 90.91% / 92.86%. It was not activated. The 84 older rows were not 84 new images: many overlapped existing staging/benchmark records, leaving too little unique development data after filtering.

Next, collect genuinely new, license-eligible Philippine field photos—prioritize Water Hyacinth and Water Lettuce, then broaden Hagonoy, Lantana and Mikania views. The current rechecks found a data shortage, not a reason to change architecture or add epochs. Keep a new blind test cohort separate; the 95% roadmap target has not been demonstrated. See the [roadmap diagnosis and next steps](model-accuracy-roadmap.md#diagnosis-at-susunod-na-recovery-run-october-31-2026).
