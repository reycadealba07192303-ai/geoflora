// The image classifier. By default it runs inside this Next.js server (src/lib/classifier.ts, ONNX Runtime), so no
// separate ML service is needed. GEOFLORA_ML_MODE=remote sends requests to the old Python service instead
// (services/ml locally, or a Hugging Face Space), at GEOFLORA_ML_API_URL with GEOFLORA_ML_API_KEY.
// mlFetch keeps the service's HTTP shape (/health, /predict, /embed) so callers work the same in both modes.
import { embed, health, ImageError, predict } from "./classifier";

export const ML_API_URL = (process.env.GEOFLORA_ML_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");
export const ML_REMOTE = process.env.GEOFLORA_ML_MODE === "remote";

async function local(path: string, init: RequestInit) {
  if (path === "/health") return Response.json(await health());
  if (path !== "/predict" && path !== "/embed") return Response.json({ detail: "Not found." }, { status: 404 });
  const image = init.body instanceof FormData ? init.body.get("image") : null;
  if (!(image instanceof Blob)) return Response.json({ detail: "Choose a plant image." }, { status: 400 });
  if (!["image/jpeg", "image/png", "image/webp"].includes(image.type)) return Response.json({ detail: "Upload a JPEG, PNG, or WebP plant photo." }, { status: 415 });
  if (image.size > 20 * 1024 * 1024) return Response.json({ detail: "Image exceeds the 20 MB limit." }, { status: 413 });
  const bytes = Buffer.from(await image.arrayBuffer());
  try {
    return Response.json(path === "/predict" ? await predict(bytes) : await embed(bytes));
  } catch (error) {
    if (error instanceof ImageError) return Response.json({ detail: error.message }, { status: 422 });
    console.error("Classifier failed", error instanceof Error ? error.message : error);
    return Response.json({ detail: "The identification model is not available right now." }, { status: 503 });
  }
}

export function mlFetch(path: string, init: RequestInit = {}) {
  if (!ML_REMOTE) return local(path, init);
  const headers = new Headers(init.headers);
  if (process.env.GEOFLORA_ML_API_KEY) headers.set("X-GeoFlora-Key", process.env.GEOFLORA_ML_API_KEY);
  return fetch(`${ML_API_URL}${path}`, { ...init, headers, cache: "no-store" });
}

export type MlHealth = { ready: boolean; model_version: string | null; supported_species_count: number; reason?: string | null; species?: { id: string; scientific_name: string; common_name: string; role?: string }[] };
export async function mlHealth(timeoutMs = 3000): Promise<MlHealth | null> {
  try { const response = await mlFetch("/health", { signal: AbortSignal.timeout(timeoutMs) }); return response.ok ? await response.json() : null; } catch { return null; }
}
