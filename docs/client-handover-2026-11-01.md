# GeoFlora client handover — 1 November 2026

## What the demo supports

The local demo's CNN is `mobilenetv2_v3_seed42`. It classifies only:

- Hagonoy — *Chromolaena odorata*
- Lantana — *Lantana camara*
- Water Hyacinth — *Pontederia crassipes*

The active confidence threshold is 0.80. A low-scoring result is returned as uncertain with no assigned species. Other plants may still receive a high score because the CNN is a closed-set classifier; users and reviewers must not treat its score or a contributor's suggested name as confirmed identification. A human reviewer records a confirmed species separately from the original CNN prediction.

Historical v3 test accuracy is 87.18% (34/39), with 50% Water Hyacinth recall (4/8). This is a small, previously inspected test partition, not an independent estimate of field performance. The requested 95% accuracy has not been established. The 11-class model is a research-stage expansion, not the active model; see the [technical summary](client-delivery-technical-summary-2026-11-01.md).

## Start the local demonstration

Prerequisites: Windows, Node.js ≥20.19, the project Python environment, and local MongoDB. Keep `apps/web/.env.local` private; it contains environment-specific credentials. The ML and web services read the same configured values.

1. Start the local MongoDB service using the machine's existing MongoDB service configuration.
2. In a PowerShell window, start the ML API:

   ```powershell
   Set-Location C:\Users\reyca\geoflora
   .\services\ml\.venv\Scripts\python.exe -m geoflora_ml.inference
   ```

3. In a second PowerShell window, start the web application:

   ```powershell
   Set-Location C:\Users\reyca\geoflora\apps\web
   npm run dev
   ```

4. Open `http://127.0.0.1:5173/`, sign in with the prepared demo account, and use **Identify**. Use photo upload for the demo; physical-device camera behavior was not checked in the final integration pass.
5. For reviewer/admin demonstration, submit a report and verify it from **Review & training**. Pending reports are not confirmed map observations.

The auto-training worker was not running during the handover checks. If you intentionally start it for future training, restart it after pulling this safety change so it uses the approval-required promotion behavior. Without the worker, candidate training jobs and administrator approvals remain queued until it is started.

The verified workflow evidence is [client-demo-e2e-smoke-2026-11-01.json](client-demo-e2e-smoke-2026-11-01.json). That integration used a disposable database and removed it afterward. It validates application behavior, not botanical truth or accuracy.

## Model improvement and approval workflow

1. Keep new source images pending until rights, provenance, visible label, and a human reviewer's rationale are recorded. AI screening and iNaturalist research-grade status alone do not qualify a staging image for training. Rejected, pending, AI-only, research-grade-only, or license-ineligible staging rows are excluded.
2. A contributor report can become a training input only when the contributor opted in and the report has an approved verified label. Rejected or unreviewed reports and non-consented reports are excluded.
3. The worker also excludes all curated historical test hashes and observation identities and filters perceptual near-duplicates. The boundary check is recorded in [training-holdout-boundary-audit-2026-11-01.json](training-holdout-boundary-audit-2026-11-01.json).
4. Training and validation produce a versioned candidate under `storage/models/candidates/`; its dataset manifest, model mapping, training record, and `evaluation.json` stay with that version. Candidates that fail the quality or live-comparison gates remain experimental and cannot be promoted.
5. For an eligible candidate, an administrator reviews the overall and per-class evaluation in **Review & training**, enters a rationale, and explicitly approves promotion. The worker checks the model, mapping, evaluation hashes and gates again before activation. Promotion is not automatic.
6. Promotion saves the prior live model, mapping, species list, and activation metadata under `storage/models/previous/`. The active metadata records the candidate version, model/mapping checksums, evaluation path/checksum, approval, and backup path.

The focused staging-export check currently finds **zero eligible staging images** because the staged records do not yet have the required human reviewer and rationale. This does not disable future training: new qualifying consented reports can still queue, and staged records can be reviewed and approved before a later dataset freeze.

To restore a saved snapshot from the GeoFlora project root:

```powershell
.\services\ml\.venv\Scripts\python.exe scripts\model_promotion.py `
  --rollback-to storage\models\previous\<snapshot-folder> `
  --reason "Describe the issue and the decision to restore the previous version"
```

The rollback command preserves the outgoing version as another snapshot, records the from/to model versions and reason, republishes/reloads if hosting is configured, and restores the outgoing version if reload fails. Check the configured hosting target before running a rollback on a connected production environment.

Focused checks for promotion approval, rollback, review eligibility, licensing and historical-test holdouts:

```powershell
Set-Location C:\Users\reyca\geoflora
& .\services\ml\.venv\Scripts\python.exe -m pytest services\ml\tests\test_promotion_safety.py services\ml\tests\test_licensing.py -q
& .\services\ml\.venv\Scripts\python.exe scripts\verify_weak_review_training_hold.py
& .\services\ml\.venv\Scripts\python.exe scripts\audit_training_holdout_boundaries.py
```

## Readiness status

**Local client demo: ready for the tested upload/report/review/map workflow.** No critical software blocker was found for that scope. Confidence and accuracy caveats above must be disclosed; use the three-class model only.

**Production deployment: not ready.** Part 12 still requires production HTTPS and secret configuration, backup/recovery and service monitoring, staging verification on the target host, and an operational decision about who can approve model promotion. A fresh blind field-photo benchmark is also needed before making an independent accuracy or 95% claim. See the [deployment readiness checklist](client-demo-readiness-2026-11-01.md).
