# GeoFlora Implementation Plan

Created: October 23, 2026

Gabay ito sa development ng GeoFlora. Ang napiling workflow ay batch collection muna sa buong 100-species research queue, saka audit, cleanup at review. Hindi tayo hihinto para mag-review o mag-train pagkatapos ng bawat species. Ang koleksyon ay hindi awtomatikong approval ng ecological status, labels o model deployment.

## Current step and next actions

**Main implementation phase for the local client demo: complete.** The complete upload, real CNN, uncertain result, geotagged report, authorized verification, and map/analytics path passed, and model promotion now requires explicit administrator approval. Remaining handoff items are owner-led Part 11 participant sessions (at least 10 consenting participants and confirmation of Part 1 targets) and Part 12 production deployment preparation. Automated Part 11 latency, concurrency, 100/100 reliability, failure/recovery, and accessibility checks pass on loopback; model quality targets remain unmet. See [client handover](docs/client-handover-2026-11-01.md), [Part 11 evaluation](docs/part-11-evaluation.md), and [usability kit](docs/part-11-usability-kit.md).

**CNN reconciliation (November 1):** the active delivery model remains the owner-authorized three-class `mobilenetv2_v3_seed42`. The inactive 11-class candidate and its 1,625-row frozen dataset were preserved; one bounded fine-tuning attempt did not improve its validation-loss checkpoint, so it was not promoted. See [11-class candidate reconciliation](docs/11-class-candidate-reconciliation-2026-11-01.md). The historical 73.52% 11-class test score is not an untouched blind-test result.

For the concrete phased plan to reach and responsibly verify the 95% image-classification target, see [Model accuracy roadmap](docs/model-accuracy-roadmap.md). The target is not yet met by the current evidence.

- [x] Build and initially screen the 100-species research queue.
- [x] Start the resumable batch worker in isolated staging.
- [x] Finish the bounded pass across all 100 queue entries, including documented unresolved names and source failures.
- [x] Audit everything obtained together, then record taxonomy/country/duplicate/label decisions and explicit holds.
- [x] Freeze the constrained experimental five-class dataset v5 (211 photos; small-sample limitations recorded).
- [x] Train/evaluate the expanded candidate and record per-species scores.
- [x] Evaluate the v5 candidate (Part 5): not approved; threshold, unsupported-input, robustness and latency results recorded.
- [ ] Improve independent field-image coverage and meet quality targets before promoting expanded identification.

Status snapshot checked October 23, 2026: the worker was running; 17 species had checkpointed outcomes, 14 had images and 121 records were saved. This is a historical checkpoint, not a live counter. See [live progress](docs/species-100-collection-progress.json) and [batch workflow](docs/species-100-batch-collection.md). A finished pass must have an outcome for each entry; it does not require successful downloads for all 100.

The initial batch targets up to 10 distinct-checksum images per species with a shared 1 GiB staging-image budget. This is a feasibility pass, not the final required training-image count. All new records remain pending. Existing experimental data/models are preserved.

## Project objective

Develop an image-based web system that identifies supported invasive plants and analyzes their spatial distribution to support monitoring and management.

Specific objectives:

1. Collect and prepare a labeled image dataset of target invasive plants.
2. Train and evaluate an image classifier using accuracy, precision, recall, and F1-score.
3. Support photo upload/capture and display identification with confidence scores.
4. Save submitted identifications with location, observation date, and time.
5. Map occurrences and provide distribution, hotspot, and temporal analytics.
6. Evaluate usability, performance, and reliability with intended users.

## Target workflow

```text
Upload/capture photo → validate → model prediction → show result/uncertainty
→ GPS permission or manual location → user confirms submission
→ save pending sighting → reviewer verifies → map and analytics
```

Dataset workflow:

```text
Batch licensed image collection across the research queue → whole-batch audit
→ taxonomy/ecological/geographic review → duplicate grouping → label review
→ versioned grouped splits → training → validation → final test evaluation
→ approved model artifact → inference service
```

## Scope and implementation rules

- Geographic scope: nationwide Philippines, with regional coverage gaps reported explicitly.
- Current experimental AI classes: Chromolaena odorata, Lantana camara, and Pontederia crassipes.
- Long-term expansion target: up to 100 evidence-backed Philippine invasive plant species. Collect candidates across the full queue first; choose the trainable class set after batch review. Earlier 3 -> 10 -> 25 -> 50 phases are optional model milestones, not collection gates. See [100-species expansion plan](docs/species-100-expansion-plan.md) and [batch workflow](docs/species-100-batch-collection.md). Research candidates are not configured model classes.
- Next.js owns the web application and application APIs; FastAPI owns ML inference. MongoDB stores application records. Training runs outside HTTP requests.
- GBIF taxonomy candidates belong to the species catalog. Importing a taxon does not make it an AI-supported class or verify invasive status.
- Use approved, licensed images for training. Human review needs a reviewer and rationale; do not bulk-approve source labels without review.
- Keep the same observation and near-duplicate images in one dataset partition. Never use the test set for model selection or threshold tuning.
- Confidence is a model score, not a guarantee of correctness. Unsupported inputs can receive high scores; test this explicitly.
- Location submission requires user consent or a manual pin. Store observation time separately from submission time.
- Separate pending and verified sightings. Public displays must not expose sensitive coordinates or personal information.
- Dashboard counts describe the recorded observations. Report trends do not by themselves establish ecological spread.
- Check applicable AGENTS.md instructions before changing files. Update this checklist and record verification after each completed part.

## Verified baseline and preserved history

The original corpus has 243 images across three classes, approved from explicit owner attestation. The early zero-approval audit is historical. Independent botanical and per-record geographic verification remain unestablished. Additional Mikania staging contains 50 pending records and is separate from the current 100-species batch.

Historical curated/v1 and v2 have cross-split near-duplicate leakage and are excluded from training. Experimental v3 has grouped splits (166 train, 38 validation, 39 test), and a real MobileNetV2 candidate was trained and reloaded successfully. Results: 87.18% top-1 accuracy, 82.74% macro F1, and 50% water-hyacinth recall. It was initially not activated after training; on October 23 the owner explicitly authorized its local experimental activation. It remains the active three-class delivery model. These results apply only to its three classes; they do not validate the expanded research queue. See [baseline results](docs/training-v3-results.md) and [11-class candidate reconciliation](docs/11-class-candidate-reconciliation-2026-11-01.md).

## Part 1 — Audit the current project and agree on the baseline

Status: Completed baseline audit; acceptance targets are proposed for confirmation. Objectives: foundation for 1–6.

- [x] Inspect current source, local instructions, dependencies, configuration, and available tests.
- [x] Run a fresh dataset audit; summarize records, reviews, species balance, and duplicates.
- [x] Check raw records, review history, approved export, and curated/v1 and v2 for consistency.
- [x] Record which dataset outputs are historical and which may be used going forward; preserve originals.
- [x] Verify web/inference startup and local MongoDB availability without exposing credentials.
- [x] Document implemented features, blockers, and existing failing checks.
- [x] Set measurable acceptance targets for identification latency, model quality, usability, and reliability before final evaluation.

Done when: there is a reproducible baseline report, an understood dataset state, and a concrete list of missing components. No unverified manifest is designated as training-ready.

Evidence: [Part 1 baseline report](docs/part-1-baseline.md) and [machine-readable checks](docs/baseline-evidence.json). Original Part 1 findings predate owner label approvals; later events supersede that historical review state.

## Part 2 — Collect the full batch, then audit and review

Status: Completed with a constrained experimental selection and explicit holds. Objective: 1. Depends on: Part 1. The full batch remains a research archive; it is not a 100-class training dataset.

### Part 2A — Complete collection across the queue

- [x] Research and initially screen all 100 candidates; retain ecological conflicts and unresolved names.
- [x] Start resumable PH-only collection in `storage/datasets/staging/species_100_ph`.
- [x] Checkpoint an outcome for every entry: collected, no eligible images, taxonomy unresolved, source failure, or storage cap.
- [x] Reconcile the final report with actual manifests and files; record interruptions or unattempted entries explicitly.

