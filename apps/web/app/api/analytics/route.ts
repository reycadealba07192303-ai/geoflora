import { currentAccount } from "../../../src/lib/auth";
import { analyticsPipeline, matchStages, parseFilters, summarize } from "../../../src/lib/occurrences";
import { sameOriginRequest, sightingModel } from "../../../src/lib/sightings";

export const runtime = "nodejs";

// Aggregate analytics. scope=workspace (default) counts every visible report but only returns generalized cells;
// scope=mine limits counts to the viewer's own reports. Contributors may include pending reports only for scope=mine.
export async function GET(request: Request) {
  if (!sameOriginRequest(request)) return Response.json({ detail: "This request is not allowed." }, { status: 403 });
  try {
    const account = await currentAccount(request);
    if (!account) return Response.json({ detail: "Sign in to view analytics." }, { status: 401 });
    const url = new URL(request.url);
    const filters = parseFilters(url, account);
    if (typeof filters === "string") return Response.json({ detail: filters }, { status: 400 });
    const scope = url.searchParams.get("scope") === "mine" ? "mine" : "workspace";
    const ownerId = scope === "mine" ? account.id : undefined;
    const model = await sightingModel();
    const [facet] = await model.aggregate(analyticsPipeline(filters, ownerId));
    const options = await model.aggregate<{ _id: string }>([...matchStages({ ...filters, species: "", from: null, to: null, bbox: null }, ownerId), { $group: { _id: "$speciesName" } }, { $sort: { _id: 1 } }]);
    return Response.json({ scope, layer: filters.layer, ...summarize(facet), speciesOptions: options.map(row => row._id) }, { headers: { "Cache-Control": "no-store" } });
  } catch { return Response.json({ detail: "Analytics are unavailable. Check the local database." }, { status: 503 }); }
}
