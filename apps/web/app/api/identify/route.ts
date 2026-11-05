import { NextResponse } from "next/server";
import { mlFetch } from "../../../src/lib/ml";
import { currentAccount, type Account } from "../../../src/lib/auth";
import { sameOriginRequest } from "../../../src/lib/sightings";
import { normalizePhoto, photoHash, rememberIdentification } from "../../../src/lib/identifications";
import { speciesInformation } from "../../../src/features/identification/species-information";
import { extractReferenceEmbedding, findExactVerifiedReference, hasVerifiedReferences, searchVerifiedReferences } from "../../../src/lib/verified-references";

const MAX_UPLOAD_BYTES = 20 * 1024 * 1024;
const INFERENCE_TIMEOUT_MS = Number(process.env.GEOFLORA_INFERENCE_TIMEOUT_MS ?? 50_000);

export const maxDuration = 60;

export async function GET() {
  try {
    const response = await mlFetch("/health", {
      signal: AbortSignal.timeout(3000),
    });
    const body: unknown = await response.json();
    return NextResponse.json(body, { status: response.status });
  } catch {
    return NextResponse.json(
      {
        service: "geoflora-ml-inference",
        ready: false,
        reason: "The local ML inference service is not reachable.",
      },
      { status: 503 },
    );
  }
}

export async function POST(request: Request) {
  let account: Account | null;
  if (!sameOriginRequest(request)) return NextResponse.json({ detail: "This request is not allowed." }, { status: 403 });
  try {
    account = await currentAccount(request);
    if (!account) return NextResponse.json({ detail: "Sign in to identify a plant." }, { status: 401 });
  } catch { return NextResponse.json({ detail: "The account database is unavailable." }, { status: 503 }); }
  let formData: FormData;
  try {
    formData = await request.formData();
  } catch {
    return NextResponse.json(
      { detail: "Request must contain a multipart plant image." },
      { status: 400 },
    );
  }

  const image = formData.get("image");
  if (!(image instanceof File)) {
    return NextResponse.json(
      { detail: "Choose a plant image before identifying it." },
      { status: 400 },
    );
  }
  if (!["image/jpeg", "image/png", "image/webp"].includes(image.type)) {
    return NextResponse.json(
      { detail: "Use a JPEG, PNG, or WebP plant photo." },
      { status: 415 },
    );
  }
  if (image.size > MAX_UPLOAD_BYTES) {
    return NextResponse.json(
      { detail: "Image exceeds the 20 MB upload limit." },
      { status: 413 },
    );
  }

  const input = Buffer.from(await image.arrayBuffer());
  let normalized: Buffer;
  try { normalized = await normalizePhoto(input); } catch { return NextResponse.json({ detail: "Choose a valid plant image at least 64 by 64 pixels." }, { status: 422 }); }
  const hashes = [photoHash(input), photoHash(normalized)];
  const upstreamForm = new FormData();
  upstreamForm.set("image", image, image.name || "plant-image");
  let response: Response;
  try {
    response = await mlFetch("/predict", {
      method: "POST",
      body: upstreamForm,
      cache: "no-store",
      signal: AbortSignal.timeout(INFERENCE_TIMEOUT_MS),
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "TimeoutError") {
      return NextResponse.json({ detail: "Identification took too long. No prediction was made; please try again." }, { status: 504 });
    }
    return NextResponse.json(
      { detail: "The local ML inference service is not reachable. No prediction was made." },
      { status: 503 },
    );
  }
  let body: { detail?: unknown; status?: string; confidence?: number; confidence_threshold?: number; species?: { id?: string; scientific_name?: string; common_name?: string; role?: string } | null; candidates?: unknown[]; model_version?: string };
  try { body = await response.json(); } catch {
    return NextResponse.json({ detail: "The identification service returned an unreadable response. No prediction was made." }, { status: 502 });
  }
  if (!response.ok) {
    const detail = typeof body.detail === "string" ? body.detail : "Identification failed. No prediction was made.";
    return NextResponse.json({ detail }, { status: response.status });
  }
  let result: Record<string, unknown> = { ...body, method: "model", information: body.species?.id ? speciesInformation[body.species.id] ?? null : null };
  try {
    if (await hasVerifiedReferences()) {
      const exact = await findExactVerifiedReference(hashes);
      if (exact) {
        result = { ...result, status: "identified", method: "verified_reference", cnnPrediction: body, species: exact.species, confidence: null, similaritySuggestions: [], information: { description: "", appearance: "", impact: "", source: { label: "Administrator-verified image reference", url: exact.botanicalCitation } }, referenceSource: { type: "exact_verified_reference_match", botanicalCitation: exact.botanicalCitation, ecologicalStatus: exact.ecologicalStatus, ecologicalCitation: exact.ecologicalCitation, sourceObservationId: exact.sourceObservationId } };
      } else {
        const encoded = await extractReferenceEmbedding(normalized);
        const search = await searchVerifiedReferences(hashes, encoded.embedding, encoded.embeddingVersion);
        // Similarity is supplementary evidence only. Keep the CNN species, status and score intact, including
        // above-threshold predictions that may be closed-set false positives for unsupported plants.
        result = { ...result, method: "model", similaritySuggestions: search.suggestions, similarityNote: "Visual similarity is an uncalibrated review suggestion. It does not override the CNN or verify this photo." };
      }
    }
  } catch (error) {
    // The classifier remains available if reference indexing or feature extraction is unavailable.
    console.warn("Verified-reference search unavailable", error instanceof Error ? error.name : "unknown");
  }
  try {
    return NextResponse.json(await rememberIdentification(account.id, input, result), { headers: { "Cache-Control": "no-store" } });
  } catch {
    return NextResponse.json({ detail: "The prediction finished but could not be stored for your report. Please try again." }, { status: 503 });
  }
}
