# GeoFlora — Clean Architecture & Development Blueprint

> Project: AI-powered invasive plant identification, verified sightings, geospatial monitoring, and controlled dataset collection/training.
>
> Status: implementation blueprint (not yet implemented). Preferred development environment: VS Code. Start with a modular monolith plus a separate Python ML service and worker.

## 1. Product goal

A user uploads or captures a plant photo. GeoFlora predicts whether it matches one of the **supported invasive plant species**, displays calibrated model confidence and uncertainty, and allows a geotagged sighting to be submitted. A reviewer verifies sightings before they are counted as confirmed occurrences. Maps and analytics distinguish **reported** from **verified** sightings and never claim that raw sighting counts prove spread.

### Core workflows

1. **Identify:** image → validation → model inference → species suggestion/unknown → user review.
2. **Report:** consented GPS or manually selected location → sighting → pending review.
3. **Verify:** reviewer examines photo, prediction, metadata → accept/reject/request correction.
4. **Monitor:** map filters, verified occurrence counts, trends, hotspots with sampling-bias caveats.
5. **Improve AI:** source import → rights/attribution check → label QA → dataset version → training job → evaluation → admin-approved model deployment.

## 2. Roles & access

| Role | Permissions |
|---|---|
| Guest | Browse public verified map and species information; optionally test identification subject to limits, without saving personal data |
| Contributor | Register/login, identify plants, submit sightings, view own history, correct/withdraw own pending reports |
| Environmental Reviewer | Review queued sightings and uncertain predictions; approve/reject with rationale; audit species labels |
| Researcher / Analyst | View permitted aggregate data, filter spatial analytics, export approved anonymized datasets |
| Administrator | Manage accounts, roles, species catalog, sources, model approvals, system settings and audit logs |
| ML Operator (optional permission, not necessarily a separate account role) | Run controlled imports, curate datasets, start/monitor training, evaluate candidates; cannot deploy without admin approval |

Use server-side authorization for every action. Roles are not frontend-only UI switches. Public location data must be generalized when sensitive.

## 3. Complete functional modules

### Public & contributor

1. Authentication and account management (signup, login, password reset, profile).
2. Species catalog (scientific/common names, photos, invasive status and references).
3. Image capture/upload (size/type validation, preview, privacy notice).
4. AI identification (prediction, top classes, model version, uncertainty and unknown handling).
5. Sighting reporting (GPS permission, manual map pin, time, notes, duplicate warning).
6. My sightings (history, status, edits before approval, withdrawal).
7. Public verified sightings map (species/date/area filters, clustered pins).
8. Community information (identification limits, invasive-species awareness, reporting guidance).

### Review, research & administration

9. Reviewer queue (approve/reject/request revision, reason, provenance, audit trail).
10. Research dashboard (counts, time-series, geographic distribution, export).
11. Hotspot analytics (density over verified reports, minimum sample requirements, bias notice).
12. User and role administration.
13. Dataset source manager (provider config, credentials status, source restrictions).
14. Dataset ingestion jobs (progress, retry, quotas, provenance, provider errors).
15. Dataset library and QA (licenses, image review, duplicates, labels, holdout management).
16. Dataset versions (immutable manifests, split reproducibility, checksums).
17. Training job manager (parameters, logs, cancellation, resource limits).
18. Model evaluation and registry (accuracy, per-class precision/recall/F1, confusion matrix, latency).
19. Model deployment (staging, approval, rollback, active model pointer).
20. Notifications and activity log (in-app/email optional).
21. Security and audit log (role changes, moderation, data imports, deployment).
22. System health, configuration and operational monitoring.

**MVP scope:** modules 1–9, 12, 15–18 (CLI/operator workflow initially), 21; add automated source management and dashboard training controls in phase 2. Do not promise fully autonomous training from unverified web images.

## 4. Technology decisions

