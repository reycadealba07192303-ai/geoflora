import { createHash } from "node:crypto";
import mongoose from "mongoose";
import sharp from "sharp";
import { mlFetch } from "./ml";
import { connectDatabase, sightingModel } from "./sightings";

type Reference = { _id: unknown; sourceObservationId: string; sourceGroupId: string; speciesId: string; scientificName: string; commonName: string; botanicalCitation: string; ecologicalStatus: string; ecologicalCitation: string; reviewerId: string; rationale: string; license: string; consent: boolean; provenance: Record<string, unknown>; imageHash: string; sourceImageHash: string; perceptualHash: string; embedding: number[]; embeddingVersion: string; active: boolean; indexedAt: Date };

async function collection() {
  await connectDatabase();
  const refs = mongoose.connection.db!.collection<Reference>("verified_image_references");
  await Promise.all([refs.createIndex({ sourceObservationId: 1, embeddingVersion: 1 }, { unique: true }), refs.createIndex({ imageHash: 1, embeddingVersion: 1 }, { unique: true }), refs.createIndex({ active: 1, embeddingVersion: 1, speciesId: 1 })]);
  return refs;
}

export async function extractReferenceEmbedding(photo: Buffer) {
  const form = new FormData();
  form.set("image", new Blob([new Uint8Array(photo)], { type: "image/jpeg" }), "verified-reference.jpg");
  const response = await mlFetch("/embed", { method: "POST", body: form, signal: AbortSignal.timeout(30_000) });
  if (!response.ok) throw new Error(`Feature extraction failed (${response.status}).`);
  const body = await response.json() as { embedding?: unknown; embedding_version?: unknown };
  if (!Array.isArray(body.embedding) || !body.embedding.length || body.embedding.some(value => typeof value !== "number" || !Number.isFinite(value)) || typeof body.embedding_version !== "string") throw new Error("Feature extractor returned an invalid embedding.");
  return { embedding: body.embedding as number[], embeddingVersion: body.embedding_version };
}

// Small automated quality screen; the human reviewer still checks plant visibility and label quality.
export async function referenceImageQuality(photo: Buffer) {
  const pixels = await sharp(photo, { limitInputPixels: 40_000_000 }).rotate().resize(32, 32, { fit: "fill" }).removeAlpha().greyscale().raw().toBuffer();
  if (pixels.length !== 1024) return false;
  const mean = pixels.reduce((sum, value) => sum + value, 0) / pixels.length;
  const variance = pixels.reduce((sum, value) => sum + (value - mean) ** 2, 0) / pixels.length;
  return mean >= 10 && mean <= 245 && variance >= 64;
}

async function perceptualHash(photo: Buffer) {
  const pixels = await sharp(photo, { limitInputPixels: 40_000_000 }).rotate().resize(9, 8, { fit: "fill" }).removeAlpha().greyscale().raw().toBuffer();
  let bits = BigInt(0);
  for (let y = 0; y < 8; y++) for (let x = 0; x < 8; x++) if (pixels[y * 9 + x] > pixels[y * 9 + x + 1]) bits |= BigInt(1) << BigInt(y * 8 + x);
  return bits.toString(16).padStart(16, "0");
}

