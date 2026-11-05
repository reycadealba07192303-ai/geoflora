# Admin, User and automatic training

Implemented and verified October 26, 2026 (Philippine time). This is the local workspace on http://127.0.0.1:5173.

## Account setup and access

Open the app and create the first administrator with your own username and password (at least 10 characters). There are no default production credentials. Once an administrator exists, public registration creates User accounts only; the client cannot request an Admin role. A unique bootstrap key prevents concurrent first-admin creation.

Admin opens **Review & training** after sign-in. Admin can see workspace reports/photos, verify or reject training labels, and monitor job results. User opens **Identify a plant**, can submit reports, and sees only their own reports and photos. Existing reports without an owner remain visible to Admin only. Map coordinates for another user's pending reports are not exposed to Users.

Roles are checked by the APIs, not just hidden navigation. Passwords use salted scrypt hashes. Sessions use random tokens stored as hashes, expire after eight hours, use HttpOnly/SameSite=Strict cookies, and are invalidated on logout. Account/report APIs retain the loopback and Origin guards. This is local authentication, not a claim of a completed shared/public deployment; password reset and administrator account management were added in Part 7 (see part-7-access.md).

## What is automatic

Valid photo submissions are accepted after automatic format, size, decode and storage checks. An opted-in submission becomes a pending training candidate. A user suggestion or a high image-model score alone does not verify the species label. Unsupported and uncertain labels require review rather than becoming the model's own ground truth.

Admin verifies the species and description, records a citation/rationale and confirms Philippine invasive status/provenance. Known labels start with the six frozen v4 classes; Admin may add verified species. Unidentified reports remain reviewable without training consent, but unconsented photos cannot enter training or be shared as reference matches with other users.

After each consented approval, a job is queued automatically by default. The background worker polls every 15 seconds, keeps earlier approved contributions, exports a versioned dataset, removes duplicates, trains a fresh candidate and evaluates it. A new class without three independent groups is held with waiting_for_data until more photos arrive. No training runs inside a web request. Only one job occupies the active training slot; failed/expired jobs retain their error details rather than retrying endlessly. See identification-report-flow.md for the distinction between immediate reviewed-photo lookup and neural-network generalization.

Training uses the existing experimental v4 corpus plus the approved reports. Its new grouped split is not a fresh prospective benchmark. Augmented views are training-only. A candidate must meet at least 85% accuracy, 85% macro F1 and 80% recall per class for the numerical quality-target flag; tiny test counts still limit conclusions. The worker does **not automatically activate** a candidate, even when numerical targets pass. Deployment review remains separate. The active model stays available during training.

## Start and monitor

- Start the web app from apps/web with npm run start after a build.
- From the repository root, run scripts/start_training_worker.ps1 to start the hidden worker. It uses the same GEOFLORA_MONGODB_URI as the web app; default mongodb://127.0.0.1:27017/geoflora.
- Admin **Review & training** polls pending labels, batch counts, the last worker activity, job status, accuracy and macro F1.
- Worker state: storage/logs/auto-training-worker-status.json. PID/stdout/stderr are alongside it. Training job logs: storage/logs/training/<job-id>.log.
- Optional local configuration: GEOFLORA_MIN_TRAINING_REPORTS (default/minimum 1). This controls when an eligibility check is queued, not the minimum evidence required for a trainable class.
- Each job saves a frozen dataset under storage/datasets/curated/auto_<job-id> and a candidate under storage/models/candidates/auto_<job-id>.

The worker must be running for queued jobs to execute. The startup helper is not an operating-system service and should be run again after a machine restart. Sign-in sessions are not background-worker credentials; the worker accesses only the configured local database.

## Verification

- TypeScript, production build and all 27 existing ML tests passed.
- scripts/smoke_roles_training.py passed in geoflora_roles_validation with synthetic fixture photos: first-admin setup restrictions, no self-elevation, cookie flags, unauthorized Admin access, per-user report/photo access, server-owned approval fields, required review confirmation, idempotent review and logout.
- The isolated test actually queued a job, exported data, trained and evaluated a model, and confirmed the active model hash stayed unchanged. Its synthetic candidate is not a real botanical evaluation and was not activated. Evidence: docs/roles-training-smoke.json.
- scripts/smoke_sightings.py passed separately in geoflora_sightings_validation after being updated to authenticate a fixture administrator.
- Real Chrome checks exercised user registration, user-only navigation, Admin login and job results, logout form reset and a 390px mobile sign-in layout. Screenshots: storage/logs/ui-preview/roles-admin-desktop.png and roles-signin-mobile.png.

Validation accounts and synthetic jobs live only in their named validation databases. The fixed fixture password in test scripts is never installed in the normal geoflora database.
