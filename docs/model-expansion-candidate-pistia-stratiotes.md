# Recommended next research class: *Pistia stratiotes*

Updated: October 31, 2026

## Recommendation

Water Lettuce (*Pistia stratiotes*, kiapo) is the next **experimental research class**. The owner reviewed and accepted the staging gallery as candidate Water Lettuce images. That approval does not activate the class in the classifier; a leakage-safe candidate must still meet the model promotion gates.

This is the strongest practical next step from the already-screened invasive-species pool: the Philippines research queue marks it as source-flagged invasive, its Philippine plant-flora record says it is non-native/naturalized and cites an invasive-species source, and a bounded iNaturalist collection has already staged a useful local corpus. The DENR field guide describes it as a common, widely distributed floating plant in Philippine water bodies and rice paddies; PhilRice documents it as a weed in irrigated lowland ricefields and describes its cabbage-like rosette. [GRIIS Philippines checklist](https://www.gbif.org/dataset/1b1f1153-f54e-418f-b9c8-3f86a2f680b4), [Co's Digital Flora of the Philippines, Araceae](https://www.philippineplants.org/Families/Araceae.html), [DENR field guide](https://erdb.denr.gov.ph/wp-content/uploads/2023/06/denr_v12.pdf#page=15), [PhilRice ricefield weeds guide](https://www.philrice.gov.ph/weeds-irrigated-rainfed-lowland-ricefields-philippines/).

## Available staged data

- 168 iNaturalist image records from the Philippines; 148 source observation groups. A continuation after the earlier result added 12 images.
- License counts: 161 CC BY-NC, 5 CC BY and 2 CC0. Per the invasive-model training policy, only the 7 CC BY/CC0 photos (6 source observation groups) are currently training-eligible. A bounded rescan with the eligible-license filter found no additional PH photos. The CC BY-NC photos remain visible in the gallery and are marked as excluded from invasive training.
- All 168 are currently marked `research_grade`; this is community-agreed identification, not independent botanical review.
- The collection script reported no invalid files or download rejections. The queue contains six exact-duplicate checksum groups (12 rows total); training freeze now retains one copy. The collector found eight duplicate/near-duplicate group IDs; keep them together in any future split.
- Staging path: `storage/datasets/staging/invasive_pistia_stratiotes_ph/`.
- Evidence report: [staging collection report](staging-pistia_stratiotes-evidence.json).
- Review gallery: [Water Lettuce](http://127.0.0.1:8767/invasive_pistia_stratiotes_ph/review_gallery.html) while the local preview server is running.

## Inclusion limits and next gate

The invasive flag and Philippine flora notes are evidence for a research candidate, not proof of a current legal designation in every locality. iNaturalist labels are community-agreed, and exact locations have not been independently verified. AI screening was unavailable during the collection window because its shared daily quota was exhausted. The owner accepted the gallery as candidate Water Lettuce images, but seven eligible photos across six groups are not enough to establish a reliable new class or a 95% result. The existing experimental 11-class candidate fails the quality and fixed-benchmark promotion gates; details are in [model expansion status](model-expansion-status-2026-10-31.md). Keep the current three-class active model unchanged.

Next: collect more Philippine field images with eligible licenses, preserve each source/license citation, deduplicate, and reserve a new independent test cohort before making another four-class candidate. Do not use the old v3 test as a new blind benchmark or claim 95% based on a small staging split.
