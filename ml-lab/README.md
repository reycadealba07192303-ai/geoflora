# GeoFlora-ML-Lab

Standalone deep-learning research workspace for the image-identification component of **GeoFlora**:
*"Development of an Image-Based Web Application for Identification and Spatial Monitoring of Invasive Alien Plant Species"*.

The lab develops and evaluates a MobileNetV2 transfer-learning classifier independently of the production
system. A model leaves this lab only as an exported **candidate bundle**. Someone integrates it into the GeoFlora FastAPI service later, by hand.

## Boundaries (enforced by design)

- **No connection to GeoFlora.** Nothing here reads or writes the GeoFlora web app, its MongoDB database, its production datasets, the active CNN or the model-activation records. Everything stays inside this folder.
- **No GPS or occurrence generation.** The model returns species identifiers and scores only. Location, occurrence records, hotspots and administrative verification belong to GeoFlora.
- **No fabricated verification.**
  - Every downloaded image starts as `review_status = pending`.
  - An image becomes a training label only after a named reviewer approves it through `scripts/review_images.py`.
  - Community identifications on source platforms (for example, iNaturalist research grade) are kept as provenance. They are not treated as botanical verification.
- **No invented ecological status.**
  - Status in `metadata/species_catalog.csv` stays `unverified` until a named person records evidence for the Philippines.
  - Only the three baseline species, which the client already treats as targets, are `target_invasive`.
  - Every other species is `unresolved`.
- **No training on insufficient data.** `scripts/train.py` refuses to start unless at least two classes meet the minimum counts of approved images and independent observation groups. It then re-checks every image's approval status at training time.
- **No automatic deployment.** Export writes `status: candidate_not_activated` and does nothing else.

## Setup (Windows laptop + VS Code)

TensorFlow publishes no wheels for Python 3.13+, so use Python 3.10–3.12. Python 3.11 was used here.

```powershell
cd GeoFlora-ML-Lab
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pytest -q             # 32 tests, about 30 s (includes a tiny end-to-end training on synthetic images)
```

Native Windows TensorFlow runs on the CPU. The default configuration is sized for that: batch size 16, 224 px input, at most 25 epochs. For GPU training, use WSL2.

## Pipeline (stages)

| Stage | Command | Output |
|---|---|---|
| 2–3 Acquire | `python scripts/download_dataset.py [--roles target] [--max-per-species N] [--max-total-mb M] [--dry-run]` | `dataset/raw/<Species>/`, `metadata/image_manifest.csv`, `dataset/raw/_occurrence_metadata/*.jsonl`, `reports/download_logs/` |
| 4 Validate + inventory | `python scripts/validate_images.py` | quality, license, label, duplicate and group columns in the manifest; `reports/dataset_inventory.md`; `reports/validation_summary.json` |
| 4 Label review | `python scripts/review_images.py export`, review in the `.html` page, **Download CSV**, then `... import <downloaded.csv> --reviewer "Full Name"` | `reports/review_sheets/*.csv/.html`; approved copies in `dataset/reviewed/` |
| 5 Split | `python scripts/split_dataset.py` | `dataset/{train,val,test,unknown_val,unknown_test}/<Species>/`, `metadata/class_mapping.json`, `metadata/split_assignments.csv`, `metadata/dataset_version.json`, `reports/split_report.json` |
| 6 Train | `python scripts/train.py [--check-only]` | `models/checkpoints/run-*/` |
| 7 Evaluate | `python scripts/evaluate.py --run models/checkpoints/run-...` | `run-*/evaluation/` and `reports/run-*/`: metrics, figures, `research_evaluation_report.md` |
| 8 Experiments | `python scripts/run_experiments.py learning_curve` / `class_expansion` | `reports/experiments/` |
| 9 Export | `python scripts/export_model.py --run ... [--model-version X]` | `models/exported/<model_version>/` |
| Predict | `python scripts/predict.py photo.jpg --model models/exported/<version>` | JSON per `prediction_output_spec.json` |

### Demo web app (flow, identification, reports and map)

```powershell
python scripts/demo_server.py      # http://127.0.0.1:8090; loads the newest export for each class count
```

When more than one model is loaded (for example the 3-class and the 10-class bundles), a selector in the header switches between them. The model with the fewest classes is the default, and each report records the model that identified it.

The app has three tabs:
1. **Flow:** every pipeline stage, with numbers read from the manifest, the reports and the exported bundle.
2. **Identify a plant:** upload a photo or use the phone camera. The page shows ✅ (sure) or ⚠️ (possibly, not sure), the top-3 scores and the species description. It then offers **Save as a sighting report**:
   - **Date and time:** from the photo's EXIF data when present, otherwise now. The user can edit them.
   - **Location:** from the photo's GPS, the device's location, a map pin, or typed coordinates. The source is recorded with each report.
