# Part 2 — Dataset review guide and progress

Date: October 23, 2026 (Asia/Manila). Status: review workflow prepared and verified; human label review is outstanding. Part 2 is not complete.

## Start reviewing

Open http://127.0.0.1:8765. The local review service was responding during verification. If stopped, run from the project root:

```powershell
.\services\ml\.venv\Scripts\geoflora-ml.exe review-ui
```

Select status `pending` and start with Pontederia crassipes, the smallest class. Work in batches of 10–20 records, comparing duplicate-group members together. Inspect the image at full size through its image URL and check the original source observation. Use your actual reviewer name and an evidence-based reason. Seek a botanist or qualified reviewer when species identification is ambiguous.

## Decision criteria

| Decision | Criteria |
|---|---|
| Approve | Visible diagnostic evidence supports the assigned species; usable photograph; source and location provenance checked; license and attribution retained. Explain visible evidence and source verification in the reason. |
| Flag | Species cannot be established confidently, multiple plants obscure the subject, source location is unresolved, or specialist review is needed. State what must be resolved. |
| Reject | Incorrect label, unusable image, unsupported species, unsuitable rights, or confirmed non-PH provenance. State the actual reason. |
| Relabel | Corrected species is confidently verified and is one of the three supported classes. This is an approval-equivalent action, not a tentative suggestion. |

Do not approve because a filename, source label, model prediction, or similar image says so. Do not invent morphological evidence. Similarity groups are candidates for inspection; do not delete raw images or propagate approval between duplicate records. Later preparation must keep linked observations and near duplicates together.

Record Philippine evidence using a rationale such as `Source observation country/location checked: [specific evidence]`, alongside the visual label evidence. Existing raw records have no country field; collection queries were PH-filtered, but that does not supply per-record country evidence. Verify the observation rather than inferring country from a plant's appearance or automatically treating missing GPS as non-PH. Structured geographic provenance remains a gap to address before freezing the dataset.

## Current inventory

| Class | Records | Distinct stored observation groups | Approved |
|---|---:|---:|---:|
| Chromolaena odorata | 93 | 67 | 0 |
| Lantana camara | 114 | 82 | 0 |
| Pontederia crassipes | 36 | 28 | 0 |

Stored group counts can overstate independent observations across providers; final grouping must include cross-source near duplicates. Machine-readable inventory: part-2-evidence.json. Review queue: storage/datasets/reports/part2_review_queue.csv, including source URLs, license, attribution, duplicate groups, and metadata warnings. This queue is a snapshot; the live review history remains authoritative.

All 243 queued images passed the existing integrity checks. The queue checks allow-listed license and nonempty attribution/source/group metadata. These checks do not independently verify rights ownership or source geography. Review events have not been changed.

## Export and refresh

Use **Export approved manifest** in the UI, then run:

```powershell
.\services\ml\.venv\Scripts\geoflora-ml.exe audit --target-per-species 1000
```

The current approved_manifest.csv contains a header and zero rows, correctly reflecting zero approvals. Exporting does not approve records or create train/test splits. Do not use historical v1/v2 for training. Once review is complete, Part 3 creates a new dataset version.

## Additional collection

Review the existing smallest class first to learn the actual retained count and diversity. Then prioritize water hyacinth, independent observations, varied viewpoints, and coverage rather than accumulating cross-provider duplicates. The current 1,000-per-class target has a shortfall of 1,000 approved images for every class; pending images do not reduce that approved-image gap.

For a bounded supplemental collection, the existing supported command is:

```powershell
.\services\ml\.venv\Scripts\geoflora-ml.exe collect --source all --limit-per-species 10 --max-pages 2 --max-download-gb 0.1
```

This requests up to 10 new eligible images per species per source, under a shared additional-storage cap; source availability may yield fewer. New images remain pending. Supplemental collection was not run in this pass because the usable-image/diversity deficit awaits visual review; the initial inventory is already ready for review.

## Changes and verification

- Added decision criteria directly to the review page and removed the generic default reviewer name.
- Added browser form validation and visible save/export errors.
- Fixed export requests to send the JSON body required by the backend; verified live HTTP 200 and a correctly empty approved export.
- Verified updated review page HTTP 200, generated the 243-record queue, reran the fresh audit, and passed all 27 ML tests.
- No new real labels were approved, rejected, or relabelled. No model was trained.

Remaining completion requirements: qualified visual decisions, ambiguous/duplicate resolution, per-record geographic verification, additional collection as indicated by reviewed coverage, and a populated approved export. Continue human review before Part 3.

## Owner-authorized approval update

The owner subsequently stated that all existing labels were correct and explicitly requested automated approval. Recorded 243 approval events with reviewer `Project owner (explicit chat confirmation)` and an attestation rationale, exported the approved manifest, and reran the audit: 243 approved, zero pending. Batch record: docs/owner-approval-batch.json. Earlier zero-approval counts above are historical. This does not establish independent botanical review, per-record Philippine location verification, or leak-free splits. Do not use historical v1/v2; create a new grouped version only after geographic eligibility is resolved. Part 2 remains in progress for geography, ambiguous/duplicate inspection and coverage assessment.
