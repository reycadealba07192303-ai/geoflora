import Anthropic from "@anthropic-ai/sdk";
import { z } from "zod";
import { askVision, useOpenRouter, VisionApiError, visionAvailable, visionImage, visionModel, visionPause } from "./ai-vision";
import { speciesInformation } from "../features/identification/species-information";
import { applyReview, type ReviewSpecies } from "./review";
import { ACTIVE, sightingModel } from "./sightings";
import { trainingClasses } from "./training-jobs";

// Automated sighting review. A vision model looks at the photo and the contributor's notes; this module, not the model,
// decides what is applied. A sighting is verified only when that model and the image classifier independently agree
// on a supported species; it is rejected only when it is not a usable plant photo or repeats another report's photo.
// Everything else stays in the human queue with the recommendation attached.
// The provider (OpenRouter or Claude) is chosen in ai-vision.ts.

export const AI_REVIEWER = { id: "ai-reviewer", username: "GeoFlora AI reviewer" };
export const VERIFY_MIN_CONFIDENCE = 0.85;
export const REJECT_MIN_CONFIDENCE = 0.9;
const MAX_ATTEMPTS = 3;
const LEASE_MS = 5 * 60_000, RETRY_MS = 10 * 60_000;
// Generous bounding box for the Philippine archipelago; points outside go to a person.
const PHILIPPINES = { south: 4.2, north: 21.3, west: 116, east: 127 };

export function aiReviewEnabled() {
  if (process.env.GEOFLORA_AI_REVIEW === "off") return false;
  return visionAvailable() || process.env.GEOFLORA_AI_REVIEW === "on";
}

const Verdict = z.object({
  is_plant: z.boolean().describe("The photo shows a living or recently living plant as its main subject."),
  photo_usable: z.boolean().describe("The plant is clear enough (focus, light, framing) to judge its identity."),
  species_id: z.string().nullable().describe("One id from the supported list that the photo clearly shows, or null."),
  decision: z.enum(["verify", "reject", "needs_human"]),
  confidence: z.number().describe("Your confidence in the decision, from 0 to 1."),
  rationale: z.string().describe("One to three plain sentences for the contributor explaining the decision."),
  concerns: z.array(z.string()).describe("Anything a human reviewer should check; empty when none."),
});
export type AiVerdict = z.infer<typeof Verdict>;

export interface PolicyContext { supportedIds: Set<string>; modelSpeciesId: string | null; inPhilippines: boolean; duplicateOf: string | null }
export type PolicyOutcome = { applied: "verified"; speciesId: string } | { applied: "rejected"; reason: string } | { applied: "needs_human"; reason: string };

// The only place that turns a recommendation into an action. Kept pure so it can be tested without the API.
export function decide(verdict: AiVerdict | null, context: PolicyContext): PolicyOutcome {
  if (context.duplicateOf) return { applied: "rejected", reason: "This photo was already submitted in another report." };
  if (!verdict) return { applied: "needs_human", reason: "The AI reviewer could not assess this report." };
  if (!context.inPhilippines) return { applied: "needs_human", reason: "The recorded location is outside the Philippines; a person should confirm it." };
  const confidence = Number.isFinite(verdict.confidence) ? Math.min(1, Math.max(0, verdict.confidence)) : 0;
  if (verdict.decision === "verify" && verdict.is_plant && verdict.photo_usable && verdict.species_id && context.supportedIds.has(verdict.species_id) && confidence >= VERIFY_MIN_CONFIDENCE) {
    if (context.modelSpeciesId === verdict.species_id) return { applied: "verified", speciesId: verdict.species_id };
    return { applied: "needs_human", reason: context.modelSpeciesId ? "The AI reviewer and the image model disagree on the species." : "The image model did not identify a species, so there is no second opinion." };
  }
  if (verdict.decision === "reject" && (!verdict.is_plant || !verdict.photo_usable) && confidence >= REJECT_MIN_CONFIDENCE) return { applied: "rejected", reason: verdict.rationale };
  return { applied: "needs_human", reason: "The AI reviewer was not confident enough to decide on its own." };
}

