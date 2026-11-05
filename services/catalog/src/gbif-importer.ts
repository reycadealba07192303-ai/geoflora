import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";
import { parse } from "csv-parse/sync";
import mongoose, { type AnyBulkWriteOperation } from "mongoose";
import { getSpeciesModel, type SpeciesCatalogDocument } from "./species.js";

const DEFAULT_URI = "mongodb://127.0.0.1:27017";
const DEFAULT_DATABASE = "geoflora";
const DEFAULT_COLLECTION = "species_catalog";
const REQUIRED_FIELDS = [
  "accepted_taxon_key",
  "accepted_scientific_name",
  "family",
  "genus",
  "source_taxon_keys",
  "source_scientific_names",
  "source_taxonomic_statuses",
  "source_iucn_red_list_categories",
  "source_usage_details",
  "source_occurrence_count",
  "source_usage_count",
  "source_country",
  "source_kingdom",
  "source_download_key",
  "source_download_doi",
  "catalog_review_status",
  "ai_model_supported",
] as const;

export interface GbifStagingRow extends Record<string, string> {
  accepted_taxon_key: string;
  accepted_scientific_name: string;
  family: string;
  genus: string;
  source_taxon_keys: string;
  source_scientific_names: string;
  source_taxonomic_statuses: string;
  source_iucn_red_list_categories: string;
  source_occurrence_count: string;
  source_usage_count: string;
  source_country: string;
  source_kingdom: string;
  source_download_key: string;
  source_download_doi: string;
  catalog_review_status: string;
  ai_model_supported: string;
}

interface Provenance {
  staging_csv_sha256?: string;
  source_file_sha256?: string;
  source_dataset?: {
    citation?: string;
    doi?: string;
    key?: string;
  };
}

export interface ImportOptions {
  inputPath: string;
  limit?: number;
  allRecords: boolean;
  apply: boolean;
  confirmFullImport: boolean;
  uri: string;
  database: string;
  collection: string;
}

function parseArgs(args: string[]): ImportOptions {
  const options: ImportOptions = {
    inputPath: "",
    allRecords: false,
    apply: false,
    confirmFullImport: false,
    uri: process.env.GEOFLORA_MONGODB_URI ?? DEFAULT_URI,
    database: process.env.GEOFLORA_MONGODB_DATABASE ?? DEFAULT_DATABASE,
    collection: DEFAULT_COLLECTION,
  };

  for (let index = 0; index < args.length; index += 1) {
    const flag = args[index];
    const value = args[index + 1];
    if (flag === "--input" && value) {
      options.inputPath = value;
      index += 1;
    } else if (flag === "--limit" && value) {
      options.limit = Number(value);
      index += 1;
    } else if (flag === "--all-records") {
      options.allRecords = true;
    } else if (flag === "--apply") {
      options.apply = true;
    } else if (flag === "--confirm-full-import") {
      options.confirmFullImport = true;
    } else if (flag === "--uri" && value) {
      options.uri = value;
      index += 1;
    } else if (flag === "--database" && value) {
      options.database = value;
      index += 1;
    } else if (flag === "--collection" && value) {
      options.collection = value;
      index += 1;
    } else {
      throw new Error(`Unknown or incomplete argument: ${flag}`);
    }
  }

  if (!options.inputPath) throw new Error("--input is required.");
  if (options.allRecords === (options.limit !== undefined)) {
    throw new Error("Specify exactly one of --limit N or --all-records.");
  }
  if (options.limit !== undefined && (!Number.isInteger(options.limit) || options.limit < 1)) {
    throw new Error("--limit must be a positive integer.");
  }
  if (!/^[A-Za-z0-9_-]+$/.test(options.database)) {
    throw new Error("Database name contains unsupported characters.");
  }
  if (!/^[A-Za-z0-9_-]+$/.test(options.collection)) {
    throw new Error("Collection name contains unsupported characters.");
  }
  validateImportConfirmation(options);
  validateLocalMongoUri(options.uri);
  return options;
}

export function validateImportConfirmation(
  options: Pick<ImportOptions, "allRecords" | "apply" | "confirmFullImport">,
): void {
  if (options.apply && options.allRecords && !options.confirmFullImport) {
    throw new Error("Full writes also require --confirm-full-import.");
  }
  if (options.confirmFullImport && (!options.apply || !options.allRecords)) {
    throw new Error("--confirm-full-import requires both --apply and --all-records.");
  }
}

export function validateLocalMongoUri(uri: string): void {
  let parsed: URL;
  try {
    parsed = new URL(uri);
  } catch {
    throw new Error("MongoDB URI is invalid.");
  }
  const allowedHosts = new Set(["localhost", "127.0.0.1", "[::1]"]);
  if (!["mongodb:", "mongodb+srv:"].includes(parsed.protocol) || !allowedHosts.has(parsed.hostname)) {
    throw new Error("Catalog imports are restricted to localhost MongoDB.");
  }
}

