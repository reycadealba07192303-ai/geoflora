import { canModerate, currentAccount } from "../../../src/lib/auth";
import { MAX_POINTS, matchStages, parseFilters } from "../../../src/lib/occurrences";
import { sameOriginRequest, sightingModel } from "../../../src/lib/sightings";
import { reportResult } from "../../../src/lib/ai-result";

export const runtime = "nodejs";

// Exact map points: reviewers/administrators see the workspace, contributors only their own reports (Part 8 rule).
export async function GET(request: Request) {
  if (!sameOriginRequest(request)) return Response.json({ detail: "This request is not allowed." }, { status: 403 });
  try {
    const account = await currentAccount(request);
    if (!account) return Response.json({ detail: "Sign in to view the map." }, { status: 401 });
    const filters = parseFilters(new URL(request.url), account, !canModerate(account));
    if (typeof filters === "string") return Response.json({ detail: filters }, { status: 400 });
    const ownerId = canModerate(account) ? undefined : account.id;
    const rows = await (await sightingModel()).aggregate<{ _id: unknown; speciesName: string; status: string; aiResult?: string; verifiedEcologicalStatus?: string; verifiedScientificName?: string; reportedSpecies?: string; location: { coordinates: number[] }; observedAt: Date; submittedAt: Date; placeName?: string }>([
      ...matchStages(filters, ownerId), { $sort: { observedAt: -1 } }, { $limit: MAX_POINTS + 1 },
      { $project: { speciesName: 1, status: 1, aiResult: 1, verifiedEcologicalStatus: 1, verifiedScientificName: 1, reportedSpecies: 1, location: 1, observedAt: 1, submittedAt: 1, placeName: 1 } },
    ]);
    return Response.json({
      scope: ownerId ? "mine" : "workspace", truncated: rows.length > MAX_POINTS,
      points: rows.slice(0, MAX_POINTS).map(row => ({ id: String(row._id), species: row.speciesName, status: row.status, result: reportResult(row), latitude: row.location.coordinates[1], longitude: row.location.coordinates[0], observedAt: new Date(row.observedAt).toISOString(), submittedAt: new Date(row.submittedAt).toISOString(), placeName: row.placeName ?? "" })),
    }, { headers: { "Cache-Control": "no-store" } });
  } catch { return Response.json({ detail: "Map data is unavailable. Check the local database." }, { status: 503 }); }
}
