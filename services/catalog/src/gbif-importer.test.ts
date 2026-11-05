import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  buildUpsertOperations,
  loadCatalogRecords,
  validateImportConfirmation,
  validateLocalMongoUri,
} from "./gbif-importer.js";

const fixtureRow = {
  accepted_taxon_key: "VXC6",
  accepted_scientific_name: "Cleistanthus vestitus Jabl.",
  family: "Phyllanthaceae",
  genus: "Cleistanthus",
  source_taxonomic_status: "ACCEPTED",
  source_taxon_keys: '["VXC6"]',
  source_scientific_names: '["Cleistanthus vestitus Jabl."]',
  source_taxonomic_statuses: '["ACCEPTED"]',
  source_iucn_red_list_categories: '["NT"]',
  source_usage_details:
    '[{"source_taxon_key":"VXC6","scientific_name":"Cleistanthus vestitus Jabl.","taxonomic_rank":"SPECIES","taxonomic_status":"ACCEPTED","occurrence_count":21,"family":"Phyllanthaceae","genus":"Cleistanthus","iucn_red_list_category":"NT"}]',
  source_occurrence_count: "21",
  source_usage_count: "1",
  source_country: "PH",
  source_kingdom: "Plantae",
  source_download_key: "0038372-260928105237408",
  source_download_doi: "10.15468/dl.r3a2uq",
  catalog_review_status: "staged_pending_taxonomic_and_source_review",
  ecological_status: "",
  ai_model_supported: "false",
};

function csvWithRows(rows: Record<string, string>[]): string {
  const fields = Object.keys(rows[0]);
  const escape = (value: string) => `"${value.replaceAll('"', '""')}"`;
  return [fields.join(","), ...rows.map((row) => fields.map((field) => escape(row[field])).join(","))].join("\n");
}

const provenance = {
  staging_csv_sha256: undefined,
  source_file_sha256: "source-file-hash",
  source_dataset: {
    key: "0038372-260928105237408",
    doi: "10.15468/dl.r3a2uq",
    citation: "GBIF.org (21 October 2026) GBIF Occurrence Download",
  },
};

test("maps source taxonomy and provenance while keeping statuses pending", () => {
  const record = loadCatalogRecords(csvWithRows([fixtureRow]), provenance)[0];
  assert.equal(record.acceptedTaxonKey, "VXC6");
  assert.equal(record.acceptedScientificName, "Cleistanthus vestitus Jabl.");
  assert.deepEqual(record.sourceTaxonKeys, ["VXC6"]);
  assert.equal(record.source.occurrenceCount, 21);
  assert.equal(record.sourceUsageDetails[0].occurrenceCount, 21);
  assert.deepEqual(record.ecologicalStatuses, []);
  assert.equal(record.reviewStatus, "pending");
  assert.equal(record.aiModelSupported, false);
});

test("rejects a duplicate stable taxon key in the manifest", () => {
  assert.throws(
    () => loadCatalogRecords(csvWithRows([fixtureRow, fixtureRow]), provenance),
    /Duplicate accepted taxon key/,
  );
});

test("refuses records with unsupported review or AI status", () => {
  assert.throws(
    () =>
      loadCatalogRecords(
        csvWithRows([{ ...fixtureRow, catalog_review_status: "approved" }]),
        provenance,
      ),
    /Non-pending review status/,
  );
  assert.throws(
    () =>
      loadCatalogRecords(csvWithRows([{ ...fixtureRow, ai_model_supported: "true" }]), provenance),
    /Refusing AI-supported/,
  );
});

test("builds stable-key upserts that do not overwrite review fields", () => {
  const [operation] = buildUpsertOperations(loadCatalogRecords(csvWithRows([fixtureRow]), provenance));
  assert.ok("updateOne" in operation);
  if (!("updateOne" in operation)) return;
  assert.deepEqual(operation.updateOne.filter, {
    taxonomyAuthority: "GBIF",
    acceptedTaxonKey: "VXC6",
  });
  assert.equal(operation.updateOne.upsert, true);
  assert.ok("$setOnInsert" in operation.updateOne.update);
  assert.equal(operation.updateOne.update.$set?.reviewStatus, undefined);
});

test("only permits loopback MongoDB hosts", () => {
  assert.doesNotThrow(() => validateLocalMongoUri("mongodb://127.0.0.1:27017"));
  assert.doesNotThrow(() => validateLocalMongoUri("mongodb://localhost:27017"));
  assert.throws(() => validateLocalMongoUri("mongodb://example.com:27017"), /localhost/);
  assert.throws(() => validateLocalMongoUri("mongodb+srv://example.com/catalog"), /localhost/);
});

test("requires explicit confirmation before full writes", () => {
  assert.throws(
    () => validateImportConfirmation({ allRecords: true, apply: true, confirmFullImport: false }),
    /--confirm-full-import/,
  );
  assert.throws(
    () => validateImportConfirmation({ allRecords: true, apply: false, confirmFullImport: true }),
    /requires both/,
  );
  assert.doesNotThrow(
    () => validateImportConfirmation({ allRecords: true, apply: true, confirmFullImport: true }),
  );
});

test("parses the real processed manifest and limits the safe sample", async () => {
  const manifestPath = new URL(
    "../../../storage/datasets/taxonomy/gbif_philippines/processed/gbif_philippines_plantae_full_0038372-260928105237408_staging.csv",
    import.meta.url,
  );
  const provenancePath = new URL(
    "../../../storage/datasets/taxonomy/gbif_philippines/processed/gbif_philippines_plantae_full_0038372-260928105237408_provenance.json",
    import.meta.url,
  );
  const [manifest, provenanceJson] = await Promise.all([
    readFile(manifestPath, "utf8"),
    readFile(provenancePath, "utf8"),
  ]);
  const records = loadCatalogRecords(manifest, JSON.parse(provenanceJson), 100);
  assert.equal(records.length, 100);
  assert.equal(new Set(records.map((record) => record.acceptedTaxonKey)).size, 100);
});
