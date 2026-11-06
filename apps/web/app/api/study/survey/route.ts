import mongoose from "mongoose";
import { currentAccount, isAdmin } from "../../../../src/lib/auth";
import { connectDatabase, sameOriginRequest } from "../../../../src/lib/sightings";
import { GROUPS, SURVEY_ITEMS, SURVEY_VERSION, susScore } from "../../../../src/features/study/protocol";

export const runtime = "nodejs";

// One self-administered survey per account (users can update it). Reports to administrators never show who answered.
const schema = new mongoose.Schema({
  accountId: { type: String, required: true, unique: true }, group: { type: String, required: true }, consentVersion: String,
  sus: [Number], susScore: Number, items: [Number], comments: String,
}, { timestamps: true, versionKey: false, collection: "usersurveys" });
async function surveys() {
  await connectDatabase();
  type Survey = mongoose.InferSchemaType<typeof schema>;
  return (mongoose.models.UserSurvey as mongoose.Model<Survey> | undefined) ?? mongoose.model<Survey>("UserSurvey", schema);
}
const scale = (values: unknown, n: number) => Array.isArray(values) && values.length === n && values.every(value => Number.isInteger(value) && Number(value) >= 1 && Number(value) <= 5);
const mean = (values: number[]) => values.length ? values.reduce((a, b) => a + b, 0) / values.length : null;

export async function GET(request: Request) {
  if (!sameOriginRequest(request)) return Response.json({ detail: "This request is not allowed." }, { status: 403 });
  try {
    const account = await currentAccount(request);
    if (!account) return Response.json({ detail: "Sign in first." }, { status: 401 });
    const model = await surveys();
    const url = new URL(request.url);
    if (url.searchParams.get("all") !== "1") {
      const mine = await model.findOne({ accountId: account.id }).lean();
      return Response.json({ answered: !!mine, response: mine ? { group: mine.group, sus: mine.sus, items: mine.items, comments: mine.comments, updatedAt: mine.updatedAt } : null }, { headers: { "Cache-Control": "no-store" } });
    }
    if (!isAdmin(account)) return Response.json({ detail: "Administrator access required." }, { status: 403 });
    const rows = await model.find().sort({ createdAt: 1 }).lean();
    if (url.searchParams.get("format") === "csv") {
      const quote = (value: unknown) => `"${String(value ?? "").replaceAll('"', '""')}"`;
      const header = ["response", "group", ...Array.from({ length: 10 }, (_, i) => `sus_${i + 1}`), "sus_score", ...SURVEY_ITEMS.map((_, i) => `geoflora_${i + 1}`), "comments", "submitted_at"];
      const lines = rows.map((row, index) => [`R${String(index + 1).padStart(2, "0")}`, row.group, ...row.sus, row.susScore, ...row.items, row.comments, row.updatedAt?.toISOString()].map(quote).join(","));
      return new Response([header.join(","), ...lines].join("\r\n"), { headers: { "Content-Type": "text/csv; charset=utf-8", "Content-Disposition": 'attachment; filename="geoflora-user-survey.csv"', "Cache-Control": "no-store" } });
    }
    const scores = rows.map(row => row.susScore).filter((value): value is number => typeof value === "number");
    return Response.json({
      responses: rows.length,
      byGroup: Object.fromEntries(Object.keys(GROUPS).map(group => [group, rows.filter(row => row.group === group).length])),
      meanSus: mean(scores),
      meanSusByGroup: Object.fromEntries(Object.keys(GROUPS).map(group => [group, mean(rows.filter(row => row.group === group).map(row => row.susScore ?? 0))])),
      items: SURVEY_ITEMS.map((text, i) => ({ text, mean: mean(rows.map(row => row.items[i]).filter(Number.isFinite)) })),
      comments: rows.map(row => row.comments).filter((text): text is string => !!text && !!text.trim()),
    }, { headers: { "Cache-Control": "no-store" } });
  } catch { return Response.json({ detail: "Survey results are unavailable." }, { status: 503 }); }
}

export async function POST(request: Request) {
  if (!sameOriginRequest(request)) return Response.json({ detail: "This request is not allowed." }, { status: 403 });
  try {
    const account = await currentAccount(request);
    if (!account) return Response.json({ detail: "Sign in first." }, { status: 401 });
    const body = await request.json().catch(() => null);
    if (!body || body.consent !== true || body.consentVersion !== SURVEY_VERSION) return Response.json({ detail: "Please agree to the research use of your answers first." }, { status: 400 });
    if (!(body.group in GROUPS)) return Response.json({ detail: "Choose which group describes you." }, { status: 400 });
    if (!scale(body.sus, 10) || !scale(body.items, SURVEY_ITEMS.length)) return Response.json({ detail: "Answer every statement from 1 to 5." }, { status: 400 });
    const comments = typeof body.comments === "string" ? body.comments.trim().slice(0, 4000) : "";
    const saved = await (await surveys()).findOneAndUpdate({ accountId: account.id }, { $set: { group: body.group, consentVersion: SURVEY_VERSION, sus: body.sus, susScore: susScore(body.sus), items: body.items, comments } }, { upsert: true, new: true });
    return Response.json({ susScore: saved.susScore }, { status: 201 });
  } catch { return Response.json({ detail: "Your answers could not be saved. Please retry." }, { status: 503 }); }
}