3. **Reports & map:** every report on an OpenStreetMap map (red: target invasive; blue: other species; amber: uncertain), plus a table with date, time, species, result, place and coordinates. You can filter, view or delete reports, or download them as CSV.

How reports are stored and handled:
- Reports and photos are stored only on this computer, in `demo_data/` (SQLite and image files), which git ignores.
- The server identifies the photo again on save, so every stored result comes from the model.
- The model never produces a location or a time.
- Reports are AI suggestions, not verified records. Administrative verification is not implemented here.
- The map needs internet for its tiles. Without internet, the table still works.

Scope note (2026-11-04): the original lab plan left geotagging and maps to the GeoFlora application. At the developer's request, this demo now includes basic sighting reports and a map, to support the thesis objective of mapping recorded locations.

### Provisional pilot (while botanical review is pending)

`configs/provisional_pilot.yaml` runs split, train and evaluate using **unreviewed** labels: the iNaturalist research-grade identifications, which reflect community agreement and not botanical verification.

- Outputs go only to `dataset/provisional/`, `metadata/provisional/`, `models/checkpoints/provisional/` and `reports/provisional/`.
- The manifest and the real class mapping are never touched.
- Rejected or uncertain images are still excluded.
- Every report carries a PROVISIONAL banner, and `export_model.py` refuses these runs.

Use it to check the pipeline on real photos. Don't report its numbers as GeoFlora model performance.

```powershell
python scripts/split_dataset.py --config configs/provisional_pilot.yaml
python scripts/train.py        --config configs/provisional_pilot.yaml --run-name pilot
python scripts/evaluate.py     --config configs/provisional_pilot.yaml
```

### Look-alike expansion experiment (Stage 8)

`configs/expansion_lookalikes.yaml` treats the seven reviewed look-alike species as extra model classes. It uses `split.extra_class_species` and leaves the catalog unchanged. Its outputs go only to `*/expansion/` folders.

1. Seed `metadata/expansion/split_assignments.csv` with the main target-species rows, so the three targets keep the same train, val and test images.
2. Run `split_dataset.py` and `run_experiments.py class_expansion` with `--config configs/expansion_lookalikes.yaml`.

All settings live in `configs/default.yaml`. Override them with `--config my.yaml`; that file only needs the keys you change.

### Label review

`review_images.py export` writes, for each species, an interactive `.html` page and a blank `.csv` sheet.

- Open the page in a browser and decide each photo with the buttons or the keys **A** (approved), **R** (rejected), **U** (uncertain) and **C** (clear). Notes and condition tags are optional. Progress is saved in the browser.
- **Download CSV** saves a filled sheet in the same layout, which `import` accepts. There is no bulk-approve control.
- `review.label_basis` in the config states how labels were established, and appears in every report and `train_summary.json`. It currently describes screening by a named non-botanist reviewer, starting from the iNaturalist research-grade identification. Change it if a qualified botanist does the review.

## Data rules

### Species catalog (`metadata/species_catalog.csv`)

Each row has a stable `species_id`, the accepted scientific name and its GBIF backbone key, synonyms, and the fields below.

- **`ecological_status`** keeps four categories separate:
  - `target_invasive`
  - `introduced_naturalized`
  - `native_nontarget`
  - `unresolved`
- **Status verification:** `status_verification`, `status_verified_by`, `status_verified_date` and `status_evidence`.
- **`role`:**
  - `target`: model classes
  - `lookalike`: discrimination and later classes
  - `unknown_eval`: never trained; used for unsupported-species testing
  - `expansion_candidate`
- **`training_enabled` / `download_enabled`:** switches for each species.
- **IDs:** never reuse or renumber a `species_id`.

Class folder names are the scientific names, with spaces replaced by underscores (for example, `Lantana_camara`).

### Splitting

The split unit is the **observation group**. Images are linked into one group when they share:
- the same occurrence
- identical bytes
- a perceptual near-duplicate (pHash Hamming distance ≤ 6)
- optionally, the same species, recorder and day

Other rules:
- A group that links two species is flagged as a label conflict and excluded.
- Assignments are **sticky**: `split_assignments.csv` keeps history, so test images never enter training when the dataset grows.
- Observation or image IDs listed in `metadata/locked_test_groups.txt` are forced into test. Use this to preserve historical GeoFlora test sets if they are imported later.

### Class eligibility

Each class needs at least 60 approved images, at least 30 observation groups and at least 8 test images (all configurable). The model's output layer has exactly as many neurons as there are eligible classes, up to the 50-species capacity goal.

