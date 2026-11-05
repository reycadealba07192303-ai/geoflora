# Research Evaluation Report - run-20261104T102547Z-class_expansion-classes10

*Generated 2026-11-04T10:40:39+00:00 from run artifacts in `models/checkpoints/expansion/run-20261104T102547Z-class_expansion-classes10`. Dataset version `ds-20261104-00998fdf5b`. This model is a research candidate: it has not been deployed or activated in GeoFlora.*

## 1. Summary of observed results

- Classes: 10 (*Chromolaena odorata*, *Lantana camara*, *Pontederia crassipes*, *Ageratum conyzoides*, *Mikania micrantha*, *Lantana montevidensis*, *Duranta erecta*, *Pistia stratiotes*, *Pontederia vaginalis*, *Limnocharis flava*)
- Independent test images: 215 from 195 observation groups
- Test accuracy: **75.3%** (95% exact binomial CI 69.0% - 81.0%; observation-group bootstrap CI 69.4% - 81.0%)
- Macro F1: **0.751** (CI 0.686 - 0.805); weighted F1: 0.751
- Unsupported-species false acceptance: 100% without rejection (closed-set softmax); **10.5%** with the validation-selected threshold, at a supported-species acceptance rate of 34.4%. AUROC 0.708.
- Forward-pass latency (batch 1, median): 16.0 ms on CPU; model file 24.51 MB.

Targets such as a specific accuracy level are only met if the figures above show it on this independent test set.

## 2. Dataset sources and selection criteria

- Source(s): GBIF; source datasets: iNaturalist research-grade observations (1418)
- Licenses used: CC-BY-NC-4.0: 1272, CC-BY-4.0: 121, CC0-1.0: 25
- Country of record (top): PH: 770, TW: 131, AU: 87, US: 72, IN: 43, TH: 39, JP: 37, ID: 24
- Selection criteria: still images with an allowed per-image license, basis of record ['HUMAN_OBSERVATION'], at most 1 image(s) per occurrence; quality checks (resolution, blur, exposure, aspect ratio); exact and perceptual duplicate removal; **photo-by-photo screening by a named non-botanist reviewer, starting from iNaturalist research-grade community identifications, with an AI-assisted pre-screen that flagged questionable photos for the reviewer's decision (not expert botanical verification)**.
- Label reviewer(s): Reyca de Alba (1418 images)
- These photographs are external biodiversity records, not GeoFlora field observations.

## 3. Target species and ecological-status evidence

| Index | Species ID | Scientific name | Ecological status | Verification | Evidence |
|---|---|---|---|---|---|
| 0 | GF-SP-0001 | *Chromolaena odorata* | target_invasive | unverified | Recognised by the existing GeoFlora active CNN (client scope). Listed in IUCN SSC ISSG '100 of the World's Worst Invasive Alien Species' (Lowe et al. 2000) - global evidence only. Philippine-specific citation still to be supplied by the client/botanist. |
| 1 | GF-SP-0002 | *Lantana camara* | target_invasive | unverified | Recognised by the existing GeoFlora active CNN (client scope). Listed in IUCN SSC ISSG '100 of the World's Worst Invasive Alien Species' (Lowe et al. 2000) - global evidence only. Philippine-specific citation still to be supplied by the client/botanist. |
| 2 | GF-SP-0003 | *Pontederia crassipes* | target_invasive | unverified | Recognised by the existing GeoFlora active CNN (client scope). Listed in IUCN SSC ISSG '100 of the World's Worst Invasive Alien Species' as Eichhornia crassipes (Lowe et al. 2000) - global evidence only. Philippine-specific citation still to be supplied by the client/botanist. |
| 3 | GF-SP-0101 | *Ageratum conyzoides* | unresolved | unverified | none recorded |
| 4 | GF-SP-0102 | *Mikania micrantha* | unresolved | unverified | Listed in IUCN SSC ISSG '100 of the World's Worst Invasive Alien Species' (global evidence only). |
| 5 | GF-SP-0103 | *Lantana montevidensis* | unresolved | unverified | none recorded |
| 6 | GF-SP-0104 | *Duranta erecta* | unresolved | unverified | none recorded |
| 7 | GF-SP-0105 | *Pistia stratiotes* | unresolved | unverified | none recorded |
| 8 | GF-SP-0106 | *Pontederia vaginalis* | unresolved | unverified | none recorded |
| 9 | GF-SP-0107 | *Limnocharis flava* | unresolved | unverified | none recorded |

## 4. Images and independent observation groups per class

