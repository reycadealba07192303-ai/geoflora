import mongoose from "mongoose";
import { possibleSpecies, reportResult } from "./ai-result";
import { speciesInformation } from "../features/identification/species-information";

const schema = new mongoose.Schema({
  ownerId: { type: String, default: null, index: true },
  requestId: { type: String, required: true, unique: true },
  payloadHash: { type: String, required: true },
  reportedSpecies: { type: String, required: true },
  notes: { type: String, default: "" },
  plantDescription: { type: String, default: "" },
  suggestedSpecies: { type: String, default: "" },
  identificationDisagrees: { type: Boolean, default: false },
  trainingConsent: { type: Boolean, default: false },
  trainingCandidateStatus: { type: String, enum: ["not_requested", "pending_review", "approved", "rejected"], default: "not_requested" },
  referenceConsent: { type: Boolean, default: false },
  referenceCandidateStatus: { type: String, enum: ["not_requested", "pending_review", "approved", "rejected"], default: "not_requested" },
  referenceIndexStatus: { type: String, enum: ["not_requested", "pending", "indexed", "ineligible", "failed", "invalidated"], default: "not_requested" },
  referenceIndexMessage: { type: String, default: "" },
  verifiedEcologicalStatus: { type: String, enum: ["target_invasive", "non_target", "pending_ecological_review"], default: "pending_ecological_review" },
  ecologicalCitation: { type: String, default: "" },
  ecologicalRationale: { type: String, default: "" },
  verifiedSpeciesId: { type: String, default: null },
  // "invasive" or "lookalike" (a non-invasive plant the model learns to tell apart); set with the verified species.
  verifiedRole: { type: String, default: "" },
  trainingJobId: { type: String, default: null },
  reviewHistory: { type: [mongoose.Schema.Types.Mixed], default: [] },
  technicalCheck: { type: String, default: "accepted" },
  labelReviewStatus: { type: String, enum: ["not_required", "pending", "approved", "rejected"], default: "not_required" },
  placeName: { type: String, default: "" },
  observedAt: { type: Date, required: true },
  submittedAt: { type: Date, default: Date.now },
  // Location and photo are removed when a contributor withdraws a report (see docs/part-8-sightings.md).
  location: { type: { type: String, enum: ["Point"], default: "Point" }, coordinates: { type: [Number], default: undefined } },
  locationMethod: { type: String, enum: ["gps", "manual", "map_pin", "photo_gps"], required: true },
  locationAccuracy: { type: Number, default: null },
  // recorded: saved with the AI model's result, no review queue (owner decision 2026-11-05; see lib/ai-result.ts).
  // Older reports: pending -> verified | rejected | correction_requested (back to pending after the owner corrects) | withdrawn.
  status: { type: String, enum: ["recorded", "pending", "correction_requested", "verified", "rejected", "withdrawn"], default: "recorded" },
  // The AI result when the report was saved: target | other | uncertain.
  aiResult: { type: String, enum: ["", "target", "other", "uncertain"], default: "" },
  verifiedAt: { type: Date, default: null },
  withdrawnAt: { type: Date, default: null },
  editHistory: { type: [mongoose.Schema.Types.Mixed], default: [] },
  prediction: { type: mongoose.Schema.Types.Mixed, default: null },
  identificationId: { type: String, default: null },
  photoHash: { type: String, default: null, index: true },
  sourcePhotoHash: { type: String, default: null, index: true },
  speciesDescription: { type: String, default: "" },
  citations: { type: [String], default: [] },
  verifiedScientificName: { type: String, default: "" },
  verifiedCommonName: { type: String, default: "" },
  verifiedDescription: { type: String, default: "" },
  verifiedCitation: { type: String, default: "" },
  photo: { type: Buffer, select: false },
  photoContentType: { type: String, default: "image/jpeg" },
  // Latest automated review (lib/ai-review.ts): its recommendation, whether it was applied, and the report version it saw.
  aiReview: { type: mongoose.Schema.Types.Mixed, default: null },
}, { versionKey: false });
schema.index({ location: "2dsphere" });

