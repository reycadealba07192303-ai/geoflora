import mongoose from "mongoose";
import { connectDatabase } from "./sightings";

// Attempt counters shared by every server instance (in-memory counters reset on each serverless invocation).
// Documents expire on their own once the window has passed.
async function limits() {
  await connectDatabase();
  const collection = mongoose.connection.db!.collection<{ _id: string; count: number; reset: Date }>("rate_limits");
  const flag = globalThis as typeof globalThis & { geofloraRateIndex?: Promise<string> };
  flag.geofloraRateIndex ??= collection.createIndex({ reset: 1 }, { expireAfterSeconds: 0 });
  await flag.geofloraRateIndex;
  return collection;
}

// Counts this attempt and reports whether the key has already used its `limit` attempts in the window.
export async function overLimit(key: string, limit: number, windowMs = 15 * 60_000) {
  const now = new Date();
  const row = await (await limits()).findOneAndUpdate({ _id: key }, [{ $set: {
    count: { $cond: [{ $gt: ["$reset", now] }, { $add: [{ $ifNull: ["$count", 0] }, 1] }, 1] },
    reset: { $cond: [{ $gt: ["$reset", now] }, "$reset", new Date(now.getTime() + windowMs)] },
  } }], { upsert: true, returnDocument: "after" });
  return (row?.count ?? 1) > limit;
}

export async function clearLimit(key: string) {
  await (await limits()).deleteOne({ _id: key });
}

// ---------- Per-account and per-IP limits for API routes (2026-11-07) ----------
// Each route has its own budget per account and per client IP address. Administrators and reviewers are exempt, so
// review work and evaluation runs are never blocked. Counters live in MongoDB, so they hold across serverless instances.
export function clientIp(request: Request) {
  return (request.headers.get("x-forwarded-for") ?? "").split(",")[0].trim() || request.headers.get("x-real-ip") || "unknown";
}

export const LIMITS = {
  identify: { perAccount: 40, perIp: 80, windowMs: 10 * 60_000 },
  suggest: { perAccount: 15, perIp: 30, windowMs: 10 * 60_000 }, // calls a paid/limited AI vision service
  report: { perAccount: 30, perIp: 60, windowMs: 60 * 60_000 },
  pdf: { perAccount: 30, perIp: 60, windowMs: 10 * 60_000 },
  survey: { perAccount: 10, perIp: 30, windowMs: 60 * 60_000 },
  auth: { perAccount: 0, perIp: 40, windowMs: 15 * 60_000 }, // sign-in, sign-up and reset requests from one address
} as const;

// Returns a 429 response when the caller is over its budget, otherwise null (and counts this request).
export async function rateLimit(request: Request, name: keyof typeof LIMITS, account?: { id: string; role?: string } | null) {
  if (account && (account.role === "admin" || account.role === "reviewer")) return null;
  const rule = LIMITS[name];
  const checks: [string, number][] = [[`${name}:ip:${clientIp(request)}`, rule.perIp]];
  if (account && rule.perAccount) checks.push([`${name}:acct:${account.id}`, rule.perAccount]);
  for (const [key, limit] of checks) {
    if (await overLimit(key, limit, rule.windowMs)) {
      const minutes = Math.ceil(rule.windowMs / 60_000);
      return Response.json({ detail: `Too many requests. Please wait a few minutes and try again (limit: ${limit} per ${minutes} minutes).` }, { status: 429, headers: { "Retry-After": String(rule.windowMs / 1000) } });
    }
  }
  return null;
}
