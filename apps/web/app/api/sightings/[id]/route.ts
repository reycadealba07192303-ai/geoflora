import { canModerate, currentAccount } from "../../../../src/lib/auth";
import { after } from "next/server";
import { reviewPendingReports } from "../../../../src/lib/ai-review";
import { editableByOwner, LOCATION_METHODS, sameOriginRequest, sightingModel, reportSummary } from "../../../../src/lib/sightings";

export const runtime = "nodejs";
// Long enough for the AI review that runs after the response (Vercel Hobby allows up to 60 s).
export const maxDuration = 60;
const NOT_EDITABLE = "This report can no longer be changed because it was verified, rejected or withdrawn.";
// Non-owners get 404 so the endpoint does not reveal whether another account's report exists.
async function ownerMissing(id: string, ownerId: string) {
  return !await (await sightingModel()).exists({ _id: id, ownerId });
}

async function context(request: Request, params: Promise<{ id: string }>) {
  if (!sameOriginRequest(request)) return { error: Response.json({ detail: "This request is not allowed." }, { status: 403 }) };
  const account = await currentAccount(request);
  if (!account) return { error: Response.json({ detail: "Sign in to manage your report." }, { status: 401 }) };
  const { id } = await params;
  if (!/^[a-f0-9]{24}$/i.test(id)) return { error: Response.json({ detail: "Invalid report reference." }, { status: 400 }) };
  return { account, id };
}

export async function GET(request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { account, id, error } = await context(request, params);
    if (error) return error;
    const report = await (await sightingModel()).findOne({ _id: id, ...(canModerate(account) ? {} : { ownerId: account.id }) }).lean();
    if (!report) return Response.json({ detail: "Report not found." }, { status: 404 });
    if (report.status === "withdrawn") return Response.json({ detail: "This report was withdrawn. Its photo and location were deleted.", withdrawnAt: report.withdrawnAt }, { status: 410 });
    return Response.json(reportSummary(report, account.id), { headers: { "Cache-Control": "no-store" } });
  } catch { return Response.json({ detail: "Report could not be loaded." }, { status: 503 }); }
}

// Owner corrections to a pending, unreviewed report. The photo and any model identification stay as submitted.
export async function PATCH(request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { account, id, error } = await context(request, params);
    if (error) return error;
    const body = await request.json().catch(() => null);
    if (!body || typeof body !== "object") return Response.json({ detail: "Send the corrected fields as JSON." }, { status: 400 });
    if (await ownerMissing(id, account.id)) return Response.json({ detail: "Report not found." }, { status: 404 });
    const model = await sightingModel();
    const original = await model.findOne({ _id: id, ...editableByOwner(account.id) }).lean();
    if (!original) return Response.json({ detail: NOT_EDITABLE }, { status: 409 });

    const set: Record<string, unknown> = {}, changes: Record<string, { from: unknown; to: unknown }> = {};
    const text = (field: "placeName" | "notes" | "plantDescription" | "suggestedSpecies", limit: number) => {
      if (body[field] === undefined) return true;
      if (typeof body[field] !== "string" || body[field].trim().length > limit) return false;
      const value = body[field].trim();
      if (value !== (original[field] ?? "")) { set[field] = value; changes[field] = { from: original[field] ?? "", to: value }; }
      return true;
    };
    if (!text("placeName", 200) || !text("notes", 2000) || !text("plantDescription", 2000) || !text("suggestedSpecies", 120)) return Response.json({ detail: "Check the place name, notes, description and suggested name lengths." }, { status: 400 });

    if (body.observedAt !== undefined) {
      const observedAt = new Date(String(body.observedAt));
      if (!/(Z|[+-]\d{2}:\d{2})$/.test(String(body.observedAt)) || !Number.isFinite(observedAt.getTime()) || observedAt.getTime() > Date.now() + 5 * 60_000) return Response.json({ detail: "Observation time must be a valid time that is not in the future." }, { status: 400 });
      if (observedAt.getTime() !== new Date(original.observedAt).getTime()) { set.observedAt = observedAt; changes.observedAt = { from: original.observedAt, to: observedAt }; }
    }
    if (body.latitude !== undefined || body.longitude !== undefined) {
      const latitude = Number(body.latitude), longitude = Number(body.longitude), method = String(body.locationMethod ?? "manual");
      const accuracy = body.accuracy === undefined || body.accuracy === null || body.accuracy === "" ? null : Number(body.accuracy);
      if (!Number.isFinite(latitude) || !Number.isFinite(longitude) || Math.abs(latitude) > 90 || Math.abs(longitude) > 180 || !(LOCATION_METHODS as readonly string[]).includes(method) || (accuracy !== null && (!Number.isFinite(accuracy) || accuracy < 0))) return Response.json({ detail: "Check the corrected location." }, { status: 400 });
      const [oldLongitude, oldLatitude] = original.location?.coordinates ?? [];
      if (latitude !== oldLatitude || longitude !== oldLongitude || method !== original.locationMethod) {
        set.location = { type: "Point", coordinates: [longitude, latitude] }; set.locationMethod = method; set.locationAccuracy = method === "gps" ? accuracy : null;
        changes.location = { from: { latitude: oldLatitude, longitude: oldLongitude, method: original.locationMethod }, to: { latitude, longitude, method } };
      }
    }
    if (!Object.keys(changes).length) return Response.json(reportSummary(original, account.id));
    // A corrected report returns to the review queue.
    if (original.status === "correction_requested") { set.status = "pending"; changes.status = { from: "correction_requested", to: "pending" }; }
    // Without a confident model identification, the reported species follows the contributor's suggestion.
    if ("suggestedSpecies" in set && original.prediction?.status !== "identified" && !original.verifiedSpeciesId) set.reportedSpecies = (set.suggestedSpecies as string) || "unknown";
    const updated = await model.findOneAndUpdate({ _id: id, ...editableByOwner(account.id) }, { $set: set, $push: { editHistory: { editedAt: new Date(), editedBy: account.username, changes } } }, { new: true }).lean();
    if (!updated) return Response.json({ detail: NOT_EDITABLE }, { status: 409 });
    // A corrected pending report gets a fresh AI review.
    if (updated.status === "pending") after(() => reviewPendingReports().catch(() => undefined));
    return Response.json(reportSummary(updated, account.id));
  } catch { return Response.json({ detail: "The correction could not be saved. Please retry." }, { status: 503 }); }
}

// Withdrawal deletes the photo, coordinates and descriptive content immediately; a minimal tombstone remains.
export async function DELETE(request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { account, id, error } = await context(request, params);
    if (error) return error;
    if (await ownerMissing(id, account.id)) return Response.json({ detail: "Report not found." }, { status: 404 });
    const model = await sightingModel();
    const now = new Date();
    const result = await model.updateOne({ _id: id, ...editableByOwner(account.id) }, {
      $set: { status: "withdrawn", withdrawnAt: now, trainingConsent: false, trainingCandidateStatus: "not_requested", labelReviewStatus: "not_required", reportedSpecies: "withdrawn" },
      $unset: { photo: "", location: "", placeName: "", notes: "", plantDescription: "", suggestedSpecies: "", prediction: "", speciesDescription: "", citations: "", photoHash: "", sourcePhotoHash: "", identificationId: "", locationAccuracy: "", editHistory: "" },
    });
    if (!result.modifiedCount) return Response.json({ detail: NOT_EDITABLE }, { status: 409 });
    return Response.json({ id, status: "withdrawn", withdrawnAt: now.toISOString() });
  } catch { return Response.json({ detail: "The report could not be withdrawn. Please retry." }, { status: 503 }); }
}
