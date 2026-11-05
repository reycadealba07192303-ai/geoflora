import mongoose from "mongoose";
import { currentAccount } from "../../../src/lib/auth";
import { catalogIndex } from "../../../src/lib/catalog";
import { sameOriginRequest } from "../../../src/lib/sightings";

export const runtime = "nodejs";
const PAGE_SIZE = 20;
type Detail = { _id: mongoose.Types.ObjectId; source?: { citation?: string; doi?: string }; sourceUsageDetails?: { scientificName: string; taxonomicStatus: string }[]; sourceIucnRedListCategories?: string[]; ecologicalStatuses?: { status: string; geographicScope: string }[] };

export async function GET(request: Request) {
  if (!sameOriginRequest(request)) return Response.json({ detail: "This request is not allowed." }, { status: 403 });
  try {
    if (!await currentAccount(request)) return Response.json({ detail: "Sign in to browse the catalog." }, { status: 401 });
    const params = new URL(request.url).searchParams;
    const q = (params.get("q") ?? "").trim().toLowerCase().slice(0, 100), filter = params.get("filter") ?? "all";
    const page = Math.max(1, Math.min(10_000, Number.parseInt(params.get("page") ?? "1", 10) || 1));
    const { entries, model, at } = await catalogIndex();
    const matches = entries.filter(entry =>
      (!q || entry.scientificName.toLowerCase().includes(q) || entry.family.toLowerCase().includes(q)) &&
      (filter === "model" ? entry.activeModel : filter === "listed" ? entry.sourceListings.length > 0 : filter === "verified" ? entry.verifiedSightings > 0 : true));
    const slice = matches.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
    const details = await mongoose.connection.db!.collection<Detail>("species_catalog").find(
      { _id: { $in: slice.map(entry => new mongoose.Types.ObjectId(entry.id)) } },
      { projection: { source: 1, sourceUsageDetails: 1, sourceIucnRedListCategories: 1, ecologicalStatuses: 1, aiModelSupported: 1 } }).toArray();
    const byId = new Map(details.map(row => [String(row._id), row]));
    return Response.json({
      total: matches.length, catalogTotal: entries.length, reviewCounts: entries.reduce<Record<string, number>>((counts, entry) => ({ ...counts, [entry.reviewStatus]: (counts[entry.reviewStatus] ?? 0) + 1 }), {}), page, pageSize: PAGE_SIZE, indexedAt: new Date(at).toISOString(),
      activeModel: { version: model.version, species: model.classes.length },
      species: slice.map(entry => {
        const row: Partial<Detail> = byId.get(entry.id) ?? {};
        return { ...entry, gbif: { citation: row.source?.citation ?? "", doi: row.source?.doi ?? "", usages: (row.sourceUsageDetails ?? []).map(usage => ({ name: usage.scientificName, status: usage.taxonomicStatus })) },
          iucn: row.sourceIucnRedListCategories ?? [], verifiedEcologicalStatuses: row.ecologicalStatuses ?? [] };
      }),
    }, { headers: { "Cache-Control": "no-store" } });
  } catch { return Response.json({ detail: "The species catalog is unavailable. Check the local database." }, { status: 503 }); }
}