function systemPrompt(species: ReviewSpecies[]) {
  const list = species.map(entry => {
    const info = speciesInformation[entry.id];
    return `- ${entry.id}: ${entry.scientific_name} (${entry.common_name})${entry.role === "lookalike" ? ", a non-invasive look-alike" : ""}${info?.appearance ? `. Identifying features: ${info.appearance}` : ""}`;
  }).join("\n");
  return `You review plant sightings submitted to GeoFlora, a monitoring workspace for invasive plants in the Philippines. Contributors photograph a plant and may describe it or suggest a name. An image classifier has already made its own prediction, which you will see; form your own judgement from the photo first and do not defer to it.

Supported species (use these ids only):
${list}

Decide:
- "verify" when the photo clearly shows the diagnostic features of exactly one supported species. Name it in species_id.
- "reject" only when the photo is not a plant, or is too blurred, dark or distant to identify anything.
- "needs_human" in every other case: a plant outside the supported list, a plausible but unclear match, conflicting evidence, or anything unusual. When unsure, choose needs_human; a person will check it.

Write the rationale for the contributor: plain, kind, specific to what is visible, and without mentioning scores, thresholds or the classifier. Put anything only a reviewer needs in concerns.`;
}

type ReviewReport = { plantDescription?: string; suggestedSpecies?: string; reportedSpecies?: string; notes?: string; observedAt: Date; prediction?: Record<string, any> | null };

async function reviewInput(photo: Buffer, report: ReviewReport) {
  const image = await visionImage(photo);
  const prediction = report.prediction;
  const classifier = !prediction ? "No classifier prediction was attached." : prediction.method === "verified_reference" ? `The photo exactly matches an earlier reviewed photo labelled ${prediction.species?.scientific_name ?? "unknown"}.` : prediction.status === "identified" ? `Classifier suggests ${prediction.species?.scientific_name} (score ${(Number(prediction.confidence) * 100).toFixed(1)}%).` : "Classifier was uncertain and assigned no species.";
  // Only what is needed to judge the plant: no names, accounts, place names or coordinates leave the workspace.
  const details = [
    `Contributor's description: ${report.plantDescription?.trim() || "(none)"}`,
    `Contributor's suggested name: ${report.suggestedSpecies?.trim() || (report.reportedSpecies && report.reportedSpecies !== "unknown" ? report.reportedSpecies : "(none)")}`,
    `Contributor's notes: ${report.notes?.trim() || "(none)"}`,
    `Observed: ${report.observedAt.toISOString().slice(0, 10)}, in the Philippines`,
    classifier,
  ].join("\n");
  return { image, text: `Review this sighting.\n\n${details}` };
}

const inPhilippines = (coordinates?: number[] | null) => !!coordinates && coordinates.length === 2 && coordinates[1] >= PHILIPPINES.south && coordinates[1] <= PHILIPPINES.north && coordinates[0] >= PHILIPPINES.west && coordinates[0] <= PHILIPPINES.east;

// Claims one pending report that has no current AI review, so concurrent runs never review the same report twice.
async function claimNext() {
  const model = await sightingModel(), now = new Date();
  const editCount = { $size: { $ifNull: ["$editHistory", []] } };
  return model.collection.findOneAndUpdate(
    { ...ACTIVE, status: "pending", identificationDisagrees: { $ne: true }, $or: [
      { aiReview: null },
      // A review that stopped without recording anything (for example a server restart) is picked up again.
      { "aiReview.state": "running", "aiReview.startedAt": { $lt: new Date(now.getTime() - LEASE_MS) } },
      // Waiting for the provider's allowance to reset.
      { "aiReview.state": "paused" },
      { "aiReview.state": "error", "aiReview.attempts": { $lt: MAX_ATTEMPTS }, "aiReview.finishedAt": { $lt: new Date(now.getTime() - RETRY_MS) } },
      // A contributor correction sends the report back for a fresh look.
      { "aiReview.state": "done", $expr: { $ne: ["$aiReview.editCount", editCount] } },
    ] },
    [{ $set: { aiReview: { state: "running", startedAt: now, editCount, attempts: { $cond: [{ $eq: ["$aiReview.editCount", editCount] }, { $add: [{ $ifNull: ["$aiReview.attempts", 0] }, 1] }, 1] } } } }],
    { sort: { submittedAt: 1 }, returnDocument: "after", projection: { _id: 1, aiReview: 1 } },
  );
}

