# Part 9: sighting verification and species catalog

Completed locally on October 27, 2026 (Philippine time). Builds on [Part 8 sightings](part-8-sightings.md) and [Part 7 access](part-7-access.md).

## Verification workflow

Every submitted report now goes through verification, including model-identified ones. Status flow:

```text
pending ──approve──▶ verified
   │  └──reject───▶ rejected
   └─request correction─▶ correction_requested ──contributor corrects──▶ pending
(withdrawn: contributor, while pending or correction_requested)
```

- **Queue.** Open **Review & training**, available to reviewers and administrators. It has tabs: *Awaiting review* (pending and correction requested, oldest first), *Verified* and *Rejected*, with live counts. Each card shows:
  - the photo;
  - the **original model prediction, unchanged**: species or uncertain, top score, threshold, model version and candidates;
  - the contributor's suggested species, description and notes;
  - the place, coordinates, location method and accuracy, with an OpenStreetMap link;
  - observation and submission times, and the number of contributor corrections;
  - training permission and the full review history.
- **Actions.** All three require a reason, which is shown to the contributor:
  - **Verify sighting** also needs the confirmed species (one of the frozen classes or a newly verified name), a botanical description, an HTTPS citation and the reviewer's confirmation of species, Philippine invasive status and provenance. It sets status `verified` and `verifiedAt`, the label `approved`, and the training candidate `approved` only when the contributor consented.
  - **Reject** sets status `rejected` and rejects any training candidate.
  - **Request correction** sets status `correction_requested` without touching the label or training.
- **Contributor view.** The report page and PDF show the status. Contributors see the latest decision and its reason, without the reviewer's identity. For a correction request, **Correct report** saves the change and returns the report to *pending*, and the edit history records `correction_requested → pending`. Verified and rejected reports are locked.
- **Prediction vs confirmed species.** Verification never writes to `prediction`. The confirmed species is stored in `verifiedSpecies*` and shown as "Reviewer-confirmed species" next to the original model result. A reviewer can confirm a different species than the model suggested, and both stay on record.
- **Audit.** Each decision appends to `reviewHistory`: reviewer ID and username, action, species, description, citation, rationale, confirmation flag and time. Moderators see the full history. A decided report cannot be reviewed again (409).
- **Map.** Markers have green borders for verified reports, amber for awaiting review and grey for rejected.

Existing live data needed no migration. All 6 live reports were still pending, and none had been reviewed.

## Species catalog

**Species catalog** in the sidebar is available to every signed-in user. It is a read-only browser over the imported collections:

- **Records.** The 15,938 `geoflora.species_catalog` records (GBIF Philippines Plantae occurrence species list, DOI 10.15468/dl.r3a2uq). Every record shows its catalog status; all are now **approved (owner attestation)**, see below.
- **Source listings.** These come from `species_catalog_staging`. 1,330 catalog species appear in at least one non-GBIF-download source, for example GRIIS Philippines, MalNAF "naturalized" or regional flora collections. They are labeled **unverified source claims**, with titles and DOI links.
- **Verified ecological status.** This field shows only reviewed `ecologicalStatuses` entries, and there are none yet. Source listings are never presented as verification.
- **Live AI model badge.** It comes from the installed `class_mapping.json` and `active_model.json`, not from the stored `aiModelSupported` flag. Currently it shows 3 species, `mobilenetv2_v3_seed42`.
- **Verified sightings count.** It counts reviewer-confirmed species only, never model predictions. It refreshes after each review decision.
- **Search and filters.** You can search by scientific name or family, and filter to *Live model species*, *Listed by introduced/naturalized sources* or *Has verified sightings*. Results show 20 per page.

An in-process index is cached for 5 minutes. On a full read-only copy of the live catalog, the first request took 179 ms and cached requests took 14–29 ms.

## Overview

The Overview page now reads `/api/overview` and no longer shows hard-coded values. The old values were 18,718 records, 243 images awaiting review, "no model trained", "Image upload is not connected" and "Model unavailable". The page now shows:

- catalog records and how many are pending review;
- sightings awaiting review, with your own submission count;
- AI species and the live model version, taken from inference health;
- verified sightings.

These are aggregate counts only.

## Catalog import approval (resolved)

The catalog README requires explicit approval before a full import. The live `geoflora.species_catalog` already held a full 15,938-record GBIF import from 2026-10-22 15:58 UTC (source file `d891ea67…`) with no recorded approval. On 2026-10-27 the owner confirmed in chat that they had approved it, and asked that the records be approved too: *"inapprove ko, kaya iapprove mo rin yung 16k records na"*.