### Part 2B — Audit and organize the whole collection

- [x] Produce one batch inventory: species, source, image counts, failures, rights and storage.
- [x] Validate image decoding/checksums, license/attribution, source country and observation evidence.
- [x] Record known synonym mappings and route unresolved taxonomy, native/cryptogenic conflicts and unverified ecological candidates to explicit holds; no class activation until evidence is reconciled.
- [x] Group duplicates across providers, the separate Mikania staging and the existing corpus; preserve provenance.
- [x] Organize candidate field/herbarium/unknown-domain queues and report observation/similarity groups and region-coverage gaps; retain manual verification requirements.

### Part 2C — Review and choose the supported classes

- [x] Document review criteria and retain existing review-tool support for the original classes.
- [x] Prepare isolated batch review packets and validated staging review/export support for all collected research taxa.
- [x] Record label/location/domain decisions with provenance and rationale for the selected experimental records; review tools do not fabricate independent verification.
- [x] Decide the usable experimental class set from available evidence and independent observations; do not force all 100 into training.
- [x] Record the supplementation outcome: keep weak/unreviewed and global images out of PH evaluation, retain the separate Mikania staging pool for a distinct future review.
- [x] Export the selected corpus and rerun integrity, rights, decode and leakage audits.

The original 243-image approved export is already populated from owner attestation. Selected batch records carry their separate owner label/location and visual-screening evidence; the separate Mikania staging still does not have its own approval.

Done when: the full batch has documented outcomes, cleanup/review decisions are traceable, and the selected experimental subset has a reproducible grouped partition. Collection completeness, experimental split feasibility and model-promotion readiness are different milestones. Neither ten collected images nor the older 1,000-per-class target guarantees accuracy.

Evidence: [batch progress](docs/species-100-collection-progress.json), [ecological screening](docs/species-100-verification-report.md), [verification ledger](docs/species_100_verification_ledger.csv), [Part 2 finalization](docs/part-2-finalization.md), and [Mikania staging](docs/mikania-staging-review.md). Source-country metadata and owner attestation do not by themselves establish independently verified location.

## Part 3 — Freeze a reproducible dataset version

Status: Completed for constrained experimental v5; experimental v3 and unactivated v4 are preserved history. Objective: 1. Depends on: completion of Parts 2A–2C. This is a technical/reproducibility freeze, not approval to promote a five-class model.

- [x] Prepare train/validation/test partitions using the recorded seed and experimentally eligible records only.
- [x] Verify no exact duplicate, near duplicate, or shared observation crosses partitions.
- [x] Report per-class image and independent-group counts for every partition.
- [x] Save immutable manifests, checksums, class names, review snapshot, decision ledger, and preparation settings.
- [x] Keep any external pretraining corpus separately tracked and out of Philippine evaluation partitions.

Done when: every manifest path resolves, all included records meet the documented experimental eligibility rule, and split checks pass. Subsequent dataset changes create a new version.

## Part 4 — Implement and train the classifier

Status: Completed for experimental v5. The training pipeline (shared preprocessing, train-only augmentation, validation-gated fine-tuning, export, reload and isolated verification) is in place and produced a v5 candidate; the candidate fails quality targets and is not activated. Objective: 2. Depends on: Part 3.

- [x] Implement a reproducible MobileNetV2 transfer-learning training entry point.
- [x] Match training and inference preprocessing; augment training data only.
- [x] Save settings, seed, dataset identity, class order, and training history.
- [x] Use validation results for checkpoint selection, early stopping, and any fine-tuning.
- [x] Export the candidate model and the class-mapping format expected by the existing loader.
- [x] Verify output dimensions, class order, and artifact reload behavior.

Done when: expanded-data training produces a reloadable model and matching mapping with traceable inputs. Expanded entry point: `scripts/train_expanded.py --frozen-dataset <curated version> --output <new candidate> [--fine-tune]`; isolated check: `scripts/verify_expanded_candidate.py`. The preserved three-class v3 entry point `scripts/train_baseline.py` uses the same shared preprocessing without augmentation.

Evidence: [v5 results](docs/training-v5-five-results.md) and [v5 status](docs/training-v5-status.json); history: [v3 evaluation](docs/training-v3-results.md), [v4 results](docs/training-v4-six-results.md). Preprocessing parity and train-only augmentation are covered by `services/ml/tests/test_preprocess.py` (30 ML tests pass). On v5 the fine-tune stage did not lower validation loss, so the frozen-head weights were kept.

## Part 5 — Evaluate and approve a model candidate

Status: Completed for v5 with outcome **not approved**. The three-class baseline and the v5 candidate are evaluated reproducibly; v5 fails the model-quality targets and unsupported-input checks, so no expanded model is activated and the experimental v3 model stays live. Objective: 2. Depends on: Part 4.

- [x] Select confidence/uncertainty settings using validation data (v5: 0.90 by the lowest-threshold-with-≥90%-validation-selective-accuracy rule; recorded with the candidate, not applied to the live service).
- [x] Evaluate the frozen baseline candidate on the held-out test set; repeat for the expanded model.
- [x] Report baseline accuracy, per-class precision/recall/F1, macro F1, support, and confusion matrix; repeat for the expanded model.
- [x] Examine errors and test unsupported species, non-plant photos, blur, and difficult lighting (76 unsupported PH species from the research archive; synthetic non-plant proxies only, so real non-plant photos are still needed).
- [x] Measure inference latency on the intended hardware and record limitations (current local host; inference-only; end-to-end timing is Part 6, deployment hardware is remeasured in Part 12).
- [x] Write a model card with dataset version, results, intended use, and failure cases.
- [x] Review the candidate against the targets established in Part 1 before activation.

Done when: evaluation is reproducible and honestly reports whether targets were met. If improvement is needed, train a new candidate without tuning against the final test set.

Evidence: [v5 model card](docs/model-card-v5.md) and [machine-readable evaluation](docs/part-5-v5-evaluation.json); reproduce with `scripts/evaluate_candidate_part5.py`. Key findings: 75.00% accuracy and 49.47% macro F1; at the 0.90 threshold, 47.22% test coverage with 88.24% selective accuracy; 35.37% of unsupported-species photos were still accepted, mostly as Water Hyacinth; dark and overexposed photos degrade sharply; FastAPI inference p95 was 116 ms locally. Part 1 targets remain proposed, not user-confirmed.

## Part 6 — Complete real photo identification

Status: Completed locally with the owner-authorized experimental v3 model (no candidate meets Part 1 targets; v5 not approved). Real-phone camera check remains. Objective: 3. Depends on: Part 5.

- [x] Install the approved artifact and mapping through the existing loader configuration (experimental v3, checksum-identical to its candidate; version and validation-selected 0.80 threshold now read from `active_model.json`).
- [x] Verify Next.js → FastAPI inference with actual model predictions.
- [x] Complete upload and mobile camera capture with file validation and preview (checked in 390px mobile browser emulation; physical-phone check pending).
- [x] Show species, confidence, model version, and clear uncertainty messages.
- [x] Handle unsupported files, oversized uploads, timeouts, and unavailable models.
- [x] Measure full upload-to-result latency and verify the primary user flow (loopback, development machine: p95 255 ms over 39 photos).

Done when: a supported photo produces a real prediction and service failures produce useful messages. Identification does not silently save a sighting.

Evidence: [Part 6 identification](docs/part-6-identification.md), [HTTP smoke](docs/part-6-identification-smoke.json), [browser smoke](docs/part-6-identification-browser-smoke.json), [v3 threshold/unsupported-input evaluation](docs/part-6-v3-evaluation.json). At 0.80 the live model still accepts 37% of unsupported-species photos (62% at the old 0.65); the result screen states this limit.

## Part 7 — Add accounts and controlled access

