# GeoFlora: working notes for Claude

GeoFlora is a student thesis system: image-based identification of invasive alien plants in the Philippines, plus spatial monitoring. Reyca de Alba is the hired developer. Reyca is not a botanist.

## Layout

| Path | What it is |
|---|---|
| `apps/web/` | Next.js app (http://127.0.0.1:5173). Read `apps/web/AGENTS.md` before editing. The dev server runs detached and logs to `storage/logs/web-dev.log`. Restart it after a mongoose schema change, because the dev server caches models. Identify flow: `docs/simple-identify-flow-2026-11-05.md`. |
| `apps/web/models/` | **The live classifier, running inside Next.js** (ONNX, `src/lib/classifier.ts`). `ensemble.json` = 21cls v1+v2 averaged, with 3cls-v2 confirming uncertain Hagonoy/Lantana/hyacinth guesses when the ensemble score is at least 0.60. See `docs/ml-in-nextjs.md`. |
| `services/ml/` | Old FastAPI inference service. No longer needed; it is used only if `GEOFLORA_ML_MODE=remote`. |
| `services/catalog/` | Species catalog service |
| `ml-lab/` | **Data and training system** (GBIF download, label review, split, train, evaluate, export, lab demo). It has its own `.venv` and `README.md`. Copied from `C:\Users\reyca\geoflowra\GeoFlora-ML-Lab` on 2026-11-05. |
| `storage/` | Runtime data and models for the app (git-ignored) |
| `docs/`, `plan.md`, `geofora.md` | Project records and plans |

The folder is not a git repo. Before changing app code, make a backup or snapshot (earlier ones are in `C:\Users\reyca\geoflora-backups\`).

## ML lab (`ml-lab/`)

Run from `ml-lab/` with `.venv\Scripts\python.exe`. The pipeline commands are in `ml-lab/README.md`.
- Configs: `configs/default.yaml` (3 targets), `configs/expansion_nissap.yaml` (21 classes).
- Lab demo: `python scripts/demo_server.py` → http://127.0.0.1:8090 (flow, identify, reports, map).
- Tests: `python -m pytest -q -m "not slow"`.
- Latest models are in `models/exported/`. The 21-class `geoflora-mnv2-21cls-v1` scored 82.5% test accuracy. The 3-class `geoflora-mnv2-3cls-v2` scored 97.4%. The 21+3 cascade result is in `reports/cascade/`.
- Read target status from `models/exported/<v>/class_mapping.json`. A run's evaluation report shows the statuses at split time.

## Honesty rules (thesis integrity)

- Labels: Reyca screens the photos, with an AI pre-screen flagging questionable ones. Never import review decisions under Reyca's name for photos Reyca has not decided. Keep `review.label_basis` accurate. Never call it "botanical review" unless a botanist actually did it.
- Ecological status: 13 species are `target_invasive`. Reyca is the named verifier, and the NISSAP 2020-2030 citation was located by an AI assistant. A new target needs a named verifier, a date and a citation.
- Never fake predictions, metrics or data. Use each test set once, and never tune on it.
- Don't activate a model in the app (`storage/models/active_model.json`) without Reyca's OK. Use the app's promotion flow, with backup and rollback.
- App reports have no blocking review (owner decision, 2026-11-05). They are saved as `recorded` with the AI result (target / not a target / not sure), like the ML lab. The UI calls it "Identified by GeoFlora AI". Reyca does not want the phrase "not expert-verified". Admins can optionally **Approve** or **Correct** a report. Approved or corrected photos that the AI did not get right become training data (`ml-lab/scripts/app_training_worker.py`, log `storage/logs/app-training-worker.log`). It retrains after 20 new photos, and the admin approves the new model before it goes live. See `docs/simple-identify-flow-2026-11-05.md`.

## How to work with Reyca

- **Reply in Taglish/Tagalog**, in short, plain language. Reyca often asks "kumusta?" or "musta?". Answer with a quick status:
  - ✅ **Mga nagawa:** results with numbers (accuracy, photo counts)
  - ⏳ **Tumatakbo:** what's running and an honest estimate of how long it will take
  - ❓ **Tanong:** only when a decision is Reyca's to make
- Reyca delegates ("ikaw na bahala", "do the rest"). Proceed on routine work, but bring real decisions (active model, verifier, what to claim in the thesis) back as clear options with a recommendation.
- **Show, don't just tell.** Reyca wants to *see* the flow. After changes, run the app or demo, give the URL, and list a few things to try (e.g., photos that should come out ✅ TARGET, 🔵 hindi target, ⚠️ hindi sigurado).
- Results in the UI: 🔴/✅ TARGET INVASIVE, 🔵 hindi target (with species name and description), ⚠️ hindi sigurado. Don't declare a plant invasive straight away. Every identified species shows a description: how to recognise it, its look-alikes, and its NISSAP status.
- Priority: "gagana ang system at hindi mahirap i-navigate". Working and easy to use beats extra features.
- Long jobs (training, downloads) run in the background. Say how long they'll take and how Reyca can check them.
- Only one Claude session should edit app code at a time.
