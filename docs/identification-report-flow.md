# Identification, field reports and reviewed learning

Implemented October 26, 2026. The flow is now upload, a separate identification-result screen, report confirmation, a saved receipt with two actions, and a downloadable report.

## Identified plants

1. Upload or capture a photo. The server validates it and returns a possible match, description and species citation.
2. The result screen displays the plant photograph, scientific/common names, model score when applicable, descriptive information and source link.
3. **Create report for this plant** requests GPS permission. With permission, coordinates and observation date/time are filled automatically. Permission denial preserves a manual-coordinate fallback; users must confirm the location before submission.
4. The report is saved with the photo, server-bound identification, descriptive/citation snapshot, observation time and separate server submission time. Observation time is stored as UTC and displayed in Philippine time; it may be adjusted for an older photo.
5. The receipt offers **View result report** and **Create another report**. The latter resets the upload flow.
6. The saved report includes a photo, species, description, map/coordinates, observation and creation timestamps, and citations. Map markers use the actual plant photo, including in the PDF. **Download PDF** returns an actual PDF attachment containing these items. A ?report=<id> URL survives refresh, and report links are available from the sightings map.

An identification is an expiring server record bound to the account and normalized photo hash. Client-supplied species/citation metadata cannot replace that trusted result. An unchanged retry of a saved report uses its saved snapshot even if the temporary identification has expired. Report reads, photo reads and PDF downloads enforce account ownership or Admin access.

PDF street-map tiles are fetched from OpenStreetMap with attribution. If map tiles are unavailable, the PDF explicitly labels its fallback as an offline location diagram, includes the precise coordinates and an OpenStreetMap link, and does not pretend the diagram is a street map. Long descriptions continue onto additional pages.

## Unidentified plants

The result screen asks for a required botanical description and an optional species suggestion. The photo/description is submitted to Admin review with the report. Label review is available even without training consent; absence of consent prevents reuse in training or other users' reference lookups.

Admin checks the image, description, scientific name, Philippine invasive status/provenance and source citation. The reviewer can correct the description, select a known species or add a newly verified species. The approved description/name/citation appear in the saved report. Review records identify the administrator and retain the rationale/time.

## Recognition after approval

Uploading the **same approved photo** (including the stored normalized JPEG) can now return its administrator-reviewed species immediately. It is labeled **Admin-reviewed photo match**, with method verified_reference and no fabricated confidence score. Personal references without training consent are usable by their owner only; consented reviewed references may be used for matching by other accounts. Location, owner and private report metadata are not returned with a shared match.

This exact-photo lookup is distinct from learning to identify different photographs of the species. Approval does not instantly retrain or validate a neural network from one example. With consent, each approval now queues a training eligibility check by default (GEOFLORA_MIN_TRAINING_REPORTS defaults to 1). The worker retains previous approved contributions, groups duplicates and uses all eligible classes in subsequent versions. New classes need at least three independent source/near-duplicate groups for separate train/validation/test partitions; classes below that floor are held and jobs can show waiting_for_data. Three groups is a technical floor, not proof of reliable identification.

Eligible jobs train/evaluate experimental candidates automatically. Passing evaluation gates never changes the live model by itself: an administrator must inspect the saved per-class evaluation and explicitly approve promotion. The worker revalidates the artifact and quality gates before activation. No generalization guarantee is made from a single approval.

## Validation

- TypeScript and production builds passed.
- docs/report-flow-smoke.json records real HTTP checks for cited results, photo-bound report snapshots, map/date fields, report/PDF authorization, a required unknown description, Admin review without training consent and immediate reviewed-photo matching without a numeric model confidence.
- PDF validation loaded the downloaded file and verified two pages, photograph/map images and expected report text. The offline-map fallback was exercised explicitly.
- A second PDF check successfully fetched the actual OpenStreetMap street-map tiles. docs/report-retry-smoke.json records expired-identification retry handling; changed submissions still produce conflicts. Existing report/photo/consent regression checks and all 27 ML tests passed.
- The same isolated test created a synthetic new species: one example entered waiting_for_data; after three independent synthetic examples, the actual worker trained/evaluated a seven-class candidate while preserving the active model. Synthetic labels/data are confined to the named validation DB and candidate artifacts, not the live system.
- docs/report-flow-browser-smoke.json records Chrome checks of the complete upload-to-PDF flow, GPS emulation, report refresh, a 390px mobile layout, unknown-description submission, Admin approval and a reviewed-photo result. Evidence images/downloads are under storage/logs/ui-preview.

Reproduce the HTTP test with a fresh geoflora_report_flow_validation-prefixed local database shared by the test web server and GEOFLORA_MONGODB_URI. Use port 5174 and a minimum of 1. The test uses disposable fixture accounts; do not run it against the live database. Browser validation uses a loopback-only headless Chrome CDP port 9317 and scripts/smoke_report_ui.mjs.
