import { reviewPendingReports } from "../../../../src/lib/ai-review";

export const runtime = "nodejs";
export const maxDuration = 60;

// Vercel Cron calls this (vercel.json) with "Authorization: Bearer $CRON_SECRET". Reviews waiting sightings that were
// not reviewed when submitted, for example while the free AI allowance was used up.
export async function GET(request: Request) {
  if (!process.env.CRON_SECRET || request.headers.get("authorization") !== `Bearer ${process.env.CRON_SECRET}`) return Response.json({ detail: "Not allowed." }, { status: 401 });
  return Response.json(await reviewPendingReports(5), { headers: { "Cache-Control": "no-store" } });
}
