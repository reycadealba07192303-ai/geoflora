# Part 8: geotagged sightings

Completed locally on October 27, 2026 (Philippine time). This builds on [sighting submission](sighting-submission.md) and the [Part 7 access](part-7-access.md) roles.

## What a report stores

Each report is one MongoDB document:

- the owner account and pending status;
- the normalized photo (JPEG, metadata stripped, at most 1600 px);
- the contributor's species suggestion and description;
- observation time and server submission time in UTC;
- GeoJSON coordinates in longitude/latitude order, with a 2dsphere index;
- how the location was set, plus GPS accuracy when available.

**Identification snapshot.** When the report comes from an identification, the server attaches its own snapshot: status, top score, threshold, candidates and model version (for example `mobilenetv2_v3_seed42` at 0.80). It comes from the stored identification for that exact photo, not from client input. The report page and the PDF show this snapshot as the **Identification record**.

## Map-pin location

The report form has a map below the coordinate fields. You can tap or click to drop a pin, drag it to adjust, or type coordinates. The pin and the fields stay in sync. A pin location is saved with `locationMethod: map_pin` and no GPS accuracy, so it is distinguishable from `gps` and typed `manual` coordinates. The map background needs internet (OpenStreetMap tiles). Typed coordinates always work. Coordinates are range-checked but not verified as Philippine locations.

## Contributor correction and withdrawal

A report is **editable** only by its owner, only while it is `pending`, and only before any review decision. That means it has no review history and no approved or rejected label or training decision. The report page offers **Correct report** and **Withdraw report** only in that state, and the server enforces the same rule. Other accounts, including reviewers and administrators, get 404. Owner actions after review get 409.

**Correct.** The owner can correct the place, observation time, location (pin or typed), description, notes and, for reports without a model label, the suggested name.

- The photo, the identification snapshot and server-owned fields such as status, training and verification cannot be changed.
- A report awaiting identification must keep a description.
- Each correction appends an `editHistory` entry with the time, the editor and the previous and new values, including the previous location.

**Withdraw.** After a confirmation step, the server immediately deletes:

- the photo and photo hashes;
- the coordinates and place name;
- the description, notes and suggested name;
- the identification snapshot and citations;
- the edit history.

It also cancels training consent. A minimal tombstone remains: the ID, owner, request ID, submission time, observation time and withdrawal time. The tombstone stops a retried submission from recreating the report and keeps a count for audit.

After withdrawal:

- The report reads as 410 Gone.
- The photo and PDF return 404.
- It disappears from the map, review queue and training candidates.

## Retention policy

| Data | Retained | Removed |
|---|---|---|
| Active report and photo | While the report is active (no automatic expiry; it is a research record) | On contributor withdrawal (immediately), or by an administrator in a later moderation feature |
| Withdrawn report | Tombstone only, as listed above | Photo, coordinates and all descriptive content, at withdrawal |
| Correction history | With the active report | With the report's content at withdrawal |
| Identification results (not yet reported) | 24 hours (TTL index) | Automatically |
| Sessions / reset codes | 8 hours / 30 minutes | Automatically, on logout, reset or disable |
| Photos approved for training | With the frozen dataset version that used them, for reproducibility | Only by an administrator creating a new dataset version |

Contributors cannot withdraw a report after review. After a training approval, the photo may already be part of a frozen dataset, so removing it requires an administrator.

## Public coordinate visibility

- **No public access today.** Every report, photo, map and PDF endpoint requires sign-in and stays on loopback.
- **Exact coordinates** are visible only to the report's owner and to reviewers and administrators, for moderation.
- Contributors never receive other contributors' reports.

Rules for any later shared or public display (Part 10 map and analytics):

- show verified reports by default and label any pending layer;
- generalize locations to at least a 0.1° grid (about 11 km) or an administrative area;
- never expose exact coordinates, photos' original metadata (already stripped at upload), usernames, owner IDs or edit history;
- suppress cells with fewer reports than the documented minimum, so sparse areas do not reveal individual sightings.

## Verification

- `scripts/smoke_part8.py` passed 39 checks through real HTTP on the isolated `geoflora_part8_validation` database, using a real v3 identification. Evidence: [part-8-sightings-smoke.json](part-8-sightings-smoke.json).
  - **Stored fields:** owner, pending status, photo, score, threshold and model version, species, map-pin method, longitude/latitude order and separate times; the PDF still generates.
  - **Corrections:** a correction saved with its history; the identification is unchanged; server-owned fields are ignored; bad times and coordinates are rejected.
  - **Boundaries:** other contributors, reviewers and signed-out requests are refused; a required description is kept; the suggestion updates the reported species.
  - **Locking:** a reviewed report locks both correction and withdrawal.
  - **Withdrawal:** content is deleted and the tombstone fields remain; 410/404 responses; removal from the map, review queue and training candidates; no double withdrawal; no resurrection by retry.
- `scripts/smoke_part8_ui.mjs` passed 9 checks in headless Chrome at 390x844 mobile emulation. The checks covered dropping and moving a pin, the saved pin method and identification record, owner correction, withdrawal confirmation and completion. Evidence: [part-8-sightings-browser-smoke.json](part-8-sightings-browser-smoke.json). Screenshots: `storage/logs/ui-preview/part8-*.png`.
- These regressions passed after the change:
  - `smoke_access.py` (57 checks)
  - `smoke_sightings.py`
  - `smoke_identification.py`
  - typecheck and production build

  The live web on 5173 was restarted. The 6 existing live reports needed no migration.
- `smoke_report_flow.py` was not rerun. It trains a real candidate and still asserts the earlier 221-image v4 base, while the worker now uses the v5 base set up before this part. That assertion needs updating separately.