| Species | Train imgs / groups | Val imgs / groups | Test imgs / groups |
|---|---|---|---|
| *Chromolaena odorata* | 103 / 98 | 23 / 22 | 22 / 18 |
| *Lantana camara* | 104 / 95 | 23 / 23 | 23 / 20 |
| *Pontederia crassipes* | 95 / 90 | 21 / 19 | 21 / 16 |
| *Ageratum conyzoides* | 99 / 92 | 22 / 20 | 22 / 21 |
| *Mikania micrantha* | 98 / 94 | 21 / 21 | 21 / 19 |
| *Lantana montevidensis* | 98 / 90 | 21 / 21 | 21 / 20 |
| *Duranta erecta* | 98 / 98 | 22 / 22 | 21 / 20 |
| *Pistia stratiotes* | 95 / 71 | 21 / 17 | 21 / 19 |
| *Pontederia vaginalis* | 98 / 94 | 21 / 18 | 21 / 20 |
| *Limnocharis flava* | 98 / 94 | 22 / 22 | 22 / 22 |

## 5. Preprocessing

EXIF orientation applied, converted to RGB, re-encoded as JPEG (max side 1024 px), resized to 224x224 (bilinear, aspect ratio not preserved), float32 in [0, 255]; MobileNetV2 scaling to [-1, 1] inside the model.
Training augmentation: {'horizontal_flip': True, 'rotation': 0.08, 'zoom': 0.15, 'translation': 0.1, 'contrast': 0.2, 'brightness': 0.2}.

## 6. Training configuration and architecture

- Architecture: MobileNetV2, ImageNet-pretrained, alpha=1.0 -> GlobalAveragePooling -> Dropout(0.3) -> Dense(10, softmax). Parameters: 2,270,794.
- Phase 1 (frozen base): up to 15 epochs, Adam lr=0.001.
- Phase 2 (fine-tuning layers >= 100, BatchNorm frozen): up to 10 epochs, Adam lr=1e-05. Selected phase: **finetune** (lowest validation loss).
- Early stopping (patience 5), ReduceLROnPlateau, checkpointing on validation loss; batch size 16; seed 42; class weights: none.
- Epochs run: 25; training time 394.9 s.

## 7. Train / validation / test methodology

Images were partitioned by observation group (same occurrence, exact duplicates, perceptual near-duplicates [pHash Hamming <= 6], and same recorder on the same day) with target ratios {'train': 0.7, 'val': 0.15, 'test': 0.15}. Assignments are sticky across dataset versions so test images never enter training. Model selection and the unsupported-species threshold used validation data only; the test and unknown_test sets were used once, for this report.

## 8. Evaluation results (test set)

Validation (for reference): accuracy 71.4%, macro F1 0.714.

| Species | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| *Chromolaena odorata* | 0.765 | 0.591 | 0.667 | 22 |
| *Lantana camara* | 0.808 | 0.913 | 0.857 | 23 |
| *Pontederia crassipes* | 0.654 | 0.810 | 0.723 | 21 |
| *Ageratum conyzoides* | 0.733 | 0.500 | 0.595 | 22 |
| *Mikania micrantha* | 0.720 | 0.857 | 0.783 | 21 |
| *Lantana montevidensis* | 0.750 | 0.714 | 0.732 | 21 |
| *Duranta erecta* | 0.941 | 0.762 | 0.842 | 21 |
| *Pistia stratiotes* | 0.889 | 0.762 | 0.821 | 21 |
| *Pontederia vaginalis* | 0.762 | 0.762 | 0.762 | 21 |
| *Limnocharis flava* | 0.633 | 0.864 | 0.731 | 22 |
| **Macro** | 0.765 | 0.753 | 0.751 | 215 |

Top 3 accuracy: 93.5%.

![Training curves](training_curves.png)

## 9. Confusion matrix

![Confusion matrix](confusion_matrix_counts.png) ![Normalised](confusion_matrix_normalized.png)

Most frequent confusions (true -> predicted): *Pontederia crassipes* -> *Limnocharis flava* (4); *Chromolaena odorata* -> *Mikania micrantha* (4); *Chromolaena odorata* -> *Ageratum conyzoides* (4); *Pontederia vaginalis* -> *Limnocharis flava* (3); *Pistia stratiotes* -> *Pontederia crassipes* (3); *Lantana montevidensis* -> *Lantana camara* (3); *Ageratum conyzoides* -> *Lantana montevidensis* (3); *Pontederia vaginalis* -> *Pontederia crassipes* (2); *Pistia stratiotes* -> *Limnocharis flava* (2); *Mikania micrantha* -> *Chromolaena odorata* (2)

