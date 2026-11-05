# Research Evaluation Report - run-20261104T155431Z-nissap21-v1

*Generated 2026-11-04T17:00:16+00:00 from run artifacts in `models/checkpoints/nissap/run-20261104T155431Z-nissap21-v1`. Dataset version `ds-20261104-5bb0dfbfae`. This model is a research candidate: it has not been deployed or activated in GeoFlora.*

## 1. Summary of observed results

- Classes: 21 (*Chromolaena odorata*, *Lantana camara*, *Pontederia crassipes*, *Ageratum conyzoides*, *Mikania micrantha*, *Lantana montevidensis*, *Duranta erecta*, *Pistia stratiotes*, *Pontederia vaginalis*, *Limnocharis flava*, *Imperata cylindrica*, *Leucaena leucocephala*, *Spathodea campanulata*, *Piper aduncum*, *Salvinia molesta*, *Broussonetia papyrifera*, *Acacia mangium*, *Swietenia macrophylla*, *Gmelina arborea*, *Eucalyptus deglupta*, *Acacia auriculiformis*)
- Independent test images: 931 from 861 observation groups
- Test accuracy: **82.5%** (95% exact binomial CI 79.9% - 84.9%; observation-group bootstrap CI 80.1% - 84.8%)
- Macro F1: **0.830** (CI 0.805 - 0.850); weighted F1: 0.825
- Unsupported-species false acceptance: 100% without rejection (closed-set softmax); **22.8%** with the validation-selected threshold, at a supported-species acceptance rate of 60.4%. AUROC 0.764.
- Forward-pass latency (batch 1, median): 24.2 ms on CPU; model file 26.07 MB.

Targets such as a specific accuracy level are only met if the figures above show it on this independent test set.

## 2. Dataset sources and selection criteria

- Source(s): GBIF; source datasets: iNaturalist research-grade observations (6183); unspecified (6)
- Licenses used: CC-BY-NC-4.0: 5482, CC-BY-4.0: 566, CC0-1.0: 141
- Country of record (top): PH: 1377, TW: 886, US: 717, AU: 501, IN: 356, BR: 166, PR: 152, ID: 147
- Selection criteria: still images with an allowed per-image license, basis of record ['HUMAN_OBSERVATION'], at most 1 image(s) per occurrence; quality checks (resolution, blur, exposure, aspect ratio); exact and perceptual duplicate removal; **photo-by-photo screening by a named non-botanist reviewer, starting from iNaturalist research-grade community identifications, with an AI-assisted pre-screen that flagged questionable photos for the reviewer's decision (not expert botanical verification)**.
- Label reviewer(s): Reyca de Alba (6189 images)
- These photographs are external biodiversity records, not GeoFlora field observations.

## 3. Target species and ecological-status evidence

