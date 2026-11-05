# Part 1 — Verified project baseline

Audit date: October 23, 2026, Asia/Manila. Scope: current local foundation; real identification awaits reviewed data and a trained model.

## Verification results

| Check | Result |
|---|---|
| ML unittest suite | 27 passed |
| Taxonomy/staging unittest suite | 14 passed |
| TypeScript catalog tests | 7 passed |
| Web typecheck and production build | Passed |
| Catalog TypeScript build | Passed |
| ML environment dependency check | `pip check`: no broken requirements |
| MongoDB | Local `127.0.0.1:27017` ping returned 1.0; no writes performed |
| Web production startup | HTTP 200 at `/` on port 5173 |
| Inference startup/health | HTTP 200 on port 8000, explicitly `ready: false` |
| Next.js inference proxy | HTTP 200 health response matching missing-model state |
| Photo submission through proxy | HTTP 503, explicit missing-model explanation |
| Invalid upload through proxy | HTTP 415 |
| Dataset review UI | HTTP 200 at port 8765; statistics endpoint returned 243 records |

Existing inference/review services were reused when listening; only processes started by the smoke script were terminated. Web availability after the test requires starting `npm run dev` or `npm run start`. The review statistics endpoint took about 4.47 seconds in a separate request. An initial smoke check with a two-second timeout failed; increasing the statistics budget to 45 seconds verified successful completion. This is not evidence of acceptable final dashboard latency.

Environment: Node v22.19.0, Python 3.11.9. Applicable web instructions: apps/web/AGENTS.md. No root AGENTS.md was found. The workspace is not a Git repository, so no Git diff/status baseline is available.

## Dataset consistency

Fresh `geoflora-ml audit --target-per-species 1000` result:

| Species | Valid images | Approved | Pending |
|---|---:|---:|---:|
| Chromolaena odorata | 93 | 0 | 93 |
| Lantana camara | 114 | 0 | 114 |
| Pontederia crassipes | 36 | 0 | 36 |
| Total | 243 | 0 | 243 |

No invalid images, review conflicts, or exact duplicate groups were reported. There are 93 perceptual near-duplicate groups and 16 historical download rejections. Near duplicates are candidate similarity groups, not automatic grounds for deleting images. No review events or approved export exist.

| Historical manifest | Rows | Train / validation / test | Unapproved rows | Near-duplicate groups crossing splits |
|---|---:|---|---:|---:|
| curated/v1/manifest.csv | 78 | 54 / 13 / 11 | 78 | 1 |
| curated/v2/manifest.csv | 243 | 170 / 38 / 35 | 243 | 39 |

Both manifests reference existing raw records and images with matching checksums. Neither has exact-checksum or identical observation-group leakage, but both have perceptual group leakage and lack current human approvals. **Both are historical, unsuitable for training or final evaluation.** Files were preserved unchanged; hashes are recorded in baseline-evidence.json.

The current prepare implementation correctly refuses this dataset: `No approved, unique images are available`. The check used a temporary output directory and did not overwrite v1/v2. After human review, generate a new version with an explicit output directory; do not promote either historical manifest.

## Implemented features and blockers

Implemented and checked: collection/rights/provenance tooling, image validation, review workflows, group-aware preparation, taxonomy staging/import validation, web build, upload proxy, and inference missing-model behavior. Collection tests use controlled fixtures; no fresh external collection was attempted.

Blockers to real identification: zero approved images, class imbalance (especially water hyacinth), unsuitable historical splits, no training/evaluation module, and no installed model/mapping. Later parts must add accounts, sighting storage, geotagging, verification, live catalog APIs, mapping, analytics, and intended-user evaluation. Catalog tooling is an importer, not a complete web catalog service. Unit tests do not establish live full-import success, and no full catalog import was performed.

## Proposed acceptance targets

These are initial engineering/research targets, not measured results or user-approved scientific requirements. Confirm or revise before final evaluation; preserve the chosen criteria in evaluation records.

| Area | Initial target and measurement |
|---|---|
| Model | Held-out accuracy and macro F1 >= 0.85; each target species recall >= 0.80. Report precision/recall/F1, support, confusion matrix, and uncertainty; small samples limit interpretation. |
| Identification | p95 upload-to-result <= 5 seconds for <= 5 MB supported photos, one concurrent user; >= 30 timed requests on documented hardware/network. Measure cold startup separately. |
| Dashboard | p95 filtered map/API response <= 3 seconds under a documented representative dataset and load. |
| Usability | >= 90% completion of core upload/submit/map tasks without assistance, and SUS >= 70; aim for at least 10 participants across intended user groups and disclose actual sampling. |
| Reliability | >= 99% successful valid requests in a 100-request controlled run; all defined failure scenarios return clear recoverable errors, with no duplicate saved sightings from retries. This is not a production uptime claim. |
| Access/data integrity | All defined permission and location/time validation checks pass; no pending sighting is presented as verified. |

## Reproduce

Run from the project root unless specified:

```powershell
.\services\ml\.venv\Scripts\geoflora-ml.exe audit --target-per-species 1000
.\services\ml\.venv\Scripts\python.exe -m unittest discover -s services/ml/tests -v
.\services\ml\.venv\Scripts\python.exe -m unittest discover -s scripts/species_catalog -p 'test_*.py' -v
```

In apps/web: `npm run typecheck`, then `npm run build`.
In services/catalog: `npm test`, then `npm run build`.

After building the web application:

```powershell
.\services\ml\.venv\Scripts\python.exe scripts/baseline_audit.py
```

The script saves docs/baseline-evidence.json, checks manifests without modifying them, pings local MongoDB, and exercises local HTTP endpoints. Requires installed dependencies, the web build, and available ports or the intended GeoFlora services already running on those ports. It does not collect new images, change reviews, or import database records. The fresh dataset audit separately updates storage/datasets/reports/dataset_audit.json.

Next: Part 2, human image review. Part 1 establishes a functioning baseline, not a trained identification system.
