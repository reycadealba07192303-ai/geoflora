# Six-species experimental training results

Completed October 25, 2026 (Philippine time). Candidate trained and saved; the live three-species model remains active.

The new candidate includes Caladium bicolor (Corazon de Maria), Chromolaena odorata (Hagonoy), Lantana camara (Lantana), Mikania micrantha (Mile-a-minute), Pistia stratiotes (Water Lettuce), and Pontederia crassipes (Water Hyacinth).

## Data and method

221 unique photos: 147 training, 36 validation, 38 test. The existing five-class field-photo selection contributes 211 photos. Ten Caladium photos from the owner-approved Philippine batch were visually screened as live foliage, preserving the original owner label/location attestation. The other batch species retain their ecological/domain holds and were not silently added to training.

Caladium ecological reference: [DENR–FMB Philippine Guidebook on Plant Species Suitable for Urban Greening, printed page 157](https://forestry.denr.gov.ph/fmb_web/wp-content/uploads/2023/06/Philippine-Guidebook-on-Plant-Species-Suitable-for-Urban-Greening-EBOOK_compressed.pdf). This is a documented invasive-species reference, not a claim of current legal restriction. Screening contact sheet: storage/datasets/selection/pilot_five_classes/caladium-contact-sheet.jpg. Botanical identification and geography remain owner/source-based, not independently certified.

Frozen ImageNet MobileNetV2 with a new class-balanced softmax head, seed 42. Training-only views: original, horizontal mirror, and a small rotation with brightness adjustment. These views do not increase the count of independent photos. The validation loss selected epoch 10; early stopping ended at epoch 18. No test-set selection or threshold tuning was performed.

Source observation, checksum and recomputed perceptual-similarity groups do not cross dataset partitions. This is a new experimental split of previously explored data; scores are not directly comparable to v3 or a fresh prospective benchmark.

## Held-out results

Top-1 accuracy: **30/38 = 78.95%**. Macro F1: **54.39%**. These scores precede the 65% inference abstention threshold.

| Species | Train / validation / test | Precision | Recall | F1 |
|---|---|---:|---:|---:|
| Caladium bicolor | 6 / 2 / 2 | 100.00% | 50.00% | 66.67% |
| Chromolaena odorata | 57 / 14 / 14 | 71.43% | 71.43% | 71.43% |
| Lantana camara | 55 / 12 / 15 | 78.95% | 100.00% | 88.24% |
| Mikania micrantha | 5 / 1 / 1 | 0.00% | 0.00% | 0.00% |
| Pistia stratiotes | 3 / 2 / 2 | 0.00% | 0.00% | 0.00% |
| Pontederia crassipes | 21 / 5 / 4 | 100.00% | 100.00% | 100.00% |

One or two test images cannot establish dependable performance. Mikania and Pistia had no correct held-out predictions. The candidate fails the proposed 85% accuracy, 85% macro F1 and 80% per-class recall targets and is **not promoted**. Unsupported plants/non-plants can still receive high model scores; this training does not solve open-set recognition.

## Saved artifacts and checks

- Frozen data: storage/datasets/curated/v4_six_classes/manifest.csv, dataset_metadata.json, reviews_snapshot.json, class_mapping.json, species.yaml.
- Candidate: storage/models/candidates/mobilenetv2_v4_six_seed42/mobilenetv2.keras.
- Beside the model: evaluation.json, test_predictions.json, checksums.json and inference_smoke.json.
- Training progress/final state: docs/expanded-training-status.json.
- Entry point: services/ml/.venv/Scripts/python.exe scripts/train_expanded.py. Existing output versions are protected from overwrite; this command does not resume or replace a completed run.
- Isolated verification: services/ml/.venv/Scripts/python.exe scripts/verify_expanded_candidate.py. Loads the candidate with its own registry, checks hashes and split isolation, and submits one held-out photo per species through FastAPI. The active registry and model are preserved.
- Saved-model reload equivalence passed; the existing 27 ML tests passed.

Next training work should add distinct, reviewed Philippine field observations for the new classes, especially Mikania and Pistia, and reserve a fresh evaluation set. Augmentation alone does not replace independent examples. Do not repeatedly tune this candidate against the reported test results.
