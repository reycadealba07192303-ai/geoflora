# Batch collection before review

Owner direction, October 23, 2026: collect across the 100-species research queue first; organize and review afterwards instead of stopping after every new species.

The batch worker is started locally in the background with stdout/stderr logs. This document describes a running job, not a claim that 100 datasets have already been obtained.

## Initial pass

- Up to 10 distinct normalized image checksums per species (up to 1,000 in total if available).
- Philippine-filtered iNaturalist and GBIF sources, retaining the existing photo-license allow-list and attribution requirements.
- One API page and at most 40 candidate attempts per source/species.
- One GiB total staging image budget across all taxon folders; oversized/unsafe downloads remain rejected.
- Staging only: storage/datasets/staging/species_100_ph/<source_taxon_id>/raw.
- Source IDs/checksums support resumption; report checkpoints after every attempted species. Failed sources are recorded and do not stop the next species.
- Current unresolved exact names are recorded as taxonomy_unresolved rather than guessed. Recent zero-PH iNaturalist probes are skipped, with GBIF still attempted for resolved names.

Ten images per species is an initial batch feasibility target, not adequate training data or a cap on future collection. Some species will produce fewer or no images. Ten distinct checksums may include near duplicates; deduplication and independent observation grouping follow collection.

## Progress and logs

- docs/species-100-collection-progress.json: attempted species, species with images, total records and source outcomes.
- storage/datasets/staging/species_100_ph/logs/worker.pid: last launched worker process ID.
- logs/stdout-resumed.log and logs/stderr-resumed.log: current worker logs.
- The report's pass_finished_at_utc appears only when the worker reaches the end of the queue.

Check process status using the recorded PID before launching another copy. To resume a stopped job from the repository root:

```powershell
.\services\ml\.venv\Scripts\python.exe scripts/collect_research_batch.py
```

Completed species are skipped. A storage-cap stop needs an explicit budget/code adjustment before further downloading. Do not run two copies simultaneously against the same staging root.

## After the batch

1. Summarize actual records/species obtained, missing taxa, failures and storage use.
2. Check integrity, country metadata, licenses, attribution and observation provenance.
3. Group exact/perceptual duplicates across providers and existing corpora; separate field and herbarium images.
4. Resolve taxonomy and ecological conflicts before any class is approved. The queue includes introduced-only, native-conflict and cryptogenic candidates; downloaded photos do not establish invasive status.
5. Review labels, decide the usable class set, and create new grouped dataset versions before retraining.

All newly downloaded labels remain pending. Existing approvals do not transfer to this research staging corpus. The active species registry, original 243-image manifest, v3 holdouts and model candidate are preserved.
