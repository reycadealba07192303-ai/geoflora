import type { PipelineStage } from "mongoose";
import type { Account } from "./auth";
import { ACTIVE } from "./sightings";
import { TARGET_SPECIES } from "./ai-result";

// MongoDB expression for a report's result (target | other | uncertain), matching reportResult() in lib/ai-result.ts.
const reviewedName = { $cond: [{ $gt: [{ $strLenCP: { $ifNull: ["$verifiedScientificName", ""] } }, 0] }, "$verifiedScientificName", "$reportedSpecies"] };
export const RESULT_EXPR = { $cond: [
  { $or: [{ $eq: ["$aiResult", "target"] }, { $and: [{ $eq: ["$status", "verified"] }, { $or: [{ $eq: ["$verifiedEcologicalStatus", "target_invasive"] }, { $in: [reviewedName, TARGET_SPECIES] }] }] }] },
  "target",
  { $cond: [{ $or: [{ $eq: ["$aiResult", "other"] }, { $eq: ["$status", "verified"] }] }, "other", "uncertain"] },
] };
export const SHOWN_STATUSES = ["recorded", "verified", "pending", "correction_requested"];

// Spatial aggregation for analytics (see docs/part-10-map-analytics.md): fixed 0.1° latitude/longitude cells
// (about 11 km), counted by observation. Cells below MIN_CELL_REPORTS are suppressed so a sparse cell cannot
// reveal an individual sighting; cells with at least HOTSPOT_MIN_REPORTS are listed as high report density.
export const CELL_DEGREES = 0.1;
export const MIN_CELL_REPORTS = 3;
export const HOTSPOT_MIN_REPORTS = 5;
export const SPARSE_TOTAL = 20;
export const MAX_POINTS = 2000;
export const TIME_ZONE = "Asia/Manila";

// layer "target": target invasive reports only; "all": every recorded or reviewed report except rejected ones.
export type Filters = { layer: "target" | "all"; species: string; from: Date | null; to: Date | null; bbox: [number, number, number, number] | null };

function day(value: string | null, end: boolean) {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const date = new Date(`${value}T${end ? "23:59:59.999" : "00:00:00.000"}+08:00`);
  return Number.isFinite(date.getTime()) ? date : null;
}

// ownReportsOnly: the caller restricts results to the viewer's reports, so their own pending reports may be included.
export function parseFilters(url: URL, account: Account, ownReportsOnly = false): Filters | string {
  const params = url.searchParams;
  const layer = params.get("layer") === "target" ? "target" : "all";
  const species = (params.get("species") ?? "").trim().toLowerCase().slice(0, 120);
  const from = day(params.get("from"), false), to = day(params.get("to"), true);
  if ((params.get("from") && !from) || (params.get("to") && !to) || (from && to && from > to)) return "Use valid from/to dates (YYYY-MM-DD), with from on or before to.";
  let bbox: Filters["bbox"] = null;
  if (params.get("bbox")) {
    const parts = params.get("bbox")!.split(",").map(Number);
    if (parts.length !== 4 || parts.some(value => !Number.isFinite(value)) || parts[0] >= parts[2] || parts[1] >= parts[3] || Math.abs(parts[1]) > 90 || Math.abs(parts[3]) > 90) return "Use bbox=west,south,east,north.";
    bbox = parts.map(value => Math.max(-180, Math.min(180, value))) as Filters["bbox"];
  }
  return { layer, species, from, to, bbox };
}

