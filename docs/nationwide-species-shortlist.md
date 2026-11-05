# Nationwide species shortlist and dataset expansion plan

Prepared October 23, 2026 (Asia/Manila). Scope confirmed by the owner: nationwide Philippines. Ten proposed research targets; only the existing three classes are currently configured. No species registry, model mapping or database ecological flags were changed.

## Evidence and meaning

The Philippines Fourth National Report to the CBD (2009), printed page 23, Table 3 lists the ten taxa below; its introduction describes potential invasive alien species. This is historical evidence for a research shortlist, not a current exhaustive or legally designated priority list. Water hyacinth appears under an older name/spelling. [National report, Table 3](https://www.cbd.int/doc/world/ph/ph-nr-04-en.pdf#page=23).

The 2016?2026 NISSAP draft discusses hagonoy, lantana and water hyacinth as Philippine invasion concerns. Treat the linked version as a dated draft, not proof of the latest adopted policy. [Philippine CHM document](https://www.philchm.ph/wp-content/uploads/2019/03/NISSAP-Philippines-2016_final-draft.pdf).

The PIA report dated August 29, 2025 describes local impacts of lantana and ipil-ipil in the wetland-park context. It does not establish that either invades every region. [PIA report](https://pia.gov.ph/features/beautiful-but-invasive-species-threatening-wetlands/).

## Proposed classes and live image availability

| Scientific name | Common name | PH observations | Global observations, includes PH | Current class? |
|---|---|---:|---:|---|
| Chromolaena odorata | Hagonoy | 33 | 2125 | Yes |
| Lantana camara | Lantana / coronitas | 28 | 6415 | Yes |
| Pontederia crassipes | Water hyacinth | 12 | 3251 | Yes |
| Leucaena leucocephala | Ipil-ipil | 28 | 2915 | Proposed |
| Mikania micrantha | Mile-a-minute | 13 | 1280 | Proposed |
| Broussonetia papyrifera | Paper mulberry | 0 | 2752 | Proposed |
| Coccinia grandis | Ivy gourd | 33 | 1011 | Proposed |
| Swietenia macrophylla | Big-leaf mahogany | 1 | 133 | Proposed |
| Acacia mangium | Mangium | 0 | 312 | Proposed |
| Acacia auriculiformis | Auri | 3 | 310 | Proposed |

Counts are live iNaturalist research-grade **observations with at least one allow-listed photo**, not downloaded photos, reviewed labels, or independent groups. Query: exact active species match, photo_license=cc0,cc-by,cc-by-sa, PH place filter for the PH column. Global counts include PH and must not be added to the PH count. Multiple photos or repeated observations can reduce independence. Counts can change and cannot guarantee download availability, rights completeness or usable training data. Zero means no results under this query, not absence from the Philippines.

Full timestamp, taxon IDs, API results, evidence links and probe status are saved in nationwide-species-availability.json. Reproduce using scripts/check_species_shortlist.py; this read-only probe downloads no images.

## Recommended sequence

1. Retain the three existing classes as the experimental baseline. Their test scores do not apply to a future ten-class model.
2. Prioritize feasibility review and bounded candidate collection for Leucaena leucocephala, Mikania micrantha and Coccinia grandis. This is an engineering prioritization based on the observed PH photo availability, not a ranking of ecological harm. Review possible lookalikes and field identification requirements before class activation.
3. Keep Broussonetia papyrifera, Swietenia macrophylla, Acacia mangium and Acacia auriculiformis as proposed classes with PH-data gaps. Obtain independent local observations and current ecological evidence before including them in the local evaluation benchmark.
4. Use licensed non-PH photos only in a separate supplemental training corpus. Explicitly exclude Philippine observations from the global training import, plus cross-source copies and observations linked to Philippine holdouts. Preserve actual source country; unresolved location goes to quarantine.
5. Stage a bounded collection of at most 100 unique candidate images per proposed class initially, with a recorded storage/request budget. This is a feasibility target, not proof of adequate model quality. Do not automatically approve new labels.
6. Measure approved independent observations and image diversity before choosing the final class count. Do not force ten classes if some cannot support valid evaluation.

## Nationwide data requirements

- Record verified source country, source observation ID, license, attribution and review basis for each image; preserve source snapshots/checksums and acquisition date.
- For Philippine records, summarize Luzon, Visayas and Mindanao coverage from verified locality/coordinates. Missing or obscured coordinates remain unknown; do not infer locations from photographs.
- Include varied backgrounds, plant parts, growth stages and devices. Avoid allowing source/background differences alone to identify each class.
- Freeze observation/duplicate groups before splitting. Keep v3 and its existing evaluation history intact; the next expanded dataset uses a new version and class mapping.
- Use validation for tuning; collect an untouched prospective Philippine test set for final evaluation. Report class support and regional gaps. Nationwide reporting scope is not nationwide model validation.
- Test unsupported plants and non-plant inputs explicitly. A multiclass softmax model can confidently misclassify an unsupported species.

## Activation checklist

- [ ] Current Philippine ecological evidence and taxonomy reconciled for each additional class.
- [ ] Bounded images acquired with adequate rights/provenance.
- [ ] New labels reviewed; conflicts and duplicates resolved.
- [ ] Philippine geographic evidence and regional coverage documented.
- [ ] Enough independent groups for all evaluation classes.
- [ ] New dataset version, model output width and mapping updated together.
- [ ] Per-class quality, unsupported-input behavior and latency evaluated.

This step completes the shortlist and availability investigation only. It does not download the global corpus, approve new images, change the active classes or train a ten-class model.

## Subsequent ecological cross-check

The later CDFP check marks Coccinia grandis as cryptogenic (origin uncertain). Its earlier image-based collection priority is therefore on hold for invasive-alien class inclusion pending ecological reconciliation. Image availability alone does not establish Philippine invasive status. See species-100-verification-report.md and the separate verification ledger.

## Updated next-class recommendation: *Pistia stratiotes*

For the next experimental class after the three-class baseline, prioritize Water Lettuce (*Pistia stratiotes*) over candidates with a Philippine-data gap. The source ledger marks it as source-flagged invasive, the Co's Digital Flora Araceae entry identifies it as non-native/naturalized and cites an invasive-species source, and bounded staging runs have 168 Philippine image records across 148 observation groups. The owner confirmed the gallery class labels. However, only 7 images across 6 groups use the CC BY/CC0 licenses eligible for invasive training; the remaining 161 CC BY-NC photos are excluded by the current training policy. This remains a research candidate, not an ecological approval or a production class addition. Its existing 11-class candidate failed quality and benchmark gates. See [the candidate dossier](model-expansion-candidate-pistia-stratiotes.md), [current expansion status](model-expansion-status-2026-10-31.md), and [Water Lettuce gallery](http://127.0.0.1:8767/invasive_pistia_stratiotes_ph/review_gallery.html) while the local preview server is running.
