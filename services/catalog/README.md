# GeoFlora species catalog importer

This standalone TypeScript service uses Mongoose and local MongoDB for the
searchable species catalog. It does not change the Vite UI, the Python ML
service, or the image training dataset. GBIF rows remain pending human review;
occurrence records do not establish native, endemic, or invasive status.

## Install and validate

From the repository root:

```powershell
Push-Location services\catalog
npm install
npm test
npm run build
Pop-Location
```

The source GBIF archive and its downloaded CSV are retained as received under
`storage\datasets\taxonomy\gbif_philippines\raw`. The reproducible processing
pipeline writes its cleaned candidates and audit files under
`storage\datasets\taxonomy\gbif_philippines\processed`.
The GBIF `SPECIES_LIST` download is tab-delimited even though its filename
ends in `.csv`. Existing Python staging tooling validates ranks and taxonomic
status, reconciles synonyms by accepted GBIF taxon key, and writes the
source-attributed candidate CSV and audit/provenance sidecars.
The processed directory also contains a row-level unresolved/rejected CSV with
reason flags; per-usage occurrence counts remain embedded in each eligible
candidate record.

## Dry-run the first 100 candidate species

```powershell
Push-Location services\catalog
npm run import:gbif -- `
  --input ..\..\storage\datasets\taxonomy\gbif_philippines\processed\gbif_philippines_plantae_full_0038372-260928105237408_staging.csv `
  --limit 100
Pop-Location
```

Dry-run is the default. `--apply` is mandatory before writes. Imports reject
non-loopback MongoDB hosts, check the source manifest checksum and provenance,
and use bulk upserts keyed by `(taxonomyAuthority, acceptedTaxonKey)`.
Re-imports update source metadata without overwriting review decisions.
Ecological status starts empty and AI support remains disabled.

The applied validation used the isolated local database
`geoflora_catalog_validation`, collection `species_catalog_100_test`. The
import was repeated; the second run matched the same 100 taxon keys and
upserted zero new documents.

The collection is `geoflora.species_catalog`; it is separate from the legacy
`species_catalog_staging` collection. Do not run the full import until the
100-record validation has been reviewed and explicitly approved. Once approved,
run:

```powershell
Push-Location services\catalog
npm run import:gbif -- `
  --input ..\..\storage\datasets\taxonomy\gbif_philippines\processed\gbif_philippines_plantae_full_0038372-260928105237408_staging.csv `
  --all-records `
  --confirm-full-import `
  --apply
Pop-Location
```

**Status (2026-10-27):** the full import into `geoflora.species_catalog` (15,938 records, imported 2026-10-22) was confirmed by the owner as approved. Its records were set to `approved` by owner attestation in batch `owner-catalog-approval-20261026T171926Z` via `scripts/approve_catalog_owner.py` (revertible). This approves catalog inclusion only; ecological status and AI support remain unverified. See `docs/part-9-review-catalog.md`.
