# GeoFlora

[![CI](https://github.com/reycadealba07192303-ai/geoflora/actions/workflows/ci.yml/badge.svg)](https://github.com/reycadealba07192303-ai/geoflora/actions/workflows/ci.yml) · Live: https://geoflora-ph.vercel.app

GeoFlora is a research-oriented system for invasive plant identification and
geospatial monitoring. The initial target species are Chromolaena odorata
(Hagonoy), Lantana camara, and Pontederia crassipes (Water Hyacinth), with the
project's initial geographic scope in the Philippines.

The architecture and phased roadmap are described in [geofora.md](./geofora.md).
The project includes a responsive Next.js + React + TypeScript + Tailwind CSS
web app in `apps/web`, a rights-aware image collection and dataset preparation
pipeline, and an initial image upload/preview workflow. The identification UI
connects through a same-origin Next.js route to a local FastAPI inference
service. It reports the model as unavailable until a real trained model and
class mapping are installed; it never substitutes mock predictions.

## Next.js web UI foundation

Use Node.js 20.19+ and npm. From `apps/web`, install dependencies and start the
local Next.js development server:

```powershell
Push-Location apps\web
npm install
npm run dev
Pop-Location
```

Open `http://127.0.0.1:5173`. Build and type-check the frontend with:

```powershell
Push-Location apps\web
npm run typecheck
npm run build
Pop-Location
```

Open `http://127.0.0.1:5173`. The dashboard shows the research workspace,
staged catalog-source record count, image-review status, configured AI classes,
and planned feature areas. These are initial local snapshot counts, not live
API values.

### Local plant identification workflow

The upload page and inference API can be run in separate terminals. First, from
`services/ml`, install the inference and test dependencies into the ML virtual
environment:

```powershell
Push-Location services\ml
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,inference]"
python -m geoflora_ml.inference
```

Then start the web app in another terminal using the Next.js commands above and
open **Identify a plant** from the navigation. The image preview is local to
the browser; when submitted, the photo is sent to the loopback inference
service and this workflow does not save it. The API currently returns a
not-ready response because no trained model is installed. To enable real
inference, first review/approve the dataset, train and evaluate the model, then
install the model artifact and matching class mapping under `storage/models`
(or configure `GEOFLORA_MODEL_PATH` and `GEOFLORA_CLASS_MAPPING_PATH`). TensorFlow
is required for real image preprocessing and model inference; install the
training extra in that environment when preparing the model:

```powershell
python -m pip install -e ".[training]"
```

The confidence cutoff is configurable with `GEOFLORA_CONFIDENCE_THRESHOLD`.
Without it, the installed model's validation-selected `confidence_threshold` in
`storage/models/active_model.json` is used (currently `0.80`), else `0.65`. It is
a decision threshold, not a claim of model accuracy or calibration. Predictions
below it are returned as uncertain. See `docs/part-6-identification.md`.

## Dataset pipeline setup

Use Python 3.10–3.12; Python 3.11 is recommended for the planned TensorFlow
training milestone. From `services/ml`, create and activate a virtual
environment, then install the package:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

The pipeline collects only images with an explicit CC0, CC BY, or CC BY-SA
license and preserves the source URL, license, and attribution in its JSONL
manifest. It normalizes accepted images to JPEG (discarding embedded metadata),
rejects unsupported or oversized files, and keeps downloaded data under the
gitignored `storage/datasets` directory.

```powershell
geoflora-ml collect --source inaturalist --limit-per-species 100
geoflora-ml collect --source gbif --limit-per-species 100
geoflora-ml prepare --seed 42
```

Collection is resumable by source ID, validates integrity, and stores exact
duplicate image bytes only once while retaining each source's provenance.
Transient HTTP failures use configurable retries. Source-specific request
intervals, page caps, image limits, and an additional-download storage cap are
configurable. Set `GEOFLORA_CONTACT_EMAIL` to provide a contact in the
User-Agent. Do not commit downloaded data. Review source terms and attribution
requirements before redistributing any collected images.

To collect every eligible record returned by iNaturalist or GBIF for the
Philippines, use `--all-available` instead of `--limit-per-species`:

```powershell
geoflora-ml collect --source all --all-available --max-download-gb 5
```

This runs the supported Philippines-filtered iNaturalist and GBIF sources
under one shared additional-storage cap. It resumes from the existing manifest
and skips source IDs already collected. Exact duplicate image bytes are stored
once by checksum, while each eligible source record keeps its own
attribution/provenance entry. Collection may take a long time; API quotas,
pagination caps, or timeouts mean it cannot guarantee every image ever
published is retrieved. The 5 GB cap is additional to existing image storage.

For a bounded test batch, limit each source to two new images per species and
at most two API pages:

```powershell
geoflora-ml collect --source all --limit-per-species 2 --max-pages 2 --max-download-gb 0.1
geoflora-ml audit --target-per-species 1000
```

The collector marks every new image `pending` review. These are candidates,
not verified training images. Review labels individually with a rationale:

```powershell
geoflora-ml review --source inaturalist --source-id PHOTO_ID --decision approved --reviewer "Reviewer name" --reason "Species label visually confirmed"
```

Use `--decision rejected` with a reason for incorrect or ambiguous labels.
Audit output is saved to `storage/datasets/reports/dataset_audit.json` and
tracks unique valid images, pending/approved/rejected labels, licenses,
duplicates, source progress, and the remaining count to each verified-image
target. Collection rejections are recorded in
`storage/datasets/raw/rejected.jsonl`. Image GPS/location is retained when
provided by the source; unavailable or obscured coordinates remain null.

`prepare` only includes approved, integrity-checked Philippine records. It
computes perceptual near-duplicate groups and keeps source observation and
near-duplicate groups within one partition. External training datasets are not
included in this manifest or in Philippine validation/test partitions.

### Local dataset review UI

Launch the review tool from the ML service directory:

```powershell
.\.venv\Scripts\geoflora-ml.exe review-ui
```

Open `http://127.0.0.1:8765`. The tool binds only to loopback, shows image
provenance and review history, and supports species/status/source/duplicate
filters. Approve, reject, flag, or relabel each record with a reviewer and
rationale. New source labels are always pending; duplicate detection never
approves an image. Use **Export approved manifest** to create
`storage/datasets/curated/approved_manifest.csv`. Rejected, flagged, and
pending images stay in raw storage with their append-only review events and
are excluded from the export and training splits.

### Importing a Kaggle download

Use Kaggle's official CLI or website to download a dataset whose terms permit
the intended use. Provide a CSV manifest alongside the downloaded images with
these columns. The optional `group_id` can tie images from the same observation
or photographer together for splitting.

```text
source_id,species,image_path,source_url,license,attribution,country,group_id
```

`species` must exactly match one of the scientific names in the GeoFlora
catalog, and `country` must be `PH` or `Philippines`. This importer is for the
Philippines core dataset only; external Kaggle pretraining data must be kept in
a separately tracked corpus and must not enter the Philippines evaluation
split. Paths must be relative to the manifest directory. Rows without an
allow-listed license are excluded. Then run:

```powershell
geoflora-ml collect --source kaggle --kaggle-manifest C:\data\manifest.csv
```

### Dataset preparation

`prepare` removes exact duplicate images by normalized SHA-256 checksum and
writes `storage/datasets/curated/v1/manifest.csv`. Images from the same source
observation/occurrence are assigned as a group, so they cannot cross train,
validation, and test splits. Each species needs at least three independent
source groups; otherwise preparation stops rather than producing a misleading
split. The split seed is recorded through the command invocation and can be
reused for reproducibility.

### Species catalog staging

The separate GBIF occurrence-derived species-list workflow is documented in
[scripts/species_catalog/README.md](./scripts/species_catalog/README.md). It
stages reviewed catalog candidates only; it does not add taxa to the AI classes
or training data. This is not a complete Philippine flora checklist. Existing
source staging files can be imported to the localhost MongoDB
`geoflora.species_catalog_staging` collection; these remain review-required
source records, not a deduplicated or verified species catalog.

Run the tests from `services/ml`:

```powershell
python -m unittest discover -s tests -v
```

## Current scope

- Implemented: licensed iNaturalist and GBIF collection, local Kaggle-manifest
  import, resumable all-available API pagination, image
  validation/normalization, provenance manifests, exact deduplication, and
  group-aware dataset splitting.
- Implemented: responsive React/TypeScript/Tailwind workspace, image
  upload/preview, Next.js inference proxy, and FastAPI inference scaffolding
  with explicit not-ready and uncertain-result behavior.
- Not yet implemented: reviewed training corpus, MobileNetV2
  training/evaluation, real model artifacts, live catalog browsing,
  authentication, and geospatial reporting. No model accuracy or real
  prediction is claimed until a model is trained and evaluated.
