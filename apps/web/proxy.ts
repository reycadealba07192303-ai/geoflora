import { NextResponse, type NextRequest } from "next/server";

// Requests-per-minute guard for every API route (Next.js 16 "Proxy", formerly Middleware; runs before the route).
// It keeps one client from flooding the server: each IP address may make GEOFLORA_RPM_LIMIT API requests per minute
// (default 120), of which GEOFLORA_RPM_WRITE_LIMIT may change data (POST/PATCH/PUT/DELETE, default 40).
// Counters are kept in memory per server instance (no database round trip), so this is a fast first line of defence;
// the per-action, per-account limits in src/lib/rate-limit.ts are stored in MongoDB and hold across instances.
const WINDOW_MS = 60_000;
const READ_LIMIT = Number(process.env.GEOFLORA_RPM_LIMIT) || 120;
const WRITE_LIMIT = Number(process.env.GEOFLORA_RPM_WRITE_LIMIT) || 40;
const MAX_TRACKED = 50_000;
const counters = new Map<string, { count: number; reset: number }>();

function clientIp(request: NextRequest) {
  return (request.headers.get("x-forwarded-for") ?? "").split(",")[0].trim() || request.headers.get("x-real-ip") || "unknown";
}

function take(key: string, limit: number, now: number) {
  if (counters.size > MAX_TRACKED) for (const [k, v] of counters) if (v.reset <= now) counters.delete(k);
  const entry = counters.get(key);
  if (!entry || entry.reset <= now) { counters.set(key, { count: 1, reset: now + WINDOW_MS }); return { ok: true, remaining: limit - 1, reset: now + WINDOW_MS }; }
  entry.count += 1;
  return { ok: entry.count <= limit, remaining: Math.max(0, limit - entry.count), reset: entry.reset };
}

export function proxy(request: NextRequest) {
  // Vercel Cron calls are authenticated with CRON_SECRET inside the route and must not be throttled.
  if (request.nextUrl.pathname.startsWith("/api/cron/")) return NextResponse.next();
  const now = Date.now(), ip = clientIp(request);
  const write = !["GET", "HEAD", "OPTIONS"].includes(request.method);
  const all = take(`all:${ip}`, READ_LIMIT, now);
  const writes = write ? take(`write:${ip}`, WRITE_LIMIT, now) : null;
  const blocked = !all.ok || (writes !== null && !writes.ok);
  const limit = writes ?? all, max = writes ? WRITE_LIMIT : READ_LIMIT;
  const headers = { "X-RateLimit-Limit": String(max), "X-RateLimit-Remaining": String(limit.remaining), "X-RateLimit-Reset": String(Math.ceil(limit.reset / 1000)) };
  if (blocked) {
    const retry = Math.max(1, Math.ceil(((writes && !writes.ok ? writes : all).reset - now) / 1000));
    return NextResponse.json({ detail: `Too many requests from your connection. Please wait ${retry} seconds and try again.` }, { status: 429, headers: { ...headers, "Retry-After": String(retry) } });
  }
  const response = NextResponse.next();
  for (const [name, value] of Object.entries(headers)) response.headers.set(name, value);
  return response;
}

export const config = { matcher: "/api/:path*" };
