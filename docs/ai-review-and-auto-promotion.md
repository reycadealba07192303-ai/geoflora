# AI review and administrator-approved model promotion

AI review can triage or verify reports under the configured agreement policy. Model training remains progressive, but candidate activation now requires explicit administrator approval after evaluation. This promotion rule supersedes the automatic-promotion behavior described in the original October 31 implementation notes below.

## How a sighting is reviewed

After a report is saved (or a contributor corrects one), the web app sends it to the AI reviewer in the background (`apps/web/src/lib/ai-review.ts`). Claude (`claude-opus-5-5`) receives the photo, the contributor's description, suggested name and notes, the observation date and the image classifier's prediction. It does not receive coordinates, place names or account names. It returns a structured verdict: plant or not, photo usable or not, species, decision, confidence, a rationale for the contributor and concerns for a reviewer.

The code, not Claude, decides what is applied:

| Outcome | When |
|---|---|
| Verified automatically | Claude says verify with confidence ≥ 0.85, the species is supported, and the image classifier independently identified the **same** species; the photo is usable and the location is inside the Philippines |
| Rejected automatically | Claude is ≥ 0.90 confident the photo is not a plant or is unusable, or the photo exactly repeats an earlier pending/verified report (no API call) |
| Left for a person | Everything else: disagreement with the classifier, no classifier species, low confidence, unsupported species, location outside the Philippines, API refusal or error |

Decisions are recorded in the report's review history as `GeoFlora AI reviewer` with `basis: "ai_review"`; the original classifier prediction is never changed. Reports left for a person show the AI recommendation and why it was not applied, with **Use AI suggestion** to prefill the form. Administrators can run a pass with **Run AI review now**. Failed reviews retry up to three times.

Claude requests use structured outputs and server-side refusal fallbacks (`fallbacks: "default"`); OpenRouter requests use a strict JSON schema and are validated again on receipt.

## Provider and turning it on

