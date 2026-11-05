import { catalogIndex } from "../../../src/lib/catalog";
import { mlHealth } from "../../../src/lib/ml";
import { sameOriginRequest, sightingModel } from "../../../src/lib/sightings";

export const runtime = "nodejs";

// Public aggregate counts for the signed-out landing page. No records, accounts or locations are exposed.
export async function GET(request: Request) {
  if (!sameOriginRequest(request)) return Response.json({ detail: "This request is not allowed." }, { status: 403 });
  const [verified, catalog, health] = await Promise.all([
    sightingModel().then(model => model.countDocuments({ status: "verified" })).catch(() => null),
    catalogIndex().then(index => index.entries.length).catch(() => null),
    mlHealth(2500),
  ]);
  return Response.json({
    verifiedSightings: verified,
    catalogRecords: catalog,
    model: { ready: health?.ready === true, species: health?.supported_species_count ?? null },
  }, { headers: { "Cache-Control": "no-store" } });
}