| Layer | Choice | Reason |
|---|---|---|
| Frontend | Next.js App Router + React + TypeScript | Server-capable React foundation and route handlers |
| UI | Tailwind CSS + accessible headless primitives | Consistent responsive design |
| Server state | TanStack Query | Cache, loading/error and refetch management |
| Forms | React Hook Form + Zod | Client validation |
| Main API | Next.js route handlers + TypeScript | Catalog and application APIs alongside the web app |
| Database | MongoDB | Document-oriented species/provenance records and GeoJSON geospatial queries |
| Database access | Mongoose for Next.js; PyMongo for operator import tooling | Typed document schemas and native MongoDB indexes |
| ML inference/training API | Python + FastAPI | TensorFlow integration |
| ML framework | TensorFlow/Keras, MobileNetV2 pretrained ImageNet weights | Transfer learning baseline |
| Job queue | Redis + BullMQ (Node orchestration) | Long-running imports/training coordination |
| Training worker | Python process/container launched by controlled job runner | Isolates resource-heavy training |
| Object storage | S3-compatible in production; local adapter for development | Image/model artifacts |
| Maps | Leaflet + OpenStreetMap-compatible tile provider | Interactive sightings |
| Tests | Vitest, React Testing Library, Supertest, Pytest, Playwright | Unit, integration and E2E |
| Tooling | pnpm workspaces, Ruff, ESLint, Prettier, Docker Compose | Consistent development |

**Simplification rule:** Next.js owns web and catalog API workflows. FastAPI owns ML inference/training interfaces only. Avoid duplicating user records or business logic in Python. Training jobs must run outside the HTTP request lifecycle.

## 5. Correct clean repository tree

```text
geoflora/
├── README.md
├── geofora.md                         # This plan (requested filename)
├── .gitignore
├── .editorconfig
├── .env.example                       # Placeholder names ONLY, no secrets
├── package.json                       # pnpm workspace scripts
├── pnpm-workspace.yaml
├── docker-compose.yml                 # local MongoDB, Redis, optional MinIO (if containerized)
├── docs/
│   ├── architecture.md
│   ├── api-contract.md
│   ├── data-governance.md
│   ├── model-card.md
│   └── decisions/                     # Architecture decision records
├── apps/
│   ├── web/                           # Next.js + React + TypeScript
│   │   ├── app/
│   │   │   ├── layout.tsx
│   │   │   └── page.tsx
│   │   ├── next.config.ts
│   │   ├── postcss.config.mjs
│   │   ├── src/
│   │   │   ├── App.tsx
│   │   │   └── styles.css
│   │   ├── package.json
│   │   ├── tsconfig.json
│   │   └── next.config.ts
├── services/
│   ├── catalog/                       # Mongoose catalog importer and model
│   └── ml/                            # Python FastAPI + ML pipelines
│       ├── pyproject.toml
│       ├── .env.example
│       ├── src/
│       │   └── geoflora_ml/
│       │       ├── api/
│       │       │   ├── main.py
│       │       │   ├── routes/
│       │       │   │   ├── health.py
│       │       │   │   ├── predict.py
│       │       │   │   └── jobs.py
│       │       │   └── schemas.py
│       │       ├── core/
│       │       │   ├── config.py
│       │       │   └── logging.py
│       │       ├── inference/
│       │       │   ├── loader.py
│       │       │   ├── preprocess.py
│       │       │   └── predictor.py
│       │       ├── collection/
│       │       │   ├── base.py        # DatasetSource interface
│       │       │   ├── inaturalist.py
│       │       │   ├── gbif.py
│       │       │   ├── kaggle.py
│       │       │   └── plantclef.py   # Approved offline import
│       │       ├── datasets/
│       │       │   ├── manifest.py
│       │       │   ├── licensing.py
│       │       │   ├── validate.py
│       │       │   ├── deduplicate.py
│       │       │   ├── split.py
│       │       │   └── version.py
│       │       ├── training/
│       │       │   ├── mobilenetv2.py
│       │       │   ├── train.py
│       │       │   ├── evaluate.py
│       │       │   └── callbacks.py
│       │       └── registry/
│       │           └── artifacts.py
│       ├── scripts/
│       │   ├── collect.py
│       │   ├── prepare.py
│       │   ├── train.py
│       │   └── evaluate.py
│       ├── tests/
│       └── notebooks/                 # Exploration only, not production logic
├── packages/
│   ├── contracts/                     # Shared TypeScript API types/Zod schemas
│   └── ui/                            # Optional shared design system later
├── storage/                            # gitignored local runtime artifacts
│   ├── datasets/raw/
│   ├── datasets/curated/
│   ├── datasets/versions/
│   ├── models/
│   └── uploads/
├── scripts/
│   ├── bootstrap.ps1
│   └── bootstrap.sh
└── .github/workflows/
    ├── ci.yml
    └── security.yml
```