export async function indexVerifiedReference(reportId: string) {
  const reports = await sightingModel();
  const setStatus = async (status: "pending" | "indexed" | "ineligible" | "failed", message: string) => {
    await reports.updateOne({ _id: reportId }, { $set: { referenceIndexStatus: status, referenceIndexMessage: message } });
  };
  const report = await reports.findOne({ _id: reportId, status: "verified", referenceConsent: true, referenceCandidateStatus: "approved", verifiedSpeciesId: { $type: "string" } }).select("+photo ownerId identificationId placeName location observedAt verifiedSpeciesId verifiedScientificName verifiedCommonName verifiedCitation verifiedEcologicalStatus ecologicalCitation reviewHistory photoHash sourcePhotoHash").lean();
  if (!report || !report.photo || !report.verifiedSpeciesId) { await setStatus("ineligible", "Reference eligibility is no longer valid or the photo is unavailable."); return { indexed: false, reason: "Reference eligibility is no longer valid." }; }
  const review = report.reviewHistory?.at(-1);
  if (review?.basis !== "human" || !review?.confirmed || !review?.referenceEligible || !review?.reviewerId || typeof review?.rationale !== "string" || review.rationale.trim().length < 10) { await setStatus("ineligible", "A human verification and reference-use approval are required."); return { indexed: false, reason: "A human verification and reference-use approval are required." }; }
  const photo = Buffer.from(report.photo.buffer.subarray(0, report.photo.position));
  if (!(await referenceImageQuality(photo))) { await setStatus("ineligible", "Photo did not pass the basic image-quality screen."); return { indexed: false, reason: "The photo did not pass the basic image-quality screen." }; }
  const imageHash = createHash("sha256").update(photo).digest("hex");
  const refs = await collection();
  const existing = await refs.findOne({ active: true, $or: [{ imageHash }, ...(report.sourcePhotoHash ? [{ sourceImageHash: report.sourcePhotoHash }] : [])] });
  if (existing) {
    if (existing.sourceObservationId === String(report._id)) { await setStatus("indexed", `Already indexed with embedding ${existing.embeddingVersion}.`); return { indexed: true, embeddingVersion: existing.embeddingVersion, imageHash }; }
    await setStatus("ineligible", "Duplicate of an already indexed reference."); return { indexed: false, duplicateOf: existing.sourceObservationId };
  }
  const { embedding, embeddingVersion } = await extractReferenceEmbedding(photo);
  const imagePHash = await perceptualHash(photo);
  const hashValue = BigInt(`0x${imagePHash}`);
  const candidates = await refs.find({ active: true }).project({ sourceObservationId: 1, sourceGroupId: 1, perceptualHash: 1 }).toArray();
  const duplicate = candidates.find(row => row.sourceGroupId === String(report.identificationId || report._id) || (row.perceptualHash && (hashValue ^ BigInt(`0x${row.perceptualHash}`)).toString(2).replace(/0/g, "").length <= 6));
  if (duplicate) { await setStatus("ineligible", "Same observation or near-duplicate of an already indexed reference."); return { indexed: false, duplicateOf: duplicate.sourceObservationId }; }
  const reference: Reference = {
    _id: new mongoose.Types.ObjectId(), sourceObservationId: String(report._id), sourceGroupId: String(report.identificationId || report._id), speciesId: report.verifiedSpeciesId,
    scientificName: report.verifiedScientificName || "", commonName: report.verifiedCommonName || "", botanicalCitation: report.verifiedCitation || "",
    ecologicalStatus: report.verifiedEcologicalStatus || "pending_ecological_review", ecologicalCitation: report.ecologicalCitation || "",
    reviewerId: String(review.reviewerId), rationale: review.rationale.trim(), license: "explicit_contributor_reference_permission",
    consent: report.referenceConsent === true, provenance: { source: "contributor_sighting", observationId: String(report._id), ownerId: String(report.ownerId || ""), placeName: report.placeName || "", coordinates: report.location?.coordinates || [], observedAt: report.observedAt }, imageHash, sourceImageHash: report.sourcePhotoHash || "", perceptualHash: imagePHash, embedding, embeddingVersion, active: true, indexedAt: new Date(),
  };
  // _id may only be written on insert: also listing it in $set makes MongoDB reject the upsert ("would create a conflict
  // at '_id'"). That path runs whenever a new model's embedding version re-indexes an existing reference.
  const { _id, ...fields } = reference;
  await refs.updateOne({ sourceObservationId: String(report._id), embeddingVersion }, { $set: fields, $setOnInsert: { _id } }, { upsert: true });
  await setStatus("indexed", `Indexed with embedding ${embeddingVersion}.`);
  return { indexed: true, embeddingVersion, imageHash };
}

export async function markReferenceIndexFailed(reportId: string, error: unknown) {
  const reports = await sightingModel();
  console.error("Verified-reference indexing diagnostic", reportId, error instanceof Error ? error.message : "unknown");
  await reports.updateOne({ _id: reportId }, { $set: { referenceIndexStatus: "failed", referenceIndexMessage: "Embedding service or database error. Server logs contain diagnostics; retry from the review queue." } });
}

