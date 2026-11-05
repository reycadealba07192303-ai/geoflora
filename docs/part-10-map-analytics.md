# Part 10: occurrence map and analytics

Completed locally on October 27, 2026 (Philippine time). The **Occurrence map** page replaces the earlier sightings map. Builds on [Part 9 review and catalog](part-9-review-catalog.md) and the visibility rules in [Part 8 sightings](part-8-sightings.md).

## Map

- **Visibility and layers.**
  - Reviewers and administrators see every workspace report at its recorded location. Contributors see only their own reports, at exact coordinates. Data comes from `GET /api/occurrences`, capped at the 2,000 most recent matches, with a notice when the cap is reached.
  - **Verified only** is the default. **Include unverified (pending)** adds pending and correction-requested reports, with a notice that their names are contributor suggestions. Rejected and withdrawn reports never appear.
  - Verified reports use the reviewer-confirmed species. Other reports use the contributor's name.
- **Clustering.** Markers are clustered in screen space: reports within the same 64-pixel cell at the current zoom share a numbered circle. Selecting a circle zooms to its reports, and clusters recompute on every zoom. A circle has a green border when all its reports are verified, and amber when any is unverified. A single report shows its photo thumbnail with a status border, or a leaf placeholder if the photo is missing.
- **Filters.** These work together on the map and the analytics, in one row above the map:
  - **Species**, using the species present in the layer.
  - **Observed from/to**, as whole Philippine days.
  - **Reports layer**: verified only, or include unverified.
  - **Limit to map area**, using the current view as a west/south/east/north rectangle.
  - **Clear filters**, which keeps the chosen layer.
- **Density grid (optional).** It shades generalized 0.1° cells from light to dark green by report count, a sequential single-hue ramp. Each cell has a tooltip with its report and species counts.

## Analytics (`GET /api/analytics`)

**What it shows.**

- Total reports and species count.
- Status mix of the included layer.
- **Reports by species**, as horizontal bars.
- **Reports by month observed**, as columns by Philippine-time month. Months with no reports are left out.
- **High report density cells**.
- A data-table view, plus value labels and tooltips on every bar.

**Scope.**

- *workspace* (the default) counts all visible reports but returns only generalized cells: no report IDs, owners or exact coordinates.
- Contributors get workspace analytics for **verified** reports only. They may include their own unverified reports with `scope=mine`.
- Reviewers and administrators may include the pending layer workspace-wide.

**Spatial aggregation method (documented rule).**

| Rule | Value |
|---|---|
| Cell | Fixed 0.1° latitude × 0.1° longitude grid (about 11 km), cell index `floor(coordinate / 0.1)`, counted by report |
| Minimum to display a cell | 3 reports. Sparser cells are suppressed and reported only as a total ("1 sparse cell (2 reports) hidden"), so a cell cannot point to one person's sighting |
| High report density ("hotspot") | A displayed cell with 5 or more reports in the current filters; top 10 listed |
| Sparse warning | Fewer than 20 matching reports: "distribution and trends are not meaningful" |
| Time | Months and date filters use Asia/Manila |

**Meaning and limits.** The page states these in the analytics notice and the hotspot panel:

- Counts are **submitted reports**. They show where people reported plants, not invasion severity, abundance or ecological spread.
- A high-density cell may reflect where people looked.
- Unverified layers are labeled whenever they are included.

**Sparse data and empty filters.**

- A filter with no matches shows explicit empty messages on the map and in the analytics.
- A small total shows the sparse warning.
- Invalid dates, an inverted date range or a malformed bbox return 400 with a message.

**Public location generalization.** Generalization follows the Part 8 rule: 0.1° cells and a minimum count of 3, with no identities or exact points. There is still no unauthenticated access. These are the same aggregates any future public view must use.

## Verification against database queries

- `scripts/smoke_part10.py` passed 23 checks on the isolated `geoflora_part10_validation` database. It inserts 19 synthetic reports spanning 3 grid cells (dense, threshold and sparse), 4 statuses plus withdrawn, two owners, three months and a Manila-midnight boundary. It then **recomputes every count independently from the stored documents** and compares the results. Evidence: [part-10-map-analytics-smoke.json](part-10-map-analytics-smoke.json). The checks covered:
  - Sign-in requirement.
  - Map visibility per role and layer.
  - Exact coordinates and species against the stored records.
  - Combined species, date and area filters.
  - Philippine-day date boundaries.
  - Workspace analytics totals, species, months, cells, suppression, hotspots and the sparse flag, against the database.
  - No identifying fields in analytics.
  - Pending-layer permissions, contributor `scope=mine`, and reviewer layer and status mix.
  - Combined-filter analytics and species options.
  - Empty results and four invalid-input cases.
- `scripts/smoke_part10_ui.mjs` passed 11 checks in headless Chrome on the isolated `geoflora_part10_ui_validation` database. Evidence: [part-10-map-analytics-browser-smoke.json](part-10-map-analytics-browser-smoke.json). Screenshots: `storage/logs/ui-preview/part10-*.png`. The checks covered:
  - The verified default.
  - Clusters at the overview zoom, and a cluster click splitting into markers.
  - Charts rendered.
  - The density grid with its suppressed-cell note.
  - Species filter, the labeled unverified layer, and clear filters keeping the layer.
  - The empty date range, the data table and the 390 px mobile fit.
- Regressions passed: `smoke_part9.py` (34), `smoke_part8.py` (39), `smoke_access.py` (57), typecheck and production build. The live web on 5173 was rebuilt and restarted.

## Limitations

- **Little real data.** The live workspace has 6 reports, all still awaiting review, so the verified map and analytics are empty until reviews happen. The fixtures demonstrate the behavior.
- **No administrative boundaries.** The area filter is the map rectangle; there is no province or municipality filtering.
- **Grid edges.** The 0.1° grid is a fixed lattice, so a dense area that straddles a cell edge splits across cells.
- **Basic clustering.** It is simple screen-space grouping, not a dedicated clustering library, so it is adequate for the current scale (up to 2,000 points).
- **Light theme only.** The map tiles need internet. The charts follow the app's light theme, because the app has no dark mode yet.