**Tree notation note:** `{api,components,...}` abbreviates directories to create; it is not a literal directory name. Only create modules/files as features are implemented. Do not put production datasets, `.env`, secrets, user uploads, or `.keras` binaries in Git.

**Current frontend foundation:** `apps/web` is a Next.js App Router application
with a responsive overview shell in `src/App.tsx`, Tailwind v4 styles in
`src/styles.css`, and a local-only development server. The dashboard remains a
client component; future catalog reads and API handlers can run server-side.
Counts are explicit local snapshot values, not database results. Image
identification is not simulated and does not replace the existing dataset
review tool.

## 6. Dependency rules (clean code)

- Frontend pages compose feature components and hooks; feature API functions call the centralized `api-client`.
- Express routes → controllers (HTTP) → services (business rules) → repositories (database). No SQL in controllers, no `req/res` in services.
- Python API routes → inference service → model loader; collection and training are separate pipeline modules.
- Provider adapters implement one `DatasetSource` interface; no provider-specific logic inside generic ingestion services.
- Share schemas and API contracts, not database internals. Validate at system boundaries.
- One source of truth for each concept. Prefer descriptive naming, short functions, typed errors, dependency injection where it helps testing.
- Never trigger model training from an ordinary prediction request.
- Avoid circular dependencies and overengineering; build vertical slices first.

## 7. UI/UX blueprint

### Visual direction

Environmental science dashboard: trustworthy, calm, modern and accessible, not a generic neon AI interface.

| Token | Hex | Use |
|---|---|---|
| Forest | `#174B3A` | Main navigation, primary actions |
| Leaf | `#3E8B63` | Active states, highlights |
| Mist | `#EFF6F0` | Light surfaces |
| Sand | `#F7F4EA` | Page background |
| Ink | `#183029` | Main text |
| Slate | `#66756D` | Secondary text |
| Amber | `#D99A36` | Warnings and review pending |
| Red | `#B84B49` | Errors/rejected statuses |

Typography: Inter or system sans; clear hierarchy; WCAG-aware contrast. Responsive navigation: desktop sidebar + topbar, mobile bottom navigation for contributor workflows. Keyboard access and labeled controls throughout.

### Pages and navigation

**Public:** Home (`/`), Species (`/species`), Species detail (`/species/:id`), Verified Map (`/map`), About (`/about`), Login/Register.

**Contributor:** Identify (`/app/identify`), Identification Result (`/app/identify/:id`), Report Sighting (`/app/sightings/new`), My Sightings (`/app/sightings`), Sighting Detail (`/app/sightings/:id`), Profile (`/app/profile`).

**Reviewer:** Review Queue (`/review/queue`), Review Detail (`/review/sightings/:id`), Review History (`/review/history`).

**Researcher:** Analytics (`/research/analytics`), Map Explorer (`/research/map`), Exports (`/research/exports`).

**Admin / ML operator:** Overview (`/admin`), Users (`/admin/users`), Species (`/admin/species`), Sources (`/admin/data-sources`), Dataset Library (`/admin/datasets`), Import Jobs (`/admin/imports`), Training (`/admin/training`), Models (`/admin/models`), Audit (`/admin/audit`), Settings (`/admin/settings`).

### Key screen specifications

- **Home:** concise mission, Identify Plant CTA, live *verified* sighting counts, educational species cards, map preview.
- **Identify:** drag/drop + camera, image preview, file checks, optional location permission, progress, helpful error states.
- **Result:** top prediction(s), model confidence explained, unsupported/uncertain state, species reference, report action. Do not display invented certainty.
- **Report:** photo, predicted/confirmed label, map pin, date/time, optional notes, privacy consent, submit as pending.
- **Map:** search, species/date/status filters, clustering, accessible list alternative, legend, generalized public coordinates.
- **Reviewer:** side-by-side photo, predicted class, location, provenance, previous reports, approve/reject/needs info with rationale.
- **AI Studio:** dataset source cards, license warnings, import queue, labeled image gallery, quality flags, dataset version selector, training status and metrics, deployment approval.