The reviewer runs on **OpenRouter** when `OPENROUTER_API_KEY` is set in `apps/web/.env.local` (set October 31, 2026, at the owner's request, to use free models). It sends the request to `nvidia/nemotron-3.5-super-vl:free`, with `google/gemma-4-31b-it:free` and `google/gemma-4-26b-a4b-it:free` as automatic fallbacks, only to providers that honour the JSON schema (`provider.require_parameters`). `GEOFLORA_AI_REVIEW_MODELS` overrides the list (comma-separated). Without an OpenRouter key it uses Claude (`claude-opus-5-5`) when `ANTHROPIC_API_KEY` is set; with neither, the reviewer is off and every sighting waits for a person. `GEOFLORA_AI_REVIEW=off` turns it off. Restart the web app after changing keys.

Free OpenRouter models are rate-limited, and their providers may log or train on prompts and images. The request carries the photo, the contributor's description, suggested name and notes, the observation date and the classifier result; no coordinates, place names or account names. The decision rules above apply unchanged whichever model answers; the model that answered is stored with each review.

Live check on an isolated database with the owner's key: a Lantana photo that the classifier also identified was auto-verified (Nemotron VL, confidence 0.98), and a plain brown image was auto-rejected as not a plant.

## Plant suggestion on Identify

The image classifier only knows the species it was trained on (three today), so for any other plant it can only say "uncertain" and list the closest of its three. When that happens, the result screen asks the same vision model what the plant is (`POST /api/identify/suggest`, `src/lib/plant-suggestion.ts`). It returns a name (species, or genus/family when the photo does not settle it), common names, a confidence, the features that support it, look-alikes, and a field description of what is visible.

GeoFlora, not the model, then checks its own catalog: whether the name is recorded in the Philippines (GBIF), whether any source lists it as introduced or naturalized, and whether it is one of the species the classifier tracks. The card is labelled "AI suggestion · not verified". "Use this name in my report" fills the suggested-name field, and an empty "What does it look like?" field is filled with the AI's description, marked as drafted by the AI until the person edits it. A reviewer still confirms the species before a sighting counts as verified.

Example (owner's water lily photo): classifier uncertain (70.9%, closest water hyacinth); suggestion "Water lily, Nymphaea (genus only)", not tracked, recorded in the Philippines (6 species in the catalog).

## Non-invasive look-alikes

The classifier now learns non-invasive plants that people confuse with the monitored species, so it can say what they are instead of only "uncertain". Each look-alike group is one class (for example **Water lily, *Nymphaea***, often mistaken for water hyacinth) with `role: lookalike`; monitored species have `role: invasive`. A recognised look-alike is shown on Identify as "Possible match · not invasive".

Photos reach a look-alike class three ways, all ending in the same staging queue `storage/datasets/staging/lookalike_<group>_ph/review_queue.csv`:

1. **Licensed field photos**: `python scripts/collect_staging_photos.py [group ...]` collects research-grade Philippine iNaturalist observations for monitored species and look-alikes into `storage/datasets/staging/<role>_<group>_ph/`. GBIF media for these taxa were herbarium sheets, so GBIF is not used.
2. **The owner's own photos**: `python scripts/import_field_photos.py <group> <folder> --photographer "Name" --attest` (the owner attests they took them in the Philippines and that they show the plant).
3. **Contributors' sightings**: a reviewer, or the AI reviewer when it and the classifier agree, verifies a report as the look-alike group (offered in the species list as "not invasive"), or adds a new species marked "Not invasive". With training consent the photo joins training like any verified report, with `verifiedRole: lookalike`.

`python scripts/screen_staging_photos.py <group>` has the OpenRouter vision model check each unscreened photo (owner photos first, then research-grade ones): approved only if it is a field photograph (not a herbarium sheet, drawing or screenshot) that clearly and usably shows the plant, with confidence ≥ 0.8. Decisions, model and rationale are written to the queue, and a person can overrule them. AI-only approvals and research-grade-only source labels are excluded from staging training. A staging row must be marked approved by a human reviewer, include the reviewer identity and a written visible-feature rationale, and pass strict license and historical-test duplicate checks before export. Contributor reports use the separate consent and approved-label requirements below.

**Licence and label decisions (owner, October 31, 2026):** Creative Commons non-commercial licences (CC BY-NC, CC BY-NC-SA) are accepted for staging photos of both look-alikes and monitored species, because GeoFlora is non-commercial research and most Philippine field photos carry them (for example Chromolaena 228 photos with them against 33 without). If GeoFlora is ever used commercially, those photos must be removed and the model retrained. Licences and attribution are recorded per photo; the original corpus keeps its CC0 / CC BY / CC BY-SA rule (`allow_noncommercial` is off by default in the collectors). iNaturalist research-grade identifications (community agreement) are accepted as labels (`review_status: research_grade`, `label_basis: inaturalist_research_grade`); the AI screen checks them as the free quota allows and can reject any.

**Temporary training hold (owner direction, November 1, 2026):** The project is preparing client delivery, and the client's permitted downstream use has not been confirmed as non-commercial-only. Therefore CC BY-NC/CC BY-NC-SA assets are excluded from new training freezes and automatic training until that use is explicitly confirmed. The automatic worker now enforces the strict CC0/CC BY/CC BY-SA allowlist (plus attributed owner photos) instead of trusting a review status alone. Existing CC BY-NC files remain in staging with their provenance and pending status; no source files are deleted. This temporary hold takes precedence over the October 31 non-commercial research approval for new training. The current 58-image weak-class review package contains CC BY and CC0 images only. The unpromoted eleven-class candidate was trained from a corpus that included CC BY-NC images; do not deliver it until rights for that use are confirmed.

**Species added for monitoring:** besides Chromolaena, Lantana and water hyacinth, Mikania micrantha, Pistia stratiotes and Broussonetia papyrifera (GRIIS source-flagged invasive), and Leucaena leucocephala, Spathodea campanulata, Coccinia grandis and Antigonon leptopus (introduced in the Philippines; invasive status not yet verified in GeoFlora's sources, monitored at the owner's choice and marked `introduced_review` in their staging metadata).

## Training and administrator-approved promotion

Reports can enter training only when the contributor opted in and the report has an approved verified label. The existing AI reviewer may verify a report only under its configured supported-species agreement policy; otherwise a human reviewer handles it. Rejected, pending, or non-consented reports do not enter training. Staging photos additionally require a human review identity and written rationale; AI screening and iNaturalist research-grade labels alone are not verification. Every source must pass the strict CC0/CC BY/CC BY-SA or attributed owner-photo license check.

The worker excludes hashes and observation identities for every curated historical test split and checks baseline and approved additions against historical test perceptual hashes (Hamming distance <= 6). The frozen v5 test split also remains the existing candidate-to-live comparison benchmark. Candidates must first pass the training quality gates (85% accuracy, 85% macro F1, 80% recall per class) and live comparison. Passing candidates are saved as experimental artifacts with per-class metrics, dataset manifest, model mapping, and evaluation record; training does not activate them.

An authorized administrator opens **Review & training**, inspects overall and per-class evaluation and explicitly approves promotion with a rationale. The worker rechecks the evaluation gates, live comparison, and candidate model/mapping/evaluation checksums before installing. Each promotion stores the prior live model, mapping, species list, activation metadata, and evaluation snapshot under storage/models/previous/<timestamp>/. Active metadata records model version, evaluation checksum, administrator approval and rollback path. Automatic promotion is disabled.

To roll back from the project root, restore a snapshot from storage/models/previous/ with the Python environment:

```powershell
.\services\ml\.venv\Scripts\python.exe scripts\model_promotion.py `
  --rollback-to storage\models\previous\<snapshot-folder> `
  --reason approved_rollback_reason
```

Rollback validates saved checksums when available, keeps the outgoing model as another snapshot, records the from/to versions and reason, and republishes/reloads when hosted model settings are configured. If reload fails, it restores the outgoing version.

## Served species travel with the model

A promoted candidate installs its served-species list (`storage/models/species.yaml`, each species with its role) together with the model, so any class it learned and passed the quality gate on (at least 80% recall per class) becomes servable, including look-alikes and Mikania/Pistia. Without that file the packaged `services/ml/src/geoflora_ml/species.yaml` applies. Rollback restores or removes it with the model. A real comparison of the v5 candidate now loads it and correctly declines it (benchmark accuracy 81.8% against the live model's 90.9%).

## Verification

- 14 policy checks of the decision rules.
- 15 end-to-end checks on an isolated database with the real web app and ML model and a local stand-in for the Messages API: agreement auto-verified with the species and training candidate status; disagreement, low confidence and out-of-country left for a person; non-plant and duplicate auto-rejected (duplicate without an API call); request contents (model, image, structured output, fallbacks; no place, coordinates or account); human override; contributor label.
- Worker dataset freeze accepted the AI-verified label with its basis and included 0 benchmark photos.
- 33 ML tests (2 new for `/reload`); real comparison run refused the v5 candidate because Mikania/Pistia are not servable.
- Live inference restarted with `/reload`; the same v3 model reloads successfully.

## First look-alike training run (October 31, 2026)

Collection: 42 iNaturalist field photos (CC BY-NC) plus 15 earlier GBIF herbarium sheets. AI screen (free tier, stopped by its daily limit after 35 requests): 29 field photos approved, 6 herbarium sheets rejected, 22 still pending (re-run `scripts/screen_staging_photos.py nymphaea` to continue).

One worker pass trained a six-class candidate (Water lily 19/5/5 train/validation/test, Mikania 1/1/4, Pistia 1/2/2). Test accuracy 60.5%, macro F1 35.3%: quality targets failed, the live v3 model was kept. Water lily recall was 80% (4 of 5), but it was confused with other aquatic plants (Pistia, water hyacinth); Mikania and Pistia scored 0%, and the model over-predicted Hagonoy, the largest class (4 of 5 water hyacinth test photos). More water lily and water hyacinth photos are needed, and classes with only a handful of photos hold every candidate below the gate.

## Free daily limit and background reviewing (October 31, 2026)

OpenRouter's free tier allows 50 requests a day to free models (`free-models-per-day`; resets 08:00 Philippine time; adding 10 USD of credits raises it to 1,000 a day). The reviewer, plant suggestions and photo screening share it. On 31 October the photo screening used it up, and reviews then appeared to stop: reports were left in `running` because a review cut short was never recorded, and three restarts locked one out for good.

Changes: a 429 from OpenRouter records a pause (collection `ai_service`, document `vision`) until the reset time it reports; every caller checks it first, so no requests are spent while paused. A report hit by the limit is marked `paused` without using an attempt and resumes automatically after the reset. Reviews left `running` are picked up again after five minutes, and one that never finishes after three tries is handed to a person with a visible error. A background timer started with the server (`apps/web/instrumentation.ts`) reviews waiting reports every minute, so reviewing no longer depends on a request staying open. The admin panel shows the pause and when reviews resume; plant suggestions say when they are available again. Photo screening stops at the daily limit and screens at most 15 photos per run by default, leaving most of the allowance for sightings.

Verified: against the real exhausted limit, the first pass paused one report (attempts unchanged) and recorded the pause until 2026-11-01 00:00 UTC; the second pass made no API request. A server started with no requests reviewed a seeded report on its own within about 65 seconds.

## Expanded training run (October 31, 2026)

Collection added 1,463 usable Philippine field photos (research grade, mostly CC BY-NC) for ten monitored species and the water lily group; 15 were excluded as benchmark photos by checksum or observation and none by the new visual near-duplicate check (perceptual hash within 6 bits, cached in storage/datasets/staging/.perceptual_hashes.json). The training script now keeps images as uint8 and builds full pixel arrays only for the test split or fine-tuning, cutting memory about fourfold without changing results.

One worker pass trained an 11-class candidate on 1,625 photos (frozen MobileNetV2, head only, best epoch 4). Test accuracy 73.5% and macro F1 73.5% (253 test photos), up from 60.5% / 35.3%, but below the 85% gates, so the live v3 model was kept. Recall: Lantana 97%, water lily 92%, water hyacinth 86%, Pistia 83%, Chromolaena 74%, Leucaena 74%, Antigonon 74%, Broussonetia 67% (6 test photos), Spathodea 65%, Coccinia 57%, Mikania 36%. Main confusions are between look-alike plants: Mikania and Chromolaena (white flower heads, 10), Mikania and Coccinia (climbing vines, 4), Pistia and water hyacinth (floating plants, 4).

