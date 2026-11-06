"use client";
import { useCallback, useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { CircleCheck, CircleX, ClipboardList, Download, Gauge, Pause, Play, Target, Trash2, Users } from "lucide-react";
import { CONSENT_VERSION, GROUPS, SUS_ITEMS, susScore, TARGETS, TASKS, type Group } from "./protocol";

interface SurveySummary { responses: number; byGroup: Record<string, number>; meanSus: number | null; meanSusByGroup: Record<string, number | null>; items: { text: string; mean: number | null }[]; comments: string[] }

interface Summary { participants: number; byGroup: Record<string, number>; perTask: { taskId: string; title: string; core: boolean; attempts: number; unassistedCompletion: number | null; medianSeconds: number | null; errors: number }[]; coreCompletion: number | null; meanSus: number | null; targets: { participantsMet: boolean; coreCompletionMet: boolean; susMet: boolean } }
interface Session { participantCode: string; group: Group; susScore: number; createdAt: string }
type TaskEntry = { outcome: string; seconds: number; errors: number; notes: string; startedAt: number | null };
const percent = (value: number | null) => value === null ? "—" : `${Math.round(value * 100)}%`;
const clock = (seconds: number) => `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
const blankTasks = () => Object.fromEntries(TASKS.map(task => [task.id, { outcome: "", seconds: 0, errors: 0, notes: "", startedAt: null }])) as Record<string, TaskEntry>;
const outcomeTone: Record<string, string> = { completed: "tone-green", assisted: "tone-amber", failed: "tone-rose", skipped: "tone-slate" };

export default function StudyRecorder() {
  const [data, setData] = useState<{ sessions: Session[]; summary: Summary } | null>(null), [error, setError] = useState(""), [message, setMessage] = useState("");
  const [code, setCode] = useState(""), [group, setGroup] = useState<Group>("public"), [device, setDevice] = useState(""), [consent, setConsent] = useState(false);
  const [tasks, setTasks] = useState(blankTasks), [sus, setSus] = useState<number[]>(Array(10).fill(0)), [feedback, setFeedback] = useState(""), [busy, setBusy] = useState(false);
  const [, tick] = useState(0); const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const load = useCallback(async () => { try { const response = await fetch("/api/study", { cache: "no-store" }); const body = await response.json(); if (!response.ok) throw Error(body.detail); setData(body); setError(""); if (!code) setCode(`P${String(body.sessions.length + 1).padStart(2, "0")}`); } catch (e) { setError(e instanceof Error ? e.message : "Study records are unavailable."); } }, [code]);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => { timer.current = setInterval(() => tick(value => value + 1), 1000); return () => { if (timer.current) clearInterval(timer.current); }; }, []);
  const applicable = TASKS.filter(task => task.groups.includes(group));
  const update = (id: string, patch: Partial<TaskEntry>) => setTasks(current => ({ ...current, [id]: { ...current[id], ...patch } }));
  const elapsed = (entry: TaskEntry) => entry.seconds + (entry.startedAt ? Math.round((Date.now() - entry.startedAt) / 1000) : 0);
  const codeValid = /^P\d{2,3}$/i.test(code), tasksDone = applicable.filter(task => tasks[task.id].outcome).length, susDone = sus.filter(value => value > 0).length;
  const ready = consent && codeValid && tasksDone === applicable.length && susDone === sus.length;
  const missing = [!codeValid && "a participant code like P01", !consent && "consent", tasksDone < applicable.length && `${applicable.length - tasksDone} task outcome${applicable.length - tasksDone > 1 ? "s" : ""}`, susDone < sus.length && `${sus.length - susDone} SUS answer${sus.length - susDone > 1 ? "s" : ""}`].filter(Boolean);

  async function save(event: FormEvent) {
    event.preventDefault(); setBusy(true); setMessage(""); setError("");
    try {
      const body = { participantCode: code, group, device, consent, consentVersion: CONSENT_VERSION, sus, feedback, tasks: applicable.map(task => ({ taskId: task.id, outcome: tasks[task.id].outcome, seconds: elapsed(tasks[task.id]), errors: tasks[task.id].errors, notes: tasks[task.id].notes })) };
      const response = await fetch("/api/study", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      const result = await response.json(); if (!response.ok) throw Error(result.detail);
      setMessage(`Saved ${result.participantCode} (SUS ${result.susScore}).`); setCode(""); setConsent(false); setTasks(blankTasks()); setSus(Array(10).fill(0)); setFeedback(""); setDevice(""); await load();
    } catch (e) { setError(e instanceof Error ? e.message : "The session could not be saved."); } finally { setBusy(false); }
  }
  async function withdraw(participant: string) {
    if (!window.confirm(`Delete all study data for ${participant}? Use this when a participant withdraws.`)) return;
    const response = await fetch(`/api/study?participant=${encodeURIComponent(participant)}`, { method: "DELETE" }); const body = await response.json();
    if (!response.ok) setError(body.detail); else { setMessage(`Deleted ${participant}.`); await load(); }
  }
  const s = data?.summary;
  return <section className="admin-page">
    <header className="admin-header">
      <div><span className="content-eyebrow">ADMINISTRATION · PART 11</span><h1>Usability study</h1>
        <p>Record moderated sessions with environmental officers, researchers and public users. Follow the script in docs/part-11-usability-kit.md. Identify participants only by code; record consent before starting. Use an isolated study workspace, not live reports.</p></div>
      <div className="admin-header-actions"><a className="admin-btn is-small" href="/api/study?format=csv"><Download size={14} />Download sessions (CSV)</a></div>
    </header>
    {error && <p role="alert" className="content-notice is-error !mt-0">{error}</p>}{message && <p role="status" className="content-notice !mt-0">{message}</p>}
    <UserSurveyResults />

    {s && <>
      <div className="grid gap-3 md:grid-cols-3" aria-label="Results against targets">
        <TargetCard icon={<Users size={18} />} label="Participants" value={`${s.participants} / ${TARGETS.participants}`} met={s.targets.participantsMet ? true : null} pendingText="Not yet" note={Object.entries(s.byGroup).map(([key, n]) => `${GROUPS[key as Group]} ${n}`).join(" · ") || "No sessions recorded yet"} />
        <TargetCard icon={<Target size={18} />} label="Core tasks done without help" value={percent(s.coreCompletion)} met={s.coreCompletion === null ? null : s.targets.coreCompletionMet} note={`Target ≥ ${TARGETS.coreCompletion * 100}%`} />
        <TargetCard icon={<Gauge size={18} />} label="Mean SUS" value={s.meanSus === null ? "—" : s.meanSus.toFixed(1)} met={s.meanSus === null ? null : s.targets.susMet} note={`Target ≥ ${TARGETS.sus}`} />
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <div className="surface-card admin-panel">
          <h2 className="admin-panel-title"><span className="admin-icon is-small tone-blue"><ClipboardList size={16} /></span>Per-task results</h2>
          <div className="admin-table-wrap mt-3"><table className="admin-table"><caption className="sr-only">Per-task results</caption>
            <thead><tr><th scope="col">Task</th><th scope="col">Attempts</th><th scope="col">Unassisted</th><th scope="col">Median time</th><th scope="col">Errors</th></tr></thead>
            <tbody>{s.perTask.map(task => <tr key={task.taskId}><td><span className="font-semibold">{task.taskId}</span> {task.title}{task.core && <span className="admin-badge tone-green ml-2">core</span>}</td><td>{task.attempts}</td><td>{percent(task.unassistedCompletion)}</td><td>{task.medianSeconds === null ? "—" : `${task.medianSeconds} s`}</td><td>{task.errors}</td></tr>)}</tbody></table></div>
        </div>
        <div className="surface-card admin-panel">
          <h2 className="admin-panel-title"><span className="admin-icon is-small tone-green"><Users size={16} /></span>Recorded sessions</h2>
          {data.sessions.length === 0 ? <p className="mt-4 text-[12px] text-[var(--muted)]">No sessions recorded yet.</p> : <ul className="mt-3 divide-y divide-[var(--line)]">{data.sessions.map(row => <li key={row.participantCode} className="flex items-center gap-3 py-2.5 text-[12px]">
            <span className="font-semibold">{row.participantCode}</span><span className="min-w-0 flex-1 truncate text-[var(--muted)]">{GROUPS[row.group]} · SUS {row.susScore}</span>
            <button className="admin-btn is-small is-danger" onClick={() => void withdraw(row.participantCode)}><Trash2 size={13} />Withdraw data</button>
          </li>)}</ul>}
        </div>
      </div>
    </>}

    <form onSubmit={save} className="space-y-5" aria-label="Record a session">
      <div className="surface-card admin-panel space-y-4">
        <h2 className="admin-panel-title"><span className="admin-step">1</span>Participant and consent</h2>
        <div className="grid gap-4 sm:grid-cols-3">
          <label className="admin-field">Participant code<input className="admin-input" value={code} onChange={e => setCode(e.target.value.toUpperCase())} placeholder="P01" maxLength={4} /></label>
          <label className="admin-field">Group<select className="admin-input" value={group} onChange={e => setGroup(e.target.value as Group)}>{Object.entries(GROUPS).map(([key, name]) => <option key={key} value={key}>{name}</option>)}</select></label>
          <label className="admin-field">Device / browser<input className="admin-input" value={device} onChange={e => setDevice(e.target.value)} placeholder="e.g. Android phone, Chrome" maxLength={120} /></label>
        </div>
        <label className="admin-check is-warning"><input type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)} /><span>I read the consent script ({CONSENT_VERSION}) to the participant and they agreed to take part and to have their task results, times, answers and comments recorded under this code.</span></label>
      </div>

      <fieldset disabled={!consent} aria-labelledby="study-tasks" className="surface-card admin-panel space-y-3 disabled:opacity-60">
        <h2 id="study-tasks" className="admin-panel-title"><span className="admin-step">2</span><span>Tasks for this group<small>{tasksDone} of {applicable.length} recorded · start the timer when you read the prompt</small></span></h2>
        {applicable.map(task => { const entry = tasks[task.id]; return <div key={task.id} className="study-task">
          <div className="flex flex-wrap items-center gap-2"><span className="text-[13px] font-semibold">{task.id} {task.title}</span>{task.core && <span className="admin-badge tone-green">core</span>}{entry.outcome && <span className={`admin-badge ${outcomeTone[entry.outcome]}`}>{entry.outcome}</span>}</div>
          <p className="mt-1.5 text-[13px] leading-[1.6]">“{task.prompt}”</p><p className="mt-1 text-[11px] text-[var(--muted)]">Success: {task.success}</p>
          <div className="mt-3 grid items-end gap-3 sm:grid-cols-[auto_1fr_6rem] lg:grid-cols-[auto_14rem_6rem_1fr]">
            <div className="flex items-center gap-2"><button type="button" className={`admin-btn is-small ${entry.startedAt ? "is-primary" : ""}`} onClick={() => entry.startedAt ? update(task.id, { seconds: elapsed(entry), startedAt: null }) : update(task.id, { startedAt: Date.now() })}>{entry.startedAt ? <Pause size={13} /> : <Play size={13} />}{entry.startedAt ? "Stop timer" : "Start timer"}</button><span className="study-timer" aria-live="polite" aria-label={`${elapsed(entry)} seconds`}>{clock(elapsed(entry))}</span></div>
            <label className="admin-field">Outcome<select className="admin-input" value={entry.outcome} onChange={e => update(task.id, { outcome: e.target.value })}><option value="">Choose</option><option value="completed">Completed without help</option><option value="assisted">Completed with help</option><option value="failed">Not completed</option><option value="skipped">Skipped</option></select></label>
            <label className="admin-field">Errors<input type="number" min={0} max={100} className="admin-input" value={entry.errors} onChange={e => update(task.id, { errors: Math.max(0, Number(e.target.value) || 0) })} /></label>
            <label className="admin-field sm:col-span-3 lg:col-span-1">Notes<input className="admin-input" value={entry.notes} maxLength={1000} onChange={e => update(task.id, { notes: e.target.value })} /></label>
          </div>
        </div>; })}
      </fieldset>

      <fieldset disabled={!consent} aria-labelledby="study-sus" className="surface-card admin-panel disabled:opacity-60">
        <h2 id="study-sus" className="admin-panel-title"><span className="admin-step">3</span><span>System Usability Scale<small>1 = strongly disagree, 5 = strongly agree · {susDone} of {sus.length} answered</small></span></h2>
        <div className="mt-3">{SUS_ITEMS.map((item, index) => <div key={item} className="sus-row" role="radiogroup" aria-label={`SUS ${index + 1}: ${item}`}><span className="min-w-0 flex-1">{index + 1}. {item}</span><span className="sus-scale">{[1, 2, 3, 4, 5].map(value => <label key={value}><input className="sr-only" type="radio" name={`sus-${index}`} checked={sus[index] === value} onChange={() => setSus(current => current.map((old, i) => i === index ? value : old))} />{value}</label>)}</span></div>)}</div>
        {susDone === sus.length && <p className="mt-3 text-[13px] font-semibold">SUS score: {susScore(sus)}</p>}
      </fieldset>

      <div className="surface-card admin-panel">
        <label className="admin-field"><span className="admin-panel-title"><span className="admin-step">4</span>Participant comments</span><textarea className="admin-input" rows={3} maxLength={4000} value={feedback} onChange={e => setFeedback(e.target.value)} disabled={!consent} /></label>
      </div>

      <div className="admin-savebar">
        <p className="text-[12px] text-[var(--muted)]">{ready ? `Ready to save ${code.toUpperCase()}.` : `Still needed: ${missing.join(", ")}.`}</p>
        <button className="admin-btn is-primary" disabled={!ready || busy}>{busy ? "Saving..." : "Save session"}</button>
      </div>
    </form>
  </section>;
}

function TargetCard({ icon, label, value, met, note, pendingText = "No data" }: { icon: ReactNode; label: string; value: string; met: boolean | null; note: string; pendingText?: string }) {
  return <div className="surface-card admin-stat !items-start">
    <span className="admin-icon tone-green">{icon}</span>
    <div className="min-w-0 flex-1"><div className="flex flex-wrap items-center justify-between gap-2"><strong>{value}</strong>
      <span className={`admin-badge ${met === null ? "tone-slate" : met ? "tone-green" : "tone-rose"}`}>{met === null ? pendingText : met ? <><CircleCheck size={11} />Met</> : <><CircleX size={11} />Not met</>}</span></div>
      <p>{label}</p><p>{note}</p></div>
  </div>;
}

// Answers users gave themselves on the Feedback survey page (one per account, reported without names).
export function UserSurveyResults() {
  const [data, setData] = useState<SurveySummary | null>(null);
  useEffect(() => { fetch("/api/study/survey?all=1", { cache: "no-store" }).then(r => r.ok ? r.json() : null).then(setData).catch(() => {}); }, []);
  if (!data) return null;
  const fmt = (value: number | null, digits = 1) => value === null ? "—" : value.toFixed(digits);
  return <section className="surface-card admin-panel space-y-4" aria-label="User feedback survey results">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h2 className="admin-panel-title"><span className="admin-icon is-small tone-violet"><Users size={16} /></span><span>Survey results (all users)<small>Shown only to administrators · {data.responses} response{data.responses === 1 ? "" : "s"}</small></span></h2>
      <a className="admin-btn is-small" href="/api/study/survey?all=1&format=csv"><Download size={14} />Download answers (CSV)</a>
    </div>
    <div className="grid gap-3 sm:grid-cols-4">
      <div className="rounded-2xl bg-[#f3f6f1] p-4"><p className="text-[11px] text-[var(--muted)]">Mean SUS (target ≥ {TARGETS.sus})</p><p className="text-[26px] font-semibold">{fmt(data.meanSus)}</p></div>
      {Object.entries(GROUPS).map(([key, name]) => <div key={key} className="rounded-2xl bg-[#f3f6f1] p-4"><p className="text-[11px] text-[var(--muted)]">{name} · {data.byGroup[key] ?? 0}</p><p className="text-[26px] font-semibold">{fmt(data.meanSusByGroup[key] ?? null)}</p></div>)}
    </div>
    <table className="admin-table text-[12px]"><thead><tr><th>GeoFlora statement</th><th className="!text-right">Mean (1-5)</th></tr></thead><tbody>{data.items.map(item => <tr key={item.text}><td>{item.text}</td><td className="text-right font-semibold">{fmt(item.mean, 2)}</td></tr>)}</tbody></table>
    {data.comments.length > 0 && <details><summary className="cursor-pointer text-[12px] font-semibold">Comments ({data.comments.length})</summary><ul className="mt-2 list-disc space-y-1 pl-5 text-[12px]">{data.comments.map((comment, i) => <li key={i} className="whitespace-pre-wrap">{comment}</li>)}</ul></details>}
  </section>;
}
