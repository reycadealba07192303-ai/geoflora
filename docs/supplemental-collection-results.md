# Supplemental collection results

Date: October 23, 2026 (Asia/Manila).

## Completed bounded runs

Used the existing Philippine-filtered iNaturalist/GBIF collectors. Each run had a 0.1 GB additional image-storage cap and at most three API pages per species/source. Water hyacinth was first, with a limit of 20 new eligible images per source; other classes had a limit of 10 per source. Existing source IDs were skipped and no existing review decisions changed.

1. All three classes, both sources: zero new images, zero additional bytes. GBIF reported 16 failed image candidates across the species (some were previously recorded rejections).
2. Water hyacinth after correcting the iNaturalist photo-license query: zero new images, zero additional bytes; two GBIF candidates failed.

Run reports:

- storage/datasets/reports/supplement_20261022T170135Z.json
- storage/datasets/reports/supplement_20261022T170247Z.json

No new image queue or visual label review was needed because neither run added records. This does not establish that every eligible Philippine image on the internet has been collected. It establishes no additions under these sources, queries, page limits and eligibility policies.

## Collector correction

The iNaturalist query previously used `license`, which filters observation licenses. Changed it to `photo_license`, matching the existing per-photo allow-list (CC0, CC BY, CC BY-SA). Per-photo license/attribution validation, research-grade restriction and Philippine place filtering are retained. A photo may have a different license from its observation metadata; this correction does not certify redistribution rights for all associated metadata.

Official parameter definitions: [iNaturalist v1 API specification](https://github.com/inaturalist/iNaturalistAPI/blob/main/lib/views/swagger_v1.yml.ejs). Regression assertions verify the photo-license parameter and absence of the observation-license filter, alongside existing rejection of restricted photo licenses. All 27 ML tests passed.

Live bounded availability probe for water hyacinth returned 14 research-grade observations under the old observation-license query and 12 under the photo-license query. These are observation counts, not photo counts or independent training groups. The corrected water-hyacinth pass yielded no new eligible photos.

GBIF failures included inaccessible HTTP 403 images, JSON IIIF manifests instead of direct images, files over the 20 MB download limit, and oversized decoded images. Limits were preserved. A future IIIF adapter could resolve permissible image derivatives; no such support was added here.

## Refreshed audit and next action

The dataset remains 243 valid owner-approved images, zero pending: Hagonoy 93, Lantana 114, Water Hyacinth 36. No approvals were added. The existing v3 model candidate, test set and metrics were preserved; no retraining occurred because the corpus did not improve.

The next dataset improvement needs a different source of independent observations: locally captured Philippine photos with date/location and photographer permission, or an eligible offline corpus with a source manifest. External non-PH data must be tracked separately and must not enter a Philippine evaluation split. New records require their own label/provenance review; prior owner approval covers only the original 243 records.

Reusable entry point:

```powershell
.\services\ml\.venv\Scripts\python.exe scripts/collect_supplement.py
.\services\ml\.venv\Scripts\python.exe scripts/collect_supplement.py --species pontederia_crassipes
```

These commands perform a new bounded run and save a timestamped report. Avoid repeating identical collection without a reason to expect changed availability.