## 10. False-positive and false-negative analysis

| Species | TP | FN | FP | FN predicted as | FP true species | Mean score correct / incorrect |
|---|---|---|---|---|---|---|
| *Chromolaena odorata* | 13 | 9 | 4 | {'Ageratum conyzoides': 4, 'Mikania micrantha': 4, 'Limnocharis flava': 1} | {'Mikania micrantha': 2, 'Ageratum conyzoides': 1, 'Lantana montevidensis': 1} | 0.766 / 0.601 |
| *Lantana camara* | 21 | 2 | 5 | {'Duranta erecta': 1, 'Lantana montevidensis': 1} | {'Lantana montevidensis': 3, 'Ageratum conyzoides': 1, 'Duranta erecta': 1} | 0.997 / 0.650 |
| *Pontederia crassipes* | 17 | 4 | 9 | {'Limnocharis flava': 4} | {'Pistia stratiotes': 3, 'Pontederia vaginalis': 2, 'Ageratum conyzoides': 1, 'Lantana montevidensis': 1, 'Duranta erecta': 1, 'Limnocharis flava': 1} | 0.819 / 0.611 |
| *Ageratum conyzoides* | 11 | 11 | 4 | {'Lantana montevidensis': 3, 'Mikania micrantha': 2, 'Pontederia vaginalis': 2, 'Pontederia crassipes': 1, 'Chromolaena odorata': 1, 'Pistia stratiotes': 1, 'Lantana camara': 1} | {'Chromolaena odorata': 4} | 0.692 / 0.602 |
| *Mikania micrantha* | 18 | 3 | 7 | {'Chromolaena odorata': 2, 'Pistia stratiotes': 1} | {'Chromolaena odorata': 4, 'Ageratum conyzoides': 2, 'Limnocharis flava': 1} | 0.715 / 0.539 |
| *Lantana montevidensis* | 15 | 6 | 5 | {'Lantana camara': 3, 'Chromolaena odorata': 1, 'Limnocharis flava': 1, 'Pontederia crassipes': 1} | {'Ageratum conyzoides': 3, 'Lantana camara': 1, 'Duranta erecta': 1} | 0.866 / 0.621 |
| *Duranta erecta* | 16 | 5 | 1 | {'Pontederia vaginalis': 2, 'Pontederia crassipes': 1, 'Lantana camara': 1, 'Lantana montevidensis': 1} | {'Lantana camara': 1} | 0.836 / 0.497 |
| *Pistia stratiotes* | 16 | 5 | 2 | {'Pontederia crassipes': 3, 'Limnocharis flava': 2} | {'Ageratum conyzoides': 1, 'Mikania micrantha': 1} | 0.902 / 0.585 |
| *Pontederia vaginalis* | 16 | 5 | 5 | {'Limnocharis flava': 3, 'Pontederia crassipes': 2} | {'Ageratum conyzoides': 2, 'Duranta erecta': 2, 'Limnocharis flava': 1} | 0.774 / 0.748 |
| *Limnocharis flava* | 19 | 3 | 11 | {'Pontederia crassipes': 1, 'Mikania micrantha': 1, 'Pontederia vaginalis': 1} | {'Pontederia crassipes': 4, 'Pontederia vaginalis': 3, 'Pistia stratiotes': 2, 'Chromolaena odorata': 1, 'Lantana montevidensis': 1} | 0.921 / 0.717 |

Misclassified images with attribution: `misclassified_test_images.csv`.

## 11. Unsupported-species evaluation

- Score: `max_softmax`; threshold strategy `youden` -> threshold 0.9346 (selected on validation (val + unknown_val); test sets not used).
- unknown_val species (threshold selection): Imperata cylindrica, Ixora coccinea, Mimosa pudica
- unknown_test species (final evaluation): Bidens pilosa, Hibiscus rosa-sinensis, Ipomoea aquatica
- Test: supported-species acceptance 34.4%, accuracy on accepted 95.9%; unsupported false acceptance 10.5% (n=57); AUROC 0.708.

| Unsupported species | Images | False acceptance (thresholded) | Labels assigned without rejection |
|---|---|---|---|
| *Bidens pilosa* | 18 | 16.7% | {'Lantana camara': 4, 'Ageratum conyzoides': 4, 'Limnocharis flava': 3, 'Chromolaena odorata': 2, 'Duranta erecta': 2, 'Pontederia vaginalis': 2, 'Pontederia crassipes': 1} |
| *Hibiscus rosa-sinensis* | 19 | 5.3% | {'Lantana camara': 8, 'Lantana montevidensis': 6, 'Duranta erecta': 2, 'Ageratum conyzoides': 1, 'Limnocharis flava': 1, 'Pontederia crassipes': 1} |
| *Ipomoea aquatica* | 20 | 10.0% | {'Pontederia vaginalis': 14, 'Mikania micrantha': 3, 'Chromolaena odorata': 1, 'Ageratum conyzoides': 1, 'Limnocharis flava': 1} |

