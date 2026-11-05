import { currentAccount, isAdmin } from "../../../../src/lib/auth";
import { aiReviewStatus, reviewPendingReports } from "../../../../src/lib/ai-review";
import { sameOriginRequest } from "../../../../src/lib/sightings";

export const runtime = "nodejs";
// Long enough for the AI review that runs after the response (Vercel Hobby allows up to 60 s).
export const maxDuration = 60;

// Administrator-triggered pass of the AI reviewer over waiting reports; returns what it decided.
export async function POST(request: Request) {
  if (!sameOriginRequest(request)) return Response.json({ detail: "This request is not allowed." }, { status: 403 });
  try {
    const account = await currentAccount(request);
    if (!account) return Response.json({ detail: "Sign in first." }, { status: 401 });
    if (!isAdmin(account)) return Response.json({ detail: "Administrator access required." }, { status: 403 });
    const status = await aiReviewStatus();
    if (!status.enabled) return Response.json({ detail: "The AI reviewer is off. Add OPENROUTER_API_KEY (or ANTHROPIC_API_KEY) to apps/web/.env.local and restart the web app." }, { status: 409 });
    const summary = await reviewPendingReports(25);
    return Response.json({ summary, status: await aiReviewStatus() }, { headers: { "Cache-Control": "no-store" } });
  } catch { return Response.json({ detail: "The AI review could not run." }, { status: 503 }); }
}