// One connection per server instance, kept on globalThis so warm serverless invocations (Vercel) and every route bundle
// reuse it. GEOFLORA_MONGODB_URI is a local server in development or MongoDB Atlas (mongodb+srv://) in production.
const shared = globalThis as typeof globalThis & { geofloraMongo?: Promise<typeof mongoose> };
export async function connectDatabase() {
  const uri = process.env.GEOFLORA_MONGODB_URI ?? "mongodb://127.0.0.1:27017/geoflora";
  shared.geofloraMongo ??= mongoose.connect(uri, { serverSelectionTimeoutMS: 8000, maxPoolSize: 10 }).catch(error => { shared.geofloraMongo = undefined; throw error; });
  await shared.geofloraMongo;
}
export async function sightingModel() {
  await connectDatabase();
  type Sighting = mongoose.InferSchemaType<typeof schema>;
  const model: mongoose.Model<Sighting> = (mongoose.models.Sighting as mongoose.Model<Sighting> | undefined) ?? mongoose.model<Sighting>("Sighting", schema);
  await model.init();
  return model;
}

// Blocks cross-site requests: a browser request must come from this site itself (or an origin listed in
// GEOFLORA_ALLOWED_ORIGINS). Requests without an Origin header (same-origin GETs, scheduled jobs) are allowed; every route
// also checks the signed-in account.
export function sameOriginRequest(request: Request) {
  const origin = request.headers.get("origin");
  if (!origin) return true;
  const host = request.headers.get("x-forwarded-host") ?? request.headers.get("host") ?? new URL(request.url).host;
  const allowed = (process.env.GEOFLORA_ALLOWED_ORIGINS ?? "").split(",").map(value => value.trim()).filter(Boolean);
  try { return new URL(origin).host === host || allowed.includes(origin); } catch { return false; }
}