### Shared UI states

Every data-driven page must support loading, empty, error, unauthorized, and success states. Use skeletons sparingly, accessible toasts, confirmation dialogs for destructive actions, and explicit pending/verified/rejected badges.

## 8. Database entities (conceptual)

- `users`, `roles`, `user_roles`, `sessions` (or secure auth session store)
- `species`, `species_identifiers`, `species_names`, `species_status_assertions`, `species_references`
- `images` (object key, checksum, mime, rights/attribution)
- `identifications` (user, image, predicted species, scores, model version, status)
- `sightings` (reporter, species, observed_at, GeoJSON Point, privacy level, verification status)
- `sighting_reviews` (reviewer, decision, rationale, timestamp)
- `dataset_sources` (provider, enabled, config without raw secrets)
- `ingestion_jobs`, `dataset_images` (provider record ID, photo license, attribution, provenance, quality status)
- `dataset_versions`, `dataset_version_items` (immutable membership and train/val/test split)
- `training_jobs`, `model_versions`, `model_metrics`, `model_deployments`
- `notifications`, `audit_events`

Use stable `_id` values and unique compound indexes for source/provider identifiers.
Represent relationships with explicit ObjectId/string references and validate them
in repositories; MongoDB does not enforce relational foreign keys. Store sighting
locations as GeoJSON Points in `[longitude, latitude]` order and add `2dsphere`
indexes for nearby/spatial queries. Index catalog names, taxonomic identifiers,
review status, and source keys. Keep unbounded review history, source evidence,
and import events in separate collections rather than growing embedded arrays.
Use versioned, idempotent import scripts and retain source checksums/citations.
Local development currently connects to `mongodb://127.0.0.1:27017` and the
`geoflora` database. Sensitive location is not automatically public.

## 9. API contract sketch

All routes under `/api/v1`. Return consistent JSON errors `{code, message, details?, requestId}`. Paginate list endpoints and validate input on the server.

| Method | Route | Purpose | Access |
|---|---|---|---|
| POST | `/auth/register` | Register | Public |
| POST | `/auth/login` | Login | Public |
| GET | `/species` | Species catalog | Public |
| POST | `/identifications` | Upload photo and request inference | Contributor / limited guest |
| GET | `/identifications/:id` | Prediction result | Owner/reviewer |
| POST | `/sightings` | Submit geotagged sighting | Contributor |
| GET | `/sightings/mine` | Own sightings | Contributor |
| GET | `/map/sightings` | Verified generalized map data | Public |
| GET | `/review/sightings` | Pending queue | Reviewer |
| POST | `/review/sightings/:id/decision` | Review decision | Reviewer |
| GET | `/analytics/overview` | Authorized aggregates | Researcher/Admin |
| GET | `/admin/dataset-sources` | Source config/status | Admin/ML operator |
| POST | `/admin/ingestion-jobs` | Start authorized import | Admin/ML operator |
| GET | `/admin/ingestion-jobs/:id` | Job status | Admin/ML operator |
| POST | `/admin/dataset-versions` | Freeze curated dataset | Admin/ML operator |
| POST | `/admin/training-jobs` | Queue training | Admin/ML operator |
| GET | `/admin/training-jobs/:id` | Metrics/logs/status | Admin/ML operator |
| GET | `/admin/models` | Candidate and deployed models | Admin/ML operator |
| POST | `/admin/models/:id/deploy` | Approve deployment | Admin |

**Internal ML endpoints (private network/service auth):** `POST /predict`, `GET /health`, `POST /internal/jobs/train` (enqueue/dispatch only), `GET /internal/jobs/{id}`. Never expose raw training execution to unauthenticated clients.

## 10. Data-source integration policy