function parseJsonArray(value: string, field: string): string[] {
  let parsed: unknown;
  try {
    parsed = JSON.parse(value);
  } catch {
    throw new Error(`${field} must contain a JSON array.`);
  }
  if (!Array.isArray(parsed) || parsed.some((item) => typeof item !== "string")) {
    throw new Error(`${field} must contain a JSON array of strings.`);
  }
  return parsed;
}

function parseNonnegativeInteger(value: string, field: string): number {
  if (!/^\d+$/.test(value)) throw new Error(`${field} must be a nonnegative integer.`);
  const parsed = Number(value);
  if (!Number.isSafeInteger(parsed)) throw new Error(`${field} is outside the safe integer range.`);
  return parsed;
}

function parseSourceUsageDetails(
  value: string,
): SpeciesCatalogDocument["sourceUsageDetails"] {
  let parsed: unknown;
  try {
    parsed = JSON.parse(value);
  } catch {
    throw new Error("source_usage_details must contain a JSON array.");
  }
  if (!Array.isArray(parsed) || parsed.length === 0) {
    throw new Error("source_usage_details must contain a nonempty JSON array.");
  }
  return parsed.map((item, index) => {
    if (!item || typeof item !== "object" || Array.isArray(item)) {
      throw new Error(`Invalid source usage detail at index ${index}.`);
    }
    const usage = item as Record<string, unknown>;
    const textFields = [
      "source_taxon_key",
      "scientific_name",
      "taxonomic_rank",
      "taxonomic_status",
      "family",
      "genus",
      "iucn_red_list_category",
    ] as const;
    for (const field of textFields) {
      if (typeof usage[field] !== "string") {
        throw new Error(`source_usage_details ${field} must be a string.`);
      }
    }
    if (
      typeof usage.occurrence_count !== "number" ||
      !Number.isSafeInteger(usage.occurrence_count) ||
      usage.occurrence_count < 0
    ) {
      throw new Error("source_usage_details occurrence_count must be a nonnegative integer.");
    }
    return {
      sourceTaxonKey: usage.source_taxon_key as string,
      scientificName: usage.scientific_name as string,
      taxonomicRank: usage.taxonomic_rank as string,
      taxonomicStatus: usage.taxonomic_status as string,
      occurrenceCount: usage.occurrence_count,
      family: usage.family as string,
      genus: usage.genus as string,
      iucnRedListCategory: usage.iucn_red_list_category as string,
    };
  });
}

export function loadCatalogRecords(
  input: string,
  provenance: Provenance,
  limit?: number,
): SpeciesCatalogDocument[] {
  const rows = parse(input, {
    bom: true,
    columns: true,
    skip_empty_lines: true,
    trim: true,
    relax_column_count: false,
  }) as GbifStagingRow[];
  if (rows.length === 0) throw new Error("Staging manifest contains no species records.");
  const fields = new Set(Object.keys(rows[0]));
  const missingFields = REQUIRED_FIELDS.filter((field) => !fields.has(field));
  if (missingFields.length > 0) {
    throw new Error(`Staging manifest is missing columns: ${missingFields.join(", ")}.`);
  }
  if (provenance.source_dataset?.key !== rows[0].source_download_key) {
    throw new Error("Provenance download key does not match the staging manifest.");
  }
  if (!provenance.source_dataset.doi || !provenance.source_dataset.citation) {
    throw new Error("Provenance must include the GBIF DOI and citation.");
  }
  const checksum = createHash("sha256").update(input, "utf8").digest("hex");
  if (provenance.staging_csv_sha256 && provenance.staging_csv_sha256 !== checksum) {
    throw new Error("Staging manifest checksum does not match its provenance file.");
  }
  const seenKeys = new Set<string>();
  const records = rows.map((row, index) => {
    const rowNumber = index + 2;
    if (!/^[A-Za-z0-9]+$/.test(row.accepted_taxon_key)) {
      throw new Error(`Invalid accepted taxon key at manifest row ${rowNumber}.`);
    }
    if (!row.accepted_scientific_name.trim()) {
      throw new Error(`Missing accepted scientific name at manifest row ${rowNumber}.`);
    }
    if (row.source_kingdom !== "Plantae" || row.source_country !== "PH") {
      throw new Error(`Unexpected source taxon scope at manifest row ${rowNumber}.`);
    }
    if (!row.catalog_review_status.startsWith("staged_pending")) {
      throw new Error(`Non-pending review status at manifest row ${rowNumber}.`);
    }
    if (row.ai_model_supported !== "false") {
      throw new Error(`Refusing AI-supported catalog row ${rowNumber}.`);
    }
    const sourceTaxonKeys = parseJsonArray(row.source_taxon_keys, "source_taxon_keys");
    if (sourceTaxonKeys.length === 0) {
      throw new Error(`Source taxon keys are missing at manifest row ${rowNumber}.`);
    }
    if (seenKeys.has(row.accepted_taxon_key)) {
      throw new Error(`Duplicate accepted taxon key ${row.accepted_taxon_key}.`);
    }
    seenKeys.add(row.accepted_taxon_key);

    return {
      taxonomyAuthority: "GBIF",
      acceptedTaxonKey: row.accepted_taxon_key,
      acceptedScientificName: row.accepted_scientific_name,
      family: row.family,
      genus: row.genus,
      sourceTaxonKeys,
      sourceScientificNames: parseJsonArray(row.source_scientific_names, "source_scientific_names"),
      sourceTaxonomicStatuses: parseJsonArray(row.source_taxonomic_statuses, "source_taxonomic_statuses"),
      sourceIucnRedListCategories: parseJsonArray(
        row.source_iucn_red_list_categories,
        "source_iucn_red_list_categories",
      ),
      sourceUsageDetails: parseSourceUsageDetails(row.source_usage_details),
      source: {
        datasetKey: row.source_download_key,
        doi: provenance.source_dataset?.doi ?? row.source_download_doi,
        citation: provenance.source_dataset?.citation ?? "",
        country: row.source_country,
        kingdom: row.source_kingdom,
        occurrenceCount: parseNonnegativeInteger(row.source_occurrence_count, "source_occurrence_count"),
        usageCount: parseNonnegativeInteger(row.source_usage_count, "source_usage_count"),
        sourceFileSha256: provenance.source_file_sha256 ?? "",
      },
      ecologicalStatuses: [],
      reviewStatus: "pending",
      aiModelSupported: false,
      createdAt: new Date(),
      updatedAt: new Date(),
    } satisfies SpeciesCatalogDocument;
  });
  return limit === undefined ? records : records.slice(0, limit);
}

