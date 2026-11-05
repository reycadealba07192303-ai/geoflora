import mongoose from "mongoose";
import { mlHealth } from "./ml";
import { connectDatabase } from "./sightings";

// Read-only view over the imported catalog collections. Nothing here changes review status or ecological flags:
// species_catalog rows are GBIF occurrence-derived candidates, and staging rows are unverified source listings.
type CatalogRow = { _id: unknown; acceptedScientificName: string; family?: string; genus?: string; reviewStatus?: string; catalogReview?: { basis?: string }; source?: { occurrenceCount?: number } };
type SourceListing = { title: string; status: string; citation: string; doi: string };
export type CatalogEntry = { id: string; scientificName: string; binomial: string; family: string; genus: string; reviewStatus: string; reviewBasis: string; occurrenceCount: number; activeModel: boolean; sourceListings: SourceListing[]; verifiedSightings: number };

const TTL_MS = 5 * 60_000;
let cache: { at: number; entries: CatalogEntry[]; model: { version: string; classes: string[] } } | null = null;
// Review decisions change verified-sighting counts, so they reset the cached index.
export function invalidateCatalog() { cache = null; }
export const binomial = (name: string) => name.trim().split(/\s+/).slice(0, 2).join(" ").toLowerCase();

async function activeModel() {
  const health = await mlHealth();
  return { version: health?.model_version ?? "", classes: (health?.species ?? []).filter(entry => entry.role !== "lookalike").map(entry => binomial(entry.scientific_name)) };
}

export async function catalogIndex(force = false) {
  if (cache && !force && Date.now() - cache.at < TTL_MS) return cache;
  await connectDatabase();
  const db = mongoose.connection.db!;
  const [rows, staging, verified, model] = await Promise.all([
    db.collection<CatalogRow>("species_catalog").find({}, { projection: { acceptedScientificName: 1, family: 1, genus: 1, reviewStatus: 1, "catalogReview.basis": 1, "source.occurrenceCount": 1 } }).toArray(),
    // The full GBIF download is already the catalog itself; other staged sources are independent listings.
    db.collection("species_catalog_staging").find({ source_key: { $not: /^gbif-download:/ } }, { projection: { scientific_name: 1, source_ecological_status: 1, source: 1 } }).toArray(),
    db.collection("sightings").aggregate<{ _id: string; n: number }>([{ $match: { status: "verified", verifiedEcologicalStatus: "target_invasive", verifiedScientificName: { $nin: ["", null] } } }, { $group: { _id: "$verifiedScientificName", n: { $sum: 1 } } }]).toArray(),
    activeModel(),
  ]);
  const listings = new Map<string, SourceListing[]>();
  for (const row of staging) {
    const key = binomial(String(row.scientific_name ?? "")), source = (row.source ?? {}) as { title?: string; citation?: string; doi?: string };
    const listing = { title: source.title ?? "Unknown source", status: String(row.source_ecological_status ?? ""), citation: source.citation ?? "", doi: source.doi ?? "" };
    const list = listings.get(key) ?? [];
    if (!list.some(item => item.title === listing.title)) list.push(listing);
    listings.set(key, list);
  }
  const verifiedCounts = new Map<string, number>();
  for (const row of verified) verifiedCounts.set(binomial(row._id), (verifiedCounts.get(binomial(row._id)) ?? 0) + row.n);
  const entries = rows.map(row => {
    const key = binomial(row.acceptedScientificName);
    return { id: String(row._id), scientificName: row.acceptedScientificName, binomial: key, family: row.family ?? "", genus: row.genus ?? "", reviewStatus: row.reviewStatus ?? "pending", reviewBasis: row.catalogReview?.basis ?? "",
      occurrenceCount: row.source?.occurrenceCount ?? 0, activeModel: model.classes.includes(key), sourceListings: listings.get(key) ?? [], verifiedSightings: verifiedCounts.get(key) ?? 0 };
  }).sort((a, b) => Number(b.activeModel) - Number(a.activeModel) || b.verifiedSightings - a.verifiedSightings || a.scientificName.localeCompare(b.scientificName));
  cache = { at: Date.now(), entries, model };
  return cache;
}