| Provider | Integration | Authentication | Caveats |
|---|---|---|---|
| iNaturalist | Public observations API + permitted licensed images | Usually no key for public reads | Follow API rate limits, image licensing, attribution, and observation quality filters |
| GBIF | Occurrence API and linked multimedia | Public search no key; bulk downloads require account | Many records lack photos; preserve occurrence and media licenses |
| Kaggle | Official CLI/API or approved dataset import | Authenticated access | No arbitrary dataset-wide scraping; dataset license and schema vary |
| PlantCLEF | Approved downloaded dataset importer | Dataset-specific access terms | Not a universal live image API; check challenge rules and reuse rights |

Provider flow: discover → metadata/provenance → license eligibility → bounded download → checksum/deduplicate → human label review → curate → version. Keep a CSV/JSON manifest with `provider`, `source_id`, `source_url`, `scientific_name`, `license`, `attribution`, `downloaded_at`, `sha256`, `split`, `review_status`.

**Never** train automatically on unreviewed uploads or every downloaded image. Restrict to approved dataset versions. Support idempotent jobs, exponential backoff, quotas, pause/cancel, and clear failure logs. Credentials are server-side only.

## 11. ML training specification

1. Define a supported species list plus an **unknown/non-target** evaluation set; don't force every image into a supported invasive class.
2. Curate legally reusable labeled images, including local field photos where possible; document label confidence and class balance.
3. Deduplicate before splitting; group by observation/photographer/near-duplicate cluster to reduce leakage.
4. Freeze an immutable dataset version with train/validation/test split and random seed.
5. Resize to 224×224, apply the exact MobileNetV2 preprocessing in both training and inference; augment **training only**.
6. Load `tf.keras.applications.MobileNetV2(weights='imagenet', include_top=False)`; freeze backbone, add global pooling + dropout + softmax classifier.
7. Train classification head with early stopping/checkpoints; optionally unfreeze top backbone layers at low learning rate.
8. Evaluate on untouched test data: accuracy, macro/per-class precision, recall, F1, confusion matrix, inference latency, unknown-case behavior, and confidence calibration.
9. Save `.keras` artifact, label mapping, preprocessing config, metrics, model card, dataset version, and SHA-256 checksum.
10. Register candidate; admin reviews against baseline and promotes explicitly. Retain previous model for rollback.

No target accuracy is guaranteed; define acceptance thresholds after pilot testing. Confidence score is not a probability of correctness without calibration. A small curated dataset may not generalize to new lighting, locations, growth stages, or similar species.

## 12. Security, privacy & reliability

- Restrict uploads by file size, decoded format, dimensions and content; strip EXIF where appropriate; scan and store outside the web root.
- GPS is opt-in; support manual pin; restrict precise coordinates to authorized roles; consider ecological sensitivity and personal privacy.
- Enforce authorization and rate limiting on all privileged and upload endpoints.
- Store secrets in environment/secret manager; never in React bundles or committed files.
- Validate all provider responses; sanitize logs; do not run arbitrary uploaded code or notebooks.
- Isolate ML jobs with resource/time quotas and controlled worker permissions.
- Implement audit trails for label changes, reviews, exports, and model deployments.
- Add backups, migration rollback plans, health checks, structured logs, and queue retries.
- Honor image attribution, redistribution restrictions, and data deletion requests as applicable.

## 13. Testing plan

- **Frontend unit:** forms, upload errors, role-aware UI, map filters, empty states.
- **API unit/integration:** auth, permission boundaries, validations, moderation state machine, spatial queries, source adapters.
- **ML:** deterministic preprocessing, label mapping, unknown handling, leakage checks, inference consistency.
- **E2E:** register → upload → prediction → submit sighting → review → verified map appearance.
- **Operational:** restart/retry import job, training failure recovery, model rollback, storage unavailable.
- **Usability:** contributors, reviewers and researchers complete representative tasks.

## 14. Phased development roadmap

### Phase 0 — Decisions & foundation

- [ ] Confirm target invasive species, geographic scope, image rights, and stakeholder roles.
- [ ] Create monorepo, editor/formatter rules, environment validation, Docker services, CI.
- [ ] Define API schemas and initial DB migrations.

### Phase 1 — Working identification MVP

