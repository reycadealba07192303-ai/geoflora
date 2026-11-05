import mongoose from "mongoose";
import { connectDatabase, sightingModel } from "./sightings";
import { speciesInformation } from "../features/identification/species-information";

const jobSchema = new mongoose.Schema({
  status: { type: String, enum: ["queued", "running", "completed", "failed", "waiting_for_data"], default: "queued" },
  activeKey: { type: String, unique: true, sparse: true },
  reportIds: { type: [String], required: true },
  createdAt: { type: Date, default: Date.now },
  updatedAt: { type: Date, default: Date.now },
  detail: { type: String, default: "" },
  metrics: { type: mongoose.Schema.Types.Mixed, default: null },
  candidatePath: { type: String, default: "" },
  promotion: { type: mongoose.Schema.Types.Mixed, default: null },
  // "ml-lab": retrained by ml-lab/scripts/app_training_worker.py from approved/corrected app reports.
  source: { type: String, default: "" },
}, { collection: "trainingjobs" });
export async function trainingJobs() {
  await connectDatabase();
  type Job = mongoose.InferSchemaType<typeof jobSchema>;
  const model: mongoose.Model<Job> = (mongoose.models.TrainingJob as mongoose.Model<Job> | undefined) ?? mongoose.model<Job>("TrainingJob", jobSchema);
  await model.init(); return model;
}
type TrainingClass = { id: string; scientific_name: string; common_name: string; role?: string; citation?: string; ecological_status?: string };
// Every class the model is trained on or may learn, kept in the database by scripts/species_registry.py (the training
// computer writes it after collecting photos and on each training pass), plus species reviewers have added.
export async function trainingClasses(): Promise<TrainingClass[]> {
  await connectDatabase();
  const registry = await mongoose.connection.db!.collection<TrainingClass & { _id: string }>("species_classes").find().sort({ _id: 1 }).toArray();
  const known = new Map(registry.map(({ _id, ...entry }) => [_id, { ...entry, id: _id, role: entry.role === "lookalike" ? "lookalike" : entry.ecological_status === "confirmed_target_invasive" ? "invasive" : "unclassified" }]));
  // Every species of the live model (generated species-information.ts), so admins can correct to any of them.
  for (const [id, info] of Object.entries(speciesInformation)) {
    if (known.has(id)) continue;
    const scientific = id.replace(/_/g, " ").replace(/^./, first => first.toUpperCase());
    known.set(id, { id, scientific_name: scientific, common_name: info.commonNames?.[0] || scientific, role: info.ecologicalStatus === "target_invasive" ? "invasive" : "lookalike", citation: info.source?.url });
  }
  const reviewed = await (await sightingModel()).find({ labelReviewStatus: "approved", verifiedSpeciesId: { $ne: null } }).select("verifiedSpeciesId verifiedScientificName verifiedCommonName verifiedRole verifiedCitation").lean();
  for (const entry of reviewed) if (entry.verifiedSpeciesId && entry.verifiedScientificName && !known.has(entry.verifiedSpeciesId)) known.set(entry.verifiedSpeciesId, { id: entry.verifiedSpeciesId, scientific_name: entry.verifiedScientificName, common_name: entry.verifiedCommonName || entry.verifiedScientificName, role: entry.verifiedRole || "unclassified", citation: entry.verifiedCitation || undefined });
  return [...known.values()];
}
export const MIN_TRAINING_REPORTS = Math.max(1, Number(process.env.GEOFLORA_MIN_TRAINING_REPORTS) || 1);
export const MIN_TRAINING_GROUPS_PER_CLASS = Math.max(3, Number(process.env.GEOFLORA_MIN_TRAINING_GROUPS_PER_CLASS) || 10);
export async function queueTrainingIfReady() {
  const reports = await sightingModel(), jobs = await trainingJobs();
  if (await jobs.exists({ activeKey: "training" })) return false;
  const ready = await reports.find({ status: "verified", labelReviewStatus: "approved", verifiedEcologicalStatus: "target_invasive", trainingConsent: true, trainingCandidateStatus: "approved", trainingJobId: null, "reviewHistory.0": { $exists: true } }).select("_id verifiedSpeciesId identificationId photoHash sourcePhotoHash reviewHistory").sort({ _id: 1 }).limit(500).lean();
  if (ready.length < MIN_TRAINING_REPORTS) return false;
  const bySpecies = new Map<string, Set<string>>();
  for (const report of ready) {
    const review = report.reviewHistory?.at(-1) as { basis?: string; action?: string; confirmed?: boolean; trainingEligible?: boolean } | undefined;
    if (!report.verifiedSpeciesId || review?.basis !== "human" || review.action !== "detailed_verify" || review.confirmed !== true || review.trainingEligible !== true) continue;
    const groupId = report.identificationId || report.photoHash || report.sourcePhotoHash || String(report._id);
    const groups = bySpecies.get(report.verifiedSpeciesId) ?? new Set<string>(); groups.add(String(groupId)); bySpecies.set(report.verifiedSpeciesId, groups);
  }
  const eligibleSpecies = new Set([...bySpecies].filter(([, groups]) => groups.size >= MIN_TRAINING_GROUPS_PER_CLASS).map(([species]) => species));
  const eligible = ready.filter(report => report.verifiedSpeciesId && eligibleSpecies.has(report.verifiedSpeciesId));
  if (!eligible.length) return false;
  try {
    const job = await jobs.create({ activeKey: "training", reportIds: eligible.map(row => String(row._id)) });
    await reports.updateMany({ _id: { $in: eligible.map(row => row._id) }, trainingJobId: null }, { $set: { trainingJobId: String(job._id) } });
    return true;
  } catch (error) { if ((error as { code?: number }).code === 11000) return false; throw error; }
}