Status: Completed locally (loopback authentication; HTTPS and deployment hardening are Part 12). Supports objectives: 4–6. Depends on: Part 6.

- [x] Implement contributor, reviewer, and administrator authentication and permissions.
- [x] Enforce authorization on the server for protected actions.
- [x] Support session handling, logout, and the chosen account recovery workflow (administrator-issued one-time reset codes; local CLI fallback for administrators; password change revokes other sessions).
- [x] Test ownership boundaries and unauthorized review/admin access.

Done when: contributors can manage their permitted records and only authorized reviewers/admins can moderate them.

Evidence: [Part 7 access](docs/part-7-access.md), [HTTP access smoke](docs/part-7-access-smoke.json) (57 checks), [browser smoke](docs/part-7-access-browser-smoke.json) (12 checks). Contributor correction/withdrawal of pending reports remains a Part 8 item.

## Part 8 — Save geotagged sightings

Status: Completed locally. Objective: 4. Depends on: Part 7.

- [x] Define the sighting schema and API validation.
- [x] Implement GPS permission and manual-coordinate fallback; device permission behavior needs browser validation.
- [x] Add manual map-pin selection (tap/drag pin synced with coordinate fields; saved as `map_pin`).
- [x] Store GeoJSON Point coordinates in longitude/latitude order with a geospatial index.
- [x] Save photo reference, species suggestion, confidence, model version, observation time, submission time, owner, and pending status (server-bound identification snapshot; shown on the report and PDF).
- [x] Validate coordinate ranges and record location accuracy when available.
- [x] Add explicit submission confirmation, image storage, and retry/duplicate handling.
- [x] Allow contributors to view and correct or withdraw their pending reports (owner-only, before any review; corrections keep an edit history; withdrawal deletes photo/location/content immediately and leaves a tombstone).
- [x] Define image retention and public coordinate visibility.

Done when: an explicitly submitted report survives reload, has correct location/time data, and is accessible only under the intended permissions.

Evidence: [Part 8 sightings](docs/part-8-sightings.md) (including the retention table and public-coordinate rules), [HTTP smoke](docs/part-8-sightings-smoke.json) (39 checks), [browser smoke](docs/part-8-sightings-browser-smoke.json) (9 checks); earlier details in [sighting submission](docs/sighting-submission.md).

## Part 9 — Verify sightings and connect the species catalog

Status: Completed locally. Supports objectives: 4–5. Depends on: Part 8.

- [x] Build a reviewer queue with photo, prediction, location, and observation details.
- [x] Support approve, reject, and request-correction actions with reasons and audit history.
- [x] Preserve the original model prediction separately from reviewer-confirmed species.
- [x] Provide catalog browsing with references, review status, and active-model support indicators.
- [x] Respect the existing catalog import review requirements before a full database import. Part 9 imported nothing; the owner confirmed the existing 15,938-record import was approved and asked to approve its records, recorded as owner attestation in batch `owner-catalog-approval-20261026T171926Z` (revertible; not independent taxonomic review; ecological status and AI support unchanged). See [catalog owner approval](docs/catalog-owner-approval.json).
- [x] Replace relevant static dashboard counts with live API values.

Done when: report verification is traceable, pending records remain distinguishable, and catalog presence is separate from AI support and verified ecological status.

Evidence: [Part 9 review and catalog](docs/part-9-review-catalog.md), [HTTP smoke](docs/part-9-review-catalog-smoke.json) (34 checks), [browser smoke](docs/part-9-review-catalog-browser-smoke.json) (12 checks).

## Part 10 — Build the occurrence map and analytics

Status: Completed locally (verified with fixtures; live data has 6 reports awaiting review). Objective: 5. Depends on: Part 9.

- [x] Add an interactive map with clustering and species/date/area filters.
- [x] Display verified occurrences by default and explicitly label any pending layer.
- [x] Show species distribution and occurrence counts over time.
- [x] Define a documented spatial aggregation method and minimum sample requirements for hotspot displays (0.1° cells; display ≥3 reports; high density ≥5; sparse warning below 20).
- [x] Distinguish report density from confirmed invasion severity or ecological spread.
- [x] Handle sparse data, empty filters, and public location generalization.
- [x] Verify map coordinates and aggregate counts against database queries.

Done when: map and chart results agree with stored records, filters work together, and analytics clearly state their meaning and limits.

Evidence: [Part 10 map and analytics](docs/part-10-map-analytics.md), [HTTP smoke vs database](docs/part-10-map-analytics-smoke.json) (23 checks), [browser smoke](docs/part-10-map-analytics-browser-smoke.json) (11 checks).

## Part 11 — Evaluate the complete system with intended users

Status: Automated evaluation complete; usability study prepared but **not yet conducted** (needs ≥10 consenting participants). Objective: 6. Depends on: Part 10.