### Unsupported species

Approved images of non-class species are split **by species** into two sets:
- `unknown_val`, used only to choose the rejection threshold
- `unknown_test`, used only for the final false-acceptance measurement

The threshold is never chosen on test data.

### Licenses

The allowed licenses are CC0, PDM, CC BY and CC BY-NC, checked per image. NC images restrict commercial use. Remove `CC-BY-NC-4.0` from `download.allowed_licenses` if commercial use is planned.

## Model

```
image (224×224×3 float32, RGB, 0–255)
  → Rescaling to [-1, 1]
  → MobileNetV2 (ImageNet weights, frozen; later top layers fine-tuned, BatchNorm frozen)
  → GlobalAveragePooling → Dropout(0.3) → Dense(num_classes, softmax)
```

Training runs in two phases:
1. Train the head on the frozen base.
2. Fine-tune from layer 100 at a learning rate of 1e-5.

Both phases use early stopping, checkpoints, ReduceLROnPlateau, augmentation and automatic class weights (applied only when the class ratio exceeds 1.5), with a fixed seed. The final model is whichever phase has the lower **validation** loss.

## Evaluation outputs

Evaluation produces:
- accuracy, with an observation-group bootstrap 95% confidence interval
- per-class precision, recall and F1
- macro and weighted F1
- top-k accuracy
- confusion matrices (counts and normalised)
- training curves
- per-species false-positive and false-negative analysis, plus a CSV of misclassified images with attribution
- unsupported-species false acceptance (with and without the validation-selected threshold), AUROC, and a breakdown for each unknown species
- calibration (ECE before and after temperature scaling fitted on validation)
- synthetic robustness (darker, brighter, low contrast, blur, rotation, JPEG artefacts, crop)
- accuracy by reviewer-tagged photo condition, when tags exist
- batch-1 latency, throughput, parameter count and model size

The report separates **observed results** from **proposed future improvements (not yet tested)**.

## Research questions → evidence

| RQ | Where the evidence comes from |
|---|---|
| 1 Accuracy | `metrics.json → test.accuracy` (+ CI) |
| 2 Similar species | confusion matrix, `top_confusions`, look-alike classes once they are approved |
| 3 Precision, recall, F1, confusion | report §8–10 |
| 4 Unsupported plants misclassified | report §11 (`unknown_false_acceptance_rate_*`) |
| 5 Adding species | `run_experiments.py class_expansion` |
| 6 Amount, quality and diversity of data | `run_experiments.py learning_curve`; inventory (sources, countries); condition tags |
| 7 Reproducible, integrable outputs | run directory (config, seed, environment, image lists), export bundle, checksums |
| 8 Limitations (lighting, background, angle, stage) | report §12 (synthetic perturbations + reviewer condition tags), §14 |

## Integration bundle (`models/exported/<model_version>/`)

| File | Contents |
|---|---|
| `model.keras` | trained model |
| `class_mapping.json` | maps output index to `species_id` and scientific name |
| `preprocessing.json` | preprocessing steps the service must apply |
| `model_metadata.json` | version, dataset version, SHA-256, supported species, threshold, metric summary, status `candidate_not_activated` |
| `supported_species.json` | list of supported species |
| `species_descriptions.json` | description of each supported species (summary, identifying features, impacts, look-alikes, references, review status), copied from `metadata/species_descriptions.json`; `predict` returns it as `prediction.description` |
| `prediction_output_spec.json` | JSON Schema for prediction output |
| `evaluation_report.md` + figures | evaluation report |
| `SHA256SUMS.txt` | checksums for every file |

Minimal FastAPI usage, for when GeoFlora decides to integrate:

```python
from geoflora_ml.inference import Predictor   # or port preprocess_image() + model call
predictor = Predictor("models/exported/<model_version>")
result = predictor.predict("upload.jpg")      # dict matching prediction_output_spec.json
# GeoFlora stores result["model_version"], result["prediction"]["species_id"] with its own observation + location record.
```

Key downstream logic on `species_id`, never on the output index. Treat `softmax_score` as an uncalibrated score, not a probability of being correct.

## Tests

`python -m pytest -q` covers:
- license parsing
- catalog integrity, including no unverified claims
- quality checks and near-duplicate detection
- grouping and label conflicts
- GBIF record parsing and provenance fields
- the review round trip (no reviewer means no import; invalid sheets change nothing)
- split leakage, stickiness and locked test groups
- the training gate (no approvals, or a revoked approval, blocks training)
- threshold selection and calibration
- a full train → evaluate → export → predict run on synthetic images

The synthetic run checks that the pipeline works. It is **not** a model result.
