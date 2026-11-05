# Part 2C — Batch label review and class selection

Status: staging review/export tools prepared and tested; visual label and location decisions remain pending. No new approvals or active model classes were created.

Update: the owner subsequently confirmed viewing the batch and explicitly authorized approval of all labels. Recorded 674 owner-attested label approvals; the UI now shows 674 approved and zero pending. This supersedes the earlier pending-label snapshot. No new country or field/herbarium verification was inferred: all 674 remain in approved_labels_on_hold.csv, with zero field-training candidates until those checks and ecological holds are resolved. Evidence: docs/batch-owner-label-approval.json. Label approvals do not mean every research taxon is invasive or training-ready.

## Open the review packet

**Interactive approval UI: http://127.0.0.1:8766.** This loads the 674-record batch with Pending selected by default. The original review UI at http://127.0.0.1:8765 links here; its original 243-image dataset is separate.

In the batch UI, select a species/status, inspect the image and original source, enter reviewer name and reason, then Approve, Reject or Flag. Approval also requires confirming PH source location and selecting the visually verified field/herbarium domain. Saved decisions use the same append-only batch history and held-versus-field-candidate exports as the CSV importer. Ecological holds are preserved. Refresh approved exports using the UI button; no CSV editing is required for UI decisions.

If stopped, start from the project root: `.\services\ml\.venv\Scripts\python.exe scripts/batch_review_ui.py`. It binds only to loopback at port 8766. Existing galleries remain read-only alternatives.

Open storage/datasets/staging/species_100_ph/review/index.html in a browser. It links to 80 species galleries covering all 674 candidates, with full-size photos, original source observations, license/attribution, similarity groups and audit holds.

Use the record_key to match a photograph to its row in review/decisions.csv. This file starts with blank decisions and is preserved on subsequent packet generation. The galleries are read-only; decisions must be entered in the CSV and explicitly imported. Do not edit the generated audit CSV or change a species label silently.

## First review batch

The metadata audit identifies 46 priority records across six species, with no currently detected blocking route beyond label/location review. They remain unverified, and some are repeats of existing images.

| Species | Priority records |
|---|---:|
| Chromolaena odorata | 10 |
| Lantana camara | 10 |
| Mikania micrantha | 10 |
| Pachystachys coccinea | 4 |
| Piper aduncum | 2 |
| Pistia stratiotes | 10 |

Prioritize Mikania for the next class feasibility review. Ten batch records represent only five estimated observation/similarity components. Include comparison with the separate 50-image Mikania collection before choosing independent groups. These counts do not establish adequate validation/test coverage or a final six-class model.

## Record explicit decisions

For each reviewed row, enter:

- decision: approved, rejected or flagged; leave blank if not reviewed.
- reviewer: actual reviewer name.
- rationale: specific visible identification evidence and source/location checks, or the reason for rejection/flagging.
- verified_country: PH only when confirmed from observation evidence.
- verified_domain: field or herbarium for approval, following visual inspection. A URL heuristic alone is insufficient.

Approval here confirms a label/provenance decision; it cannot clear unresolved ecological status or activate a species class. Flag any proposed species correction rather than modifying scientific_name in place. Ambiguous cases need qualified identification review.

Apply reviewed rows from the project root:

```powershell
.\services\ml\.venv\Scripts\python.exe scripts/batch_review.py apply --decisions storage/datasets/staging/species_100_ph/review/decisions.csv
```

The importer validates every supplied decision before appending events to review/review_events.jsonl. Invalid keys, missing reasons, label changes or corrupt approved files stop the import. Reapplying identical decisions does not duplicate events. Latest decisions regenerate two staging exports:

- approved_field_candidates.csv: approved PH field records without remaining blocking audit routes; still candidates for dataset/class selection, not an automatically accepted training split.
- approved_labels_on_hold.csv: approved labels with ecological/technical holds or herbarium-only domain. They remain outside the field training candidate export.

No automatic approvals were performed. The original 243 approvals do not apply to these new records. No global collector/model class registry is expanded by this staging workflow.

## Class-selection handoff

review/class_selection.csv summarizes all 100 queue entries, including species without images, component estimates, ecological screens and counts available for review. Every approved_for_training value starts False. After review, produce a separately justified selected-class configuration and a new dataset version. Existing three-class v3 and model metrics remain historical baselines.

Preparation command:

```powershell
.\services\ml\.venv\Scripts\python.exe scripts/batch_review.py prepare
```

Validation: generated 674 review rows and 80 galleries. Temporary fixtures verified hold/domain segregation, idempotent imports and all-or-nothing decision validation without touching production labels. Part 2C stays in progress until real review decisions and class-selection evidence exist.