async function reviewOne(id: unknown, editCount: number, attempts: number) {
  const model = await sightingModel();
  const report = await model.findById(id).select("+photo");
  if (!report?.photo) { await model.updateOne({ _id: id }, { $set: { aiReview: { state: "done", applied: "needs_human", reason: "No photo is stored for this report.", editCount, attempts, finishedAt: new Date() } } }); return "needs_human"; }
  // Species the reviewer can verify: monitored species with reference information, and non-invasive look-alike groups.
  const species = (await trainingClasses()).filter(entry => speciesInformation[entry.id] || entry.role === "lookalike");
  const prediction = report.prediction as Record<string, any> | null;
  const modelSpeciesId = prediction && (prediction.status === "identified" || prediction.method === "verified_reference") ? prediction.species?.id ?? null : null;
  const duplicate = report.photoHash ? await model.findOne({ _id: { $ne: report._id }, photoHash: report.photoHash, status: { $in: ["pending", "verified"] }, submittedAt: { $lte: report.submittedAt } }).select("_id").lean() : null;
  let verdict: AiVerdict | null = null, note = "", answeredBy = visionModel();
  if (!duplicate) {
    const input = await reviewInput(report.photo, report);
    ({ data: verdict, note, model: answeredBy } = await askVision(Verdict, "sighting_review", systemPrompt(species), input.text, input.image));
  }
  const outcome = decide(verdict, { supportedIds: new Set(species.map(entry => entry.id)), modelSpeciesId, inPhilippines: inPhilippines(report.location?.coordinates), duplicateOf: duplicate ? String(duplicate._id) : null });
  const record = { state: "done", applied: outcome.applied, verdict, note, model: answeredBy, editCount, attempts, finishedAt: new Date(), reason: outcome.applied === "verified" ? "" : outcome.reason };
  if (outcome.applied !== "needs_human") {
    const chosen = outcome.applied === "verified" ? species.find(entry => entry.id === outcome.speciesId)! : null;
    const info = chosen ? speciesInformation[chosen.id] : null;
    const rationale = outcome.applied === "verified" ? verdict!.rationale : outcome.reason;
    const saved = await applyReview({ id: String(report._id), reviewer: AI_REVIEWER, action: outcome.applied === "verified" ? "approve" : "reject", species: chosen, description: info?.description ?? (chosen ? verdict!.rationale : ""), citation: info?.source.url ?? chosen?.citation ?? "", rationale: rationale.slice(0, 2000), confirmed: outcome.applied === "verified", basis: "ai_review", ai: { model: answeredBy, confidence: verdict?.confidence ?? null, agreedWithClassifier: outcome.applied === "verified" }, statuses: ["pending"] });
    // Someone else decided it meanwhile; keep the recommendation for the record only.
    if (!saved) record.applied = "needs_human";
  }
  await model.updateOne({ _id: report._id }, { $set: { aiReview: record } });
  return record.applied;
}

