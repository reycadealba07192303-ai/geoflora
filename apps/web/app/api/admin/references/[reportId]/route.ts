import { currentAccount, isAdmin } from "../../../../../src/lib/auth";
import { sameOriginRequest, sightingModel } from "../../../../../src/lib/sightings";
import { invalidateVerifiedReference } from "../../../../../src/lib/verified-references";

export const runtime = "nodejs";

export async function PATCH(request: Request, context: { params: Promise<{ reportId: string }> }) {
  if (!sameOriginRequest(request)) return Response.json({ detail: "This request is not allowed." }, { status: 403 });
  const account = await currentAccount(request).catch(() => null);
  if (!account) return Response.json({ detail: "Sign in first." }, { status: 401 });
  if (!isAdmin(account)) return Response.json({ detail: "Administrator access required." }, { status: 403 });
  const { reportId } = await context.params;
  if (!/^[a-f0-9]{24}$/i.test(reportId)) return Response.json({ detail: "Invalid report id." }, { status: 400 });
  let body: { action?: string; rationale?: string };
  try { body = await request.json(); } catch { return Response.json({ detail: "Supply a JSON invalidation rationale." }, { status: 400 }); }
  const rationale = typeof body.rationale === "string" ? body.rationale.trim() : "";
  if (body.action !== "invalidate" || rationale.length < 10 || rationale.length > 2000) return Response.json({ detail: "Invalidation requires a reason of 10 to 2000 characters." }, { status: 400 });
  try {
    const model = await sightingModel();
    const report = await model.findOne({ _id: reportId }).select("referenceCandidateStatus reviewHistory");
    if (!report || report.referenceCandidateStatus !== "approved") return Response.json({ detail: "No approved reference is attached to this report." }, { status: 404 });
    const removed = await invalidateVerifiedReference(reportId, account.id, rationale);
    await model.updateOne({ _id: reportId }, { $set: { referenceCandidateStatus: "rejected", referenceIndexStatus: "invalidated", referenceIndexMessage: `Removed from active reference search: ${rationale}` }, $push: { reviewHistory: { reviewerId: account.id, reviewer: account.username, basis: "human", action: "invalidate_reference", confirmed: true, referenceEligible: false, rationale, reviewedAt: new Date() } } });
    return Response.json({ id: reportId, invalidatedReferences: removed, referenceCandidateStatus: "rejected" });
  } catch (error) {
    console.error("Reference invalidation failed", error instanceof Error ? error.message : "unknown");
    return Response.json({ detail: "Reference invalidation could not be completed." }, { status: 503 });
  }
}