// photo_gps: read from the photo's EXIF in the browser at identification time.
export const LOCATION_METHODS = ["gps", "manual", "map_pin", "photo_gps"] as const;
// Visible reports exclude withdrawn tombstones.
export const ACTIVE = { status: { $ne: "withdrawn" } };
export const AWAITING_REVIEW = ["pending", "correction_requested"];
// A contributor may correct or withdraw a recorded report, or one awaiting review, never one that was verified or rejected.
export const OWNER_EDITABLE = ["recorded", ...AWAITING_REVIEW];
export function editableByOwner(ownerId: string) {
  return { ownerId, status: { $in: OWNER_EDITABLE }, trainingCandidateStatus: { $nin: ["approved", "rejected"] }, labelReviewStatus: { $nin: ["approved", "rejected"] } };
}
export function reportSummary(row: { _id: unknown; aiResult?: string | null; reportedSpecies: string; placeName?: string; notes?: string; plantDescription?: string; suggestedSpecies?: string; identificationDisagrees?: boolean; trainingConsent?: boolean; trainingCandidateStatus?: string; referenceConsent?: boolean; referenceCandidateStatus?: string; referenceIndexStatus?: string; referenceIndexMessage?: string; verifiedEcologicalStatus?: string; ecologicalCitation?: string; ecologicalRationale?: string; labelReviewStatus?: string; observedAt: Date; submittedAt: Date; location?: { coordinates?: number[] | null } | null; status?: string; speciesDescription?: string; citations?: string[]; verifiedSpeciesId?: string | null; verifiedScientificName?: string; verifiedDescription?: string; verifiedCitation?: string; prediction?: Record<string, unknown> | null; locationMethod?: string; locationAccuracy?: number | null; editHistory?: { editedAt: Date }[]; reviewHistory?: { action: string; rationale: string; reviewedAt: Date; speciesId?: string | null; scientificName?: string | null; basis?: string }[]; ownerId?: string | null; verifiedAt?: Date | null; verifiedCommonName?: string }, viewerId?: string) {
  const referenceIndexStatus = row.referenceIndexStatus ?? (!row.referenceConsent ? "not_requested" : row.referenceCandidateStatus === "rejected" || row.status === "rejected" ? "ineligible" : "pending");
  const referenceIndexMessage = row.referenceIndexMessage ?? (referenceIndexStatus === "ineligible" ? "Reference-use approval was declined or the report was rejected." : row.referenceConsent ? "Awaiting human verification and separate reference-use approval." : "Contributor did not grant reference-use permission.");
  return { id: String(row._id), species: row.verifiedScientificName || row.reportedSpecies, reportedSpecies: row.reportedSpecies, identificationDisagrees: row.identificationDisagrees ?? false, placeName: row.placeName ?? "", notes: row.notes,
    observedAt: new Date(row.observedAt).toISOString(), submittedAt: new Date(row.submittedAt).toISOString(),
    latitude: row.location?.coordinates?.[1], longitude: row.location?.coordinates?.[0], status: row.status,
    plantDescription: row.plantDescription ?? "", suggestedSpecies: row.suggestedSpecies ?? "", trainingConsent: row.trainingConsent ?? false, trainingCandidateStatus: row.trainingCandidateStatus ?? "not_requested", referenceConsent: row.referenceConsent ?? false, referenceCandidateStatus: row.referenceCandidateStatus ?? "not_requested", referenceIndexStatus, referenceIndexMessage, verifiedEcologicalStatus: row.verifiedEcologicalStatus ?? "pending_ecological_review", ecologicalCitation: row.ecologicalCitation ?? "", ecologicalRationale: row.ecologicalRationale ?? "",
    // The identified species' description (AI identification), or for an uncertain result the closest match's.
    result: reportResult(row), possibleSpecies: possibleSpecies(row.prediction as never)?.scientific_name ?? null,
    description: row.verifiedDescription || row.speciesDescription || speciesInformation[String(possibleSpecies(row.prediction as never)?.id ?? "")]?.description || row.plantDescription || row.notes || "",
    citations: [...new Set([...(row.citations ?? []), ...(row.verifiedCitation ? [row.verifiedCitation] : [])])],
    prediction: row.prediction ?? null, labelReviewStatus: row.labelReviewStatus ?? "not_required", labelSource: row.verifiedSpeciesId ? "admin_review" : row.prediction?.status === "identified" ? row.prediction.method || "model" : "user_suggestion",
    locationMethod: row.locationMethod ?? "manual", locationAccuracy: row.locationAccuracy ?? null,
    lastEditedAt: row.editHistory?.length ? new Date(row.editHistory[row.editHistory.length - 1].editedAt).toISOString() : null,
    // Mirrors editableByOwner so the client only offers actions the server will accept.
    editable: !!viewerId && row.ownerId === viewerId && OWNER_EDITABLE.includes(row.status ?? "recorded") && !["approved", "rejected"].includes(row.trainingCandidateStatus ?? "") && !["approved", "rejected"].includes(row.labelReviewStatus ?? ""),
    // The model's original output stays in `prediction`; reviewer-confirmed species is reported separately.
    verifiedSpecies: row.verifiedScientificName ? { id: row.verifiedSpeciesId ?? null, scientificName: row.verifiedScientificName, commonName: row.verifiedCommonName ?? "" } : null,
    verifiedAt: row.verifiedAt ? new Date(row.verifiedAt).toISOString() : null,
    // Latest decision without the reviewer's identity, for the contributor's view.
    latestReview: row.reviewHistory?.length ? (({ action, rationale, reviewedAt, basis }) => ({ action, rationale, reviewedAt: new Date(reviewedAt).toISOString(), byAi: basis === "ai_review" }))(row.reviewHistory[row.reviewHistory.length - 1]) : null };
}