export async function retryApprovedReferenceIndexing(limit = 50) {
  const reports = await sightingModel();
  const eligible = await reports.find({ status: "verified", referenceConsent: true, referenceCandidateStatus: "approved", verifiedSpeciesId: { $type: "string" }, referenceIndexStatus: { $in: ["pending", "failed", null] }, reviewHistory: { $elemMatch: { basis: "human", confirmed: true, referenceEligible: true } } }).select("_id").sort({ submittedAt: 1 }).limit(limit).lean();
  const ids = eligible.map(report => String(report._id));
  if (!ids.length) return 0;
  const refs = await collection();
  const indexedRows = await refs.find({ active: true, sourceObservationId: { $in: ids } }).project({ sourceObservationId: 1 }).toArray();
  const indexed = new Set(indexedRows.map(row => row.sourceObservationId));
  if (indexed.size) await reports.updateMany({ _id: { $in: indexedRows.map(row => new mongoose.Types.ObjectId(row.sourceObservationId)) } }, { $set: { referenceIndexStatus: "indexed", referenceIndexMessage: "Reference is present in the active MongoDB index." } });
  const pending = ids.filter(id => !indexed.has(id));
  await Promise.all(pending.map(id => indexVerifiedReference(id).catch(async error => { await markReferenceIndexFailed(id, error).catch(() => undefined); console.error("Verified-reference retry failed", error instanceof Error ? error.message : "unknown"); })));
  return pending.length;
}

export async function hasVerifiedReferences() {
  const refs = await collection();
  return (await refs.countDocuments({ active: true })) > 0;
}

export async function findExactVerifiedReference(imageHashes: string[]) {
  if (!imageHashes.length) return null;
  const refs = await collection();
  const row = await refs.findOne({ active: true, $or: [{ imageHash: { $in: imageHashes } }, { sourceImageHash: { $in: imageHashes } }] });
  return row ? { species: { id: row.speciesId, scientific_name: row.scientificName, common_name: row.commonName }, botanicalCitation: row.botanicalCitation, ecologicalStatus: row.ecologicalStatus, ecologicalCitation: row.ecologicalCitation, sourceObservationId: row.sourceObservationId } : null;
}

export async function searchVerifiedReferences(imageHashes: string[], embedding: number[], embeddingVersion: string, limit = 5) {
  const refs = await collection();
  // Exact SHA matches do not depend on the active backbone embedding version.
  const exact = imageHashes.length ? await refs.findOne({ active: true, $or: [{ imageHash: { $in: imageHashes } }, { sourceImageHash: { $in: imageHashes } }] }) : null;
  const rows = await refs.find({ active: true, embeddingVersion }).project({ sourceObservationId: 1, sourceGroupId: 1, speciesId: 1, scientificName: 1, commonName: 1, botanicalCitation: 1, ecologicalStatus: 1, ecologicalCitation: 1, embedding: 1 }).toArray();
  const ranked = rows.map(row => {
    const stored = row.embedding ?? [];
    if (stored.length !== embedding.length) return null;
    let score = 0;
    for (let i = 0; i < stored.length; i++) score += stored[i] * embedding[i];
    return { row, score: Math.max(-1, Math.min(1, score)) };
  }).filter((value): value is NonNullable<typeof value> => value !== null).sort((a, b) => b.score - a.score);
  const speciesBest = new Map<string, (typeof ranked)[number]>();
  for (const item of ranked) if (!speciesBest.has(item.row.speciesId)) speciesBest.set(item.row.speciesId, item);
  const suggestions = [...speciesBest.values()].sort((a, b) => b.score - a.score).slice(0, limit).map(({ row, score }) => ({
    species: { id: row.speciesId, scientific_name: row.scientificName, common_name: row.commonName },
    similarity: Number(score.toFixed(4)), score_type: "uncalibrated_cosine_similarity" as const,
    reference_count: rows.filter(candidate => candidate.speciesId === row.speciesId).length,
    botanical_citation: row.botanicalCitation, ecological_status: row.ecologicalStatus, ecological_citation: row.ecologicalCitation, provenance: { source: "administrator-reviewed contributor photo", observation_id: row.sourceObservationId },
  }));
  return { exact: exact ? { species: { id: exact.speciesId, scientific_name: exact.scientificName, common_name: exact.commonName }, botanicalCitation: exact.botanicalCitation, ecologicalStatus: exact.ecologicalStatus, ecologicalCitation: exact.ecologicalCitation, sourceObservationId: exact.sourceObservationId } : null, suggestions, embeddingVersion };
}

export async function invalidateVerifiedReference(reportId: string, reviewerId: string, rationale: string) {
  const refs = await collection();
  const result = await refs.updateMany({ sourceObservationId: reportId, active: true }, { $set: { active: false, invalidatedAt: new Date(), invalidatedBy: reviewerId, invalidationRationale: rationale } });
  return result.modifiedCount;
}
