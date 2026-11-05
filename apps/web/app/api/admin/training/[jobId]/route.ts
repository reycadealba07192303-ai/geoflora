import { currentAccount, isAdmin } from "../../../../../src/lib/auth";
import { sameOriginRequest } from "../../../../../src/lib/sightings";
import { trainingJobs } from "../../../../../src/lib/training-jobs";

export const runtime = "nodejs";

export async function PATCH(request: Request, context: { params: Promise<{ jobId: string }> }) {
  if (!sameOriginRequest(request)) return Response.json({ detail: "This request is not allowed." }, { status: 403 });
  try {
    const account = await currentAccount(request);
    if (!account) return Response.json({ detail: "Sign in first." }, { status: 401 });
    if (!isAdmin(account)) return Response.json({ detail: "Administrator access required." }, { status: 403 });
    const { jobId } = await context.params;
    if (!/^[a-f0-9]{24}$/i.test(jobId)) return Response.json({ detail: "Invalid training job." }, { status: 400 });
    const body = await request.json();
    const rationale = typeof body.rationale === "string" ? body.rationale.trim() : "";
    if (body.action !== "approve_promotion" || body.confirmed !== true || rationale.length < 20 || rationale.length > 2000) {
      return Response.json({ detail: "Confirm that you reviewed the candidate evaluation and provide a rationale of at least 20 characters." }, { status: 400 });
    }
    const jobs = await trainingJobs();
    const job = await jobs.findOne({ _id: jobId });
    const prefix = job?.source === "ml-lab" ? "storage/models/candidates/geoflora-mnv2-" : "storage/models/candidates/auto_";
    if (!job || job.status !== "completed" || !job.candidatePath?.startsWith(prefix) || job.promotion?.status !== "awaiting_approval" || job.promotion?.eligible !== true || job.metrics?.qualityTargetsPassed !== true || job.metrics?.benchmark?.promote !== true) {
      return Response.json({ detail: "This candidate is not eligible for administrator promotion approval." }, { status: 409 });
    }
    const now = new Date();
    const promotion = { ...job.promotion, status: "approved", approvedBy: account.id, approvedUsername: account.username, approvedAt: now, rationale };
    const saved = await jobs.updateOne({ _id: job._id, "promotion.status": "awaiting_approval" }, { $set: { promotion, detail: "Promotion approved by an administrator; waiting for the model worker to revalidate and activate", updatedAt: now } });
    if (saved.modifiedCount !== 1) return Response.json({ detail: "The candidate's approval state changed. Refresh and review it again." }, { status: 409 });
    return Response.json({ jobId, promotionStatus: "approved", detail: "Approval recorded. The model worker will recheck evaluation gates before activation." });
  } catch {
    return Response.json({ detail: "Promotion approval could not be saved." }, { status: 503 });
  }
}
