# GBIF Philippine Species Catalog Staging

This tool requests or processes GBIF's authenticated `SPECIES_LIST` occurrence
download, then stages source-attributed accepted species separately from
GeoFlora's image-training dataset.

The output is an occurrence-derived candidate list, not a complete national
flora checklist. A count from this download must not be represented as the
approximately 11,435 Philippine wild-flora reference statistic. Ecological
status is left blank, every staged taxon requires review, and no record is
enabled as an AI class.

## Build a searchable master export from acquired sources

The current source snapshots include the complete locally staged GBIF
Philippines/Plantae Species List, GRIIS Philippines, GBIF regional flora
checklists, and the Philippines subset of MalNAF. Build the CSV/JSON export and
source-usage audit with:

```powershell
python .\scripts\species_catalog\build_master_catalog.py
python .\scripts\species_catalog\build_image_readiness.py
```

Outputs are written to `storage/species_catalog/exports`. The builders check
source checksums, preserve source rows and license/provenance fields, keep
ecological assertions unverified, refuse ambiguous name joins, and compare
staged image checksums with every curated test partition. They do not download,
approve, train, or promote anything. Co's Digital Flora is linked for manual
verification only because its copyright terms restrict bulk checklist copying.

## Configure GBIF access

Create a GBIF account, then set credentials in the local PowerShell session.
Never paste the password into chat or commit it:

```powershell
$env:GBIF_USER = "your-gbif-username"
$env:GBIF_PASSWORD = Read-Host "GBIF password"
$env:GBIF_EMAIL = "your-email@example.org"
```

## Request, check, and download

Run from the repository root:

```powershell
python .\scripts\species_catalog\gbif_species_list.py request
python .\scripts\species_catalog\gbif_species_list.py status DOWNLOAD_KEY
python .\scripts\species_catalog\gbif_species_list.py download DOWNLOAD_KEY
```

The request key is printed by the first command. GBIF prepares occurrence
downloads asynchronously; wait for `SUCCEEDED` before downloading. The request
uses the official `SPECIES_LIST` format and stores the resulting DOI and
citation in `storage\species_catalog\downloads\DOWNLOAD_KEY.json`. Credentials
are read only from environment variables and are never written to that file.

## Process an already downloaded CSV

For the GBIF download `0038372-260928105237408`, the supplied TSV-formatted
`.csv` contains 32,472 rows. Its request metadata was independently checked
against the public GBIF API: the status is `SUCCEEDED`, the download DOI is
`10.15468/dl.r3a2uq`, and the recorded filter is country Philippines plus
taxon key Plantae from the Catalogue of Life checklist. A `.csv` extension does
not mean comma-delimited; the importer detects the tab separator.

Run this from the repository root to stage the bounded 100-record validation
sample:

```powershell
.\services\ml\.venv\Scripts\python.exe `
  .\scripts\species_catalog\gbif_species_list.py stage `
  .\0038372-260928105237408\0038372-260928105237408.csv `
  --download-key 0038372-260928105237408 `
  --source-doi 10.15468/dl.r3a2uq `
  --citation "GBIF.org (21 October 2026) GBIF Occurrence Download https://doi.org/10.15468/dl.r3a2uq" `
  --source-record-count 32472
```

The importer treats GBIF taxon keys as opaque alphanumeric identifiers. It
deduplicates synonym usages by `acceptedTaxonKey`, retains source names and
taxonomic statuses, excludes non-species ranks and ambiguous/misapplied names
from the accepted-species candidates, and records the exclusions in an audit.
The output's 100 records validate the import workflow; they are not a
scientifically reviewed or representative sample.

After inspecting the sample, stage all candidate taxa from the same supplied
CSV:

```powershell
.\services\ml\.venv\Scripts\python.exe `
  .\scripts\species_catalog\gbif_species_list.py stage `
  .\0038372-260928105237408\0038372-260928105237408.csv `
  --download-key 0038372-260928105237408 `
  --source-doi 10.15468/dl.r3a2uq `
  --citation "GBIF.org (21 October 2026) GBIF Occurrence Download https://doi.org/10.15468/dl.r3a2uq" `
  --source-record-count 32472 --all-records
```

