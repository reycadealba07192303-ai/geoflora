import { canModerate, currentAccount } from "../../../src/lib/auth";
import { catalogIndex } from "../../../src/lib/catalog";
import { mlHealth } from "../../../src/lib/ml";
import { ACTIVE, sameOriginRequest, sightingModel } from "../../../src/lib/sightings";
import { RESULT_EXPR, SHOWN_STATUSES } from "../../../src/lib/occurrences";

export const runtime = "nodejs";

// Live counts for the Overview page. Workspace-wide numbers are aggregate counts only; no records are exposed.
export async function GET(request: Request) {
  if (!sameOriginRequest(request)) return Response.json({ detail: "This request is not allowed." }, { status: 403 });
  try {
    const account = await currentAccount(request);
    if (!account) return Response.json({ detail: "Sign in first." }, { status: 401 });
    const model = await sightingModel();
    const [statuses, results, mine, catalog, health] = await Promise.all([
      model.aggregate<{ _id: string; n: number }>([{ $match: ACTIVE }, { $group: { _id: "$status", n: { $sum: 1 } } }]),
      model.aggregate<{ _id: string; n: number }>([{ $match: { ...ACTIVE, status: { $in: SHOWN_STATUSES } } }, { $group: { _id: RESULT_EXPR, n: { $sum: 1 } } }]),
      model.countDocuments({ ...ACTIVE, ownerId: account.id }),
      catalogIndex(),
      mlHealth(2500),
    ]);
    const count = Object.fromEntries(statuses.map(row => [row._id, row.n]));
    const result = Object.fromEntries(results.map(row => [row._id, row.n]));
    return Response.json({
      catalog: { records: catalog.entries.length, approved: catalog.entries.filter(entry => entry.reviewStatus === "approved").length, pendingReview: catalog.entries.filter(entry => entry.reviewStatus === "pending").length, listedBySources: catalog.entries.filter(entry => entry.sourceListings.length > 0).length },
      sightings: { awaitingReview: (count.recorded ?? 0) + (count.pending ?? 0) + (count.correction_requested ?? 0), verified: count.verified ?? 0, rejected: count.rejected ?? 0, mine, canReview: canModerate(account),
        total: (result.target ?? 0) + (result.other ?? 0) + (result.uncertain ?? 0), target: result.target ?? 0, other: result.other ?? 0, uncertain: result.uncertain ?? 0 },
      model: { ready: health?.ready === true, version: health?.model_version ?? null, species: health?.supported_species_count ?? 0 },
    }, { headers: { "Cache-Control": "no-store" } });
  } catch { return Response.json({ detail: "Overview counts are unavailable. Check the local database." }, { status: 503 }); }
}
