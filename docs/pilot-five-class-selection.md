# Five-class experimental selection

Decision date: October 23, 2026 (Asia/Manila). The owner confirmed Philippine location, required invasive-species scope and delegated class selection. Country is recorded from owner attestation; no independent geolocation is claimed. Label approvals remain owner-based.

## Selected direction

| Species | Common name | Candidate images retained |
|---|---|---:|
| Chromolaena odorata | Hagonoy | 85 |
| Lantana camara | Lantana | 82 |
| Pontederia crassipes | Water Hyacinth | 30 |
| Mikania micrantha | Mile-a-minute | 7 |
| Pistia stratiotes | Water Lettuce | 7 |

Total: 211 distinct normalized image checksums. This is a selection pool, not a new frozen dataset version or a validated five-class model.

The initial three classes and Mikania have Philippine invasion references in the [national report, Table 3](https://www.cbd.int/doc/world/ph/ph-nr-04-en.pdf#page=23) and/or the dated [NISSAP draft](https://www.philchm.ph/wp-content/uploads/2019/03/NISSAP-Philippines-2016_final-draft.pdf). [CDFP Araceae](https://www.philippineplants.org/Families/Araceae.html) provides the Pistia invasion note. These are research inclusion references, not a declaration that every location is invaded or a regulatory classification.

## What was checked

- Updated all 674 batch review events with owner-confirmed PH location while preserving label attestation and ecological holds.
- Visually inspected all ten batch Mikania and ten batch Pistia images as an image-quality/domain screen. This is not an independent botanical certification.
- Retained seven field photos of each. Held three Mikania images with blur/distant dark subjects; held three Pistia images with distant habitat-only views or a mixed subject.
- New retained records have explicit assistant visual-domain evidence plus owner label/country evidence. The other 660 batch records remain held; country confirmation alone does not resolve domain/ecological issues.
- Existing three-class selection retains 197 previously approved images whose source URLs indicate iNaturalist photos. These were not all newly visually rechecked. Forty-six legacy non-photo-source records were excluded from this field-photo candidate pool without deleting their originals.
- Verified selected image paths/checksums, removed exact duplicates and recomputed near-duplicate/source grouping for dry split feasibility. Distinct checksums do not guarantee independent observations.

## What stays out

- Piper aduncum and Pachystachys coccinea: only one available batch observation/similarity component each for field-photo candidates, unsuitable for meaningful grouped train/validation/test partitions.
- Broussonetia and Salvinia: current batch coverage lacks qualifying field-photo candidates for this selection.
- Native/cryptogenic conflicts and introduced-only taxa without sufficient Philippine invasion evidence remain held. No attempt was made to fill all 100 classes.
- The separate 50-image Mikania staging remains pending its own label review; it is not silently included under approval of the 674-record batch.

## Readiness and next work

The two new classes are acquisition priorities, not robustly training-ready classes. Dry grouping produces only two Mikania training images and three Pistia training images under the current splitter. Those numbers are too small for credible expanded-model validation. Do not train or advertise a dependable five-class model from this pool alone.

Next, collect/review more independent Mikania and Pistia field observations, including adjudication of the existing separate Mikania corpus. Preserve v3 and its evaluation history. After coverage improves, freeze a new dataset version, protect independent holdouts and update the class mapping/training configuration together. No active registry, original training manifest, model artifact or final split was changed here.

## Artifacts and reproduction

- storage/datasets/selection/pilot_five_classes/selected_classes.json: class direction, counts, references and dry feasibility numbers.
- selected_candidates.csv: 211 records with provenance and explicit review/domain/country bases.
- visual_screening.json: the 20 inspected paths and six exclusion reasons.
- docs/batch-country-confirmation.json: owner country-attestation scope.

Run `services/ml/.venv/Scripts/python.exe scripts/select_pilot_classes.py` from the root to regenerate the selection from current evidence. The six-image floor in this prototype is a mechanical feasibility guard only, not a scientific sample-size requirement. Output is explicitly experimental; source records and owner approvals are preserved.