| Index | Species ID | Scientific name | Ecological status | Verification | Evidence |
|---|---|---|---|---|---|
| 0 | GF-SP-0001 | *Chromolaena odorata* | target_invasive | unverified | Recognised by the existing GeoFlora active CNN (client scope). Listed in IUCN SSC ISSG '100 of the World's Worst Invasive Alien Species' (Lowe et al. 2000) - global evidence only. Philippine-specific citation still to be supplied by the client/botanist. / Philippines: DENR-BMB National Invasive Species Strategy and Action Plan (NISSAP) 2020-2030, p. 9 (most noxious invasive plants) and Box 2.1 (https://www.philchm.ph/wp-content/uploads/2024/01/NISSAP-2020-2030.pdf). Citation added 2026-11-04; not yet checked by a named verifier. |
| 1 | GF-SP-0002 | *Lantana camara* | target_invasive | unverified | Recognised by the existing GeoFlora active CNN (client scope). Listed in IUCN SSC ISSG '100 of the World's Worst Invasive Alien Species' (Lowe et al. 2000) - global evidence only. Philippine-specific citation still to be supplied by the client/botanist. / Philippines: DENR-BMB National Invasive Species Strategy and Action Plan (NISSAP) 2020-2030, p. 9 and Box 2.1 (https://www.philchm.ph/wp-content/uploads/2024/01/NISSAP-2020-2030.pdf). Citation added 2026-11-04; not yet checked by a named verifier. |
| 2 | GF-SP-0003 | *Pontederia crassipes* | target_invasive | unverified | Recognised by the existing GeoFlora active CNN (client scope). Listed in IUCN SSC ISSG '100 of the World's Worst Invasive Alien Species' as Eichhornia crassipes (Lowe et al. 2000) - global evidence only. Philippine-specific citation still to be supplied by the client/botanist. / Philippines: DENR-BMB National Invasive Species Strategy and Action Plan (NISSAP) 2020-2030, p. 9 and Box 2.1 (as Eichhornia crassipes) (https://www.philchm.ph/wp-content/uploads/2024/01/NISSAP-2020-2030.pdf). Citation added 2026-11-04; not yet checked by a named verifier. |
| 3 | GF-SP-0101 | *Ageratum conyzoides* | unresolved | unverified | none recorded |
| 4 | GF-SP-0102 | *Mikania micrantha* | unresolved | unverified | Listed in IUCN SSC ISSG '100 of the World's Worst Invasive Alien Species' (global evidence only). / Philippines: DENR-BMB National Invasive Species Strategy and Action Plan (NISSAP) 2020-2030, Box 2.1 (https://www.philchm.ph/wp-content/uploads/2024/01/NISSAP-2020-2030.pdf). Citation added 2026-11-04; not yet checked by a named verifier. |
| 5 | GF-SP-0103 | *Lantana montevidensis* | unresolved | unverified | none recorded |
| 6 | GF-SP-0104 | *Duranta erecta* | unresolved | unverified | none recorded |
| 7 | GF-SP-0105 | *Pistia stratiotes* | unresolved | unverified | none recorded |
| 8 | GF-SP-0106 | *Pontederia vaginalis* | unresolved | unverified | none recorded |
| 9 | GF-SP-0107 | *Limnocharis flava* | unresolved | unverified | none recorded |
| 10 | GF-SP-0206 | *Imperata cylindrica* | unresolved | unverified | Listed in IUCN SSC ISSG '100 of the World's Worst Invasive Alien Species' but generally regarded as native in tropical Asia. Illustrates why global invasive lists cannot be used as Philippine status evidence. / Philippines: DENR-BMB National Invasive Species Strategy and Action Plan (NISSAP) 2020-2030, p. 9 (notes some botanists consider it naturalized) (https://www.philchm.ph/wp-content/uploads/2024/01/NISSAP-2020-2030.pdf). Citation added 2026-11-04; not yet checked by a named verifier. |
| 11 | GF-SP-0303 | *Leucaena leucocephala* | unresolved | unverified | Listed in IUCN SSC ISSG '100 of the World's Worst Invasive Alien Species' (global evidence only). / Philippines: DENR-BMB National Invasive Species Strategy and Action Plan (NISSAP) 2020-2030, Box 2.1 and Table 3.2 (https://www.philchm.ph/wp-content/uploads/2024/01/NISSAP-2020-2030.pdf). Citation added 2026-11-04; not yet checked by a named verifier. |
| 12 | GF-SP-0304 | *Spathodea campanulata* | unresolved | unverified | Listed in IUCN SSC ISSG '100 of the World's Worst Invasive Alien Species' (global evidence only). / Philippines: DENR-BMB National Invasive Species Strategy and Action Plan (NISSAP) 2020-2030, Box 2.1 and Fig. 2.5 (https://www.philchm.ph/wp-content/uploads/2024/01/NISSAP-2020-2030.pdf). Citation added 2026-11-04; not yet checked by a named verifier. |
| 13 | GF-SP-0305 | *Piper aduncum* | unresolved | unverified | Listed in IUCN SSC ISSG '100 of the World's Worst Invasive Alien Species' (global evidence only). / Philippines: DENR-BMB National Invasive Species Strategy and Action Plan (NISSAP) 2020-2030, Box 2.1 and Fig. 2.4 (https://www.philchm.ph/wp-content/uploads/2024/01/NISSAP-2020-2030.pdf). Citation added 2026-11-04; not yet checked by a named verifier. |
| 14 | GF-SP-0308 | *Salvinia molesta* | unresolved | unverified | Listed in IUCN SSC ISSG '100 of the World's Worst Invasive Alien Species' (global evidence only). / Philippines: DENR-BMB National Invasive Species Strategy and Action Plan (NISSAP) 2020-2030, p. 9 and Box 2.1 (https://www.philchm.ph/wp-content/uploads/2024/01/NISSAP-2020-2030.pdf). Citation added 2026-11-04; not yet checked by a named verifier. |
| 15 | GF-SP-0311 | *Broussonetia papyrifera* | unresolved | unverified | Philippines: DENR-BMB National Invasive Species Strategy and Action Plan (NISSAP) 2020-2030, Box 2.1 and Table 3.2 (https://www.philchm.ph/wp-content/uploads/2024/01/NISSAP-2020-2030.pdf). Citation added 2026-11-04; not yet checked by a named verifier. |
| 16 | GF-SP-0312 | *Acacia mangium* | unresolved | unverified | Philippines: DENR-BMB National Invasive Species Strategy and Action Plan (NISSAP) 2020-2030, Box 2.1 and Table 3.2 (https://www.philchm.ph/wp-content/uploads/2024/01/NISSAP-2020-2030.pdf). Citation added 2026-11-04; not yet checked by a named verifier. |
| 17 | GF-SP-0313 | *Swietenia macrophylla* | unresolved | unverified | Philippines: DENR-BMB National Invasive Species Strategy and Action Plan (NISSAP) 2020-2030, p. 9 and Table 3.2 (reforestation species) (https://www.philchm.ph/wp-content/uploads/2024/01/NISSAP-2020-2030.pdf). Citation added 2026-11-04; not yet checked by a named verifier. |
| 18 | GF-SP-0314 | *Gmelina arborea* | unresolved | unverified | Philippines: DENR-BMB National Invasive Species Strategy and Action Plan (NISSAP) 2020-2030, p. 9 and Table 3.2 (reforestation species) (https://www.philchm.ph/wp-content/uploads/2024/01/NISSAP-2020-2030.pdf). Citation added 2026-11-04; not yet checked by a named verifier. |
| 19 | GF-SP-0315 | *Eucalyptus deglupta* | unresolved | unverified | Philippines: DENR-BMB National Invasive Species Strategy and Action Plan (NISSAP) 2020-2030, p. 9 and Table 3.2 (as Eucalyptus spp.) (https://www.philchm.ph/wp-content/uploads/2024/01/NISSAP-2020-2030.pdf). Citation added 2026-11-04; not yet checked by a named verifier. |
| 20 | GF-SP-0316 | *Acacia auriculiformis* | unresolved | unverified | Philippines: DENR-BMB National Invasive Species Strategy and Action Plan (NISSAP) 2020-2030, p. 9 (reforestation species) (https://www.philchm.ph/wp-content/uploads/2024/01/NISSAP-2020-2030.pdf). Citation added 2026-11-04; not yet checked by a named verifier. |

## 4. Images and independent observation groups per class

| Species | Train imgs / groups | Val imgs / groups | Test imgs / groups |
|---|---|---|---|
| *Chromolaena odorata* | 262 / 245 | 57 / 52 | 57 / 52 |
| *Lantana camara* | 243 / 218 | 53 / 47 | 52 / 46 |
| *Pontederia crassipes* | 199 / 188 | 43 / 40 | 43 / 36 |
| *Ageratum conyzoides* | 257 / 244 | 56 / 53 | 55 / 51 |
| *Mikania micrantha* | 235 / 217 | 51 / 49 | 51 / 48 |
| *Lantana montevidensis* | 215 / 201 | 46 / 42 | 46 / 44 |
| *Duranta erecta* | 206 / 197 | 44 / 43 | 44 / 42 |
| *Pistia stratiotes* | 228 / 198 | 49 / 44 | 49 / 46 |
| *Pontederia vaginalis* | 211 / 193 | 46 / 42 | 45 / 41 |
| *Limnocharis flava* | 201 / 194 | 45 / 44 | 43 / 43 |
| *Imperata cylindrica* | 136 / 130 | 29 / 29 | 29 / 28 |
| *Leucaena leucocephala* | 203 / 191 | 44 / 42 | 44 / 42 |
| *Spathodea campanulata* | 110 / 109 | 24 / 23 | 24 / 21 |
| *Piper aduncum* | 260 / 245 | 56 / 50 | 56 / 55 |
| *Salvinia molesta* | 235 / 216 | 51 / 46 | 51 / 40 |
| *Broussonetia papyrifera* | 235 / 205 | 51 / 48 | 51 / 42 |
| *Acacia mangium* | 124 / 106 | 30 / 24 | 27 / 26 |
| *Swietenia macrophylla* | 165 / 141 | 36 / 36 | 36 / 33 |
| *Gmelina arborea* | 212 / 202 | 46 / 45 | 46 / 45 |
| *Eucalyptus deglupta* | 192 / 190 | 41 / 41 | 41 / 40 |
| *Acacia auriculiformis* | 190 / 153 | 41 / 40 | 41 / 40 |

## 5. Preprocessing

EXIF orientation applied, converted to RGB, re-encoded as JPEG (max side 1024 px), resized to 224x224 (bilinear, aspect ratio not preserved), float32 in [0, 255]; MobileNetV2 scaling to [-1, 1] inside the model.
Training augmentation: {'horizontal_flip': True, 'rotation': 0.08, 'zoom': 0.15, 'translation': 0.1, 'contrast': 0.2, 'brightness': 0.2}.

## 6. Training configuration and architecture

- Architecture: MobileNetV2, ImageNet-pretrained, alpha=1.0 -> GlobalAveragePooling -> Dropout(0.3) -> Dense(21, softmax). Parameters: 2,284,885.
- Phase 1 (frozen base): up to 20 epochs, Adam lr=0.001.
- Phase 2 (fine-tuning layers >= 80, BatchNorm frozen): up to 30 epochs, Adam lr=3e-05. Selected phase: **finetune** (lowest validation loss).
- Early stopping (patience 5), ReduceLROnPlateau, checkpointing on validation loss; batch size 16; seed 42; class weights: {'0': 0.7849872773536896, '1': 0.8463648834019204, '2': 1.033500837520938, '3': 0.8002594033722439, '4': 0.875177304964539, '5': 0.9565891472868217, '6': 0.9983818770226537, '7': 0.902046783625731, '8': 0.9747235387045814, '9': 1.023217247097844, '10': 1.5122549019607843, '11': 1.013136288998358, '12': 1.8696969696969696, '13': 0.791025641025641, '14': 0.875177304964539, '15': 0.875177304964539, '16': 1.6586021505376345, '17': 1.2464646464646465, '18': 0.970125786163522, '19': 1.0711805555555556, '20': 1.0824561403508772}.
- Epochs run: 50; training time 3880.0 s.

## 7. Train / validation / test methodology

Images were partitioned by observation group (same occurrence, exact duplicates, perceptual near-duplicates [pHash Hamming <= 6], and same recorder on the same day) with target ratios {'train': 0.7, 'val': 0.15, 'test': 0.15}. Assignments are sticky across dataset versions so test images never enter training. Model selection and the unsupported-species threshold used validation data only; the test and unknown_test sets were used once, for this report.

## 8. Evaluation results (test set)

Validation (for reference): accuracy 80.8%, macro F1 0.814.

| Species | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| *Chromolaena odorata* | 0.841 | 0.649 | 0.733 | 57 |
| *Lantana camara* | 0.980 | 0.942 | 0.961 | 52 |
| *Pontederia crassipes* | 0.792 | 0.884 | 0.835 | 43 |
| *Ageratum conyzoides* | 0.800 | 0.727 | 0.762 | 55 |
| *Mikania micrantha* | 0.673 | 0.686 | 0.680 | 51 |
| *Lantana montevidensis* | 0.977 | 0.913 | 0.944 | 46 |
| *Duranta erecta* | 0.925 | 0.841 | 0.881 | 44 |
| *Pistia stratiotes* | 0.816 | 0.816 | 0.816 | 49 |
| *Pontederia vaginalis* | 0.838 | 0.689 | 0.756 | 45 |
| *Limnocharis flava* | 0.929 | 0.907 | 0.918 | 43 |
| *Imperata cylindrica* | 0.967 | 1.000 | 0.983 | 29 |
| *Leucaena leucocephala* | 0.949 | 0.841 | 0.892 | 44 |
| *Spathodea campanulata* | 0.852 | 0.958 | 0.902 | 24 |
| *Piper aduncum* | 0.747 | 1.000 | 0.855 | 56 |
| *Salvinia molesta* | 0.837 | 0.804 | 0.820 | 51 |
| *Broussonetia papyrifera* | 0.636 | 0.686 | 0.660 | 51 |
| *Acacia mangium* | 0.605 | 0.852 | 0.708 | 27 |
| *Swietenia macrophylla* | 0.756 | 0.861 | 0.805 | 36 |
| *Gmelina arborea* | 0.826 | 0.826 | 0.826 | 46 |
| *Eucalyptus deglupta* | 0.929 | 0.951 | 0.940 | 41 |
| *Acacia auriculiformis* | 0.824 | 0.683 | 0.747 | 41 |
| **Macro** | 0.833 | 0.834 | 0.830 | 931 |

Top 3 accuracy: 95.4%.

![Training curves](training_curves.png)

## 9. Confusion matrix

![Confusion matrix](confusion_matrix_counts.png) ![Normalised](confusion_matrix_normalized.png)

Most frequent confusions (true -> predicted): *Mikania micrantha* -> *Broussonetia papyrifera* (7); *Acacia auriculiformis* -> *Acacia mangium* (7); *Chromolaena odorata* -> *Mikania micrantha* (6); *Broussonetia papyrifera* -> *Gmelina arborea* (6); *Pistia stratiotes* -> *Salvinia molesta* (5); *Chromolaena odorata* -> *Ageratum conyzoides* (5); *Ageratum conyzoides* -> *Mikania micrantha* (5); *Gmelina arborea* -> *Broussonetia papyrifera* (4); *Broussonetia papyrifera* -> *Piper aduncum* (4); *Ageratum conyzoides* -> *Chromolaena odorata* (4)

## 10. False-positive and false-negative analysis

| Species | TP | FN | FP | FN predicted as | FP true species | Mean score correct / incorrect |
|---|---|---|---|---|---|---|
| *Chromolaena odorata* | 37 | 20 | 7 | {'Mikania micrantha': 6, 'Ageratum conyzoides': 5, 'Piper aduncum': 3, 'Acacia mangium': 2, 'Broussonetia papyrifera': 2, 'Pontederia crassipes': 1, 'Limnocharis flava': 1} | {'Ageratum conyzoides': 4, 'Mikania micrantha': 2, 'Lantana camara': 1} | 0.750 / 0.499 |
| *Lantana camara* | 49 | 3 | 1 | {'Spathodea campanulata': 2, 'Chromolaena odorata': 1} | {'Lantana montevidensis': 1} | 0.820 / 0.413 |
| *Pontederia crassipes* | 38 | 5 | 10 | {'Piper aduncum': 2, 'Imperata cylindrica': 1, 'Acacia mangium': 1, 'Pontederia vaginalis': 1} | {'Pontederia vaginalis': 3, 'Pistia stratiotes': 2, 'Chromolaena odorata': 1, 'Duranta erecta': 1, 'Limnocharis flava': 1, 'Salvinia molesta': 1, 'Swietenia macrophylla': 1} | 0.788 / 0.414 |
| *Ageratum conyzoides* | 40 | 15 | 10 | {'Mikania micrantha': 5, 'Chromolaena odorata': 4, 'Pontederia vaginalis': 2, 'Broussonetia papyrifera': 1, 'Swietenia macrophylla': 1, 'Pistia stratiotes': 1, 'Acacia auriculiformis': 1} | {'Chromolaena odorata': 5, 'Mikania micrantha': 3, 'Lantana montevidensis': 2} | 0.727 / 0.428 |
| *Mikania micrantha* | 35 | 16 | 17 | {'Broussonetia papyrifera': 7, 'Ageratum conyzoides': 3, 'Pistia stratiotes': 2, 'Chromolaena odorata': 2, 'Acacia mangium': 1, 'Swietenia macrophylla': 1} | {'Chromolaena odorata': 6, 'Ageratum conyzoides': 5, 'Pontederia vaginalis': 2, 'Pistia stratiotes': 1, 'Broussonetia papyrifera': 1, 'Swietenia macrophylla': 1, 'Eucalyptus deglupta': 1} | 0.659 / 0.524 |
| *Lantana montevidensis* | 42 | 4 | 1 | {'Ageratum conyzoides': 2, 'Broussonetia papyrifera': 1, 'Lantana camara': 1} | {'Leucaena leucocephala': 1} | 0.750 / 0.411 |
| *Duranta erecta* | 37 | 7 | 3 | {'Pontederia crassipes': 1, 'Acacia auriculiformis': 1, 'Broussonetia papyrifera': 1, 'Gmelina arborea': 1, 'Swietenia macrophylla': 1, 'Spathodea campanulata': 1, 'Pontederia vaginalis': 1} | {'Limnocharis flava': 1, 'Broussonetia papyrifera': 1, 'Gmelina arborea': 1} | 0.740 / 0.417 |
| *Pistia stratiotes* | 40 | 9 | 9 | {'Salvinia molesta': 5, 'Pontederia crassipes': 2, 'Mikania micrantha': 1, 'Broussonetia papyrifera': 1} | {'Salvinia molesta': 3, 'Mikania micrantha': 2, 'Pontederia vaginalis': 2, 'Ageratum conyzoides': 1, 'Broussonetia papyrifera': 1} | 0.797 / 0.516 |
| *Pontederia vaginalis* | 31 | 14 | 6 | {'Piper aduncum': 3, 'Pontederia crassipes': 3, 'Mikania micrantha': 2, 'Pistia stratiotes': 2, 'Acacia auriculiformis': 2, 'Acacia mangium': 1, 'Salvinia molesta': 1} | {'Ageratum conyzoides': 2, 'Limnocharis flava': 2, 'Pontederia crassipes': 1, 'Duranta erecta': 1} | 0.691 / 0.427 |
| *Limnocharis flava* | 39 | 4 | 3 | {'Pontederia vaginalis': 2, 'Duranta erecta': 1, 'Pontederia crassipes': 1} | {'Gmelina arborea': 2, 'Chromolaena odorata': 1} | 0.729 / 0.356 |
| *Imperata cylindrica* | 29 | 0 | 1 | - | {'Pontederia crassipes': 1} | 0.820 / n/a |
| *Leucaena leucocephala* | 37 | 7 | 2 | {'Swietenia macrophylla': 2, 'Acacia mangium': 1, 'Piper aduncum': 1, 'Lantana montevidensis': 1, 'Eucalyptus deglupta': 1, 'Broussonetia papyrifera': 1} | {'Swietenia macrophylla': 1, 'Acacia auriculiformis': 1} | 0.854 / 0.415 |
| *Spathodea campanulata* | 23 | 1 | 4 | {'Gmelina arborea': 1} | {'Lantana camara': 2, 'Duranta erecta': 1, 'Eucalyptus deglupta': 1} | 0.868 / 0.593 |
| *Piper aduncum* | 56 | 0 | 19 | - | {'Broussonetia papyrifera': 4, 'Chromolaena odorata': 3, 'Pontederia vaginalis': 3, 'Acacia mangium': 3, 'Acacia auriculiformis': 3, 'Pontederia crassipes': 2, 'Leucaena leucocephala': 1} | 0.863 / n/a |
| *Salvinia molesta* | 41 | 10 | 8 | {'Swietenia macrophylla': 3, 'Pistia stratiotes': 3, 'Broussonetia papyrifera': 2, 'Acacia mangium': 1, 'Pontederia crassipes': 1} | {'Pistia stratiotes': 5, 'Pontederia vaginalis': 1, 'Broussonetia papyrifera': 1, 'Gmelina arborea': 1} | 0.789 / 0.363 |
| *Broussonetia papyrifera* | 35 | 16 | 20 | {'Gmelina arborea': 6, 'Piper aduncum': 4, 'Pistia stratiotes': 1, 'Duranta erecta': 1, 'Salvinia molesta': 1, 'Mikania micrantha': 1, 'Swietenia macrophylla': 1, 'Eucalyptus deglupta': 1} | {'Mikania micrantha': 7, 'Gmelina arborea': 4, 'Chromolaena odorata': 2, 'Salvinia molesta': 2, 'Ageratum conyzoides': 1, 'Lantana montevidensis': 1, 'Duranta erecta': 1, 'Pistia stratiotes': 1, 'Leucaena leucocephala': 1} | 0.719 / 0.416 |
| *Acacia mangium* | 23 | 4 | 15 | {'Piper aduncum': 3, 'Acacia auriculiformis': 1} | {'Acacia auriculiformis': 7, 'Chromolaena odorata': 2, 'Pontederia crassipes': 1, 'Mikania micrantha': 1, 'Pontederia vaginalis': 1, 'Leucaena leucocephala': 1, 'Salvinia molesta': 1, 'Swietenia macrophylla': 1} | 0.677 / 0.687 |
| *Swietenia macrophylla* | 31 | 5 | 10 | {'Acacia mangium': 1, 'Mikania micrantha': 1, 'Pontederia crassipes': 1, 'Acacia auriculiformis': 1, 'Leucaena leucocephala': 1} | {'Salvinia molesta': 3, 'Leucaena leucocephala': 2, 'Ageratum conyzoides': 1, 'Mikania micrantha': 1, 'Duranta erecta': 1, 'Broussonetia papyrifera': 1, 'Acacia auriculiformis': 1} | 0.790 / 0.360 |
| *Gmelina arborea* | 38 | 8 | 8 | {'Broussonetia papyrifera': 4, 'Limnocharis flava': 2, 'Duranta erecta': 1, 'Salvinia molesta': 1} | {'Broussonetia papyrifera': 6, 'Duranta erecta': 1, 'Spathodea campanulata': 1} | 0.765 / 0.440 |
| *Eucalyptus deglupta* | 39 | 2 | 3 | {'Mikania micrantha': 1, 'Spathodea campanulata': 1} | {'Leucaena leucocephala': 1, 'Broussonetia papyrifera': 1, 'Acacia auriculiformis': 1} | 0.909 / 0.525 |
| *Acacia auriculiformis* | 28 | 13 | 6 | {'Acacia mangium': 7, 'Piper aduncum': 3, 'Eucalyptus deglupta': 1, 'Leucaena leucocephala': 1, 'Swietenia macrophylla': 1} | {'Pontederia vaginalis': 2, 'Ageratum conyzoides': 1, 'Duranta erecta': 1, 'Acacia mangium': 1, 'Swietenia macrophylla': 1} | 0.703 / 0.522 |

Misclassified images with attribution: `misclassified_test_images.csv`.

## 11. Unsupported-species evaluation

- Score: `max_softmax`; threshold strategy `youden` -> threshold 0.6864 (selected on validation (val + unknown_val); test sets not used).
- unknown_val species (threshold selection): Bidens pilosa, Ixora coccinea
- unknown_test species (final evaluation): Hibiscus rosa-sinensis, Ipomoea aquatica, Mimosa pudica
- Test: supported-species acceptance 60.4%, accuracy on accepted 96.4%; unsupported false acceptance 22.8% (n=408); AUROC 0.764.

| Unsupported species | Images | False acceptance (thresholded) | Labels assigned without rejection |
|---|---|---|---|
| *Hibiscus rosa-sinensis* | 140 | 40.0% | {'Spathodea campanulata': 114, 'Pontederia crassipes': 8, 'Pistia stratiotes': 4, 'Lantana montevidensis': 3, 'Lantana camara': 2, 'Swietenia macrophylla': 2, 'Gmelina arborea': 1, 'Acacia auriculiformis': 1, 'Piper aduncum': 1, 'Duranta erecta': 1, 'Acacia mangium': 1, 'Ageratum conyzoides': 1, 'Limnocharis flava': 1} |
| *Ipomoea aquatica* | 135 | 8.9% | {'Piper aduncum': 21, 'Acacia auriculiformis': 16, 'Swietenia macrophylla': 13, 'Pontederia vaginalis': 13, 'Lantana montevidensis': 13, 'Broussonetia papyrifera': 9, 'Gmelina arborea': 8, 'Chromolaena odorata': 7, 'Mikania micrantha': 7, 'Pontederia crassipes': 6, 'Ageratum conyzoides': 5, 'Limnocharis flava': 5, 'Acacia mangium': 5, 'Pistia stratiotes': 4, 'Imperata cylindrica': 3} |
| *Mimosa pudica* | 133 | 18.8% | {'Leucaena leucocephala': 72, 'Swietenia macrophylla': 20, 'Lantana montevidensis': 19, 'Ageratum conyzoides': 7, 'Broussonetia papyrifera': 4, 'Chromolaena odorata': 3, 'Imperata cylindrica': 2, 'Mikania micrantha': 2, 'Acacia mangium': 1, 'Lantana camara': 1, 'Pistia stratiotes': 1, 'Limnocharis flava': 1} |

![Score distribution](unknown_score_distribution.png)

Calibration: ECE 0.105 (raw softmax) and 0.022 after temperature scaling (T=0.73, fitted on validation). Softmax scores are model scores, not calibrated identification confidence.

![Reliability](reliability_diagram.png)

## 12. Robustness and photographic conditions

Synthetic perturbations of the test images (these approximate, but are not, real lighting/angle/background changes):

| Perturbation | Accuracy | Macro F1 |
|---|---|---|
| none | 82.5% | 0.830 |
| darker_40pct | 77.0% | 0.777 |
| brighter_40pct | 80.2% | 0.807 |
| low_contrast | 73.4% | 0.739 |
| gaussian_blur | 68.9% | 0.701 |
| rotate_90 | 76.5% | 0.773 |
| jpeg_q20 | 69.1% | 0.695 |
| center_crop_60pct | 84.4% | 0.848 |

No reviewer condition tags (lighting, background, organ, growth stage) were available, so real-condition breakdowns were not computed.

## 13. Runtime and model size

Device CPU; batch-1 latency median 24.2 ms (p95 26.8 ms); batch-32 throughput 103.6 img/s; 2,284,885 parameters; `.keras` file 26.07 MB. Model forward pass only (excludes image decoding/resizing). Measured on this machine.

## 14. Model limitations (observed or inherent to this setup)

- Training and test images come from external biodiversity platforms; their photographers, devices and framing differ from GeoFlora users' photos, so field performance may differ from the figures above.
- Test-set size (931 images) bounds precision of the estimates; see the bootstrap confidence intervals.
- The model is closed-set: without the rejection threshold every unsupported plant receives a supported label.
- Softmax scores are not calibrated probabilities of a correct identification.
- 22.2% of the images used were recorded in the Philippines (country of record per source metadata).
- Ecological status is not yet verified with Philippine-specific evidence for: *Chromolaena odorata*, *Lantana camara*, *Pontederia crassipes*, *Ageratum conyzoides*, *Mikania micrantha*, *Lantana montevidensis*, *Duranta erecta*, *Pistia stratiotes*, *Pontederia vaginalis*, *Limnocharis flava*, *Imperata cylindrica*, *Leucaena leucocephala*, *Spathodea campanulata*, *Piper aduncum*, *Salvinia molesta*, *Broussonetia papyrifera*, *Acacia mangium*, *Swietenia macrophylla*, *Gmelina arborea*, *Eucalyptus deglupta*, *Acacia auriculiformis*.
- Unsupported-species evaluation covers only 3 species; false-acceptance rates for other plants are unknown.
- At least one class has fewer than 30 test images; per-class metrics for those classes are highly uncertain.
- Aspect ratio is not preserved during resizing, which may distort plant morphology.

## 15. Reproducibility

- Run directory: `models/checkpoints/nissap/run-20261104T155431Z-nissap21-v1` (contains run_config.yaml, class_mapping.json, train/val/test image lists, history, logs).
- Dataset version `ds-20261104-5bb0dfbfae`; image lists for each split are stored with the run.
- Seed 42; deterministic ops: False.
- Environment: Python 3.11.9, TensorFlow 2.20.0, Keras 3.15.1, Windows-10-10.0.26200-SP0, GPUs: none.
- Re-run: `python scripts/train.py --config <run_config.yaml>` then `python scripts/evaluate.py --run <run_dir>`.

## 16. Proposed future improvements (not yet tested)

- Collect and review more diverse images of *Broussonetia papyrifera* (test F1 0.660).
- Collect and review more diverse images of *Mikania micrantha* (test F1 0.680).
- Collect and review more diverse images of *Acacia mangium* (test F1 0.708).
- Add targeted reviewed images that separate *Mikania micrantha* from *Broussonetia papyrifera* (7 confusions observed).
- Add targeted reviewed images that separate *Acacia auriculiformis* from *Acacia mangium* (7 confusions observed).
- Add targeted reviewed images that separate *Chromolaena odorata* from *Mikania micrantha* (6 confusions observed).
- Collect GeoFlora-style field photographs from the Philippines (with consent and botanist verification) as an additional held-out test set.
- Expand the unsupported-species set with more look-alike and common non-target plants to tighten false-acceptance estimates.
- Evaluate alternative rejection methods (e.g. energy scores from logits, feature-space distance) on the same validation protocol.
- Ask reviewers to tag photographic conditions so that real-condition robustness can be measured.

