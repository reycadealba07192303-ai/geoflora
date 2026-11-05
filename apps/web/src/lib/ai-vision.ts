import Anthropic from "@anthropic-ai/sdk";
import { betaZodOutputFormat } from "@anthropic-ai/sdk/helpers/beta/zod";
import mongoose from "mongoose";
import sharp from "sharp";
import { z } from "zod";
import { connectDatabase } from "./sightings";

// One structured vision request, shared by the sighting reviewer (ai-review.ts) and the plant suggestion on Identify.
// OpenRouter (free vision models) when OPENROUTER_API_KEY is set, otherwise Claude through the Anthropic API.

export const CLAUDE_MODEL = "claude-opus-5-5";
// Tried in order by OpenRouter; later ones take over when the first is rate-limited or down.
export const OPENROUTER_MODELS = (process.env.GEOFLORA_AI_REVIEW_MODELS || "nvidia/nemotron-3.5-super-vl:free,google/gemma-4-31b-it:free,google/gemma-4-26b-a4b-it:free").split(",").map(name => name.trim()).filter(Boolean);
const OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions";
export const useOpenRouter = () => !!process.env.OPENROUTER_API_KEY;
export const visionModel = () => useOpenRouter() ? OPENROUTER_MODELS[0] : CLAUDE_MODEL;
export const visionAvailable = () => !!(process.env.OPENROUTER_API_KEY || process.env.ANTHROPIC_API_KEY || process.env.ANTHROPIC_AUTH_TOKEN);

export class VisionApiError extends Error { constructor(readonly status: number, message: string, readonly resumesAt: Date | null = null) { super(message); } }

// When the provider's allowance runs out (OpenRouter's free tier allows 50 requests a day), every caller waits until it
// resets instead of failing over and over. Kept in the database so all parts of the app and restarts see it.
type Pause = { until: Date; reason: string };
async function pauses() {
  await connectDatabase();
  return mongoose.connection.db!.collection<{ _id: string; until: Date; reason: string }>("ai_service");
}
export async function visionPause(): Promise<Pause | null> {
  const pause = await (await pauses()).findOne({ _id: "vision" });
  return pause && pause.until > new Date() ? { until: pause.until, reason: pause.reason } : null;
}
async function pauseVision(until: Date, reason: string) {
  await (await pauses()).updateOne({ _id: "vision" }, { $set: { until, reason } }, { upsert: true });
}

// Upright JPEG, at most 1568 px on a side: enough detail for leaves and flowers without oversized requests.
export async function visionImage(photo: Buffer) {
  return (await sharp(photo).rotate().resize({ width: 1568, height: 1568, fit: "inside", withoutEnlargement: true }).jpeg({ quality: 85 }).toBuffer()).toString("base64");
}

let client: Anthropic | null = null;
const anthropic = () => client ??= new Anthropic();

export type VisionAnswer<T> = { data: T | null; note: string; model: string };

export async function askVision<T extends z.ZodObject>(schema: T, name: string, system: string, text: string, image: string): Promise<VisionAnswer<z.infer<T>>> {
  const paused = await visionPause();
  if (paused) throw new VisionApiError(429, paused.reason, paused.until);
  if (!useOpenRouter()) {
    const response = await anthropic().beta.messages.parse({
      model: CLAUDE_MODEL,
      max_tokens: 16000,
      betas: ["server-side-fallback-2026-07-01"],
      fallbacks: "default",
      output_config: { effort: "high", format: betaZodOutputFormat(schema) },
      system,
      messages: [{ role: "user", content: [
        { type: "image", source: { type: "base64", media_type: "image/jpeg", data: image } },
        { type: "text", text },
      ] }],
    });
    if (response.stop_reason === "refusal") return { data: null, note: `Declined (${response.stop_details?.category ?? "unspecified"})`, model: CLAUDE_MODEL };
    const parsed = (response.parsed_output ?? null) as z.infer<T> | null;
    return { data: parsed, note: parsed ? "" : `No structured answer (stop: ${response.stop_reason})`, model: CLAUDE_MODEL };
  }
  const { $schema: _, ...jsonSchema } = z.toJSONSchema(schema) as Record<string, unknown>;
  const response = await fetch(OPENROUTER_URL, {
    method: "POST",
    signal: AbortSignal.timeout(45_000),
    headers: { Authorization: `Bearer ${process.env.OPENROUTER_API_KEY}`, "Content-Type": "application/json", "X-Title": "GeoFlora" },
    body: JSON.stringify({
      models: OPENROUTER_MODELS,
      max_tokens: 4000,
      // Only route to providers that honour the JSON schema below.
      provider: { require_parameters: true },
      response_format: { type: "json_schema", json_schema: { name, strict: true, schema: jsonSchema } },
      messages: [
        { role: "system", content: system },
        { role: "user", content: [{ type: "text", text }, { type: "image_url", image_url: { url: `data:image/jpeg;base64,${image}` } }] },
      ],
    }),
  });
  const body = await response.json().catch(() => null) as { model?: string; error?: { message?: string; metadata?: { limit_source?: string; headers?: Record<string, string> } }; choices?: { message?: { content?: string | null } }[] } | null;
  if (response.status === 429) {
    const reset = Number(response.headers.get("X-RateLimit-Reset") ?? body?.error?.metadata?.headers?.["X-RateLimit-Reset"]);
    const daily = body?.error?.metadata?.limit_source === "openrouter_free_tier_daily" || /per-day/i.test(body?.error?.message ?? "");
    const until = Number.isFinite(reset) && reset > Date.now() ? new Date(reset) : new Date(Date.now() + 60_000);
    const reason = daily ? "The free daily allowance of AI requests is used up" : "The AI provider is busy";
    await pauseVision(until, reason);
    throw new VisionApiError(429, reason, until);
  }
  if (!response.ok || body?.error) throw new VisionApiError(response.ok ? 502 : response.status, body?.error?.message ?? `OpenRouter returned ${response.status}`);
  const model = body?.model ?? OPENROUTER_MODELS[0];
  // Some models wrap JSON in a code fence even in JSON mode; the schema is checked again here either way.
  const content = (body?.choices?.[0]?.message?.content ?? "").trim().replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "");
  let parsed: unknown = null;
  try { parsed = JSON.parse(content); } catch { /* Reported below as no answer. */ }
  const result = schema.safeParse(parsed);
  return result.success ? { data: result.data as z.infer<T>, note: "", model } : { data: null, note: `No valid structured answer from ${model}`, model };
}
