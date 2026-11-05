# Parts 2A and 2B — running batch and audit workflow

Activated October 23, 2026 (Asia/Manila). Part 2A collection is still running. Part 2B has an initial snapshot audit and an automatic final-audit worker; neither part is marked finished before the complete pass is reconciled.

## Background jobs

The collector continues the full 100-entry queue with the existing 10-image/species initial target and 1 GiB total staging budget. Taxonomy failures, no-image outcomes and source errors remain explicit. Only one collector should write the staging root.

The finalizer waits for all 100 checkpointed outcomes and a finished-pass marker. It then runs the audit, checks source-snapshot stability and checkpoint/file counts, writes docs/part-2ab-results.md, and updates Part 2A/2B checklists in plan.md. If finalization fails, docs/part-2ab-job-status.json records the error instead of claiming completion. It waits up to six hours; an interrupted collection needs inspection/resumption.

Live status:

- docs/species-100-collection-progress.json
- docs/part-2ab-job-status.json
- storage/datasets/staging/species_100_ph/logs/worker.pid and finalizer.pid
- logs/stderr-resumed.log and finalizer-stderr.log

## Audit scope and outputs

The audit checks current batch manifests plus the original 243-image corpus and the separate Mikania staging. It preserves every original and makes no approval decisions.

- SHA-256, path containment, image decoding, photo-license allow-list, attribution, observation/source fields, and source PH metadata checks.
- Exact hashes, source observation links, iNaturalist photo identity and perceptual similarity across all three corpora; cross-label similarity is flagged for review rather than treated as proof of a wrong label.
- Explicit routing of native/cryptogenic status conflicts, introduced-only evidence, unresolved names and technical/provenance issues.
- Candidate field-photo, herbarium and unknown-domain screens from URL metadata. These are not visually confirmed classifications.
- Region coverage only when Luzon, Visayas or Mindanao is explicitly present in source locality text. Other records remain unknown rather than guessed from coordinates or appearance.

Artifacts under storage/datasets/staging/species_100_ph/audit:

- species_inventory.csv: every queue entry and actual versus reported counts.
- curation_queue.csv: image-level issues, similarity component, metadata/domain/region screens and next review route.
- duplicate_components.json: linked-record provenance without deleting images.
- known_synonym_mappings.json: cited alias used for grouping, without changing raw names.
- summary.json and perceptual_cache.json.

The latest snapshot is also saved to docs/species-100-batch-audit-summary.json. During collection it is provisional: some manifests can belong to an in-flight species and have no completed checkpoint yet. Only the finalizer's successful reconciliation constitutes the final result.

## Verification performed

Ran the real snapshot audit successfully and syntax-checked both scripts. A temporary fixture verified that a corrupt checksum is flagged, cross-corpus/cross-label image similarity is detected, a native-status conflict is held, all labels remain pending and input manifests stay byte-for-byte unchanged.

## Completion boundary

Part 2B completes technical organization and explicit holds. It does not resolve every scientific disagreement, independently verify every coordinate, visually confirm image domains or approve species labels. Those unresolved items remain in Part 2C before any expanded training corpus is accepted.

## Network recovery

The network-interrupted pass recorded outcomes for all 100 entries, including 16 source errors, with 545 records saved. The collector and expired finalizer were restarted after provider connectivity checks succeeded. Current logs: logs/stderr-network-resume.log and logs/finalizer-network-stderr.log. Completed entries are skipped; failed entries are retried. The old completion marker is cleared before resumption so the finalizer cannot mistake the previous interrupted pass for the new completed pass. Do not launch another collector while the PID in worker.pid is running.