// Stages shared by the map and analytics: visible, non-withdrawn reports matching every filter.
export function matchStages(filters: Filters, ownerId?: string): PipelineStage[] {
  const match: Record<string, unknown> = { ...ACTIVE, status: { $in: SHOWN_STATUSES }, ...(filters.layer === "target" ? { $expr: { $eq: [RESULT_EXPR, "target"] } } : {}) };
  if (ownerId) match.ownerId = ownerId;
  if (filters.from || filters.to) match.observedAt = { ...(filters.from ? { $gte: filters.from } : {}), ...(filters.to ? { $lte: filters.to } : {}) };
  // A plain longitude/latitude rectangle, matching what the map view shows.
  if (filters.bbox) Object.assign(match, { "location.coordinates.0": { $gte: filters.bbox[0], $lte: filters.bbox[2] }, "location.coordinates.1": { $gte: filters.bbox[1], $lte: filters.bbox[3] } });
  const stages: PipelineStage[] = [
    { $match: match },
    // Verified reports use the reviewer-confirmed species; others keep the contributor's unverified name.
    { $addFields: { speciesName: { $cond: [{ $gt: [{ $strLenCP: { $ifNull: ["$verifiedScientificName", ""] } }, 0] }, "$verifiedScientificName", "$reportedSpecies"] } } },
  ];
  if (filters.species) stages.push({ $match: { speciesName: { $regex: `^${filters.species.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(\\s|$)`, $options: "i" } } });
  return stages;
}

export function analyticsPipeline(filters: Filters, ownerId?: string): PipelineStage[] {
  const cell = (axis: 0 | 1) => ({ $floor: { $divide: [{ $arrayElemAt: ["$location.coordinates", axis] }, CELL_DEGREES] } });
  return [...matchStages(filters, ownerId), { $facet: {
    total: [{ $count: "n" }],
    bySpecies: [{ $group: { _id: "$speciesName", n: { $sum: 1 } } }, { $sort: { n: -1, _id: 1 } }],
    byMonth: [{ $group: { _id: { $dateToString: { format: "%Y-%m", date: "$observedAt", timezone: TIME_ZONE } }, n: { $sum: 1 } } }, { $sort: { _id: 1 } }],
    byStatus: [{ $group: { _id: "$status", n: { $sum: 1 } } }],
    byResult: [{ $group: { _id: RESULT_EXPR, n: { $sum: 1 } } }],
    cells: [{ $group: { _id: { lat: cell(1), lng: cell(0) }, n: { $sum: 1 }, species: { $addToSet: "$speciesName" } } }],
  } }];
}

type Facet = { total: { n: number }[]; bySpecies: { _id: string; n: number }[]; byMonth: { _id: string; n: number }[]; byStatus: { _id: string; n: number }[]; byResult: { _id: string; n: number }[]; cells: { _id: { lat: number; lng: number }; n: number; species: string[] }[] };
const round = (value: number) => Math.round(value * 1000) / 1000;

export function summarize(facet: Facet) {
  const total = facet.total[0]?.n ?? 0;
  const shown = facet.cells.filter(cell => cell.n >= MIN_CELL_REPORTS);
  const cells = shown.map(cell => ({ south: round(cell._id.lat * CELL_DEGREES), west: round(cell._id.lng * CELL_DEGREES), north: round((cell._id.lat + 1) * CELL_DEGREES), east: round((cell._id.lng + 1) * CELL_DEGREES),
    centerLat: round((cell._id.lat + 0.5) * CELL_DEGREES), centerLng: round((cell._id.lng + 0.5) * CELL_DEGREES), reports: cell.n, species: cell.species.length })).sort((a, b) => b.reports - a.reports || a.south - b.south || a.west - b.west);
  return {
    total, sparse: total < SPARSE_TOTAL,
    bySpecies: facet.bySpecies.map(row => ({ species: row._id, reports: row.n })),
    byMonth: facet.byMonth.map(row => ({ month: row._id, reports: row.n })),
    byStatus: Object.fromEntries(facet.byStatus.map(row => [row._id, row.n])),
    byResult: Object.fromEntries(facet.byResult.map(row => [row._id, row.n])),
    cells, hotspots: cells.filter(cell => cell.reports >= HOTSPOT_MIN_REPORTS).slice(0, 10),
    suppressed: { cells: facet.cells.length - shown.length, reports: facet.cells.filter(cell => cell.n < MIN_CELL_REPORTS).reduce((sum, cell) => sum + cell.n, 0) },
    method: { cellDegrees: CELL_DEGREES, minCellReports: MIN_CELL_REPORTS, hotspotMinReports: HOTSPOT_MIN_REPORTS, sparseBelow: SPARSE_TOTAL, timeZone: TIME_ZONE,
      meaning: "Counts are submitted reports, identified by GeoFlora's AI model. They describe where people reported plants, not invasion severity, abundance or ecological spread." },
  };
}
