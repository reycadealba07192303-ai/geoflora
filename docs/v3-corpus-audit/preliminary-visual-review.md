# Preliminary visual triage: v3 corpus

Date: October 31, 2026

This is an assistant visual screen of the generated contact sheets, not botanical verification or a change to the source labels. The v3 manifest, review history, original images, and active model were not modified.

## Findings

- The contact sheets contain obvious dried herbarium/specimen-sheet photos in all three classes and in train, validation, and test partitions. These are not representative of the intended cellphone field-photo workflow.
- The 23 metadata-keyword candidates below visibly appear to be specimen sheets. Some additional specimen sheets are visible without those metadata keywords, so this list is a minimum known hold list, not a complete count.
- A second pass over the provisional contact sheets found 23 more obvious specimen sheets that had no keyword flag: `V3-0002`, `V3-0015`, `V3-0017`, `V3-0027`, `V3-0058`, `V3-0071`, `V3-0088`, `V3-0089`, `V3-0113`, `V3-0133`, `V3-0136`, `V3-0164`, `V3-0166`, `V3-0174`, `V3-0184`, `V3-0185`, `V3-0194`, `V3-0203`, `V3-0211`, `V3-0225`, `V3-0227`, `V3-0230`, and `V3-0243`.
- `V3-0068` shows harvested water hyacinth on pavement rather than an in-situ field image, so it is held for scope review.
- After those holds, 103 records remain and look like live field photos in the contact sheets: 44 Hagonoy, 44 Lantana, and 15 Water Hyacinth. They represent only 69 source observation groups: Hagonoy 19/5/7 groups (train/validation/old test), Lantana 16/5/6, Water Hyacinth 6/3/2. This is only an assistant visual screen. Species labels and row-level Philippine geography remain unverified, so this list is not training-ready. The old test split has already been used in prior evaluation and is not a new blind test.
- 93 recomputed near-duplicate pairs (all groups of two) appear in the mechanical audit, often the same iNaturalist image represented again in GBIF. No exact checksum duplicates or cross-split checksum/observation/near-duplicate groups were found. Near-duplicate pairs should still be confirmed before any clean split is made.
- All 243 files opened and matched their manifest checksums. All 243 have current approved review records. These checks do not verify species identity, Philippine locality, field context, or independence of observations.
- A separate candidate review manifest now marks 23 known specimen sheets and 93 redundant near-duplicate copies as held, leaving 127 provisional representatives/singletons for visual review. It is explicitly **not training-ready**; other specimen sheets may remain among those 127 until reviewed.

## Known specimen-sheet candidates

Do not use these in a field-photo benchmark until the image-use scope is resolved. `review_id` maps to `review.csv` and the contact sheets.

| Review ID | Class | Split |
|---|---|---|
| V3-0001 | *Chromolaena odorata* | train |
| V3-0003 | *Lantana camara* | train |
| V3-0016 | *Lantana camara* | test |
| V3-0038 | *Lantana camara* | test |
| V3-0039 | *Lantana camara* | train |
| V3-0059 | *Pontederia crassipes* | train |
| V3-0087 | *Chromolaena odorata* | train |
| V3-0098 | *Lantana camara* | test |
| V3-0099 | *Lantana camara* | train |
| V3-0103 | *Lantana camara* | train |
| V3-0104 | *Chromolaena odorata* | train |
| V3-0106 | *Pontederia crassipes* | train |
| V3-0111 | *Lantana camara* | train |
| V3-0112 | *Chromolaena odorata* | validation |
| V3-0165 | *Lantana camara* | train |
| V3-0167 | *Lantana camara* | train |
| V3-0179 | *Lantana camara* | train |
| V3-0188 | *Lantana camara* | train |
| V3-0193 | *Lantana camara* | train |
| V3-0206 | *Chromolaena odorata* | train |
| V3-0212 | *Pontederia crassipes* | train |
| V3-0226 | *Lantana camara* | validation |
| V3-0238 | *Lantana camara* | train |

## Next action

The second-pass screen did not reveal another obvious specimen sheet among the remaining 103 entries. The machine-generated [candidate review manifest](candidate-review-manifest.csv), [preliminary field-photo list](preliminary-field-photos.csv), [provisional representatives](provisional-representatives.csv), and [candidate summary](candidate-summary.json) are review aids only. Keep the current corpus frozen. Before using these as a training snapshot, confirm labels/provenance with qualified review and acquire a fresh blind test cohort; this visual screen is not expert sign-off.