![Score distribution](unknown_score_distribution.png)

Calibration: ECE 0.050 (raw softmax) and 0.079 after temperature scaling (T=1.31, fitted on validation). Softmax scores are model scores, not calibrated identification confidence.

![Reliability](reliability_diagram.png)

## 12. Robustness and photographic conditions

Synthetic perturbations of the test images (these approximate, but are not, real lighting/angle/background changes):

| Perturbation | Accuracy | Macro F1 |
|---|---|---|
| none | 75.3% | 0.751 |
| darker_40pct | 69.3% | 0.685 |
| brighter_40pct | 69.3% | 0.685 |
| low_contrast | 63.3% | 0.623 |
| gaussian_blur | 62.8% | 0.627 |
| rotate_90 | 78.6% | 0.784 |
| jpeg_q20 | 60.5% | 0.583 |
| center_crop_60pct | 74.9% | 0.747 |

No reviewer condition tags (lighting, background, organ, growth stage) were available, so real-condition breakdowns were not computed.

## 13. Runtime and model size

Device CPU; batch-1 latency median 16.0 ms (p95 19.0 ms); batch-32 throughput 101.7 img/s; 2,270,794 parameters; `.keras` file 24.51 MB. Model forward pass only (excludes image decoding/resizing). Measured on this machine.

## 14. Model limitations (observed or inherent to this setup)

- Training and test images come from external biodiversity platforms; their photographers, devices and framing differ from GeoFlora users' photos, so field performance may differ from the figures above.
- Test-set size (215 images) bounds precision of the estimates; see the bootstrap confidence intervals.
- The model is closed-set: without the rejection threshold every unsupported plant receives a supported label.
- Softmax scores are not calibrated probabilities of a correct identification.
- 54.3% of the images used were recorded in the Philippines (country of record per source metadata).
- Ecological status is not yet verified with Philippine-specific evidence for: *Chromolaena odorata*, *Lantana camara*, *Pontederia crassipes*, *Ageratum conyzoides*, *Mikania micrantha*, *Lantana montevidensis*, *Duranta erecta*, *Pistia stratiotes*, *Pontederia vaginalis*, *Limnocharis flava*.
- Unsupported-species evaluation covers only 3 species; false-acceptance rates for other plants are unknown.
- At least one class has fewer than 30 test images; per-class metrics for those classes are highly uncertain.
- Aspect ratio is not preserved during resizing, which may distort plant morphology.

## 15. Reproducibility

- Run directory: `models/checkpoints/expansion/run-20261104T102547Z-class_expansion-classes10` (contains run_config.yaml, class_mapping.json, train/val/test image lists, history, logs).
- Dataset version `ds-20261104-00998fdf5b`; image lists for each split are stored with the run.
- Seed 42; deterministic ops: False.
- Environment: Python 3.11.9, TensorFlow 2.20.0, Keras 3.15.1, Windows-10-10.0.26200-SP0, GPUs: none.
- Re-run: `python scripts/train.py --config <run_config.yaml>` then `python scripts/evaluate.py --run <run_dir>`.

## 16. Proposed future improvements (not yet tested)

- Collect and review more diverse images of *Ageratum conyzoides* (test F1 0.595).
- Collect and review more diverse images of *Chromolaena odorata* (test F1 0.667).
- Collect and review more diverse images of *Pontederia crassipes* (test F1 0.723).
- Add targeted reviewed images that separate *Pontederia crassipes* from *Limnocharis flava* (4 confusions observed).
- Add targeted reviewed images that separate *Chromolaena odorata* from *Mikania micrantha* (4 confusions observed).
- Add targeted reviewed images that separate *Chromolaena odorata* from *Ageratum conyzoides* (4 confusions observed).
- Collect GeoFlora-style field photographs from the Philippines (with consent and botanist verification) as an additional held-out test set.
- Expand the unsupported-species set with more look-alike and common non-target plants to tighten false-acceptance estimates.
- Evaluate alternative rejection methods (e.g. energy scores from logits, feature-space distance) on the same validation protocol.
- Ask reviewers to tag photographic conditions so that real-condition robustness can be measured.