Review the generated `*_audit.json` and `*_staging.csv` before loading the
candidate records into the local MongoDB staging collection. The import is
idempotent; the earlier 100 rows are matched to their existing GBIF source keys
when the full file is loaded.

## Validate the first 100 accepted species

```powershell
python .\scripts\species_catalog\gbif_species_list.py stage `
  .\storage\species_catalog\downloads\DOWNLOAD_KEY.zip `
  --download-key DOWNLOAD_KEY
```

The default limit stages up to 100 accepted species after reading and auditing
the archive. The CSV and JSON audit report are written to
`storage\species_catalog\staging`. The report distinguishes the total source
rows, non-plant rows, duplicate usages reconciled by accepted GBIF taxon key,
unresolved or conflicting names, unique accepted species available, and the
sample size. It preserves source taxon IDs and names, family/genus, occurrence
counts, download key/DOI, and review status.

After the 100-record source validation has been reviewed, stage the complete
candidate list with:

```powershell
python .\scripts\species_catalog\gbif_species_list.py stage `
  .\storage\species_catalog\downloads\DOWNLOAD_KEY.zip `
  --download-key DOWNLOAD_KEY --all-records
```

This milestone writes staging files only. After review, import a staging file
into the local MongoDB `geoflora` database using the separate importer below.
It writes to `species_catalog_staging`, never to the ML image dataset.

## Local MongoDB staging import

Install the Python service dependencies if needed. PyMongo is included in
`services/ml/pyproject.toml`:

```powershell
Push-Location services\ml
.\.venv\Scripts\python.exe -m pip install -e .
Pop-Location
```

Ensure the local MongoDB service is running. The importer defaults to
`mongodb://127.0.0.1:27017` and database `geoflora`; it rejects remote MongoDB
URIs so this development workflow cannot accidentally write to a shared or
production cluster. Override with `GEOFLORA_MONGODB_URI` only for another
loopback URI, and `GEOFLORA_MONGODB_DATABASE` if needed.

First preview all three existing review-only staging files:

```powershell
.\services\ml\.venv\Scripts\python.exe `
  .\scripts\species_catalog\import_staging_to_mongodb.py --dry-run
```

Then import them into the local staging collection:

```powershell
.\services\ml\.venv\Scripts\python.exe `
  .\scripts\species_catalog\import_staging_to_mongodb.py
```

The import is idempotent by source dataset and source record ID. It preserves
each input CSV row and source provenance, creates indexes, and records an
import audit. Reimports update the source snapshot but do not overwrite review
status or review history. All inserted documents are marked
`catalog_review_status: pending`, `ecological_status_is_verified: false`, and
`ai_model_supported: false`. The imports do not merge names across source
datasets; taxonomic reconciliation and human status review remain a later step.
There is no production catalog collection or API yet.

## Tests

```powershell
.\services\ml\.venv\Scripts\python.exe -m unittest discover `
  -s .\scripts\species_catalog -p "test_*.py" -v
```

## Stage the preserved ZIP under taxonomy storage

The received ZIP is retained at
`storage\datasets\taxonomy\gbif_philippines\raw\0038372-260928105237408.zip`.
The command below reads it in place without extracting or modifying the
original and writes the sample manifest, audit, provenance, and unresolved-row
CSV under `storage\datasets\taxonomy\gbif_philippines\processed`:

```powershell
.\services\ml\.venv\Scripts\python.exe `
  .\scripts\species_catalog\gbif_species_list.py stage `
  .\storage\datasets\taxonomy\gbif_philippines\raw\0038372-260928105237408.zip `
  --download-key 0038372-260928105237408 `
  --source-doi 10.15468/dl.r3a2uq `
  --citation "GBIF.org (21 October 2026) GBIF Occurrence Download https://doi.org/10.15468/dl.r3a2uq" `
  --source-record-count 32472 `
  --output-dir .\storage\datasets\taxonomy\gbif_philippines\processed
```

Add `--all-records` to produce the full cleaned candidate manifest after
reviewing the bounded output. Accepted-name collisions across different GBIF
taxon keys are flagged as unresolved rather than silently merged. Per-usage
occurrence counts and taxonomy are retained with each candidate.
