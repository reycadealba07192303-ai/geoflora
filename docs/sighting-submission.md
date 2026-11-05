# Local geotagged sighting submission

Implemented October 23, 2026; updated October 26 with authenticated Admin/User access. Open http://127.0.0.1:5173, sign in and select **Report a sighting** under FIELD NOTEBOOK. See [roles and automatic training](roles-and-automation.md) for first-admin setup and worker startup.

The latest upload/result/report/receipt flow and PDF export supersede the earlier receipt layout. See [identification and report flow](identification-report-flow.md). Reports now retain trusted identification descriptions/citations when an identification ID is supplied, and Admin-approved labels/descriptions are reflected in saved reports.

The form accepts a JPEG/PNG/WebP photo (up to 20 MB), an optional user-reported species suggestion, a place name or landmark, GPS or manual latitude/longitude, local observation date/time, notes and explicit submission consent. Identification hands off the photo and species suggestion to the report form. Permission denial provides a manual coordinate fallback. Map-pin selection, owner correction/withdrawal and the retention policy were added in Part 8 (see part-8-sightings.md).

Next.js POST /api/sightings validates the data and decodes/normalizes images to metadata-stripped JPEGs at up to 1600 pixels. A single MongoDB document stores the photo with GeoJSON Point coordinates in longitude/latitude order, observation time in UTC, separate server submission time, location method/accuracy and pending status. The location has a 2dsphere index. Photo and record are persisted together; an exact retry uses a unique submission ID and payload hash to return the same record. Changed data under the same ID returns 409. A new form edit creates a new submission identity.

Storage defaults to local mongodb://127.0.0.1:27017/geoflora, collection sightings. Configure GEOFLORA_MONGODB_URI for another loopback MongoDB/database. No credentials are stored in source. Report photos are stored as database binary data, not in the training corpus or public static folder.

This feature is a local development workflow: requests require loopback host and matching Origin, and the server binds 127.0.0.1. User sessions can submit and retrieve their own reports/photos/PDFs; Admin sessions can review workspace records. Legacy reports without an owner are Admin-only. User-reported suggestions are unverified; server-bound identification snapshots are stored separately as prediction data. Manual coordinates are range-checked, not independently verified as Philippine locations.

Updated October 25, 2026: submission receipts show the server-recorded creation time in Philippine time, separately from the observation time. **View report on sightings map** opens the saved record. **Sightings map** in the sidebar loads the latest 500 persisted reports through local-only GET /api/sightings, with amber pending-review markers, a selectable report list and date/location details. The listing excludes photos, payload hashes and submission request IDs. Map tiles and embedded map previews require an internet connection to OpenStreetMap; stored report coordinates and details remain available if tiles fail. The map is a view of reported suggestions, not verified species distribution. Full model scores are not persisted with these reports.

## Validation

Suggested-name selection: a suggested name from identification automatically becomes the report dropdown selection. Names absent from the preset list appear as a custom user-suggested option. Editing the suggestion updates the selection; clearing it restores the original AI/unknown value if that suggestion was still selected. Preset scientific/common names match without case differences. A manual dropdown override is allowed. This changes only the user-reported suggestion, not the AI result or review status.

Identification feedback (October 25, 2026): after any prediction, users can describe the plant and suggest a common/scientific name. Both fields pass to the report form and persist separately as plantDescription and suggestedSpecies. They never replace an uncertain AI result or create a verified species label. The description is supporting review text; the present image classifier does not run text-based identification.

An unchecked-by-default, optional trainingConsent checkbox records permission to consider the photo/description for future training. The server alone sets trainingCandidateStatus to pending_review when consent is yes, otherwise not_requested. Admin-only GET /api/sightings?trainingCandidates=1 lists opted-in pending candidates. Admin Review & training can verify labels/provenance/rights or reject candidates. Once enough approved photos accumulate, the automatic worker exports a versioned grouped dataset and trains/evaluates a candidate. User suggestions never become approved labels automatically. See roles-and-automation.md for defaults and activation policy.

Photo markers: the sightings map uses the actual report photo in a 52-pixel thumbnail marker, with an amber pending-review border. Selecting a marker shows its larger photo and report metadata. Local-only GET /api/sightings/[id]/photo returns the saved JPEG; ?thumbnail=1 returns a 120x120 crop. Invalid IDs return 400, missing reports return 404, and foreign origins return 403. Images have private/no-store caching and same-origin resource headers.

- Web typecheck and production build passed.
- scripts/smoke_sightings.py passed against a real production-mode Next.js server on port 5174 and isolated geoflora_sightings_validation MongoDB database.
- Verified persistence, normalized photo bytes, coordinate order, separate times, same-request retries and simultaneous retries saved once, changed-payload conflicts, invalid coordinates/consent/time/accuracy/image handling and foreign-origin rejection.
- Evidence: docs/sightings-smoke-evidence.json. Two fixture reports are retained only in the isolated validation database.
- GPS permission and mobile camera behavior require a real browser/device check; no browser interaction test is claimed.

To reproduce the integration check, first build apps/web. Start a separate server there with GEOFLORA_MONGODB_URI=mongodb://127.0.0.1:27017/geoflora_sightings_validation on port 5174, then run services/ml/.venv/Scripts/python.exe scripts/smoke_sightings.py from the repository root. Do not run the fixture script against the normal geoflora database.

Normal startup from apps/web: npm run dev or npm run start after a build. The launched local server PID/logs are in storage/logs. Database failures show a retry message and preserve the unchanged submission ID within the mounted form. Closing/reloading the page does not preserve an unsent draft.
