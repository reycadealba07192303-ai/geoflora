# GeoFlora-ML-Lab Dataset Inventory

Generated: 2026-11-05T18:07:53+00:00

This inventory describes externally sourced photographs (e.g. GBIF-mediated records). They are **not**
original GeoFlora field observations and none has been botanically reviewed unless the review columns
below say so. Only images with `review_status = approved` and a named reviewer can be used as training labels.

## Totals

- Images in manifest: 9950
- Independent observation groups: 8770
- Readable: 9950 | Quality pass: 9926 | License eligible: 9950
- Review status: {'approved': 7428, 'uncertain': 2370, 'rejected': 126, 'pending': 26}
- Training-eligible (approved + quality + license + not duplicate/conflict): 7401
- Quality flags: {'low_resolution': 21, 'too_dark': 3}

## Per species

| Species ID | Scientific name | Role | Ecological status | Status verified | Images | Obs. groups | Quality pass | Pending review | Approved | Training-eligible imgs / groups | Ready to train? |
|---|---|---|---|---|---|---|---|---|---|---|---|
| GF-SP-0001 | *Chromolaena odorata* | target | target_invasive | verified | 800 | 707 | 798 | 3 | 670 | 668 / 606 | yes |
| GF-SP-0002 | *Lantana camara* | target | target_invasive | verified | 400 | 355 | 400 | 0 | 348 | 348 / 311 | yes |
| GF-SP-0003 | *Pontederia crassipes* | target | target_invasive | verified | 400 | 350 | 399 | 1 | 287 | 285 / 264 | yes |
| GF-SP-0101 | *Ageratum conyzoides* | lookalike | unresolved | unverified | 800 | 750 | 795 | 6 | 624 | 624 / 592 | n/a (not a training class) |
| GF-SP-0102 | *Mikania micrantha* | lookalike | target_invasive | verified | 400 | 369 | 399 | 1 | 338 | 337 / 314 | n/a (not a training class) |
| GF-SP-0103 | *Lantana montevidensis* | lookalike | unresolved | unverified | 400 | 352 | 398 | 2 | 307 | 307 / 287 | n/a (not a training class) |
| GF-SP-0104 | *Duranta erecta* | lookalike | unresolved | unverified | 400 | 375 | 400 | 0 | 298 | 294 / 282 | n/a (not a training class) |
| GF-SP-0105 | *Pistia stratiotes* | lookalike | unresolved | unverified | 400 | 344 | 400 | 0 | 330 | 326 / 288 | n/a (not a training class) |
| GF-SP-0106 | *Pontederia vaginalis* | lookalike | unresolved | unverified | 400 | 346 | 400 | 0 | 302 | 302 / 276 | n/a (not a training class) |
| GF-SP-0107 | *Limnocharis flava* | lookalike | unresolved | unverified | 400 | 380 | 398 | 2 | 289 | 289 / 281 | n/a (not a training class) |
| GF-SP-0201 | *Mimosa pudica* | unknown_eval | unresolved | unverified | 150 | 137 | 150 | 0 | 134 | 133 / 123 | n/a (not a training class) |
| GF-SP-0202 | *Hibiscus rosa-sinensis* | unknown_eval | unresolved | unverified | 150 | 144 | 150 | 0 | 140 | 140 / 134 | n/a (not a training class) |
| GF-SP-0203 | *Ixora coccinea* | unknown_eval | unresolved | unverified | 150 | 144 | 149 | 1 | 135 | 135 / 130 | n/a (not a training class) |
| GF-SP-0204 | *Bidens pilosa* | unknown_eval | unresolved | unverified | 150 | 118 | 147 | 3 | 122 | 121 / 107 | n/a (not a training class) |
| GF-SP-0205 | *Ipomoea aquatica* | unknown_eval | unresolved | unverified | 150 | 135 | 149 | 1 | 135 | 135 / 120 | n/a (not a training class) |
| GF-SP-0206 | *Imperata cylindrica* | unknown_eval | target_invasive | verified | 400 | 363 | 400 | 0 | 196 | 194 / 187 | n/a (not a training class) |
| GF-SP-0303 | *Leucaena leucocephala* | expansion_candidate | target_invasive | verified | 400 | 368 | 400 | 0 | 292 | 291 / 275 | n/a (not a training class) |
| GF-SP-0304 | *Spathodea campanulata* | expansion_candidate | target_invasive | verified | 400 | 326 | 399 | 1 | 161 | 158 / 153 | n/a (not a training class) |
| GF-SP-0305 | *Piper aduncum* | expansion_candidate | target_invasive | verified | 400 | 374 | 400 | 0 | 372 | 372 / 350 | n/a (not a training class) |
| GF-SP-0308 | *Salvinia molesta* | expansion_candidate | target_invasive | verified | 400 | 341 | 400 | 0 | 337 | 337 / 302 | n/a (not a training class) |
| GF-SP-0311 | *Broussonetia papyrifera* | expansion_candidate | target_invasive | verified | 400 | 334 | 399 | 1 | 338 | 337 / 295 | n/a (not a training class) |
| GF-SP-0312 | *Acacia mangium* | expansion_candidate | target_invasive | verified | 400 | 227 | 400 | 0 | 182 | 181 / 156 | n/a (not a training class) |
| GF-SP-0313 | *Swietenia macrophylla* | expansion_candidate | target_invasive | verified | 400 | 348 | 398 | 2 | 238 | 237 / 210 | n/a (not a training class) |
| GF-SP-0314 | *Gmelina arborea* | expansion_candidate | target_invasive | verified | 400 | 380 | 400 | 0 | 304 | 304 / 292 | n/a (not a training class) |
| GF-SP-0315 | *Eucalyptus deglupta* | expansion_candidate | unresolved | unverified | 400 | 386 | 399 | 1 | 276 | 274 / 271 | n/a (not a training class) |
| GF-SP-0316 | *Acacia auriculiformis* | expansion_candidate | unresolved | unverified | 400 | 317 | 399 | 1 | 273 | 272 / 233 | n/a (not a training class) |

## Botanical review requirements

1. A qualified botanist (or the client's designated reviewer) must confirm species identity for each image
   used as a training, validation, test or unsupported-species label. Use `python scripts/review_images.py export`
   to create review sheets, then `python scripts/review_images.py import <sheet.csv> --reviewer "Name"`.
2. Community identifications on source platforms (e.g. iNaturalist research grade) are recorded as provenance
   only; they are not treated as botanical verification by this project.
3. Ecological status for every species with `status_verification = unverified` requires Philippine-specific
   evidence (citation, issuing body, date) and the name of the person who verified it before the model's
   outputs are described as identifying *invasive* species for that class.
4. Reviewers may optionally tag lighting, background, plant organ and growth stage so that the evaluation can
   report performance by photographic condition (research question 8).

## Licensing

Allowed licenses: CC0-1.0, PDM-1.0, CC-BY-4.0, CC-BY-NC-4.0, GEOFLORA-CONTRIBUTOR. Non-commercial (NC) licensed images restrict
commercial use of the image collection; attribution for every image is stored in `metadata/image_manifest.csv`.
