# Simple identify flow (2026-11-05)

Owner request: make the GeoFlora app's identify flow as simple as the ML lab demo, without adding steps for users or administrators.

## Flow now

**Identify a plant → result → Save report**, all on one screen. The separate "Create a field report" page is no longer used.

1. Result, with the same three outcomes as the lab demo:
   - red **Target invasive species**
   - blue **Not a target species**
   - yellow **The model is not sure** ("Possibly *X*")
2. Model scores (top 3) and the threshold. The model counts as sure from 69 for `geoflora-mnv2-21cls-v1`.
3. **Save as a sighting report**:
   - Date and time are read from the photo's EXIF; otherwise the current time is used.
   - Location comes from the photo's GPS (new method `photo_gps`), the device location, or a map pin. Typed coordinates are under a collapsed section.
   - Place name and notes are optional.
   - The optional reference and training photo-use permissions are under a collapsed section.
   - Saving is the submission consent; the button text says so.
4. Species description: summary, how to recognise it, why it matters, easily confused with, and references. For "not sure" results, it describes the closest match and labels it as such.

On "not sure" or "This doesn't match my plant", the AI suggestion card is still shown, and the plant description and name fields are now **optional**. The reviewer always has the photo, the model output and the AI review.

## Changes

| File | Change |
|---|---|
| `src/features/identification/identification-result.tsx` | Rewritten as the one-screen result |
| `src/features/identification/quick-report.tsx` | New: inline report |
| `src/features/identification/photo-exif.ts` | New: reads the EXIF date/time and GPS in the browser, before the photo is shrunk |
| `src/features/identification/identification-view.tsx`, `src/App.tsx` | Wire the inline report; the report handoff page is removed from navigation |
| `src/lib/sightings.ts` | `photo_gps` location method (schema enum and `LOCATION_METHODS`) |
| `app/api/sightings/route.ts`, `app/api/sightings/[id]/route.ts` | Plant description no longer required for uncertain or disputed reports |
| `admin-review.tsx`, `report-view.tsx`, `lib/report-pdf.ts` | Label for `photo_gps` |
| `src/styles.css` | Verdict and description styles |

The visual-similarity suggestions are no longer shown to contributors. They are still computed and stored with the prediction.

Admin review is unchanged. Every model-based report is `pending`. The AI reviewer auto-verifies when it and the classifier agree (confidence ≥ 0.85) and auto-rejects non-plant photos; everything else goes to a person.

## Checks

- `npx tsc --noEmit` passes.
- Browser check (Playwright, owner account, 1366 px and 390 px) on a Lantana photo with EXIF date and GPS added:
  - Date filled as 2026-11-03 09:41:27 and location as 7.070167, 125.61 (`photo_gps`).
  - The result was "not sure" (56.6 < 69).
  - The report saved with `labelReviewStatus: pending`, then was withdrawn through the app's own DELETE.
- A hibiscus photo (unknown_test) came out as African tulip tree, 71.2, "sure", target. This is a known false alarm of the 21-class model. Since the evening update there is no review queue, so a report like this goes on the map as a target unless it is withdrawn.
- No page errors on either viewport.

Backup before the change: `C:\Users\reyca\geoflora-backups\geoflora-src-before-simple-flow-20261105-0144.zip`.

## Update: no review queue, like the ML lab (2026-11-05 evening)

Owner decision: there is no botanist, so reports should not wait as "pending". GeoFlora now works like the ML lab demo.

- **New reports are saved as `recorded`**, with `aiResult` = `target`, `other` or `uncertain` from the identification (`src/lib/ai-result.ts`). `labelReviewStatus` is `not_required`. The background AI reviewer is no longer triggered on save; it only handles legacy `pending` reports, and there are none.
- **The UI shows the AI result everywhere**, in the same colours as the lab: red target invasive, blue not a target, amber not sure. This covers the result screen, reports list (filters by result), report page, map (markers, legend, "All results / Target invasive only"), overview counts and the PDF. Each place says the result is an AI identification and not expert-verified.
- **Description:** the report shows the identified species' description, or for "not sure" the closest match's, labelled as such. No more "No description supplied". Contributors are no longer asked to describe the plant. On "not sure", the general AI vision model's second opinion is still shown and can be saved as a possible name.
- **"This doesn't match my plant" was removed** from the result screen.
- **Older reviewed reports keep their status.** Verified reports count as target when the reviewed species is one of the 13 target species (`TARGET_SPECIES`, same rule in `RESULT_EXPR` for MongoDB). Rejected reports are hidden from the map and listed under "Rejected".
- **Data change:** the one `pending` report (6aec6c39…, *Limnocharis flava*, saved by the owner on 2026-11-05) was set to `recorded`/`other`. Backup: `C:\Users\reyca\geoflora-backups\pending-sightings-before-recorded-20261105.json`.
- **Check:** a browser run identified, saved, listed and mapped a test report, then withdrew it.
  - Result: `status: recorded`, `result: uncertain`, "Possibly Lantana camara", with a description.
  - Reports list: Target invasive 5 · Not a target 8 · Not sure 1 · Rejected 5.
  - No page errors.

## Update: admin Approve/Correct, auto-training, PDF (2026-11-05 night)

- **Options are back** on the result screen, and both are optional:
  - "This doesn't match my plant"
  - "Add your own description or species name" (collapsed)
- **Wording:** "not expert-verified" was removed (owner request). Results read "Identified by GeoFlora AI".
- **Admin check (Review & training):**
  - The "To check" tab lists `recorded` reports.
  - **Approve** keeps the AI species.
  - **Correct** picks the right species from the list, or types a new scientific name.
  - **Reject** is a small extra for non-plant or unusable photos.
  - No rationale or citation is required (`simpleReview` in `src/lib/review.ts`, actions `simple_*`).
- **Training use is on by default** in the report form. The contributor can switch it off under "Photo use".
- **Auto-training** (`ml-lab/scripts/app_training_worker.py`, running detached; log `storage/logs/app-training-worker.log`):
  - **Every 10 minutes**, it imports approved or corrected reports into the lab dataset (`scripts/import_app_reports.py`). These are reports the AI did not get right, where training use is allowed and the species is in the lab catalog. They are recorded as license `GEOFLORA-CONTRIBUTOR`, review_status approved, with the admin as reviewer.
  - **After 20 new photos**, it retrains the 21-class model and compares it with the live model on the new test photos. If it is not worse, the model appears under Review & training as "Approve new model".
  - **After approval**, it installs the model with `scripts/install_lab_model.py`, which keeps a backup for rollback, and reloads the inference service.
  - First run: 2 earlier approved Hagonoy reports were imported. The manifest backup is `geoflora-backups/image_manifest-before-app-import-20261105.csv`.
  - Restart after reboot:
    ```
    cd ml-lab
    .venv\Scripts\python.exe -u scripts\app_training_worker.py
    ```
- **PDF redesigned** (`src/lib/report-pdf.ts`). It has:
  - a header band and a coloured result banner with the AI score
  - the photo beside the sighting details
  - the location map
  - About the species: status, description, how to recognise it, why it matters, look-alikes
  - the top 3 AI matches, reporter notes and references