let running: Promise<Record<string, number>> | null = null;
// Reviews up to `limit` waiting reports. Safe to call often: one loop per process, and claims prevent double work.
export function reviewPendingReports(limit = 10): Promise<Record<string, number>> {
  if (!aiReviewEnabled()) return Promise.resolve({ disabled: 1 });
  return running ??= (async () => {
    const summary: Record<string, number> = { verified: 0, rejected: 0, needs_human: 0, errors: 0 };
    try {
      if (await visionPause()) return { ...summary, paused: 1 };
      for (let index = 0; index < limit; index++) {
        const claimed = await claimNext();
        if (!claimed) break;
        const { editCount, attempts } = claimed.aiReview as { editCount: number; attempts: number };
        if (attempts > MAX_ATTEMPTS) {
          // Started several times without finishing: hand it to a person rather than retrying forever.
          summary.errors++;
          await (await sightingModel()).updateOne({ _id: claimed._id }, { $set: { "aiReview.state": "error", "aiReview.error": "The AI review stopped several times without finishing; a person should review this sighting.", "aiReview.finishedAt": new Date() } });
          continue;
        }
        try { summary[await reviewOne(claimed._id, editCount, attempts)]++; }
        catch (error) {
          if (error instanceof VisionApiError && error.status === 429) {
            // Not this report's fault: it waits, without using up an attempt, and the loop stops until the reset.
            await (await sightingModel()).updateOne({ _id: claimed._id }, { $set: { aiReview: { state: "paused", editCount, attempts: attempts - 1, note: error.message, resumesAt: error.resumesAt } } });
            summary.paused = 1;
            break;
          }
          console.error("AI review failed:", error);
          summary.errors++;
          const rejectedKey = error instanceof Anthropic.AuthenticationError || (error instanceof VisionApiError && (error.status === 401 || error.status === 403));
          const detail = rejectedKey ? "The API key was rejected." : error instanceof Anthropic.RateLimitError || (error instanceof VisionApiError && error.status === 429) ? "Rate limited by the AI provider; will retry." : error instanceof VisionApiError ? `OpenRouter error ${error.status}: ${error.message}`.slice(0, 300) : error instanceof Anthropic.APIError ? `Anthropic API error ${error.status ?? ""}`.trim() : "The AI review failed; will retry.";
          await (await sightingModel()).updateOne({ _id: claimed._id }, { $set: { "aiReview.state": "error", "aiReview.error": detail, "aiReview.finishedAt": new Date() } });
          if (rejectedKey) break;
        }
      }
      return summary;
    } finally { running = null; }
  })();
}

// Reviews waiting reports every minute from a background timer started when the server starts (instrumentation.ts), so
// reviewing never depends on a request staying open. Requests still trigger a pass right away.
export function startAiReviewSweeper() {
  const flag = globalThis as typeof globalThis & { geofloraAiSweeper?: NodeJS.Timeout };
  if (flag.geofloraAiSweeper || !aiReviewEnabled()) return;
  flag.geofloraAiSweeper = setInterval(() => void reviewPendingReports().catch(error => console.error("AI review sweep failed:", error)), 60_000);
  flag.geofloraAiSweeper.unref?.();
}

// Counts for the admin panel.
export async function aiReviewStatus() {
  const model = await sightingModel();
  const rows = await model.aggregate<{ _id: string | null; n: number }>([{ $match: { ...ACTIVE, aiReview: { $ne: null } } }, { $group: { _id: { $ifNull: ["$aiReview.applied", "$aiReview.state"] }, n: { $sum: 1 } } }]);
  const counts = Object.fromEntries(rows.map(row => [row._id ?? "unknown", row.n]));
  const waiting = await model.countDocuments({ ...ACTIVE, status: "pending", identificationDisagrees: { $ne: true }, $or: [{ aiReview: null }, { "aiReview.state": { $in: ["paused", "running"] } }] });
  const pause = await visionPause();
  const lastError = await model.findOne({ "aiReview.state": "error" }).sort({ "aiReview.finishedAt": -1 }).select("aiReview").lean();
  return { enabled: aiReviewEnabled(), model: visionModel(), provider: useOpenRouter() ? "OpenRouter" : "Anthropic", counts, waiting, lastError: (lastError?.aiReview as { error?: string } | undefined)?.error ?? null, thresholds: { verify: VERIFY_MIN_CONFIDENCE, reject: REJECT_MIN_CONFIDENCE }, pausedUntil: pause?.until ?? null, pauseReason: pause?.reason ?? null };
}
