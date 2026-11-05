import { invalidateCatalog } from "./catalog";
import { ACTIVE, AWAITING_REVIEW, sightingModel } from "./sightings";
import { queueTrainingIfReady } from "./training-jobs";

export type ReviewAction = "approve" | "quick_verify" | "detailed_verify" | "correct_identification" | "reject" | "request_correction";
export interface ReviewSpecies { id: string; scientific_name: string; common_name: string; role?: string; citation?: string }
export interface ReviewInput {
  id: string;
  reviewer: { id: string; username: string };
  action: ReviewAction;
  species: ReviewSpecies | null;
  description: string;
  citation: string;
  rationale: string;
  confirmed: boolean;
  trainingEligible?: boolean;
  referenceEligible?: boolean;
  ecologicalStatus?: "target_invasive" | "non_target" | "pending_ecological_review";
  ecologicalCitation?: string;
  ecologicalRationale?: string;
  evidence?: string;
  // "human" for a moderator decision, "ai_review" for the automated reviewer (see lib/ai-review.ts).
  basis: "human" | "ai_review";
  ai?: Record<string, unknown>;
  // The AI reviewer only decides reports that are still plain "pending"; people may also act on correction requests.
  statuses?: string[];
}

// Applies one review decision to a report still awaiting review. Returns null when another review changed it first.
export async function applyReview(input: ReviewInput) {
  const model = await sightingModel();
  const waiting = { _id: input.id, ...ACTIVE, status: { $in: input.statuses ?? AWAITING_REVIEW } };
  const original = await model.findOne(waiting).select("trainingConsent referenceConsent").lean();
  if (!original) return null;
  const approve = ["approve", "quick_verify", "detailed_verify", "correct_identification"].includes(input.action);
  const ecologicalStatus = approve ? input.ecologicalStatus ?? "pending_ecological_review" : "pending_ecological_review";
  const trainingApproved = approve && !!original.trainingConsent && ecologicalStatus === "target_invasive" && input.basis === "human" && input.trainingEligible === true && input.action === "detailed_verify";
  const referenceApproved = approve && !!original.referenceConsent && input.basis === "human" && input.referenceEligible === true;
  const reviewRecord = { reviewerId: input.reviewer.id, reviewer: input.reviewer.username, basis: input.basis, ...(input.ai ? { ai: input.ai } : {}), action: input.action, confirmed: input.confirmed, trainingEligible: trainingApproved, referenceEligible: referenceApproved, verifiedEcologicalStatus: ecologicalStatus, ecologicalCitation: input.ecologicalCitation ?? "", ecologicalRationale: input.ecologicalRationale ?? "", speciesId: approve ? input.species!.id : null, scientificName: approve ? input.species!.scientific_name : null, description: approve ? input.description : null, citation: approve ? input.citation : null, ...(input.evidence ? { evidence: input.evidence } : {}), rationale: input.rationale, reviewedAt: new Date() };
  // Verification never touches `prediction`, so the original model output stays alongside the confirmed species.
  const decision = input.action === "request_correction"
    ? { status: "correction_requested" }
    : { status: approve ? "verified" : "rejected", verifiedAt: approve ? new Date() : null, labelReviewStatus: approve ? "approved" : "rejected", trainingCandidateStatus: original.trainingConsent ? approve ? trainingApproved ? "approved" : "pending_review" : "rejected" : "not_requested", referenceCandidateStatus: original.referenceConsent ? approve ? referenceApproved ? "approved" : "pending_review" : "rejected" : "not_requested", referenceIndexStatus: original.referenceConsent ? approve && referenceApproved ? "pending" : "ineligible" : "not_requested", referenceIndexMessage: original.referenceConsent ? approve && referenceApproved ? "Approved; waiting for embedding and duplicate checks." : "Not approved for the reference index by the human reviewer." : "Contributor did not grant reference-use permission.", verifiedEcologicalStatus: ecologicalStatus, ecologicalCitation: approve ? input.ecologicalCitation ?? "" : "", ecologicalRationale: approve ? input.ecologicalRationale ?? "" : "", verifiedSpeciesId: approve ? input.species!.id : null, verifiedRole: approve ? ecologicalStatus === "target_invasive" ? "invasive" : ecologicalStatus === "non_target" ? "lookalike" : "unclassified" : "", verifiedScientificName: approve ? input.species!.scientific_name : "", verifiedCommonName: approve ? input.species!.common_name : "", verifiedDescription: approve ? input.description : "", verifiedCitation: approve ? input.citation : "" };
  const report = await model.findOneAndUpdate(waiting, { $set: decision, $push: { reviewHistory: reviewRecord } }, { new: true });
  if (!report) return null;
  invalidateCatalog();
  const trainingQueued = trainingApproved ? await queueTrainingIfReady() : false;
  return { report, trainingQueued, referenceQueued: referenceApproved };
}

