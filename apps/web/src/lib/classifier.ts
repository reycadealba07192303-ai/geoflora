// In-process plant classifier: the ML models run inside the Next.js server with ONNX Runtime, so GeoFlora needs no
// separate Python inference service. Models live in apps/web/models/<version>/model.onnx (converted and checked by
// ml-lab/scripts/export_onnx.py). models/ensemble.json says which models are used:
//   members  - 21-class models whose probabilities are averaged (ensemble)
//   confirm  - optional 3-class model that confirms an uncertain guess for Hagonoy, Lantana or water hyacinth
//   threshold, confirmThreshold, confirmFloor - chosen on validation data (see docs/ml-in-nextjs.md); the 3-class
//   model may confirm only when the ensemble's top score is at least confirmFloor
// Preprocessing matches services/ml and training: RGB, 224x224, x / 127.5 - 1.
import { readFile } from "node:fs/promises";
import path from "node:path";
import sharp from "sharp";

type Ort = typeof import("onnxruntime-node");
interface Species { id: string; scientific_name: string; common_name: string; role?: string }
interface Member { version: string; classes: Species[]; session: import("onnxruntime-node").InferenceSession }
interface Ensemble { version: string; members: Member[]; confirm: Member | null; threshold: number; confirmThreshold: number; confirmFloor: number }
export interface Candidate { species: Species; confidence: number }
export interface Prediction { status: "identified" | "uncertain"; species: Species | null; confidence: number; confidence_threshold: number; candidates: Candidate[]; model_version: string; confirmed_by?: string }

// turbopackIgnore: models/ is added to the bundle by outputFileTracingIncludes in next.config.ts, so the build does not
// trace the whole project from this runtime path.
export const MODELS_DIR = process.env.GEOFLORA_MODELS_DIR ?? path.join(/*turbopackIgnore: true*/ process.cwd(), "models");
export class ImageError extends Error {}

const shared = globalThis as typeof globalThis & { geofloraEnsemble?: Promise<Ensemble>; geofloraEnsembleStamp?: string };

async function load(): Promise<Ensemble> {
  const ort: Ort = await import("onnxruntime-node");
  const config = JSON.parse(await readFile(path.join(/*turbopackIgnore: true*/ MODELS_DIR, "ensemble.json"), "utf8")) as { version: string; members: string[]; confirm?: string | null; threshold: number; confirmThreshold?: number; confirmFloor?: number };
  const open = async (version: string): Promise<Member> => {
    const folder = path.join(/*turbopackIgnore: true*/ MODELS_DIR, version);
    const mapping = JSON.parse(await readFile(path.join(/*turbopackIgnore: true*/ folder, "class_mapping.json"), "utf8")) as { classes: Species[] };
    const session = await ort.InferenceSession.create(path.join(/*turbopackIgnore: true*/ folder, "model.onnx"), { executionProviders: ["cpu"], graphOptimizationLevel: "all" });
    return { version, classes: mapping.classes, session };
  };
  const members = await Promise.all(config.members.map(open));
  const ids = members[0].classes.map(entry => entry.id).join();
  if (members.some(member => member.classes.map(entry => entry.id).join() !== ids)) throw Error("Ensemble members must share the same classes in the same order.");
  return { version: config.version, members, confirm: config.confirm ? await open(config.confirm) : null, threshold: config.threshold, confirmThreshold: config.confirmThreshold ?? 1, confirmFloor: config.confirmFloor ?? 0 };
}

// Reloads automatically when models/ensemble.json changes (a newly approved model).
export async function ensemble() {
  const { mtimeMs } = await import("node:fs/promises").then(fs => fs.stat(path.join(/*turbopackIgnore: true*/ MODELS_DIR, "ensemble.json")));
  if (!shared.geofloraEnsemble || shared.geofloraEnsembleStamp !== String(mtimeMs)) {
    shared.geofloraEnsembleStamp = String(mtimeMs);
    shared.geofloraEnsemble = load().catch(error => { shared.geofloraEnsemble = undefined; throw error; });
  }
  return shared.geofloraEnsemble;
}

export async function health() {
  try {
    const model = await ensemble();
    const species = model.members[0].classes;
    return { ready: true, model_version: model.version, supported_species_count: species.length, species, reason: null };
  } catch (error) {
    console.error("Classifier unavailable", error instanceof Error ? error.message : error);
    return { ready: false, model_version: null, supported_species_count: 0, species: [], reason: "The identification model is not installed on this server." };
  }
}

async function tensor(image: Buffer) {
  let pixels: Buffer;
  try {
    const decoded = sharp(image, { limitInputPixels: 40_000_000 }).rotate();
    const meta = await decoded.metadata();
    if (!meta.width || !meta.height || meta.width < 64 || meta.height < 64) throw new ImageError("Image dimensions must be at least 64 by 64 pixels.");
    pixels = await decoded.removeAlpha().toColourspace("srgb").resize(224, 224, { fit: "fill", kernel: "cubic" }).raw().toBuffer();
  } catch (error) {
    if (error instanceof ImageError) throw error;
    throw new ImageError("Image could not be safely decoded.");
  }
  const data = new Float32Array(224 * 224 * 3);
  for (let i = 0; i < data.length; i++) data[i] = pixels[i] / 127.5 - 1;
  const ort: Ort = await import("onnxruntime-node");
  return new ort.Tensor("float32", data, [1, 224, 224, 3]);
}

async function run(member: Member, input: unknown) {
  const output = await member.session.run({ image: input as import("onnxruntime-node").Tensor });
  return { probs: Array.from(output.probs.data as Float32Array), features: Array.from(output.features.data as Float32Array) };
}

export async function predict(image: Buffer): Promise<Prediction> {
  const model = await ensemble();
  const input = await tensor(image);
  const outputs = await Promise.all(model.members.map(member => run(member, input)));
  const classes = model.members[0].classes;
  const probs = classes.map((_, i) => outputs.reduce((sum, out) => sum + out.probs[i], 0) / outputs.length);
  const order = probs.map((value, index) => [value, index] as const).sort((a, b) => b[0] - a[0]);
  const [topScore, topIndex] = order[0];
  const candidates = order.slice(0, 3).map(([value, index]) => ({ species: classes[index], confidence: value }));
  let status: Prediction["status"] = topScore >= model.threshold ? "identified" : "uncertain";
  let confirmedBy: string | undefined;
  // An uncertain guess for one of the three original targets is accepted when the 3-class model agrees and is sure.
  if (status === "uncertain" && model.confirm && topScore >= model.confirmFloor) {
    const guess = classes[topIndex];
    const confirm = await run(model.confirm, input);
    const best = confirm.probs.indexOf(Math.max(...confirm.probs));
    if (model.confirm.classes[best]?.id === guess.id && confirm.probs[best] >= model.confirmThreshold) { status = "identified"; confirmedBy = model.confirm.version; }
  }
  return { status, species: status === "identified" ? classes[topIndex] : null, confidence: topScore, confidence_threshold: model.threshold, candidates, model_version: model.version, ...(confirmedBy ? { confirmed_by: confirmedBy } : {}) };
}

// L2-normalised feature vector of the first member, for verified-reference search (not a class probability).
export async function embed(image: Buffer) {
  const model = await ensemble();
  const { features } = await run(model.members[0], await tensor(image));
  const norm = Math.hypot(...features);
  if (!Number.isFinite(norm) || norm <= 1e-12) throw Error("The visual feature vector has no usable magnitude.");
  return { embedding: features.map(value => value / norm), embedding_version: `${model.members[0].version}:backbone-output-v1`, score_type: "uncalibrated_cosine_similarity" };
}
