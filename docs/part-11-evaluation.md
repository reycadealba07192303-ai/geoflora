# Part 11: system evaluation

Run on October 27, 2026 (Philippine time). The automated performance, reliability, failure, access and accessibility evaluation is **complete**. The usability study with intended users is **prepared but not yet conducted**: it needs real participants. The study kit is [part-11-usability-kit.md](part-11-usability-kit.md), and sessions are recorded in the **Usability study** page.

## Test conditions

| Item | Value |
|---|---|
| Hardware | 13th Gen Intel Core i7-13620H (10 cores / 16 threads), 16 GB RAM |
| OS / runtime | Windows 11 Home 26200; Node 22.19 with Next.js production build (`next start`); Python 3.11.9 with TensorFlow 2.17.1; MongoDB 8.0 |
| Network | Loopback: client, web, inference and database on one machine. No mobile network or internet latency is included |
| Model | Live `mobilenetv2_v3_seed42`, threshold 0.80 |
| Dataset | Isolated `geoflora_part11_validation`: read-only copy of the 15,938 catalog and 18,718 staging records, plus 2,000 synthetic reports around 40 Philippine centres (70% verified) |

Full results: [part-11-system-evaluation.json](part-11-system-evaluation.json), produced by `scripts/evaluate_system_part11.py`.

## Results against the Part 1 targets

The Part 1 targets are still **proposed, not owner-confirmed**.

| Area | Target | Result | Met? |
|---|---|---|---|
| Identification | p95 upload-to-result ≤ 5 s, ≤ 5 MB photos, one user, ≥ 30 timed requests | 40 requests of real photos up to 1.3 MB, all HTTP 200: p50 155 ms, **p95 228 ms**, max 242 ms. With 5 concurrent users: p95 743 ms, no errors | Yes, on loopback |
| Dashboard | p95 filtered map/API ≤ 3 s under representative data and load | 8 endpoints (map, filtered map, analytics, filtered analytics, overview, catalog search and filter, review queue), 30 requests at 1 user and 100 at 10 concurrent users. Worst p95 was **170 ms** (map, 1,900 points returned), with no errors | Yes, on loopback |
| Reliability | ≥ 99% success in a 100-request controlled run; every defined failure gives a clear, recoverable error; retries never duplicate | **100/100** valid requests succeeded (30 identifications, 30 submissions, 40 reads). Failure cases are listed below | Yes |
| Access / data integrity | All permission and location/time checks pass; pending is never shown as verified | Regression suites passed: access 57, sightings Part 8 39, review Part 9 34, map/analytics Part 10 23 (recomputed against the database), identification 13 failure cases | Yes |
| Usability | ≥ 90% of core tasks completed without help, SUS ≥ 70, ≥ 10 participants across groups | **Not measured.** No sessions have been held. The protocol, consent, tasks, SUS and recorder are ready and tested | **No (not yet run)** |
| Model quality (Part 5) | Accuracy and macro F1 ≥ 0.85, each species recall ≥ 0.80 | v3: 87.2% accuracy, 82.7% macro F1, Water Hyacinth recall 50%. v5: not approved | **No** |

## Failure scenarios and recovery

| Scenario | How it was tested | Result |
|---|---|---|
| Denied GPS | Chrome with geolocation permission denied, going from identification to report | The report form opens without coordinates and shows "Location access is unavailable. Enter where the plant was found manually." The map pin and typed coordinates work, and the report saved |
| Failed upload | Raw HTTP upload cut off after a third of the photo, then retried with the same submission ID | No partial record. The retry returned 201, a second retry was replayed, and 1 record exists |
| Duplicate retries | 5 simultaneous identical submissions | 1 record; one 201 and four replays |
| Invalid images | GIF, non-image bytes, image under 64 px, file over 20 MB | 415, 422, 422 and 413, each with a message |
| Inference outage | A second inference service (port 8001) was stopped during use, then restarted, without restarting the web app | 200, then 503 "The local ML inference service is not reachable. No prediction was made." with health 503, then 200 after restart |
| Database outage | A throwaway mongod (port 27999) was stopped during use, then restarted, with a submission retried under the same ID | Submit and sign-in returned 503 with "your submission ID is preserved" / "The account database is unavailable." After restart the same submission saved once (201, 1 record) |
| Inference timeout, malformed response, reset | Part 6 fake-server cases, rerun | 504, 502 and 503, with messages |

The live inference service, live database and active model were never stopped or changed. The model hash was verified.

## Accessibility and mobile layouts

`scripts/audit_accessibility_part11.mjs` ran axe-core 4.10.2 with the WCAG 2.0/2.1 A and AA rules. It scanned 12 screens at 1440 px desktop and 390 px mobile, 24 scans in all: setup/sign-in, overview, identify, identification result, report form with GPS denied, report view, occurrence map, review queue, species catalog, account settings, manage accounts and usability study. Evidence: [part-11-accessibility-audit.json](part-11-accessibility-audit.json).

- **First run: issues found and fixed.**
  - Color contrast below 4.5:1 for muted text: the global `--muted` token (3.5:1) and the content-area override (4.47:1); Overview greys (2.4–4.4:1); identification step numbers; notice text (4.3:1).
  - The map list `div` had an `aria-label` without a role.
  - Fixes: muted text is now `#5f6b62` (5.6:1 on white), notices are 6.2–6.5:1 and the amber chip is 5.5:1; the map list became a labelled `region`.
- **Final run:** **0 violations** in all 24 scans and **no horizontal overflow** at 390 px.
- Earlier per-part keyboard and mobile checks also hold: the skip link, labelled controls, focus-trapped mobile drawer and status messages announced with `role="status"`/`alert`.
- **Limits.** Automated checks cover only part of WCAG. A manual screen-reader and keyboard walk-through with users is still needed, and it fits into the usability sessions.

## Material issues fixed in Part 11 and rechecked

- The contrast and ARIA fixes above. The audit was rerun with 0 violations, and every regression suite passed afterwards.
- No functional defects were found in the performance, reliability or failure tests.

## Unmet or open criteria

1. **The usability study has not been conducted.** It needs at least 10 consenting participants across environmental officers, researchers and public users. Run it with the kit. The recorder computes completion, times, errors and SUS against the targets.
2. **Model quality targets are not met** (see Part 5). The live model is an owner-authorized experimental activation.
3. **The figures are loopback only.** Real phones, mobile networks and the deployment host can be slower. Re-measure in Part 12 staging, and measure on a physical phone, including the camera, during the study.
4. **The Part 1 targets are still proposed.** The owner should confirm or revise them before the final report.
