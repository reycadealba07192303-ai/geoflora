import mongoose, { Schema, type Model } from "mongoose";

export interface SpeciesCatalogDocument {
  taxonomyAuthority: string;
  acceptedTaxonKey: string;
  acceptedScientificName: string;
  family: string;
  genus: string;
  sourceTaxonKeys: string[];
  sourceScientificNames: string[];
  sourceTaxonomicStatuses: string[];
  sourceIucnRedListCategories: string[];
  sourceUsageDetails: {
    sourceTaxonKey: string;
    scientificName: string;
    taxonomicRank: string;
    taxonomicStatus: string;
    occurrenceCount: number;
    family: string;
    genus: string;
    iucnRedListCategory: string;
  }[];
  source: {
    datasetKey: string;
    doi: string;
    citation: string;
    country: string;
    kingdom: string;
    occurrenceCount: number;
    usageCount: number;
    sourceFileSha256: string;
  };
  ecologicalStatuses: {
    status: string;
    geographicScope: string;
    evidence: { source: string; citation: string; verifiedAt?: Date }[];
  }[];
  reviewStatus: "pending" | "approved" | "rejected" | "flagged";
  aiModelSupported: boolean;
  createdAt: Date;
  updatedAt: Date;
}

const SourceUsageSchema = new Schema(
  {
    sourceTaxonKey: { type: String, required: true },
    scientificName: { type: String, required: true },
    taxonomicRank: { type: String, required: true },
    taxonomicStatus: { type: String, required: true },
    occurrenceCount: { type: Number, required: true, min: 0 },
    family: { type: String, default: "" },
    genus: { type: String, default: "" },
    iucnRedListCategory: { type: String, default: "" },
  },
  { _id: false },
);

const EcologicalStatusSchema = new Schema(
  {
    status: { type: String, required: true },
    geographicScope: { type: String, required: true },
    evidence: [
      new Schema(
        {
          source: { type: String, required: true },
          citation: { type: String, required: true },
          verifiedAt: { type: Date },
        },
        { _id: false },
      ),
    ],
  },
  { _id: false },
);

const SpeciesSchema = new Schema<SpeciesCatalogDocument>(
  {
    taxonomyAuthority: { type: String, required: true, immutable: true },
    acceptedTaxonKey: { type: String, required: true, immutable: true },
    acceptedScientificName: { type: String, required: true, trim: true },
    family: { type: String, default: "", trim: true },
    genus: { type: String, default: "", trim: true },
    sourceTaxonKeys: { type: [String], default: [] },
    sourceScientificNames: { type: [String], default: [] },
    sourceTaxonomicStatuses: { type: [String], default: [] },
    sourceIucnRedListCategories: { type: [String], default: [] },
    sourceUsageDetails: { type: [SourceUsageSchema], default: [] },
    source: {
      datasetKey: { type: String, required: true },
      doi: { type: String, required: true },
      citation: { type: String, required: true },
      country: { type: String, required: true },
      kingdom: { type: String, required: true },
      occurrenceCount: { type: Number, required: true, min: 0 },
      usageCount: { type: Number, required: true, min: 1 },
      sourceFileSha256: { type: String, required: true },
    },
    ecologicalStatuses: { type: [EcologicalStatusSchema], default: [] },
    reviewStatus: {
      type: String,
      enum: ["pending", "approved", "rejected", "flagged"],
      default: "pending",
    },
    aiModelSupported: { type: Boolean, default: false },
    createdAt: { type: Date, required: true },
    updatedAt: { type: Date, required: true },
  },
  { versionKey: false },
);

SpeciesSchema.index(
  { taxonomyAuthority: 1, acceptedTaxonKey: 1 },
  { unique: true, name: "unique_taxonomy_authority_taxon_key" },
);
SpeciesSchema.index(
  { acceptedScientificName: "text", sourceScientificNames: "text", family: "text", genus: "text" },
  { name: "species_catalog_text_search" },
);
SpeciesSchema.index({ family: 1, genus: 1 }, { name: "species_catalog_family_genus" });

export function getSpeciesModel(collectionName = "species_catalog"): Model<SpeciesCatalogDocument> {
  const modelName = `SpeciesCatalog_${collectionName}`;
  return (
    (mongoose.models[modelName] as Model<SpeciesCatalogDocument> | undefined) ??
    mongoose.model<SpeciesCatalogDocument>(modelName, SpeciesSchema, collectionName)
  );
}

export const Species = getSpeciesModel();