- [ ] Create curated pilot dataset and versioned split.
- [ ] Train MobileNetV2 baseline locally in VS Code (CPU is acceptable for small tests).
- [ ] Implement FastAPI `/predict` and model loading.
- [ ] Implement React upload/result pages and Express identification endpoint.
- [ ] Add unknown/uncertain behavior and model version metadata.

### Phase 2 — Reporting & monitoring

- [ ] Implement authentication and contributor accounts.
- [ ] Add geotagged sighting form and MongoDB GeoJSON/`2dsphere` storage.
- [ ] Add reviewer workflow and verified public map.
- [ ] Add basic analytics and privacy controls.

### Phase 3 — AI Studio automation

- [ ] Implement iNaturalist and GBIF source adapters first.
- [ ] Add Kaggle authenticated dataset import and PlantCLEF approved-file import.
- [ ] Add ingestion queue, dataset QA and version manager.
- [ ] Add controlled training jobs, evaluation dashboard, registry and admin-approved deployment.

### Phase 4 — Research quality & launch

- [ ] Compare MobileNetV2 with EfficientNetB0 under identical splits.
- [ ] Test on local field photos and unknown species.
- [ ] Run security, usability, load and recovery tests.
- [ ] Document limitations, results, architecture, and user manual.

## 15. First implementation sprint (VS Code)

1. Initialize `pnpm` workspace (`apps/web`, `apps/api`) and Python virtual environment (`services/ml`).
2. Start the local MongoDB service and Redis (containerized if needed).
3. Create minimal health endpoints in Express and FastAPI.
4. Build a typed `POST /api/v1/identifications` flow with upload validation and FastAPI forwarding.
5. Prepare a **small manually verified** pilot dataset, train MobileNetV2, save model and class mapping.
6. Connect React Identify page to API; render model output and uncertainty.
7. Add unit/integration tests and README setup instructions.

**Definition of done:** one end-to-end photo can be uploaded locally, validated, inferred by the trained model, and displayed with species suggestion, uncertainty, and model version; tests pass. No fake AI output in production paths.

## 16. Example environment variable names

```dotenv
# apps/api/.env (local only)
NODE_ENV=development
PORT=4000
DATABASE_URL=postgresql://USER:PASSWORD@localhost:5432/geoflora
REDIS_URL=redis://localhost:6379
ML_SERVICE_URL=http://localhost:8000
STORAGE_DRIVER=local
SESSION_SECRET=REPLACE_WITH_STRONG_SECRET
KAGGLE_API_TOKEN=
GBIF_USERNAME=
GBIF_PASSWORD=

# services/ml/.env (local only)
ML_PORT=8000
MODEL_DIR=../../storage/models
DATASET_DIR=../../storage/datasets
MODEL_VERSION=development
INTERNAL_SERVICE_TOKEN=REPLACE_WITH_STRONG_SECRET

# apps/web/.env (public, no secrets)
VITE_API_BASE_URL=http://localhost:4000/api/v1
```

Environment names are illustrative; implement schema validation and configure actual credentials according to the official provider's current authentication method. `.env.example` should use harmless placeholders.

## 17. Non-goals for the first release

- Fully autonomous ingestion of arbitrary internet images without permissions or QA.
- Auto-deploying a newly trained model based solely on its training accuracy.
- Claiming a map of user reports establishes biological invasion or actual spread rates.
- Identifying all plants worldwide with a small three-species classifier.
- Real-time training for each user upload.

## 18. Key decisions to finalize

1. **Confirmed initial species:** *Chromolaena odorata* (Hagonoy), *Lantana camara*, and *Pontederia crassipes* (Water Hyacinth), plus unknown/non-target cases.
2. **Confirmed geographic scope:** Philippines.
3. Authentication approach (secure cookie sessions or carefully designed tokens).
4. Dataset licensing/attribution policy and review responsibility.
5. Training compute (local VS Code CPU, NVIDIA GPU/WSL2, or cloud later).
6. Public map location precision and data retention rules.

---

**Recommended starting point:** implement the vertical slice **upload → FastAPI MobileNetV2 inference → result** before building a large dashboard or fully automated training pipeline. This keeps the project clean, testable, and demonstrable while preserving the architecture for advanced modules.
