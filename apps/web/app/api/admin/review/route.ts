import { canModerate, currentAccount, isAdmin } from "../../../../src/lib/auth";
import { applyReview, CHECKABLE, simpleReview } from "../../../../src/lib/review";
import { TARGET_SPECIES } from "../../../../src/lib/ai-result";
import { after } from "next/server";
import { aiReviewStatus, reviewPendingReports } from "../../../../src/lib/ai-review";
import { ACTIVE, AWAITING_REVIEW, sameOriginRequest, sightingModel, reportSummary } from "../../../../src/lib/sightings";

// "awaiting" lists reports an administrator has not checked yet (recorded with the AI result, or legacy pending).
const VIEWS: Record<string, string[]> = { awaiting: CHECKABLE, verified: ["verified"], rejected: ["rejected"] };
import { MIN_TRAINING_GROUPS_PER_CLASS, MIN_TRAINING_REPORTS, queueTrainingIfReady, trainingClasses, trainingJobs } from "../../../../src/lib/training-jobs";
import mongoose from "mongoose";
import { speciesInformation } from "../../../../src/features/identification/species-information";
import { indexVerifiedReference, markReferenceIndexFailed, retryApprovedReferenceIndexing } from "../../../../src/lib/verified-references";

export const runtime = "nodejs";
export const maxDuration = 60;
export async function GET(request: Request) {
  if (!sameOriginRequest(request)) return Response.json({ detail: "This request is not allowed." }, { status: 403 });
  try {
    const account = await currentAccount(request);
    if (!account) return Response.json({ detail: "Sign in first." }, { status: 401 });
    if (!canModerate(account)) return Response.json({ detail: "Reviewer or administrator access required." }, { status: 403 });
    await queueTrainingIfReady();
    const model = await sightingModel(), jobs = await trainingJobs();
    // Every submitted report is verified here; the queue defaults to reports awaiting review, oldest first.
    const view = new URL(request.url).searchParams.get("view") ?? "awaiting";
    const statuses = VIEWS[view] ?? CHECKABLE;
    const reports = await model.find({ ...ACTIVE, status: { $in: statuses } }).sort({ submittedAt: -1 }).limit(200).lean();
    const counts = Object.fromEntries((await model.aggregate<{ _id: string; n: number }>([{ $match: ACTIVE }, { $group: { _id: "$status", n: { $sum: 1 } } }])).map(row => [row._id, row.n]));
    let worker: unknown = null;
    // Written by the training worker on the training computer (scripts/auto_training_worker.py).
    worker = await mongoose.connection.db!.collection("worker_status").findOne({ _id: "auto_training" as never });
    // Training worker and job details are administrator-only; reviewers get the label queue.
    const admin = isAdmin(account);
    // Opening the queue also sweeps any reports the AI reviewer has not seen yet.
    after(() => Promise.all([reviewPendingReports().catch(() => undefined), retryApprovedReferenceIndexing().catch(error => console.error("Verified-reference queue retry failed", error instanceof Error ? error.message : "unknown"))]));
    const classes = await trainingClasses();
    const reviewClasses = classes.map(entry => {
      const info = speciesInformation[entry.id];
      const citation = info?.source.url || entry.citation || "";
      let acceptedCitation = "";
      try { const url = new URL(citation); if (url.protocol === "https:" && !url.username && !url.password) acceptedCitation = citation; } catch { /* No accepted reference available. */ }
      return { ...entry, acceptedCitation, diagnosticDescription: info?.appearance || info?.description || "" };
    });
    return Response.json({ role: account.role, worker: admin ? worker : null, view, counts, reports: reports.map(row => ({ ...reportSummary(row), verifiedSpeciesId: row.verifiedSpeciesId, technicalCheck: row.technicalCheck, reviewHistory: row.reviewHistory, editCount: row.editHistory?.length ?? 0, aiReview: row.aiReview ?? null })), ai: await aiReviewStatus(), classes: reviewClasses, jobs: admin ? await jobs.find().sort({ createdAt: -1 }).limit(10).lean() : [], approvedWaiting: await model.countDocuments({ status: "verified", trainingConsent: true, trainingCandidateStatus: "approved", labImport: { $exists: false } }), minTrainingReports: MIN_TRAINING_REPORTS, minTrainingGroupsPerClass: MIN_TRAINING_GROUPS_PER_CLASS }, { headers: { "Cache-Control": "no-store" } });
  } catch { return Response.json({ detail: "Review queue is unavailable." }, { status: 503 }); }
}
export async function PATCH(request: Request) {
  if (!sameOriginRequest(request)) return Response.json({ detail: "This request is not allowed." }, { status: 403 });
  try {
    const account = await currentAccount(request);
    if (!account) return Response.json({ detail: "Sign in first." }, { status: 401 });
    if (!canModerate(account)) return Response.json({ detail: "Reviewer or administrator access required." }, { status: 403 });
    const body = await request.json();
    // Simple check: Approve (keep the AI species), Correct (pick the right species) or Reject.
    if (["simple_approve", "simple_correct", "simple_reject"].includes(body.action)) {
      if (typeof body.id !== "string" || !/^[a-f0-9]{24}$/i.test(body.id)) return Response.json({ detail: "Unknown report." }, { status: 400 });
      const classes = await trainingClasses();
      let species = classes.find(entry => entry.id === body.speciesId) ?? null;
      if (!species && body.action === "simple_correct" && typeof body.scientificName === "string" && /^[A-Z][a-z-]+ [a-z-]+(?: [A-Za-z .()-]+)?$/.test(body.scientificName.trim()) && body.scientificName.length <= 150) {
        const name = body.scientificName.trim();
        species = { id: name.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/_$/, ""), role: body.notInvasive === true ? "lookalike" : "unclassified", scientific_name: name, common_name: typeof body.commonName === "string" ? body.commonName.trim().slice(0, 120) || name : name };
      }
      if (body.action === "simple_correct" && !species) return Response.json({ detail: "Choose the correct species, or type its scientific name (for example Lantana camara)." }, { status: 400 });
      const action = body.action === "simple_approve" ? "approve" : body.action === "simple_correct" ? "correct" : "reject";
      const saved = await simpleReview({ id: body.id, reviewer: { id: account.id, username: account.username }, action, species, note: typeof body.note === "string" ? body.note.slice(0, 2000) : "", targetSpecies: TARGET_SPECIES });
      if (!saved) return Response.json({ detail: "Another administrator already checked this report." }, { status: 409 });
      if ("error" in saved) return Response.json({ detail: saved.error }, { status: 400 });
      return Response.json({ id: String(saved.report._id), status: saved.report.status, training: saved.train });
    }
    const actions = ["approve", "quick_verify", "detailed_verify", "correct_identification", "reject", "request_correction"];
    if (typeof body.id !== "string" || !/^[a-f0-9]{24}$/i.test(body.id) || !actions.includes(body.action) || typeof body.rationale !== "string" || !body.rationale.trim() || body.rationale.trim().length > 2000) return Response.json({ detail: "Supply a report, action and review rationale." }, { status: 400 });
    const model = await sightingModel();
    const waiting = { _id: body.id, ...ACTIVE, status: { $in: AWAITING_REVIEW } };
    const original = await model.findOne(waiting);
    if (!original) return Response.json({ detail: "This report is no longer awaiting review." }, { status: 409 });
    const classes = await trainingClasses();
    let species = classes.find(entry => entry.id === body.speciesId);
    if (!species && body.action === "detailed_verify" && typeof body.scientificName === "string" && /^[A-Z][a-z-]+ [a-z-]+(?: [A-Za-z .()-]+)?$/.test(body.scientificName.trim()) && body.scientificName.length <= 150) {
      const name = body.scientificName.trim();
      const ecological = body.ecologicalStatus === "target_invasive" ? "invasive" : body.ecologicalStatus === "non_target" ? "lookalike" : "unclassified";
      species = { id: name.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/_$/, ""), role: ecological, scientific_name: name, common_name: typeof body.commonName === "string" ? body.commonName.trim().slice(0, 120) || name : name };
    }
    const information = species ? speciesInformation[species.id] : null;
    const acceptedCitation = information?.source.url || species?.citation || "";
    const submittedDescription = typeof body.description === "string" ? body.description.trim() : "";
    const description = body.action === "quick_verify" ? information?.appearance || information?.description || "" : submittedDescription || information?.appearance || information?.description || (body.action === "approve" ? original.plantDescription || "" : "");
    const citation = body.action === "quick_verify" || body.action === "correct_identification" ? acceptedCitation : typeof body.citation === "string" && body.citation.trim() ? body.citation.trim() : acceptedCitation;
    let citationValid = false; try { const url = new URL(citation); citationValid = url.protocol === "https:" && !url.username && !url.password; } catch { /* A reviewed species needs a real citation URL. */ }
    const rationale = body.rationale.trim();
    if (body.action === "quick_verify") {
      const submitted = `${original.suggestedSpecies || ""} ${original.reportedSpecies || ""}`.toLocaleLowerCase();
      const nameMatches = !!species && [species.id.replaceAll("_", " "), species.scientific_name, species.common_name].some(name => name && submitted.includes(name.toLocaleLowerCase()));
      const predictedMatches = !!species && original.prediction?.method === "model" && original.prediction?.status === "identified" && original.prediction?.species?.id === species.id;
      if (body.confirmed !== true || rationale.length < 10 || rationale.length > 300 || !species || !nameMatches || !predictedMatches || !citationValid || !description || description.length > 2000) return Response.json({ detail: "Quick Verify requires a supported submitted species, a matching identified CNN class, an accepted HTTPS reference, explicit photo confirmation, and a short rationale. Use Detailed Review when these conditions do not apply." }, { status: 400 });
    }
    if (["approve", "detailed_verify"].includes(body.action) && (body.confirmed !== true || !species || description.trim().length < 10 || description.length > 2000 || citation.length > 2000 || !citationValid)) return Response.json({ detail: "Confirm the species, provide its diagnostic description, and supply an HTTPS species citation." }, { status: 400 });
    if (body.action === "correct_identification" && (body.confirmed !== true || !species || citation.length > 2000 || !citationValid || rationale.length < 10)) return Response.json({ detail: "Confirm the corrected species, provide a short reason, and use an accepted HTTPS reference." }, { status: 400 });
    if (body.action === "reject" && rationale.length < 10) return Response.json({ detail: "Provide a reason of at least 10 characters before rejecting." }, { status: 400 });
    if (body.action === "request_correction" && rationale.length < 10) return Response.json({ detail: "Provide a reason of at least 10 characters when requesting a correction." }, { status: 400 });
    const evidence = typeof body.evidence === "string" ? body.evidence.trim().slice(0, 2000) : "";
    if (body.action === "detailed_verify" && body.evidenceRequired === true && evidence.length < 10) return Response.json({ detail: "Add the requested supporting evidence before completing this detailed review." }, { status: 400 });
    const ecologicalStatuses = ["target_invasive", "non_target", "pending_ecological_review"];
    const ecologicalStatus = body.action === "detailed_verify" && ecologicalStatuses.includes(body.ecologicalStatus) ? body.ecologicalStatus as "target_invasive" | "non_target" | "pending_ecological_review" : "pending_ecological_review";
    const ecologicalCitation = typeof body.ecologicalCitation === "string" ? body.ecologicalCitation.trim() : "";
    const ecologicalRationale = typeof body.ecologicalRationale === "string" ? body.ecologicalRationale.trim() : "";
    if (body.action === "detailed_verify" && ecologicalStatus !== "pending_ecological_review") {
      let ecologicalCitationValid = false; try { const url = new URL(ecologicalCitation); ecologicalCitationValid = url.protocol === "https:" && !url.username && !url.password; } catch { /* Admin ecological review requires a real source. */ }
      if (!isAdmin(account) || body.ecologyConfirmed !== true || !ecologicalCitationValid || ecologicalCitation.length > 2000 || ecologicalRationale.length < 20 || ecologicalRationale.length > 2000) return Response.json({ detail: "Only an administrator may confirm ecological status, and must confirm a Philippine-relevant HTTPS source with a rationale." }, { status: 400 });
    }
    if (body.trainingEligible === true && (original.trainingConsent !== true || ecologicalStatus !== "target_invasive" || body.action !== "detailed_verify" || !isAdmin(account))) return Response.json({ detail: "Training approval requires contributor consent, administrator-confirmed target invasive status and a separate detailed eligibility review." }, { status: 400 });
    if (body.action === "quick_verify" && body.trainingEligible === true) return Response.json({ detail: "Quick Verify cannot approve an image for CNN training." }, { status: 400 });
    if (body.referenceEligible === true && (original.referenceConsent !== true || body.confirmed !== true || !["quick_verify", "detailed_verify", "correct_identification"].includes(body.action))) return Response.json({ detail: "Reference approval requires contributor reference-use consent and a human species verification." }, { status: 400 });
    const saved = await applyReview({ id: body.id, reviewer: { id: account.id, username: account.username }, action: body.action, species: species ?? null, description, citation, rationale, confirmed: body.confirmed === true, trainingEligible: body.trainingEligible === true, referenceEligible: body.referenceEligible === true, ecologicalStatus, ecologicalCitation, ecologicalRationale, evidence: evidence || undefined, basis: "human" });
    if (!saved) return Response.json({ detail: "Another review already changed this report." }, { status: 409 });
    if (saved.referenceQueued) after(() => indexVerifiedReference(body.id).catch(async error => { await markReferenceIndexFailed(body.id, error).catch(() => undefined); console.error("Verified-reference indexing failed", error instanceof Error ? error.message : "unknown"); }));
    const { report, trainingQueued: queued } = saved;
    return Response.json({ id: String(report._id), status: report.status, trainingCandidateStatus: report.trainingCandidateStatus, trainingQueued: queued });
  } catch { return Response.json({ detail: "Review could not be saved." }, { status: 503 }); }
}
