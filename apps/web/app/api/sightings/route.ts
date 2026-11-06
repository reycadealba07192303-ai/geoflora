import { createHash } from "node:crypto";
import { identifications, normalizePhoto, photoHash } from "../../../src/lib/identifications";
import { ACTIVE, LOCATION_METHODS, sameOriginRequest, sightingModel, reportSummary } from "../../../src/lib/sightings";
import { canModerate, currentAccount } from "../../../src/lib/auth";
import { aiResultOf } from "../../../src/lib/ai-result";
import { rateLimit } from "../../../src/lib/rate-limit";

export const runtime = "nodejs";
// Long enough for the AI review that runs after the response (Vercel Hobby allows up to 60 s).
export const maxDuration = 60;
export async function GET(request: Request) {
  if (!sameOriginRequest(request)) return Response.json({ detail: "This request is not allowed." }, { status: 403 });
  try {
    const account = await currentAccount(request);
    if (!account) return Response.json({ detail: "Sign in to view reports." }, { status: 401 });
    const model = await sightingModel();
    const candidatesOnly = new URL(request.url).searchParams.get("trainingCandidates") === "1";
    if (candidatesOnly && !canModerate(account)) return Response.json({ detail: "Reviewer or administrator access required." }, { status: 403 });
    const rows = await model.find({ ...ACTIVE, ...(canModerate(account) ? {} : { ownerId: account.id }), ...(candidatesOnly ? { trainingConsent: true, trainingCandidateStatus: "pending_review" } : {}) }).select("aiResult reportedSpecies placeName notes plantDescription suggestedSpecies identificationDisagrees trainingConsent trainingCandidateStatus labelReviewStatus observedAt submittedAt location locationMethod locationAccuracy editHistory reviewHistory ownerId status speciesDescription citations verifiedSpeciesId verifiedScientificName verifiedDescription verifiedCitation prediction").sort({ submittedAt: -1, _id: -1 }).limit(500).lean();
    return Response.json({ reports: rows.map(row => reportSummary(row, account.id)), limit: 500 }, { headers: { "Cache-Control": "no-store" } });
  } catch { return Response.json({ detail: "Reports could not be loaded. Check the local database." }, { status: 503 }); }
}
export async function POST(request: Request) {
  if (!sameOriginRequest(request)) return Response.json({ detail: "This request is not allowed." }, { status: 403 });
  try {
    const account = await currentAccount(request);
    if (!account) return Response.json({ detail: "Sign in to submit a report." }, { status: 401 });
    const blocked = await rateLimit(request, "report", account);
    if (blocked) return blocked;
    const form = await request.formData();
    const image = form.get("image");
    const requestId = String(form.get("requestId") ?? "");
    let species = String(form.get("species") ?? "unknown").trim();
    const notes = String(form.get("notes") ?? "").trim();
    const plantDescription = String(form.get("plantDescription") ?? "").trim();
    const suggestedSpecies = String(form.get("suggestedSpecies") ?? "").trim();
    const consentValue = form.get("trainingConsent");
    const referenceConsentValue = form.get("referenceConsent");
    const identificationDisagreesValue = form.get("identificationDisagrees");
    const identificationDisagrees = identificationDisagreesValue === "yes";
    if (plantDescription.length > 2000 || suggestedSpecies.length > 120 || (consentValue !== null && consentValue !== "yes") || (referenceConsentValue !== null && referenceConsentValue !== "yes") || (identificationDisagreesValue !== null && !identificationDisagrees)) return Response.json({ detail: "Check description, suggested name, identification feedback and optional photo-use permissions." }, { status: 400 });
    const trainingConsent = consentValue === "yes";
    const trainingCandidateStatus = trainingConsent ? "pending_review" : "not_requested";
    const referenceConsent = referenceConsentValue === "yes";
    const referenceCandidateStatus = referenceConsent ? "pending_review" : "not_requested";
    const feedback = { ...(plantDescription ? { plantDescription } : {}), ...(suggestedSpecies ? { suggestedSpecies } : {}), ...(trainingConsent ? { trainingConsent } : {}), ...(referenceConsent ? { referenceConsent } : {}) };
    const placeName = String(form.get("placeName") ?? "").trim();
    if (placeName.length > 200) return Response.json({ detail: "Place name must be at most 200 characters." }, { status: 400 });
    const latitudeText = String(form.get("latitude") ?? "").trim();
    const longitudeText = String(form.get("longitude") ?? "").trim();
    const latitude = Number(latitudeText), longitude = Number(longitudeText);
    const method = String(form.get("locationMethod"));
    const observedText = String(form.get("observedAt") ?? "");
    const observedAt = new Date(observedText);
    const accuracyText = String(form.get("accuracy") ?? "");
    const accuracy = accuracyText ? Number(accuracyText) : null;
    if (!/^[0-9a-f-]{36}$/i.test(requestId) || !species || species.length > 120 || notes.length > 2000 || form.get("consent") !== "yes" || !latitudeText || !longitudeText || !Number.isFinite(latitude) || !Number.isFinite(longitude) || Math.abs(latitude) > 90 || Math.abs(longitude) > 180 || !(LOCATION_METHODS as readonly string[]).includes(method) || !/(Z|[+-]\d{2}:\d{2})$/.test(observedText) || !Number.isFinite(observedAt.getTime()) || observedAt.getTime() > Date.now() + 5 * 60_000 || (accuracy !== null && (!Number.isFinite(accuracy) || accuracy < 0))) {
      return Response.json({ detail: "Check location, observation time, species, notes and submission consent." }, { status: 400 });
    }
    if (!(image instanceof File) || !["image/jpeg", "image/png", "image/webp"].includes(image.type)) return Response.json({ detail: "Choose a JPEG, PNG or WebP photo." }, { status: 415 });
    if (!image.size || image.size > 20 * 1024 ** 2) return Response.json({ detail: "Photo must be between 1 byte and 20 MB." }, { status: 413 });
    const input = Buffer.from(await image.arrayBuffer());
    let photo: Buffer;
    try {
      photo = await normalizePhoto(input);
    } catch { return Response.json({ detail: "Photo could not be decoded safely; use a valid image at least 64×64 pixels." }, { status: 422 }); }
    const identificationId = String(form.get("identificationId") ?? "");
    const model = await sightingModel();
    const existing = await model.findOne({ requestId }).lean();
    if (existing && (existing.ownerId !== account.id || existing.status === "withdrawn")) return Response.json({ detail: "Submission ID is unavailable." }, { status: 409 });
    let prediction = null;
    if (identificationId) {
      if (!/^[a-f0-9]{24}$/i.test(identificationId)) return Response.json({ detail: "Invalid identification reference." }, { status: 400 });
      if (existing?.identificationId === identificationId && existing.photoHash === photoHash(photo)) prediction = existing.prediction;
      else {
        const record = await (await identifications()).findOne({ _id: identificationId, ownerId: account.id, photoHash: photoHash(photo), expiresAt: { $gt: new Date() } }).lean();
        if (!record) return Response.json({ detail: "This identification expired or belongs to another photo. Identify this photo again." }, { status: 409 });
        prediction = record.result;
      }
    }
    if (identificationDisagrees && (prediction?.method !== "model" || prediction.status !== "identified")) return Response.json({ detail: "Only an identified CNN suggestion can be marked as not matching this photo." }, { status: 400 });
    // Recorded straight away with the AI result (owner decision 2026-11-05: no botanist, no review queue).
    const aiResult = aiResultOf(prediction, identificationDisagrees);
    const labelReviewStatus = "not_required";
    // The identified species' reference description, shown as part of the AI identification.
    const speciesDescription = aiResult !== "uncertain" ? prediction?.information?.description ?? "" : "";
    if (!identificationDisagrees && prediction?.status === "identified" && prediction.species?.scientific_name) species = prediction.species.scientific_name;
    if (identificationDisagrees) species = "unknown";
    const citations = aiResult !== "uncertain" && prediction?.information?.source?.url ? [prediction.information.source.url] : [];
    const payloadHash = createHash("sha256").update(JSON.stringify({ species, notes, latitude, longitude, method, accuracy, observedAt: observedAt.toISOString(), ...(placeName ? { placeName } : {}), ...feedback, ...(identificationDisagrees ? { identificationDisagrees } : {}), ...(identificationId ? { identificationId } : {}) })).update(photo).digest("hex");
    if (existing) {
      if (existing.ownerId !== account.id) return Response.json({ detail: "Submission ID is unavailable." }, { status: 409 });
      if (existing.payloadHash !== payloadHash) return Response.json({ detail: "This submission ID was already used for different data. Start a new report." }, { status: 409 });
      return Response.json({ ...reportSummary(existing, account.id), replayed: true });
    }
    try {
      const saved = await model.create({ ownerId: account.id, requestId, payloadHash, reportedSpecies: species, placeName, notes, plantDescription, suggestedSpecies, identificationDisagrees, trainingConsent, trainingCandidateStatus, referenceConsent, referenceCandidateStatus, referenceIndexStatus: referenceConsent ? "pending" : "not_requested", verifiedEcologicalStatus: "pending_ecological_review", labelReviewStatus, aiResult, observedAt, location: { type: "Point", coordinates: [longitude, latitude] }, locationMethod: method, locationAccuracy: method === "gps" ? accuracy : null, photo, sourcePhotoHash: photoHash(input), photoHash: photoHash(photo), identificationId: identificationId || null, speciesDescription, citations, status: "recorded", prediction });
      return Response.json(reportSummary(saved, account.id), { status: 201 });
    } catch (error) {
      if ((error as { code?: number }).code === 11000) {
        const replay = await model.findOne({ requestId }).lean();
        if (replay?.ownerId === account.id && replay?.payloadHash === payloadHash) return Response.json({ ...reportSummary(replay, account.id), replayed: true });
        return Response.json({ detail: "Submission conflict. Start a new report." }, { status: 409 });
      }
      throw error;
    }
  } catch (error) {
    if (error instanceof TypeError || error instanceof SyntaxError) return Response.json({ detail: "Invalid submission format." }, { status: 400 });
    // For schema validation failures, log which fields failed (names only, never submitted values).
    const fields = error && typeof error === "object" && "errors" in error && error.errors && typeof error.errors === "object" ? Object.keys(error.errors).join(",") : "";
    console.error("Sighting persistence unavailable", error instanceof Error ? error.name : "unknown", fields);
    return Response.json({ detail: "Could not save the report. Check the local database and retry; your submission ID is preserved." }, { status: 503 });
  }
}