- [x] Prepare task scenarios and a consistent usability questionnaire for environmental officers, researchers, and public users (8 tasks, consent script and SUS in English/Tagalog; in-app recorder).
- [ ] Record task completion, errors, completion time, and user feedback with participant consent. Ready to run: study workspace `geoflora_study` prepared with practice data (http://127.0.0.1:5180 via `scripts/start_study_web.ps1`), T1–T8 facilitator dry run passed, recorder tested (consent required, codes not names, SUS scored server-side, CSV export, withdrawal). **No participant sessions held yet** — needs ≥10 consenting participants with a facilitator; see the run-day checklist in the usability kit.
- [x] Measure end-to-end response times and representative concurrent usage on documented hardware/network conditions (loopback; identification p95 228 ms, 5-user p95 743 ms; dashboard worst p95 170 ms at 10 users on 2,000 reports).
- [x] Test denied GPS access, failed uploads, invalid images, inference outages, database outages, and retry recovery.
- [x] Verify access controls, input validation, mobile layouts, and essential accessibility (regression suites; axe-core 0 violations across 24 scans; no 390px overflow).
- [x] Fix material issues and rerun the affected checks (color contrast and ARIA fixes; audit and suites rerun).
- [ ] Compare results with the pre-agreed targets and disclose unmet criteria. Comparison written against the proposed targets: performance/reliability/access met on loopback; usability not measured; model quality not met. Final once the study runs and the owner confirms the targets.

Done when: there is an evidence-based usability, performance, and reliability report, with resolved blockers and documented limitations.

Evidence: [Part 11 evaluation](docs/part-11-evaluation.md), [system evaluation](docs/part-11-system-evaluation.json), [accessibility audit](docs/part-11-accessibility-audit.json), [usability kit](docs/part-11-usability-kit.md), [study recorder smoke](docs/part-11-study-recorder-smoke.json) (13 checks).

## Part 12 — Prepare deployment and research handoff

Status: Not started. Objectives: 1–6. Depends on: Part 11.

- [ ] Document installation, configuration, service startup, storage, and recovery procedures.
- [ ] Prepare production secrets handling, HTTPS, backups, health checks, and logs.
- [ ] Package the approved model, dataset metadata, evaluation results, and user/admin guides.
- [ ] Test a complete upload → identify → submit → verify → map workflow in staging.
- [ ] Prepare a concrete deployment for review before publishing or exposing the service.
- [ ] Update project documentation to reflect the implemented system and remaining limitations.

Done when: the system can be reproduced and operated from documentation, staging checks pass, and deployment has the required approval.

## Next round: adding new species (Monday, 2026-11-09)

Full runbook: [docs/ADDING-NEW-SPECIES.md](docs/ADDING-NEW-SPECIES.md). The live model knows 21 species (13 NISSAP target invasive + 8 non-target).

**Decide first (Reyca / thesis group), per species**
- [ ] Scientific name (aim for 3-6 species per round).
- [ ] Target invasive or not. A target needs a Philippine source (e.g. NISSAP 2020-2030), a **named verifier** and a date; otherwise it is added as "not a target".
- [ ] Common name(s) in the Philippines.
- [ ] Photo screening: Reyca, with the AI pre-screen flagging doubtful photos (same as Hagonoy/Ageratum).

**Candidates** (iNaturalist research-grade photos on GBIF, checked 2026-11-07; need ≥ 60 approved photos from ≥ 30 observations, 300-400 is better)

| Species | Common name | PH photos | World photos | Note |
|---|---|---|---|---|
| *Euphorbia hirta* | Tawa-tawa | 491 | 18,435 | 5 app reports already corrected to it; imported automatically once it is in the model |
| *Coccinia grandis* | Ivy gourd / tamilok | 271 | 6,448 | In the app's species registry |
| *Caladium bicolor* | Caladium | 217 | 4,081 | 1 app report corrected to it |
| *Sphagneticola trilobata* | Wedelia | 196 | 26,466 | In the catalog (IUCN 100 worst, global evidence only) |
| *Antigonon leptopus* | Coral vine / cadena de amor | 86 | 11,803 | In the catalog |
| *Tithonia diversifolia* | Mexican sunflower | 75 | 5,688 | In the catalog |
| *Mimosa diplotricha* | Giant false sensitive plant | 14 | 1,309 | Few PH photos |
| *Miconia crenata* | Koster's curse | 0* | 5,870 | *Check PH records under *Clidemia hirta* |
| *Mimosa pigra* | Giant sensitive plant | 0 | 2,968 | Few PH photos |
| *Mimosa pudica* | Makahiya | 406 | 16,258 | ⚠️ Currently an "unknown plant" in the not-sure test; replace it there if added |

**Steps** (about 1 day of machine time, mostly training)
- [ ] 1. Catalog rows → 2. download photos → 3. validate/dedupe → 4. AI pre-screen sheets → 5. **Reyca OKs the list**, import under Reyca's name.
- [ ] 6. New config `configs/expansion_v4.yaml` writing to **new folders** (current model and test set stay intact).
- [ ] 7. Split + train (≈ 2 h per model) → 8. evaluate + export → 9. species descriptions for the app.
- [ ] 10. Package + ONNX + parity check → 11. put in `apps/web/models/ensemble.json`, test (incl. Kaggle photos) → 12. push (CI checks, Vercel deploys).

**Traps**: (A) all ensemble members must know the same species, so a 25-class model goes in alone or with a second 25-class model; (B) point cloud training at the new config and re-upload photos with `cloud_data.py upload`; (C) keep test sets fixed; (D) choose the "sure" threshold on validation only; (E) Atlas free tier is 512 MB (≈ 20 KB per photo); (F) labels are Reyca-screened iNaturalist photos, not botanist-verified.

## Turnover state (2026-11-07)

- **Live:** https://geoflora-ph.vercel.app (Vercel, auto-deploys from GitHub `main`, root `apps/web`). Database: MongoDB Atlas M0 (Singapore).
- **Model:** ensemble of `geoflora-mnv2-21cls-v1` + `v3` (ONNX, inside Next.js), 3-class `v2` confirm for Hagonoy/Lantana/water hyacinth (floor 0.60), "sure" threshold 0.69. Old test set: 84.2% top-1, 98.4% when sure; via the app API 85.8% / 97.4%.
- **Flow:** photo → AI result (target / not a target / not sure) → report saved as `recorded` → map. Admin may Approve / Correct / Reject.
- **Auto-training in the cloud:** GitHub Actions `training.yml` every 30 min imports approved/corrected photos (Atlas GridFS), retrains after 20 new photos, offers the model under Review & training → "Approve new model".
- **CI/CD:** `ci.yml` (typecheck, build, model check, ml-lab tests). CD = Vercel Git deploy; CI-gated deploy job ready once `VERCEL_TOKEN`/`VERCEL_ORG_ID`/`VERCEL_PROJECT_ID` secrets are added.
- **Protection:** rate limits per action (identify, suggest, report, PDF, survey, auth) and 120 requests/min per IP (40 writes).
- **Documents:** handover (`docs/HANDOVER-GeoFlora-2026-11-07.md`), User Manual, System Documentation and Invoice (REYCA-DEV style, PDFs in Downloads).
- [ ] Optional: add Vercel secrets and switch to CI-gated deploys.
- [ ] Part 11 participant study (Feedback survey is live) and thesis-side evaluation remain with the client.

## Working agreement for each part

1. Read the current implementation and applicable local instructions.
2. State the concrete changes for the active part.
3. Implement the authorized changes; ask only for missing decisions that block progress.
4. Run relevant checks and demonstrate the result.
5. Mark completed items, record evidence and limitations, and identify the next part.

## Progress log

| Date (Asia/Manila) | Part | Result | Verification / next action |
|---|---|---|---|
| 2026-10-23 | Planning | Created this implementation plan; implementation parts remain unchecked | Start Part 1: fresh baseline and dataset consistency audit |
| 2026-10-23 | Part 1 | Baseline audit complete: 48 tests passed, builds passed, local HTTP and MongoDB verified | See docs/part-1-baseline.md; next: human dataset review. Acceptance targets remain proposed. |
| 2026-10-23 | Part 2 | Prepared review queue/criteria, fixed UI export and validation, verified HTTP export and 27 ML tests | In progress: qualified visual review and source geography verification required; no labels changed. |
| 2026-10-23 | Part 2 | Recorded 243 approvals from explicit owner confirmation and refreshed approved export/audit | See docs/owner-approval-batch.json. Independent botanical and geographic verification were not performed; historical splits remain unsuitable. |
| 2026-10-23 | V1/V2 revalidation | Owner approvals present; paths and checksums checked; near-duplicate leakage remains (v1: 1 group, v2: 39 groups) | See docs/v1-v2-validation.md. Preserve historical versions; neither is training-ready. |
| 2026-10-23 | Experimental training | Owner requested training; prepared v3 with 166/38/39 images and zero detected cross-split groups | PH provenance remains unverified. Training dependency installation in progress; do not claim a trained model yet. See docs/training-baseline.md. |
| 2026-10-23 | Experimental training complete | MobileNetV2 v3 candidate: 87.18% top-1 accuracy, 82.74% macro F1; saved/reloaded model and real inference smoke passed; 27 ML tests passed | Water-hyacinth recall 50%; candidate not activated. See docs/training-v3-results.md. |
| 2026-10-23 | Supplemental collection | Completed bounded all-species pass and corrected-photo-license water-hyacinth pass; zero new images; 27 tests passed | Dataset remains 243 approved, zero pending. See docs/supplemental-collection-results.md. Need independent local photos or another eligible corpus before useful retraining. |
| 2026-10-23 | Nationwide scope and species shortlist | Researched ten historically documented PH candidate taxa; completed read-only PH/global licensed-photo observation probes for all ten | See docs/nationwide-species-shortlist.md. Prioritize Leucaena, Mikania and Coccinia feasibility; ecological/data review required before activation. |
| 2026-10-23 | Up to 100 species | Preserved GRIIS PH source; staged 352 plant-species source rows and a 100-entry provisional research queue | Source flags invasive in 13 plant rows; selected queue has 12 source-flagged and 88 requiring status verification. No class activation. See docs/species-100-expansion-plan.md. |
| 2026-10-23 | 100-species initial verification | All 100 screened against CDFP; 92 image queries resolved, eight names unresolved; 48 had PH qualifying observations and 44 had none | Eleven ecological holds (seven native conflicts, four uncertain-origin). See docs/species-100-verification-report.md and docs/species_100_verification_ledger.csv. No new class approval. |
| 2026-10-23 | Mikania feasibility collection | Collected 50 pending PH-source images (20 iNaturalist, 30 GBIF) in isolated staging; integrity/rights metadata checks passed; 22 connected observation/similarity components | Review gallery and queue ready. See docs/mikania-staging-review.md. No label approval, class activation or retraining; original 243-image corpus unchanged. |
| 2026-10-23 | Batch-first collection authorized | Started resumable background collection across all 100 research candidates, target up to ten images/species and 1 GiB total staging | Running, not complete. Review/cleanup follows the whole pass. See docs/species-100-batch-collection.md and docs/species-100-collection-progress.json. |
| 2026-10-23 | Plan aligned to batch-first workflow | Added current-step summary and Parts 2A collection, 2B batch audit/cleanup and 2C review/class selection; corrected stale corpus/model statuses | Worker running at verification; checkpoint counts are historical. Expanded training follows approved batch review. |

| 2026-10-23 | Parts 2A/2B execution | Collection continues; snapshot audit implemented and run across batch + original + Mikania; finalizer running to audit the finished pass and update checklists | In progress, not complete. See docs/part-2ab-workflow.md and docs/part-2ab-job-status.json. Audit corruption/conflict/non-mutation fixture passed. |

| 2026-10-23 | Network recovery | Confirmed both provider APIs reachable; resumed collector for 16 source-error entries from the saved 545-record checkpoint and restarted finalizer | Old pass-finished marker cleared before restart. New live log: storage/datasets/staging/species_100_ph/logs/stderr-network-resume.log. Collection/audit remain in progress. |

| 2026-10-23 | Parts 2A/2B | Full 100-entry pass reconciled: 674 records across 80 species folders; integrity/provenance, grouping and routing reports generated | See docs/part-2ab-results.md. Labels and unresolved ecological/geographic evidence require Part 2C review. |

| 2026-10-23 | Part 2C started | Prepared 674 decision-template rows, 80 species galleries and a 100-entry class-selection sheet; staging review importer/export tested for holds and idempotency | See docs/part-2c-review.md. Forty-six records prioritized for review; no new approvals or class activation. |

| 2026-10-23 | Batch approval UI connected | Started http://127.0.0.1:8766 with 674 pending records across 80 species; linked from original UI on 8765 | Live listing/image/link checks passed; temporary HTTP fixture verified saved decisions and ecological hold isolation. No real labels approved by testing. |

| 2026-10-23 | Batch labels approved by owner | Recorded 674 approved labels from explicit owner confirmation after viewing; UI verified 674 approved, zero pending | No new location/domain verification inferred. All 674 labels remain held from field-training export. See docs/batch-owner-label-approval.json; Part 2C class-selection/provenance work remains. |

| 2026-10-23 | Part 2C class selection | Owner confirmed PH location; recorded country attestation on 674 batch labels. Assistant visually screened 20 Mikania/Pistia images, retained 14, and selected five experimental classes (211 unique candidate images including 197 legacy photo-source candidates) | See docs/pilot-five-class-selection.md. Seven images per new class is too small for reliable validation; no model activation/final split. 660 batch labels remain held. |

| 2026-10-23 | Local sightings foundation | Added Report a sighting UI + POST API + MongoDB photo/GeoJSON persistence, consent, validation and idempotent retries | Production build/typecheck and real isolated HTTP/MongoDB integration checks passed. Live app on 5173. Accounts, map pin, listing/review and prediction attachment remain pending. |

| 2026-10-23 | Local AI activation | Owner explicitly requested activation of the trained three-class candidate. Verified model/mapping checksums, installed active artifacts, restarted inference and confirmed ready=true through the web proxy | Three real photo uploads returned HTTP 200 (Hagonoy/Lantana identified; Water Hyacinth uncertain). See docs/active-local-model.md. Experimental activation; previous quality limitations remain. |
| 2026-10-23 | Species definitions | Added descriptions, identifying features, invasive impacts and botanical reference links for all three active model classes in identified results | Typecheck and production build passed. Uncertain results retain their unassigned status. |
| 2026-10-25 | Report-to-map flow | Connected saved reports to the sightings map with selectable pending markers, place name, observation time and server creation time; receipt links to its saved map record | Typecheck/build and isolated HTTP/MongoDB checks passed, including listing privacy, original creation time on retries and location persistence. OpenStreetMap tiles require internet; browser GPS/device validation remains. |
| 2026-10-25 | Photo map markers | Replaced circle markers with actual saved-report photo thumbnails and added the photo to report details | Typecheck/build and isolated photo endpoint checks passed: full JPEG, thumbnail dimensions, missing/invalid IDs and origin restrictions. |
| 2026-10-25 | Six-species training | Froze experimental v4 (221 images); trained fresh MobileNetV2 head for the original three plus Caladium, Mikania and Pistia, selected by validation loss | 78.95% accuracy, 54.39% macro F1; Mikania/Pistia recall 0% on tiny test samples. Candidate saved, not activated. See docs/training-v4-six-results.md and docs/expanded-training-status.json. |
| 2026-10-25 | User identification feedback | Added description/name-suggestion handoff to reports, optional training consent and a local pending-candidate listing. Uncertain results remain unassigned; user suggestions remain unverified | Typecheck/build and real HTTP/MongoDB checks passed for persistence, opt-in/opt-out, server-controlled pending status, feedback validation and retry conflicts. Review/export/retraining remain separate future steps. |
| 2026-10-25 | Navigation refresh | Added a minimalist glass/clay shell, modern outline navigation icons, mobile drawer and quick-action dock | Production build/typecheck and real Chrome navigation/mobile interaction checks passed. See docs/navigation-refresh.md. |
| 2026-10-25 | Content UI refresh | Redesigned identification cards, upload/preview, model-score display, feedback and empty/loading/uncertain states; aligned shared content cards and form typography | Build/typecheck and real browser photo-identification/handoff checks passed. Identification and photo-filled report fit 390px mobile widths. See docs/content-ui-refresh.md. |
| 2026-10-26 | Admin/User and automatic training | Added real local accounts/sessions, API role and owner checks, Admin label review and a threshold-based background training/evaluation queue | Build, 27 ML tests, report integration, browser role flows and an actual isolated automatic-training job passed. Default batch floor: 20 newly approved photos. Numerical quality failures preserve the active model; model-generated suggestions are not verified ground truth. See docs/roles-and-automation.md. |
| 2026-10-26 | Revised identification/report workflow | Added dedicated cited result screen, GPS/time-filled report confirmation, two-action receipt, persistent report URLs and PDF export. Unknown descriptions go to Admin review, including new cited species; reviewed photos can match immediately | HTTP/PDF and Chrome workflow checks passed, including owner access and mobile. Automatic training checks now queue per consented approval; new classes wait for independent groups, cumulative contributions persist, and candidate quality gates preserve the live classifier. See docs/identification-report-flow.md. |
| 2026-10-26 | Part 2 finalization | Closed the selection as five experimental classes (211 images): recorded decisions/holds, retained the full 100-species archive, and excluded Caladium bicolor because invasive status was not established for this project | See docs/part-2-finalization.md and docs/part-2-finalization.json. Owner attestation/visual screens are preserved as evidence; they are not independent botanical or per-record geographic certification. |
| 2026-10-26 | Part 3 v5 freeze | Created curated/v5_part2_final_five_classes with fixed manifest, class map, review snapshot, decision ledger, checksums and grouped split audit | 211 images decode and have rights metadata; zero checksum/observation/near-duplicate groups cross splits. Mikania and Pistia have tiny partitions, so v5 is not a model-promotion approval. |
| 2026-10-27 | Part 4 v5 training | Finished shared train/inference preprocessing and train-only augmentation (tests fixed, 30 ML tests pass); trained mobilenetv2_v5_five_seed42 on frozen v5 with validation-selected epoch 13; requested fine-tune did not improve validation loss and was not applied | 75.00% accuracy, 49.47% macro F1; Mikania/Pistia recall 0% on 1–2 test photos. Isolated verifier passed (checksums, split isolation, 5 FastAPI requests, active model unchanged). Not activated. See docs/training-v5-five-results.md. Next: Part 5. |
| 2026-10-27 | Part 5 v5 evaluation | Validation-selected threshold 0.90; test coverage 47.22% at 88.24% selective accuracy; 76-species unsupported set falsely accepted 35.37% (68.71% at 0.65); synthetic non-plant proxies 1/18 accepted; blur tolerated, dark/bright lighting degrades; FastAPI inference p95 116 ms locally | Not approved; active v3 unchanged (checksum verified). See docs/model-card-v5.md and docs/part-5-v5-evaluation.json. Next: choose whether Part 6 proceeds with v3 or waits for new field data; run the same unsupported-input check on v3. |
| 2026-10-27 | Part 6 identification | v3 unsupported-input evaluation (151 photos/78 species: 62% accepted at 0.65, 37% at validation-selected 0.80); predictor reads version/threshold from active_model.json; camera capture, uncertainty explanation, model version display and distinct timeout/outage/malformed-response errors added | 31 ML tests, typecheck/build, isolated HTTP smoke (3 real predictions, 13 failure cases, upload-to-result p95 255 ms) and 9 mobile browser checks passed; live services restarted with active model unchanged. Physical-phone camera check pending. See docs/part-6-identification.md. |
| 2026-10-27 | Part 7 access | Added reviewer role, Manage accounts (roles, disable/enable, one-time reset codes), reset-code sign-in, password change with session revocation, CLI admin recovery; replaced inline admin checks with server-side moderator/admin helpers | 57 isolated HTTP checks, 12 browser checks, sightings regression, typecheck/build passed; live web restarted (1 existing admin, no migration). Next: remaining Part 8 items. |
| 2026-10-27 | Part 8 sightings | Added map-pin location picker, identification record on report/PDF, owner correction with edit history and withdrawal that deletes photo/location/content (tombstone kept); withdrawn reports excluded from map, review and training; documented retention and public-coordinate rules | 39 isolated HTTP checks, 9 mobile browser checks, access/sightings/identification regressions, typecheck/build passed; live web restarted (6 existing reports, no migration). smoke_report_flow.py still asserts the old v4 base and needs updating. Next: Part 9. |
| 2026-10-27 | Part 9 review and catalog | Added sighting verification statuses and queue (verify/reject/request correction with reasons, audit history, correction resubmission), confirmed species kept separate from the original prediction, read-only species catalog browser (GBIF records, unverified source listings, live-model and verified-sighting indicators) and live Overview counts | 34 isolated HTTP checks, 12 browser checks, Part 8/access/sightings/identification regressions, typecheck/build passed; catalog requests took 14–29 ms cached (179 ms first) on a full read-only copy; live web restarted. Open: owner decision on the pre-existing unapproved full catalog import. Next: Part 10. |
| 2026-10-27 | Catalog approval | Owner confirmed the existing full GBIF import was approved and asked to approve its records; recorded batch owner-catalog-approval-20261026T171926Z and set 15,938 catalog records to approved (basis owner_attestation, previous status kept, revertible); catalog/Overview show the basis | Tested approve/rerun/revert on a full copy first; Part 9 HTTP (34) and browser (12) checks passed after the change; ecological status and AI support unchanged; live web restarted. Next: Part 10. |
| 2026-10-27 | Catalog staging approval | Owner asked to approve all records; approved the 18,718 species_catalog_staging source rows by owner attestation (batch owner-staging-approval-20261026T172931Z, review_events entry, revertible); source ecological statuses stay unverified | Tested approve/rerun/revert on a full copy first. 6 live sightings left in the review queue: verification needs a confirmed species per report. Next: Part 10. |
| 2026-10-27 | Part 10 map and analytics | Added Occurrence map (screen-space clustering, species/date/area filters, verified default with labeled unverified layer, optional generalized density grid) and analytics (species bars, monthly columns, high-density cells, data table) on a documented 0.1° grid with ≥3-report suppression, ≥5 hotspot and <20 sparse rules | 23 HTTP checks recomputed against stored documents, 11 browser checks, Part 9/8/access regressions, typecheck/build passed; live web restarted. Next: Part 11 (needs participants and confirmed targets). |
| 2026-10-27 | Part 11 evaluation | Automated system evaluation on a 2,000-report representative dataset (identification p95 228 ms; 5-user p95 743 ms; dashboard worst p95 170 ms at 10 users; 100/100 reliability; failed-upload, duplicate-retry, invalid-image, inference and database outage recovery all passed); axe-core audit fixed contrast/ARIA issues to 0 violations across 24 scans; added usability kit and admin Usability study recorder | Study recorder smoke 13 checks and all regression suites passed; live web restarted. Open: run sessions with ≥10 participants; owner to confirm Part 1 targets; model quality unmet. |
| 2026-10-27 | Part 11 study setup | Prepared isolated study workspace geoflora_study (catalog copy, 3 practice sightings to review, 12 verified practice sightings), T2/T3 photo (live model 0.993), answer key, start script on port 5180, run-day checklist | Facilitator dry run of T1–T8 on a pilot copy: 10 checks passed (pilot DB removed). No participant data recorded; sessions need real participants. |
| 2026-10-27 | Reports list | Owner could not find their reports: the Part 10 map defaults to verified and all 6 live reports are pending. Added My reports / All reports page (every status, per-status counts, filter, search, opens the report) in the sidebar and mobile dock; map empty state points to it | Browser check 6/6 (counts, filter, search, open, axe 0 violations, 390px); live web and study web restarted. |
| 2026-10-27 | Live sighting review | Owner asked to verify all 6 live reports. After a visual check: verified Chromolaena odorata and Lantana camara as labeled; one Caladium bicolor report verified (species only; training use not approved, since Caladium is excluded from training classes) and its two duplicate submissions of the same photo rejected; a report labeled Lantana camara verified as Euphorbia hirta (naturalized, Co's Digital Flora) at the owner's choice | Recorded as owner attestation with assistant visual check in each reviewHistory entry; original labels and the absent model predictions unchanged. Live: 4 verified, 2 rejected, 0 awaiting. |
| 2026-10-31 | AI review and auto-promotion | Owner asked to stop reviewing by hand and to let models trained on uploads go live automatically. Added a Claude (claude-opus-5-5) reviewer: auto-verify only when it and the image classifier agree on a supported species (≥0.85), auto-reject non-plant/unusable/duplicate photos, everything else stays with a person with the recommendation. Fixed v5 test benchmark held out of automatic training; candidates that pass quality targets and match or beat the live model are installed with backup and loaded via the new inference /reload | 14 policy checks, 15 isolated end-to-end checks (mock Messages API), worker freeze check, 33 ML tests, typecheck/build passed; live inference restarted. Off until ANTHROPIC_API_KEY is set. Auto candidates currently include Mikania/Pistia, which are not servable, so none will be promoted until the owner decides. See docs/ai-review-and-auto-promotion.md. |
| 2026-10-31 | Single report path | Owner asked to drop the separate Report a sighting page because Identify already creates the report. Removed it from the sidebar; New sighting, the sidebar card and Overview now open Identify (Overview card points to Reports); the report form is step 3 of Identify only and has no separate photo upload; Identify stays highlighted during that step | Typecheck/build passed; smoke_part8_ui.mjs updated to report through Identify (also fixed its stale landing/setup steps) and passed 9/9; navigation check 4/4. |
| 2026-10-31 | OpenRouter reviewer, admin and Identify tidy-up | Owner switched the AI reviewer to OpenRouter free models (key in apps/web/.env.local): Nemotron 3.5 Super VL with Gemma 4 fallbacks, strict JSON schema; Claude stays as the alternative. Admins no longer see Account settings. Identify: removed the redundant status card so the photo stage and side column end together with no empty space | Typecheck/build passed; live OpenRouter check on an isolated DB auto-verified an agreeing Lantana report (0.98) and auto-rejected a non-plant image; layout measured at 1521x732 (both columns end at 742 px, actions above the fold). Free models may log prompts/images. See docs/ai-review-and-auto-promotion.md. |
| 2026-10-31 | Plant suggestion and look-alikes | Owner wants users told what any plant is. When the classifier is uncertain, Identify now shows an unverified AI suggestion (OpenRouter vision model) with GeoFlora catalog checks (tracked, recorded in PH, introduced listings), "Use this name", and an AI-drafted field description in Describe your plant. Shared vision module src/lib/ai-vision.ts. Started non-invasive look-alike staging (scripts/collect_lookalike_staging.py nymphaea) | Owner water lily photo: classifier uncertain (70.9% water hyacinth); suggestion Water lily, Nymphaea (genus), not tracked, recorded in PH; description drafted and submit enabled. Look-alike run: 15 licensed records, all herbarium sheets, unsuitable for training; no CC0/CC BY iNaturalist field photos. Typecheck/build passed. |
| 2026-10-31 | Look-alike classes (water lily) | Owner approved all three routes: CC BY-NC field photos for look-alikes only, own photos (scripts/import_field_photos.py --attest), and contributor sightings verified as not invasive. Species carry a role (invasive/lookalike); AI screen of staging photos; worker trains approved look-alikes; promoted models install their served-species list; Identify shows "not invasive" matches | 42 iNaturalist photos collected; AI screen approved 29, rejected 6 herbarium sheets, 22 pending (free-tier daily limit). One training pass: candidate 60.5% accuracy / 35.3% macro F1, failed gates, live v3 kept; water lily recall 80%, Mikania/Pistia 0%, water hyacinth often called Hagonoy. 35 ML tests, typecheck passed; v5 candidate now loads and is correctly declined on the benchmark. |
| 2026-10-31 | Email verification | New accounts (contributors and first admin) must enter a 6-digit emailed code before signing in; resend needs the password; verification and reset codes are separate; account not kept if mail fails; legacy accounts treated as verified; admins can Mark verified; SMTP host/port configurable | Local test mail server: 15 API checks, mail-down rollback, legacy login and browser flow passed; typecheck/build passed. Live Gmail rejected the stored app password (535 BadCredentials), so real delivery needs a new app password. See docs/part-7-access.md. |
| 2026-10-31 | Single settings file | apps/web/.env.local now holds every credential and setting (database, ML service, SMTP, OpenRouter/Anthropic, AI review, training, collection contact, GBIF, optional offline map) in labelled sections; the Python side reads the same file through services/ml/src/geoflora_ml/env.py (environment values still win); apps/web/.env.example is the secret-free template | Python loader check, 35 ML tests and typecheck passed; template contains no secrets; live web 200. |
| 2026-10-31 | AI reviewer stalls fixed; email sender name | Cause: OpenRouter free-models-per-day limit (50) used up by photo screening, plus reviews left running when cut short. Added a shared pause until the provider reset, paused reports that keep their attempts, re-pickup of stale reviews, a server-start background sweeper (instrumentation.ts), pause notice in the admin panel and suggestions, and a screening cap. Emails are sent as "geoflora" (GEOFLORA_SMTP_FROM_NAME) | Real-limit test: pause recorded until 08:00 PHT, no further API calls; sweeper reviewed a seeded report with no requests in ~65 s; typecheck/build passed. Restart the dev server to start the sweeper. |
| 2026-10-31 | Expanded invasive data | 1,463 usable PH field photos collected for 10 monitored species plus water lily (owner decisions: CC BY-NC allowed, research-grade labels, four introduced species added with status under review); visual benchmark near-duplicate check; training memory reduced | 11-class candidate: 73.5% accuracy / 73.5% macro F1 (was 60.5% / 35.3%); gates (85%) not met, live v3 kept. Weakest: Mikania 36%, Coccinia 57%. Next: fine-tune the backbone. |
| 2026-11-01 | Practical dataset readiness | Calculated group deficits to reproduce v3 partition group volume while protecting all historical tests; made one bounded incremental licensed collection request per original class (2 Lantana images found, both excluded as a single historical-test observation); generated 47-taxon ecological queue and 1,760-image read-only review gallery/CSV with exact, observation and perceptual holdout warnings | New training approvals: 0; fresh blind-test groups: 0; no training or model changes. Water Hyacinth collection yielded no new images. See [practical readiness report](docs/mobilenetv2-practical-readiness-2026-11-01.md). |
| 2026-11-01 | 11-class candidate reconciliation | Confirmed the 1,625-row frozen dataset, class mapping, evaluation and Keras artifact remain present; reported train/validation/test images and observation groups per class. Ran one bounded fine-tune from the existing checkpoint using validation-only minimum cross-entropy selection; all three epochs had worse loss, so baseline weights were restored. Corrected the reusable fine-tune path to unfreeze the nested MobileNetV2 parent and freeze BatchNormalization. | Candidate remains inactive; test score 73.52% / macro F1 73.53% on a previously inspected 253-image partition, not blind. Unknown → pending report → admin verification → consented queued training job smoke passed in a disposable DB (worker deliberately not run). Active v3/model mapping hashes unchanged; 37 ML tests passed. See [reconciliation report](docs/11-class-candidate-reconciliation-2026-11-01.md). |
| 2026-11-01 | Weak-class data and delivery verification | Ran the bounded existing collector for Mikania, Coccinia and Broussonetia. It found 27 newly collected rights-allowlisted Coccinia images in 17 observations; no new eligible Mikania/Broussonetia records. Cross-check against the frozen candidate found 58 unrepresented eligible staging photos in 40 observation groups (31 Mikania, 27 Coccinia); all remain pending human review. Restored license-filtered raw records to review queues without making them trainable. | No training run or promotion. Identification smoke passed; Parts 8/9/10 HTTP smokes passed 39/34/23 checks; unknown-plant review flow passed; active v3 and mapping hashes unchanged. See [weak-class and delivery results](docs/weak-class-expansion-results-2026-11-01.md), [audit](docs/weak-class-expansion-audit-2026-11-01.json), and [manual review queue](docs/weak-class-manual-review-queue-2026-11-01.csv). |
| 2026-11-01 | Weak-class review package and license guard | Built loopback review UI for 58 source records / 40 groups; checksum and visual-feature triage passed. pHash found 19 Mikania images matching 12 frozen groups (including historical test sources) plus one cross-provider source-photo alias. Added strict training license validation and retained filtered raw records as pending. | Human image decisions and client CC BY-NC use confirmation remain pending; 38 images / 27 groups are eligible for review after duplicate exclusion, not yet training-ready. No training or activation. See [visual review package](docs/weak-class-visual-review-2026-11-01.md). |
| 2026-11-01 | Weak-class visual review pre-screen | Generated 58-image/40-observation gallery with provenance, rights, pixel-quality and duplicate cues; excluded 19 frozen-match files and one cross-source alias from CNN triage, then ran top-three weak-candidate predictions on 38 remaining images (no historical test re-inference). | Gallery at http://127.0.0.1:8768/; owner choices save as non-training visual review. 4 licensing tests passed; pending-export guard confirms 58 candidates exported 0 and no ineligible-license exports. CC BY-NC remains held until client use is confirmed; no group approvals, dataset freeze, training or activation. See docs/weak-class-visual-review-2026-11-01.md and docs/weak-class-cnn-prescreen-2026-11-01.json. |
| 2026-11-01 | Weak-class review finalization and bounded fine-tune | Reconciled all 40 observation decisions (39 approve, 1 reject, 0 uncertain, 0 undecided; 57 approved files). Final immutable v3 snapshot added 34 CC BY/CC0 photos from 25 groups (Coccinia 24/15; Mikania 10/10); excluded frozen matches, one provider alias, three low-resolution files and one severe exposure image. | Two fixed-setting fine-tune passes covered successive immutable snapshots because the final Coccinia decision arrived during the first run. Neither beat validation loss; source weights restored. Historical 253-image test stayed outside train/validation and matched prior metrics (73.52% accuracy, 73.53% macro F1); it is not a fresh blind test. Active 3-class model unchanged. Identification and unknown-report smokes passed. See docs/weak-class-training-report-2026-11-01.md and the v3 dataset/candidate artifacts. |
| 2026-11-01 | Frozen-backbone head experiment | Earlier runs jointly trained the head and last 20 backbone layers but validation rejected those weights. Ran a distinct fresh-head-only experiment on the final v3 development split; backbone frozen throughout, class-balanced, conservative augmentation, validation early stopping. Historical test images were not opened. | Selected epoch 3 by validation loss (1.1944 vs baseline 1.2052); validation accuracy fell 64.8% to 63.6% and macro F1 62.75% to 61.46%. Mikania/Coccinia/Broussonetia F1 changed 42.11->46.81 / 55.56->61.02 / 16.67->25.00 validation-only. Mixed evidence; no backbone fine-tuning or promotion. Active v3 unchanged. See docs/weak-class-head-training-results-2026-11-01.md. |
| 2026-11-01 | Weak-class error gallery and bounded data follow-up | Recomputed the saved 11-class head candidate on its 250-image development validation split only and prepared a grouped image gallery with per-image source, observation, score, quality and review cues. Scanned existing weak-class staging plus 15 bounded iNaturalist pages per class using strict CC0/CC BY/CC BY-SA rights and exact/observation dedup; collected no new images. | Validation: 91 errors, including 11 Mikania↔Chromolaena, 21 Coccinia-involved, and 6 Broussonetia-involved cases. Remaining eligible Coccinia review item: 2 images / 1 group pending independent botanical verification; second Coccinia group explicitly not training-eligible. Mikania and Broussonetia: zero new independent strict-rights groups. No fresh balanced blind set available; historical test untouched. Active v3/mapping hashes unchanged; no training. Galleries: http://127.0.0.1:8770/ and /review. See [error and collection report](docs/weak-class-error-analysis-and-collection-2026-11-01.md). |
| 2026-11-01 | Client demo readiness and holdout guard | Ran a complete isolated Next.js → FastAPI/Keras → uncertain report → admin look-alike verification → map/analytics workflow; confirmed active v3, mapping and 0.80 threshold unchanged. Found historical v3/11-class test overlap in the auto-training base and extended worker exclusions to all curated test hashes and normalized observation groups, plus perceptual matches against historical tests for baseline and consented additions. | E2E passed; pending non-consented report created no job; 58 weak-review candidate hashes exported 0; holdout audit now reports zero remaining exact/group overlap and only 24 v5 train/validation rows remain before additions. Python compile, boundary audit and pending-export guard passed. No training, model/data changes, or promotion. 95%/independent field accuracy remain unverified; physical phone-camera and Part 12 production readiness remain outstanding. See [demo readiness](docs/client-demo-readiness-2026-11-01.md), [E2E evidence](docs/client-demo-e2e-smoke-2026-11-01.json), and [holdout audit](docs/training-holdout-boundary-audit-2026-11-01.json). |
| 2026-11-01 | Model promotion safety and handover | Disabled automatic promotion. Evaluation-gated worker jobs remain experimental until an admin approves a candidate in Review & training with a rationale; worker revalidates evaluation gates and artifact hashes before activation. Staging training export now requires an explicit human reviewer/rationale, eligible license, and historical-test exact/group/pHash checks. Added snapshot rollback with version/evaluation/approval records and outgoing-version preservation; wrote local setup and client handover instructions. | Focused promotion/licensing tests 15/15; Python compile; web typecheck and production build; staging export guard (58 pending candidates exported 0; unreviewed/rejected 0; ineligible-license 0; current staging eligible count 0); historical-test audit has zero remaining overlap. Active v3 hashes unchanged; no training or promotion. Local demo has no critical software blocker; Part 11 participant study and Part 12 production readiness remain incomplete. See [handover](docs/client-handover-2026-11-01.md). |
| 2026-11-01 | Hybrid references and ecological learning gates | Added MobileNetV2 backbone embeddings, consented human-reviewed reference indexing/search and admin invalidation; separated botanical labels from target-invasive status, filtered default occurrence analytics to confirmed target-invasive reports, and gated progressive training on consent, human detailed review and 10 independent groups/class. Source-flagged staging metadata remains ineligible for automatic invasive training. | Typecheck/build and 53 ML tests passed; actual active v3 embedding returned a normalized 1,280-vector; unknown-report smoke passed with no training job and admin invalidation; map analytics 25/25 passed including non-target exclusion. Active v3, mapping and 0.80 threshold unchanged. No active reference records or eligible Euphorbia hirta reports; Tawa similarity calibration/test remains blocked for lack of reviewed references. See [hybrid recognition status](docs/hybrid-progressive-recognition-2026-11-01.md). |

| 2026-11-01 | Philippine species catalog export and staging inventory | Reused the existing GBIF/GRIIS/regional flora/MalNAF snapshots; generated searchable provenance-preserving CSV/JSON and a read-only readiness report for 2,542 staged photo records across 86 taxa. No new photos, model training, or promotion. | 16,042 taxon candidates (15,500 normalized binomials), 451 name-key collision groups, 6,897 processed GBIF unresolved rows; 18 species-catalog tests and 7 licensing/split tests passed. See docs/philippine-species-catalog-automation-2026-11-01.md. |

| 2026-11-01 | MobileNetV2 up-to-50 dataset readiness | Prepared a source-backed 50-slot research roster and folder export with strict historical-test hash/group/pHash exclusions. Existing three-class mapping preserved; 47 additions remain pending ecology/label review; safe base splits are insufficient (Pontederia has no validation) and no fresh test exists. Training was correctly not started. | 48 safe baseline train + 10 validation images, 0 test; 0/47 new classes pass gates. Active v3 artifact/mapping checksums match. See docs/mobilenetv2-up-to-50-readiness-2026-11-01.md and storage/datasets/experiments/geoflora_mobilenetv2_up_to_50_20261101/. |
| 2026-11-05 | GeoFlora-ML-Lab integration | Moved the standalone ML lab into ml-lab/ (9,150 photos with provenance and named review decisions, trained runs, exported bundles, reports). Installed the developer-selected 21-class lab model geoflora-mnv2-21cls-v1 (13 NISSAP-verified target invasive species plus 8 non-target classes) with a backup, through new scripts ml-lab/scripts/package_for_geoflora.py and scripts/install_lab_model.py. Generated species information for all 21 classes. Identify now lists the live model's species; the result shows target or non-target status, look-alikes and other possibilities. | Lab test accuracy 82.5% (95% CI 79.9-84.9%, 931 photos); 83.1% re-scored through services/ml PlantPredictor. Automatic promotion gates were not met (Chromolaena recall 65%); the override, approver and rationale are recorded in active_model.json. A gumamela test photo was falsely suggested as African tulip tree. 53 ML tests and the web typecheck passed; browser check used an isolated app and a disposable database. Rollback: storage/models/previous/20261104T172339Z. See docs/ml-lab-integration-2026-11-05.md. |
| 2026-11-05 | Simple identify flow | App now works like the ML lab: AI result (target / not a target / not sure), reports saved as `recorded` immediately, optional admin Approve / Correct / Reject; corrected photos become training data. Redesigned PDF, descriptions on report and map. | See docs/simple-identify-flow-2026-11-05.md. |
| 2026-11-06 | ML inside Next.js, Atlas | Classifier runs in Next.js via ONNX (ensemble v1+v2, 3-class confirm with 0.60 floor); Python service no longer needed. Database moved to MongoDB Atlas M0; local copy kept as backup. | See docs/ml-in-nextjs.md. |
| 2026-11-07 | Hagonoy/Ageratum v3, deployment, turnover | 546 Reyca-screened Hagonoy/Ageratum photos → `21cls-v3`; ensemble v1+v3 live (old test 84.2% top-1, 98.4% when sure). Deployed to geoflora-ph.vercel.app; forgot-password with code verification; CI/CD; rate limits; Feedback survey merged with usability; cloud training on GitHub Actions + Atlas GridFS. | Handover doc; new-species runbook for Monday (docs/ADDING-NEW-SPECIES.md); User Manual, System Documentation, Invoice. |