export function buildUpsertOperations(
  records: SpeciesCatalogDocument[],
): AnyBulkWriteOperation<SpeciesCatalogDocument>[] {
  return records.map((record) => {
    const {
      taxonomyAuthority,
      acceptedTaxonKey,
      reviewStatus,
      aiModelSupported,
      createdAt,
      updatedAt,
      ...sourceData
    } = record;
    return {
      updateOne: {
        filter: { taxonomyAuthority, acceptedTaxonKey },
        update: {
          $set: sourceData,
          $setOnInsert: {
            taxonomyAuthority,
            acceptedTaxonKey,
            reviewStatus,
            aiModelSupported,
            createdAt,
            updatedAt,
          },
        },
        upsert: true,
      },
    };
  });
}

async function main(): Promise<void> {
  let options: ImportOptions;
  try {
    options = parseArgs(process.argv.slice(2));
  } catch (error) {
    console.error(error instanceof Error ? error.message : error);
    process.exitCode = 2;
    return;
  }

  const inputPath = path.resolve(options.inputPath);
  const provenancePath = inputPath.replace(/_staging\.csv$/i, "_provenance.json");
  const [input, provenanceContent] = await Promise.all([
    readFile(inputPath, "utf8"),
    readFile(provenancePath, "utf8"),
  ]);
  const provenance = JSON.parse(provenanceContent) as Provenance;
  const records = loadCatalogRecords(input, provenance, options.limit);
  const summary = {
    mode: options.apply ? "apply" : "dry-run",
    database: options.database,
    collection: options.collection,
    input: inputPath,
    candidateRecords: records.length,
    sourceDownloadKey: provenance.source_dataset?.key,
    sourceDoi: provenance.source_dataset?.doi,
    sourceFileSha256: provenance.source_file_sha256,
  };

  if (!options.apply) {
    console.log(JSON.stringify(summary, null, 2));
    return;
  }

  await mongoose.connect(options.uri, {
    dbName: options.database,
    serverSelectionTimeoutMS: 5000,
    connectTimeoutMS: 5000,
    appName: "GeoFloraSpeciesCatalog",
  });
  try {
    const speciesModel = getSpeciesModel(options.collection);
    await speciesModel.createIndexes();
    const result = await speciesModel.bulkWrite(buildUpsertOperations(records), {
      ordered: false,
      timestamps: false,
    });
    console.log(
      JSON.stringify(
        {
          ...summary,
          matched: result.matchedCount,
          modified: result.modifiedCount,
          upserted: result.upsertedCount,
        },
        null,
        2,
      ),
    );
  } finally {
    await mongoose.disconnect();
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch((error: unknown) => {
    console.error(error instanceof Error ? error.message : error);
    process.exitCode = 1;
  });
}