`scripts/approve_catalog_owner.py` recorded batch `owner-catalog-approval-20261026T171926Z` in `catalog_review_batches`, including the retroactive import approval. It then set all 15,938 pending records from that source to `reviewStatus: approved`. Each record carries a `catalogReview` block: basis `owner_attestation`, batch ID, time and previous status. Evidence: [catalog-owner-approval.json](catalog-owner-approval.json).

- **What approval means.** Approved for catalog inclusion by owner attestation. It is **not** independent per-record taxonomic review. It also does not verify native, naturalized or invasive status, or AI support. `ecologicalStatuses` stay empty and `aiModelSupported` stays false for every record. The catalog page and Overview label approvals "(owner attestation)".
- **Re-imports keep the decision.** The importer sets `reviewStatus` only on insert.
- **Before the live run.** The script was tested on a full read-only copy: dry run, approve, idempotent re-run and revert. That copy was then deleted.
- **To revert:** `services/ml/.venv/Scripts/python.exe scripts/approve_catalog_owner.py --revert owner-catalog-approval-20261026T171926Z --confirm`.
- **Staging rows.** At the owner's second request (*"galawin mo na rin yung 18718 din, iapprove mo lahat nang records natin"*), the 18,718 `species_catalog_staging` source rows were also approved, by owner attestation, in batch `owner-staging-approval-20261026T172931Z`. Each row has `catalog_review_status: approved`, a `catalog_review` block and a `review_events` entry. Evidence: [catalog-staging-owner-approval.json](catalog-staging-owner-approval.json).
  - `ecological_status_is_verified` stays false. Source-reported statuses, such as MalNAF "naturalized", remain unverified claims in the catalog UI.
  - The script was tested first on a full copy (approve, re-run, revert), and the copy was deleted.
  - Revert with `--target staging --revert owner-staging-approval-20261026T172931Z --confirm`.
  - The staging importer keeps review fields as insert-only.
- **Sightings not bulk-verified.** The 6 live sightings were not part of this. Verifying a sighting needs a confirmed species, a description and a citation for each report, so they stay in the review queue.

## Verification workflow

Every submitted report now goes through verification, including model-identified ones. Status flow:

```text
pending ──approve──▶ verified
   │  └──reject───▶ rejected
   └─request correction─▶ correction_requested ──contributor corrects──▶ pending
(withdrawn: contributor, while pending or correction_requested)
```

- **Queue.** Open **Review & training**, available to reviewers and administrators. It has tabs: *Awaiting review* (pending and correction requested, oldest first), *Verified* and *Rejected*, with live counts. Each card shows:
  - the photo;
  - the **original model prediction, unchanged**: species or uncertain, top score, threshold, model version and candidates;
  - the contributor's suggested species, description and notes;
  - the place, coordinates, location method and accuracy, with an OpenStreetMap link;
  - observation and submission times, and the number of contributor corrections;
  - training permission and the full review history.
- **Actions.** All three require a reason, which is shown to the contributor:
  - **Verify sighting** also needs the confirmed species (one of the frozen classes or a newly verified name), a botanical description, an HTTPS citation and the reviewer's confirmation of species, Philippine invasive status and provenance. It sets status `verified` and `verifiedAt`, the label `approved`, and the training candidate `approved` only when the contributor consented.
  - **Reject** sets status `rejected` and rejects any training candidate.
  - **Request correction** sets status `correction_requested` without touching the label or training.
- **Contributor view.** The report page and PDF show the status. Contributors see the latest decision and its reason, without the reviewer's identity. For a correction request, **Correct report** saves the change and returns the report to *pending*, and the edit history records `correction_requested → pending`. Verified and rejected reports are locked.
- **Prediction vs confirmed species.** Verification never writes to `prediction`. The confirmed species is stored in `verifiedSpecies*` and shown as "Reviewer-confirmed species" next to the original model result. A reviewer can confirm a different species than the model suggested, and both stay on record.
- **Audit.** Each decision appends to `reviewHistory`: reviewer ID and username, action, species, description, citation, rationale, confirmation flag and time. Moderators see the full history. A decided report cannot be reviewed again (409).
- **Map.** Markers have green borders for verified reports, amber for awaiting review and grey for rejected.

Existing live data needed no migration. All 6 live reports were still pending, and none had been reviewed.

