import mongoose from "mongoose";
import { currentAccount, isAdmin } from "../../../src/lib/auth";
import { connectDatabase, sameOriginRequest } from "../../../src/lib/sightings";
import { CONSENT_VERSION, GROUPS, susScore, TARGETS, TASKS, type Group } from "../../../src/features/study/protocol";

export const runtime = "nodejs";

// Usability sessions recorded by a facilitator. Participants are identified only by a code; no names or contacts.
const taskSchema = new mongoose.Schema({ taskId: String, outcome: { type: String, enum: ["completed", "assisted", "failed", "skipped"] }, seconds: Number, errors: Number, notes: String }, { _id: false, suppressReservedKeysWarning: true });
const sessionSchema = new mongoose.Schema({
  participantCode: { type: String, required: true, unique: true }, group: { type: String, required: true }, device: String,
  consent: { version: String, givenAt: Date, recordedBy: String }, tasks: [taskSchema], sus: [Number], susScore: Number, feedback: String, facilitator: String,
}, { timestamps: true, versionKey: false });

async function sessions() {
  await connectDatabase();
  type Session = mongoose.InferSchemaType<typeof sessionSchema>;
  return (mongoose.models.StudySession as mongoose.Model<Session> | undefined) ?? mongoose.model<Session>("StudySession", sessionSchema);
}

async function administrator(request: Request) {
  if (!sameOriginRequest(request)) return { error: Response.json({ detail: "This request is not allowed." }, { status: 403 }) };
  const account = await currentAccount(request);
  if (!account) return { error: Response.json({ detail: "Sign in first." }, { status: 401 }) };
  if (!isAdmin(account)) return { error: Response.json({ detail: "Administrator access required." }, { status: 403 }) };
  return { account };
}

type Row = { participantCode: string; group: string; device?: string | null; tasks: { taskId?: string | null; outcome?: string | null; seconds?: number | null; errors?: number | null }[]; sus: number[]; susScore?: number | null; feedback?: string | null; createdAt?: Date };

function summary(rows: Row[]) {
  const core = TASKS.filter(task => task.core).map(task => task.id);
  const perTask = TASKS.map(task => {
    const attempts = rows.flatMap(row => row.tasks.filter(item => item.taskId === task.id && item.outcome !== "skipped"));
    const completed = attempts.filter(item => item.outcome === "completed");
    const times = completed.map(item => item.seconds ?? 0).sort((a, b) => a - b);
    return { taskId: task.id, title: task.title, core: task.core, attempts: attempts.length, unassistedCompletion: attempts.length ? completed.length / attempts.length : null,
      medianSeconds: times.length ? times[Math.floor(times.length / 2)] : null, errors: attempts.reduce((sum, item) => sum + (item.errors ?? 0), 0) };
  });
  const coreAttempts = rows.flatMap(row => row.tasks.filter(item => core.includes(item.taskId ?? "") && item.outcome !== "skipped"));
  const coreCompletion = coreAttempts.length ? coreAttempts.filter(item => item.outcome === "completed").length / coreAttempts.length : null;
  const scores = rows.map(row => row.susScore).filter((value): value is number => typeof value === "number");
  const meanSus = scores.length ? scores.reduce((a, b) => a + b, 0) / scores.length : null;
  return { participants: rows.length, byGroup: Object.fromEntries(Object.keys(GROUPS).map(group => [group, rows.filter(row => row.group === group).length])), perTask, coreCompletion, meanSus,
    targets: { ...TARGETS, participantsMet: rows.length >= TARGETS.participants, coreCompletionMet: coreCompletion !== null && coreCompletion >= TARGETS.coreCompletion, susMet: meanSus !== null && meanSus >= TARGETS.sus } };
}

