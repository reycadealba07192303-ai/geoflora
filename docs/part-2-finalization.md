# Part 2 finalization

Completed: the 100-species collection is retained as a research archive, while the supported experimental subset is explicitly limited to five classes. This does not convert all collected taxa into invasive-model labels.

## Decision

- Included in `curated/v5_part2_final_five_classes`: Chromolaena odorata, Lantana camara, Pontederia crassipes, Mikania micrantha, and Pistia stratiotes.
- Excluded: Caladium bicolor. The earlier v4 exploratory experiment is preserved but unactivated; its inclusion is not sufficient evidence that the species is an invasive target.
- Held: 660 other batch records and the separate 50-image Mikania staging corpus. Neither has been silently promoted.

## What the decisions mean

All included records retain their exact source, checksum, license/attribution, group/similarity IDs, split, reviewer evidence and rationale in the [v5 decision ledger](../storage/datasets/curated/v5_part2_final_five_classes/part2_decision_ledger.csv). Label/location evidence is owner attestation; Mikania and Pistia additionally have the recorded visual field-photo screen. These are not independent botanical or per-record geographic certifications.

The inclusion references are recorded in the dataset metadata and point to the Philippine [NISSAP draft](https://www.philchm.ph/wp-content/uploads/2019/03/NISSAP-Philippines-2016_final-draft.pdf), the [CBD national report](https://www.cbd.int/doc/world/ph/ph-nr-04-en.pdf#page=23), and [CDFP Araceae](https://www.philippineplants.org/Families/Araceae.html). They support research inclusion, not a claim that every photographed site is invaded.

## Supplementation result

No new unreviewed or non-Philippine images were added merely to increase class counts. The Mikania/Pistia counts remain too small for promotion; the separate Mikania candidate corpus remains available for a distinct approval pass.

## Hand-off to Part 3

Part 3 is frozen as [curated v5](../storage/datasets/curated/v5_part2_final_five_classes/README.md): image paths and SHA-256 checksums resolve, every image decodes, rights metadata is present, and checksum/observation/similarity groups do not cross splits. Per-class image and independent-group counts are in `dataset_metadata.json`. Pretraining weights, if used later, are not data records and must remain outside Philippine evaluation partitions.
