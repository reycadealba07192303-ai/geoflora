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