export async function GET(request: Request) {
  try {
    const { error } = await administrator(request);
    if (error) return error;
    const rows = await (await sessions()).find().sort({ createdAt: 1 }).lean() as unknown as Row[];
    if (new URL(request.url).searchParams.get("format") === "csv") {
      const quote = (value: unknown) => `"${String(value ?? "").replaceAll('"', '""')}"`;
      const header = ["participant", "group", "device", "task", "outcome", "seconds", "errors", "sus_score", "recorded_at"];
      const lines = rows.flatMap(row => row.tasks.map(task => [row.participantCode, row.group, row.device, task.taskId, task.outcome, task.seconds, task.errors, row.susScore, row.createdAt?.toISOString()].map(quote).join(",")));
      return new Response([header.join(","), ...lines].join("\r\n"), { headers: { "Content-Type": "text/csv; charset=utf-8", "Content-Disposition": 'attachment; filename="geoflora-usability-sessions.csv"', "Cache-Control": "no-store" } });
    }
    return Response.json({ consentVersion: CONSENT_VERSION, sessions: rows, summary: summary(rows) }, { headers: { "Cache-Control": "no-store" } });
  } catch { return Response.json({ detail: "Study records are unavailable." }, { status: 503 }); }
}

export async function POST(request: Request) {
  try {
    const { account, error } = await administrator(request);
    if (error) return error;
    const body = await request.json().catch(() => null);
    if (!body || body.consent !== true || body.consentVersion !== CONSENT_VERSION) return Response.json({ detail: "Record the participant's consent to the current consent script before saving a session." }, { status: 400 });
    const code = typeof body.participantCode === "string" ? body.participantCode.trim().toUpperCase() : "";
    if (!/^P\d{2,3}$/.test(code)) return Response.json({ detail: "Use a participant code like P01; never a name." }, { status: 400 });
    if (!(body.group in GROUPS)) return Response.json({ detail: "Choose the participant group." }, { status: 400 });
    const allowed = new Set(TASKS.filter(task => task.groups.includes(body.group as Group)).map(task => task.id));
    const tasks = Array.isArray(body.tasks) ? body.tasks : [];
    if (!tasks.length || tasks.some((task: { taskId?: string; outcome?: string; seconds?: number; errors?: number }) => !allowed.has(String(task.taskId)) || !["completed", "assisted", "failed", "skipped"].includes(String(task.outcome))
      || !Number.isFinite(task.seconds) || Number(task.seconds) < 0 || Number(task.seconds) > 7200 || !Number.isInteger(task.errors) || Number(task.errors) < 0 || Number(task.errors) > 100)) return Response.json({ detail: "Each task needs an outcome, a time in seconds and an error count." }, { status: 400 });
    const sus = Array.isArray(body.sus) ? body.sus : [];
    if (sus.length !== 10 || sus.some((value: unknown) => !Number.isInteger(value) || Number(value) < 1 || Number(value) > 5)) return Response.json({ detail: "Answer all ten SUS questions from 1 to 5." }, { status: 400 });
    const text = (value: unknown, limit: number) => typeof value === "string" ? value.trim().slice(0, limit) : "";
    const saved = await (await sessions()).create({ participantCode: code, group: body.group, device: text(body.device, 120), consent: { version: CONSENT_VERSION, givenAt: new Date(), recordedBy: account.username },
      tasks: tasks.map((task: { taskId: string; outcome: string; seconds: number; errors: number; notes?: string }) => ({ taskId: task.taskId, outcome: task.outcome, seconds: Math.round(task.seconds), errors: task.errors, notes: text(task.notes, 1000) })),
      sus, susScore: susScore(sus), feedback: text(body.feedback, 4000), facilitator: account.username });
    return Response.json({ participantCode: saved.participantCode, susScore: saved.susScore }, { status: 201 });
  } catch (error) {
    if ((error as { code?: number }).code === 11000) return Response.json({ detail: "That participant code already has a session." }, { status: 409 });
    return Response.json({ detail: "The session could not be saved." }, { status: 503 });
  }
}

// Participant withdrawal: delete a session by its code.
export async function DELETE(request: Request) {
  try {
    const { error } = await administrator(request);
    if (error) return error;
    const code = (new URL(request.url).searchParams.get("participant") ?? "").trim().toUpperCase();
    const result = await (await sessions()).deleteOne({ participantCode: code });
    return result.deletedCount ? Response.json({ withdrawn: code }) : Response.json({ detail: "No session for that participant code." }, { status: 404 });
  } catch { return Response.json({ detail: "The session could not be deleted." }, { status: 503 }); }
}