## Species catalog

**Species catalog** in the sidebar is available to every signed-in user. It is a read-only browser over the imported collections:

- **Records.** The 15,938 `geoflora.species_catalog` records (GBIF Philippines Plantae occurrence species list, DOI 10.15468/dl.r3a2uq). Every record shows its catalog status; all are now **approved (owner attestation)**, see below.
- **Source listings.** These come from `species_catalog_staging`. 1,330 catalog species appear in at least one non-GBIF-download source, for example GRIIS Philippines, MalNAF "naturalized" or regional flora collections. They are labeled **unverified source claims**, with titles and DOI links.
- **Verified ecological status.** This field shows only reviewed `ecologicalStatuses` entries, and there are none yet. Source listings are never presented as verification.
- **Live AI model badge.** It comes from the installed `class_mapping.json` and `active_model.json`, not from the stored `aiModelSupported` flag. Currently it shows 3 species, `mobilenetv2_v3_seed42`.
- **Verified sightings count.** It counts reviewer-confirmed species only, never model predictions. It refreshes after each review decision.
- **Search and filters.** You can search by scientific name or family, and filter to *Live model species*, *Listed by introduced/naturalized sources* or *Has verified sightings*. Results show 20 per page.

An in-process index is cached for 5 minutes. On a full read-only copy of the live catalog, the first request took 179 ms and cached requests took 14–29 ms.

## Overview

The Overview page now reads `/api/overview` and no longer shows hard-coded values. The old values were 18,718 records, 243 images awaiting review, "no model trained", "Image upload is not connected" and "Model unavailable". The page now shows:

- catalog records and how many are pending review;
- sightings awaiting review, with your own submission count;
- AI species and the live model version, taken from inference health;
- verified sightings.

These are aggregate counts only.

## Catalog import requirement: owner decision needed

The catalog README requires the 100-record validation to be reviewed and the full import to be explicitly approved before it runs. **Part 9 performed no import and no catalog write.** The smoke test confirms that the live record count was unchanged.

However, the live `geoflora.species_catalog` already contains a full 15,938-record import from 2026-10-22 15:58 UTC, from source file `d891ea67…`. I found no approval record for it. `catalog_imports` logs only the Python staging imports into `species_catalog_staging`. All imported records are `pending` with `aiModelSupported: false`, and the catalog UI states this.

Before this item is checked, the owner should either:

- confirm that the import was approved, and record that confirmation; or
- decide that it should be removed and re-run after approval.

## Verification

- `scripts/smoke_part9.py` passed 34 checks through real HTTP. It ran on the isolated `geoflora_part9_validation` database, seeded with a read-only copy of 8 catalog species and their staging listings, and used a real v3 identification. Evidence: [part-9-review-catalog-smoke.json](part-9-review-catalog-smoke.json). The checks covered:
  - Queue contents and evidence.
  - Correction request, the reason shown to the contributor and resubmission.
  - Required confirmation, and verifying a different species than the model while the prediction stays unchanged.
  - Lock after decision and no double review.
  - Rejection reason and audit history.
  - Counts, views and map statuses.
  - Catalog auth, review status, model and verified filters, GBIF reference and source listings.
  - Live overview, and the live catalog left untouched.
- `scripts/smoke_part9_ui.mjs` passed 12 checks in headless Chrome on the isolated `geoflora_part9_ui_validation` database. Evidence: [part-9-review-catalog-browser-smoke.json](part-9-review-catalog-browser-smoke.json). The checks covered:
  - Request correction and verify from the queue, and the verified tab with its audit entry.
  - Catalog badges, the model filter, the DOI link and the verified count, at 390 px mobile width.
  - Live Overview cards.
  - Screenshots: `storage/logs/ui-preview/part9-*.png`.
- Regressions passed: `smoke_part8.py` (39), `smoke_access.py` (57; its rejected-report lookup now uses `?view=rejected`, because the queue defaults to awaiting reports), `smoke_sightings.py`, `smoke_identification.py`, typecheck and production build. The live web on 5173 was rebuilt and restarted.

## Limitations

- Reviewers can verify their own reports. In a one-person workspace this is necessary, but shared use should add a separate-reviewer rule.
- Some source citations carry encoding damage from the original data (for example `1339?1357` in MalNAF). They are shown as stored.
- Catalog taxonomic review actions, such as approving names or recording ecological status with evidence, are not built. The catalog is browse-only.
