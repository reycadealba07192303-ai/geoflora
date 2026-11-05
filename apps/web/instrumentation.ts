// Runs once when the Next.js server starts: begins the background AI review of waiting sightings (src/lib/ai-review.ts).
export async function register() {
  // Serverless functions on Vercel do not stay running; there, Vercel Cron (vercel.json) runs the review instead.
  if (process.env.NEXT_RUNTIME === "nodejs" && !process.env.VERCEL) {
    const { startAiReviewSweeper } = await import("./src/lib/ai-review");
    startAiReviewSweeper();
  }
}