// ---------- Simple admin check (owner decision 2026-11-05): Approve, Correct or Reject a recorded report ----------
// Approve keeps the AI's species; Correct sets the right one. A report the AI did not get right (not sure, disputed by
// the contributor, or corrected here) becomes a training example automatically when the contributor allowed training;
// scripts/train_from_reports.py adds those photos to the ML lab and retrains.
export const CHECKABLE = ["recorded", ...AWAITING_REVIEW];
export async function simpleReview(input: { id: string; reviewer: { id: string; username: string }; action: "approve" | "correct" | "reject"; species: ReviewSpecies | null; note?: string; targetSpecies: string[] }) {
  const model = await sightingModel();
  const waiting = { _id: input.id, ...ACTIVE, status: { $in: CHECKABLE } };
  const original = await model.findOne(waiting).select("trainingConsent prediction identificationDisagrees aiResult").lean();
  if (!original) return null;
  const prediction = original.prediction as { status?: string; species?: ReviewSpecies | null } | null;
  const species = input.action === "approve" ? input.species ?? (prediction?.status === "identified" ? prediction.species ?? null : null) : input.species;
  if (input.action !== "reject" && !species) return { error: "Choose the correct species first." as const };
  const aiWasRight = input.action === "approve" && prediction?.status === "identified" && !original.identificationDisagrees && prediction.species?.id === species?.id;
  const train = input.action !== "reject" && !!original.trainingConsent && !aiWasRight;
  const target = !!species && input.targetSpecies.includes(species.scientific_name);
  const now = new Date();
  const record = { reviewerId: input.reviewer.id, reviewer: input.reviewer.username, basis: "human", action: input.action === "correct" ? "correct_identification" : input.action, confirmed: input.action !== "reject", trainingEligible: train, speciesId: species?.id ?? null, scientificName: species?.scientific_name ?? null, rationale: input.note?.trim() || (input.action === "approve" ? "Approved." : input.action === "correct" ? `Corrected to ${species?.scientific_name}.` : "Rejected."), reviewedAt: now };
  const set = input.action === "reject"
    ? { status: "rejected", labelReviewStatus: "rejected", trainingCandidateStatus: original.trainingConsent ? "rejected" : "not_requested", verifiedAt: null }
    : { status: "verified", verifiedAt: now, labelReviewStatus: "approved", verifiedSpeciesId: species!.id, verifiedScientificName: species!.scientific_name, verifiedCommonName: species!.common_name || species!.scientific_name, verifiedRole: species!.role === "lookalike" ? "lookalike" : target ? "invasive" : "unclassified", verifiedEcologicalStatus: target ? "target_invasive" : "non_target", trainingCandidateStatus: train ? "approved" : "not_requested" };
  const report = await model.findOneAndUpdate(waiting, { $set: set, $push: { reviewHistory: record } }, { new: true });
  if (!report) return null;
  invalidateCatalog();
  return { report, train };
}
