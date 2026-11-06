import { currentAccount } from "../../../../src/lib/auth";
import { VisionApiError, visionAvailable } from "../../../../src/lib/ai-vision";
import { normalizePhoto } from "../../../../src/lib/identifications";
import { suggestPlant } from "../../../../src/lib/plant-suggestion";
import { sameOriginRequest } from "../../../../src/lib/sightings";
import { rateLimit } from "../../../../src/lib/rate-limit";

export const runtime = "nodejs";
// Long enough for the AI review that runs after the response (Vercel Hobby allows up to 60 s).
export const maxDuration = 60;
const MAX_UPLOAD_BYTES = 20 * 1024 * 1024;

// AI suggestion of what plant a photo shows, for results the image classifier could not identify. Unverified.
export async function POST(request: Request) {
  if (!sameOriginRequest(request)) return Response.json({ detail: "This request is not allowed." }, { status: 403 });
  try {
    const account = await currentAccount(request);
    if (!account) return Response.json({ detail: "Sign in to identify a plant." }, { status: 401 });
    const blocked = await rateLimit(request, "suggest", account);
    if (blocked) return blocked;
  } catch { return Response.json({ detail: "The account database is unavailable." }, { status: 503 }); }
  if (!visionAvailable()) return Response.json({ detail: "AI suggestions are not set up on this workspace." }, { status: 409 });
  const form = await request.formData().catch(() => null);
  const image = form?.get("image");
  if (!(image instanceof File) || !["image/jpeg", "image/png", "image/webp"].includes(image.type) || image.size > MAX_UPLOAD_BYTES) return Response.json({ detail: "Send a JPEG, PNG or WebP photo up to 20 MB." }, { status: 400 });
  let photo: Buffer;
  try { photo = await normalizePhoto(Buffer.from(await image.arrayBuffer())); } catch { return Response.json({ detail: "Choose a valid plant image at least 64 by 64 pixels." }, { status: 422 }); }
  try {
    const result = await suggestPlant(photo, String(form?.get("description") ?? ""));
    return Response.json(result, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    if (error instanceof VisionApiError && error.status === 429) {
      const when = error.resumesAt ? error.resumesAt.toLocaleString("en-PH", { timeZone: "Asia/Manila", dateStyle: "medium", timeStyle: "short" }) : null;
      return Response.json({ detail: `${error.message}${when ? `; AI suggestions are available again at ${when}` : ". Try again in a minute"}. A reviewer will still look at your report.` }, { status: 503 });
    }
    return Response.json({ detail: "The AI suggestion is unavailable right now." }, { status: 503 });
  }
}
