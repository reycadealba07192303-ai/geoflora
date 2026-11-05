"use client";
import { useCallback, useEffect, useState } from "react";
import { Activity, Bot, CalendarClock, CircleCheck, CircleX, Cpu, ExternalLink, History, Hourglass, Inbox, Leaf, Maximize2, MapPin, MessageSquareText, RefreshCw, ShieldCheck, Sparkles } from "lucide-react";

interface Prediction { status?: string; method?: string; confidence?: number | null; confidence_threshold?: number; model_version?: string; species?: { id: string; scientific_name: string } | null; candidates?: { species: { scientific_name: string }; confidence: number }[] }
interface ReviewEntry { action: string; reviewer: string; rationale: string; reviewedAt: string; scientificName?: string | null; basis?: string; referenceEligible?: boolean; trainingEligible?: boolean; verifiedEcologicalStatus?: string }
interface AiVerdict { is_plant: boolean; photo_usable: boolean; species_id: string | null; decision: string; confidence: number; rationale: string; concerns: string[] }
interface AiReview { state: string; applied?: string; verdict?: AiVerdict | null; reason?: string; note?: string; error?: string; model?: string; finishedAt?: string }
interface AiStatus { enabled: boolean; model: string; provider: string; pausedUntil?: string | null; pauseReason?: string | null; counts: Record<string, number>; waiting: number; lastError: string | null; thresholds: { verify: number; reject: number } }
interface Report { id: string; species: string; reportedSpecies: string; status: string; suggestedSpecies: string; identificationDisagrees: boolean; plantDescription: string; notes?: string; trainingCandidateStatus: string; labelReviewStatus?: string; trainingConsent: boolean; referenceConsent: boolean; referenceCandidateStatus: string; referenceIndexStatus: "not_requested" | "pending" | "indexed" | "ineligible" | "failed" | "invalidated"; referenceIndexMessage?: string; verifiedEcologicalStatus: string; ecologicalCitation: string; ecologicalRationale: string; placeName: string; latitude: number; longitude: number; locationMethod: string; locationAccuracy: number | null; observedAt: string; submittedAt: string; lastEditedAt: string | null; editCount: number; prediction: Prediction | null; verifiedSpecies: { scientificName: string; commonName: string } | null; reviewHistory: ReviewEntry[]; aiReview: AiReview | null }
interface Species { id: string; scientific_name: string; common_name: string; role?: string; acceptedCitation?: string; diagnosticDescription?: string }
interface Job { _id: string; source?: string; status: string; detail: string; candidatePath: string; createdAt: string; metrics?: { accuracy: number; macroF1: number; qualityTargetsPassed?: boolean; perClass?: Record<string, { precision: number; recall: number; "f1-score": number; support: number }>; benchmark?: { promote?: boolean; live?: { accuracy: number; macroRecall: number }; candidate?: { accuracy: number; macroRecall: number } } }; promotion?: { status: string; eligible?: boolean; approvedUsername?: string; approvedAt?: string; rationale?: string; modelVersion?: string; rollbackBackup?: string; reason?: string } }
interface Queue { role?: string; view: string; counts: Record<string, number>; worker?: { stage: string; updatedAt: string } | null; reports: Report[]; classes: Species[]; jobs: Job[]; approvedWaiting: number; minTrainingReports: number; minTrainingGroupsPerClass?: number; ai?: AiStatus }
const date = (value: string) => new Date(value).toLocaleString("en-PH", { timeZone: "Asia/Manila", dateStyle: "medium", timeStyle: "short" });
const statusLabel: Record<string, string> = { recorded: "To check", pending: "To check", correction_requested: "Correction requested", verified: "Approved", rejected: "Rejected" };
const statusTone: Record<string, string> = { recorded: "tone-amber", pending: "tone-amber", correction_requested: "tone-rose", verified: "tone-green", rejected: "tone-slate" };
const actionLabel: Record<string, string> = { approve: "Approved", quick_verify: "Quick verified", detailed_verify: "Detailed verification", correct_identification: "Corrected identification", reject: "Rejected", request_correction: "Correction requested" };
const methodLabel: Record<string, string> = { gps: "device GPS", manual: "typed coordinates", map_pin: "map pin", photo_gps: "photo GPS" };
const jobTone: Record<string, string> = { queued: "tone-amber", running: "tone-blue", completed: "tone-green", awaiting_approval: "tone-amber", approved: "tone-blue", promoted: "tone-green", not_eligible: "tone-slate", failed: "tone-rose" };
const percent = (value: number) => `${(value * 100).toFixed(1)}%`;
const referenceStatusLabel: Record<Report["referenceIndexStatus"], string> = { not_requested: "Not requested", pending: "Pending", indexed: "Indexed", ineligible: "Ineligible", failed: "Failed", invalidated: "Invalidated" };
const referenceStatusTone: Record<Report["referenceIndexStatus"], string> = { not_requested: "tone-slate", pending: "tone-amber", indexed: "tone-green", ineligible: "tone-slate", failed: "tone-rose", invalidated: "tone-slate" };

export default function AdminReview() {
  const [queue, setQueue] = useState<Queue | null>(null), [error, setError] = useState(""), [view, setView] = useState("awaiting");
  const [loading, setLoading] = useState(false), [updatedAt, setUpdatedAt] = useState<string>();
  const load = useCallback(async () => {
    setLoading(true);
    try { const response = await fetch(`/api/admin/review?view=${view}`, { cache: "no-store" }); const data = await response.json(); if (!response.ok) throw Error(data.detail); setQueue(data); setError(""); setUpdatedAt(new Date().toISOString()); }
    catch (e) { setError(e instanceof Error ? e.message : "Queue unavailable"); } finally { setLoading(false); }
  }, [view]);
  useEffect(() => { void load(); const timer = setInterval(() => void load(), 15000); return () => clearInterval(timer); }, [load]);
  const counts = queue?.counts ?? {};
  const reviewer = queue?.role === "reviewer";
  const toCheck = (counts.recorded ?? 0) + (counts.pending ?? 0) + (counts.correction_requested ?? 0);
  const tabs = [{ id: "awaiting", label: "To check", n: toCheck }, { id: "verified", label: "Approved", n: counts.verified ?? 0 }, { id: "rejected", label: "Rejected", n: counts.rejected ?? 0 }];
  const stats = [
    { label: "To check", value: toCheck, icon: Inbox, tone: "tone-amber" },
    { label: "Approved", value: counts.verified ?? 0, icon: CircleCheck, tone: "tone-green" },
    { label: "Rejected", value: counts.rejected ?? 0, icon: CircleX, tone: "tone-slate" },
    { label: "Waiting to train", value: queue?.approvedWaiting ?? 0, icon: Cpu, tone: "tone-violet" },
  ];
  return <section className="admin-page">
    <header className="admin-header">
      <div><span className="content-eyebrow">{reviewer ? "REVIEWER WORKSPACE" : "ADMIN WORKSPACE"}</span><h1>{reviewer ? "Sighting review" : "Review & training"}</h1>
        <p>Sightings are saved with GeoFlora AI&apos;s result. Approve when the AI is right, or Correct it when it is wrong. Photos the AI did not get right are used to train the model.</p></div>
      <div className="admin-header-actions">
        <span className="admin-meta" role="status"><i aria-hidden="true" />{updatedAt ? `Updated ${new Date(updatedAt).toLocaleTimeString("en-PH", { timeZone: "Asia/Manila", timeStyle: "short" })} · refreshes every 15 s` : "Loading queue…"}</span>
        <button className="admin-btn is-small" onClick={() => void load()} disabled={loading}><RefreshCw size={14} className={loading ? "animate-spin" : ""} />Refresh</button>
      </div>
    </header>

    <div className="admin-stats" aria-label="Queue totals">{stats.map(stat => <div key={stat.label} className="surface-card admin-stat">
      <span className={`admin-icon ${stat.tone}`}><stat.icon size={18} strokeWidth={1.7} /></span>
      <div className="min-w-0"><strong>{queue ? stat.value.toLocaleString() : "…"}</strong><p>{stat.label}</p></div>
    </div>)}</div>

    {error && <p role="alert" className="content-notice is-error !mt-0">{error}</p>}

    {queue?.ai && (counts.pending ?? 0) > 0 && <AiPanel status={queue.ai} admin={!reviewer} onRan={load} />}
    {queue && !reviewer && <TrainingPanel queue={queue} onRefresh={load} />}

    <div className="min-w-0 space-y-4">
        <div className="admin-toolbar">
          <div role="tablist" aria-label="Review queue" className="admin-tabs">{tabs.map(tab => <button key={tab.id} role="tab" aria-selected={view === tab.id} onClick={() => setView(tab.id)} className="admin-tab">{tab.label}<span className="admin-count">{tab.n}</span></button>)}</div>
          {queue && <span className="text-[11px] text-[var(--muted)]">{queue.reports.length} shown · newest first</span>}
        </div>
        {!queue && !error && <div className="surface-card admin-empty" role="status"><span className="admin-icon tone-green"><Hourglass size={18} /></span><h3>Loading the review queue…</h3></div>}
        {queue && queue.reports.length === 0 && <div className="surface-card admin-empty">
          <span className="admin-icon tone-green">{view === "awaiting" ? <ShieldCheck size={18} /> : <Inbox size={18} />}</span>
          <h3>{view === "awaiting" ? "All caught up" : "Nothing here yet"}</h3>
          <p>{view === "awaiting" ? "Every sighting has been checked. New ones appear here automatically." : view === "verified" ? "Approved sightings will be listed here." : "Rejected sightings will be listed here with the reason given."}</p>
        </div>}
        {queue?.reports.map(report => <ReviewCard key={report.id} report={report} classes={queue.classes} canSetEcology={!reviewer} canManageReferences={!reviewer} onSaved={load} />)}
    </div>
  </section>;
}

function AiPanel({ status, admin, onRan }: { status: AiStatus; admin: boolean; onRan: () => Promise<void> }) {
  const [busy, setBusy] = useState(false), [message, setMessage] = useState("");
  async function run() {
    setBusy(true); setMessage("");
    try { const response = await fetch("/api/admin/ai-review", { method: "POST" }); const data = await response.json(); if (!response.ok) throw Error(data.detail); const done = data.summary as Record<string, number>; setMessage(`Reviewed: ${done.verified ?? 0} verified, ${done.rejected ?? 0} rejected, ${done.needs_human ?? 0} sent to you${done.errors ? `, ${done.errors} failed` : ""}.`); await onRan(); }
    catch (e) { setMessage(e instanceof Error ? e.message : "The AI review could not run."); } finally { setBusy(false); }
  }
  const stats = [{ label: "Auto-verified", value: status.counts.verified ?? 0 }, { label: "Auto-rejected", value: status.counts.rejected ?? 0 }, { label: "Sent to you", value: status.counts.needs_human ?? 0 }, { label: "Not yet reviewed", value: status.waiting }];
  return <section className="pg-ink" aria-label="AI reviewer">
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div className="max-w-xl">
        <p className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-[#c6dcae]"><Bot size={14} />AI reviewer · {status.enabled ? "On" : "Off"}</p>
        <h2 className="lp-display mt-3 text-[clamp(24px,2.4vw,34px)] leading-[0.95]">{status.enabled ? "Reviewing sightings for you" : "Add an API key to turn it on"}</h2>
        <p className="mt-3 text-[13px] leading-6 text-white/75">{status.enabled ? `${status.model} (via ${status.provider}) checks each new photo. A sighting is verified only when it and the image model independently agree on a supported species (confidence ≥ ${Math.round(status.thresholds.verify * 100)}%); non-plant, unusable and duplicate photos are rejected. Everything else waits for you below with its recommendation.` : "Put OPENROUTER_API_KEY (or ANTHROPIC_API_KEY) in apps/web/.env.local and restart the web app. Until then every sighting waits for a person, as before."}</p>
      </div>
      {admin && status.enabled && <button className="lp-pill lp-pill-lime" disabled={busy} onClick={() => void run()}><RefreshCw size={14} className={busy ? "animate-spin" : ""} />{busy ? "Reviewing…" : "Run AI review now"}</button>}
    </div>
    <div className="mt-5 grid grid-cols-2 gap-2 sm:grid-cols-4">{stats.map(stat => <div key={stat.label} className="rounded-2xl bg-white/[0.07] px-4 py-3"><p className="lp-display text-[28px] leading-none">{stat.value}</p><p className="mt-1.5 text-[11px] text-white/65">{stat.label}</p></div>)}</div>
    {status.pausedUntil && <p role="status" className="mt-4 rounded-2xl bg-[#c6dcae] px-4 py-3 text-[13px] font-medium text-[#0d2618]">Paused: {status.pauseReason}. Reviews resume automatically at {new Date(status.pausedUntil).toLocaleString("en-PH", { timeZone: "Asia/Manila", dateStyle: "medium", timeStyle: "short" })}; waiting sightings stay in the queue until then. A paid OpenRouter balance raises the limit.</p>}
    {(message || status.lastError) && <p role="status" className="mt-4 rounded-2xl bg-white/10 px-4 py-3 text-[12px] text-white/85">{message || `Last error: ${status.lastError}`}</p>}
  </section>;
}

function AiRecommendation({ ai, classes, onUse }: { ai: AiReview; classes: Species[]; onUse?: (speciesId: string, reason: string) => void }) {
  if (ai.state === "running") return <p className="review-prediction flex items-center gap-2 text-[13px]"><Bot size={15} className="animate-pulse" />The AI reviewer is looking at this sighting…</p>;
  if (ai.state === "error") return <p className="review-prediction text-[13px]"><Bot size={14} className="mr-1.5 inline" />AI review failed: {ai.error ?? "unknown error"}. It will retry automatically.</p>;
  const verdict = ai.verdict;
  const species = verdict?.species_id ? classes.find(entry => entry.id === verdict.species_id) : null;
  const label: Record<string, string> = { verify: "Recommends verifying", reject: "Recommends rejecting", needs_human: "Wants a person to decide" };
  return <section className="rounded-2xl bg-[#0d2618] p-4 text-[13px] text-white" aria-label="AI reviewer recommendation">
    <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#c6dcae]"><Bot size={13} />AI reviewer</h3>{verdict && <span className="rounded-full bg-white/10 px-2.5 py-1 text-[11px] font-semibold">{label[verdict.decision] ?? verdict.decision} · {Math.round(verdict.confidence * 100)}%</span>}</div>
    {verdict ? <>
      {species && <p className="mt-2"><span className="text-white/60">Species: </span><strong className="italic">{species.scientific_name}</strong> ({species.common_name})</p>}
      <p className="mt-2 leading-6 text-white/85">{verdict.rationale}</p>
      {verdict.concerns.length > 0 && <ul className="mt-2 list-disc space-y-0.5 pl-5 text-[12px] text-white/70">{verdict.concerns.map(concern => <li key={concern}>{concern}</li>)}</ul>}
    </> : <p className="mt-2 text-white/75">{ai.note || "No recommendation was returned."}</p>}
    {ai.applied === "needs_human" && ai.reason && <p className="mt-2 text-[12px] text-[#c6dcae]">Why it is waiting for you: {ai.reason}</p>}
    {onUse && verdict && <button type="button" className="mt-3 rounded-full bg-white px-3.5 py-1.5 text-[12px] font-semibold text-[#0d2618] transition hover:bg-[#c6dcae]" onClick={() => onUse(verdict.species_id ?? "", verdict.rationale)}>Use AI suggestion</button>}
  </section>;
}

function TrainingPanel({ queue, onRefresh }: { queue: Queue; onRefresh: () => Promise<void> }) {
  const [showJobs, setShowJobs] = useState(false);
  const [approvalNotes, setApprovalNotes] = useState<Record<string, string>>({}), [approving, setApproving] = useState(""), [approvalMessage, setApprovalMessage] = useState("");
  async function approvePromotion(job: Job) {
    const rationale = (approvalNotes[job._id] || "").trim() || (job.source === "ml-lab" ? "Approved in GeoFlora admin after checking the new model's results." : "");
    if (rationale.length < 20 || !window.confirm("Use this new model in GeoFlora? The current model is saved, so it can be restored.")) return;
    setApproving(job._id); setApprovalMessage("");
    try {
      const response = await fetch(`/api/admin/training/${job._id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action: "approve_promotion", confirmed: true, rationale }) });
      const data = await response.json(); if (!response.ok) throw Error(data.detail); setApprovalMessage("Approval recorded. The worker will recheck the evaluation before activation."); await onRefresh();
    } catch (e) { setApprovalMessage(e instanceof Error ? e.message : "Promotion approval failed."); }
    finally { setApproving(""); }
  }
  const latest = queue.jobs[0];
  return <section className="surface-card admin-panel" aria-label="Automatic training">
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)] lg:gap-8">
      <div>
        <h2 className="admin-panel-title"><span className="admin-icon is-small tone-violet"><Cpu size={16} /></span><span>Automatic training<small>Photos you approve or correct (when the AI was not sure or wrong) are used to retrain the model</small></span></h2>
        <div className="mt-4 flex items-baseline justify-between gap-3"><span className="text-[12px] text-[var(--muted)]">Checked photos waiting to train</span><strong className="text-[20px] font-semibold tracking-[-.04em]">{queue.approvedWaiting}</strong></div>
        <p className="mt-3 text-[11px] leading-[1.7] text-[var(--muted)]">After enough new photos, GeoFlora retrains the model and compares it with the current one. A better model appears below; it goes live only when you approve it.</p>
      </div>
      <div className="space-y-3">
        <p className="flex items-start gap-2 rounded-xl bg-[#f3f6f1] p-3 text-[11px] leading-[1.6] text-[#4d5c51]"><Activity size={14} className="mt-0.5 shrink-0" />{queue.worker ? `Last worker activity: ${queue.worker.stage.replaceAll("_", " ")} — ${date(queue.worker.updatedAt)}` : "No worker activity recorded for this workspace yet."}</p>
        <div className="flex flex-wrap items-center justify-between gap-2 text-[12px]">
          <span className="flex min-w-0 items-center gap-2"><History size={14} className="shrink-0 text-[var(--muted)]" />{latest ? <>Latest job <span className={`admin-badge ${jobTone[latest.status] ?? "tone-slate"}`}>{latest.status}</span></> : "No jobs yet. Waiting for reviewed photos."}</span>
          {queue.jobs.length > 0 && <button className="admin-btn is-small" aria-expanded={showJobs} onClick={() => setShowJobs(!showJobs)}>{showJobs ? "Hide training jobs" : `Training jobs (${queue.jobs.length})`}</button>}
        </div>
      </div>
    </div>
    {approvalMessage && <p role="status" className="mt-3 text-[12px] text-[var(--muted)]">{approvalMessage}</p>}
    {showJobs && <ol className="mt-5 grid gap-3 border-t border-[#e9efe6] pt-5 md:grid-cols-2">{queue.jobs.map(job => <li key={job._id} className="rounded-2xl border border-[#e3eadf] bg-white/70 p-3.5 text-[12px]">
      <div className="flex items-center justify-between gap-2"><span className={`admin-badge ${jobTone[job.promotion?.status || job.status] ?? "tone-slate"}`}>{job.promotion?.status || job.status}</span><time className="text-[10px] text-[var(--muted)]" dateTime={job.createdAt}>{date(job.createdAt)}</time></div>
      <p className="mt-2 leading-[1.6]">{job.detail || "Waiting for the training worker"}</p>
      {job.metrics && <div className="mt-2 grid grid-cols-2 gap-2"><Metric label="Accuracy" value={job.metrics.accuracy} /><Metric label="Macro F1" value={job.metrics.macroF1} /></div>}
      {job.metrics?.perClass && <details className="mt-2"><summary className="cursor-pointer text-[11px] font-semibold">Per-class evaluation results</summary><div className="mt-2 overflow-x-auto"><table className="w-full text-left text-[10px]"><thead><tr><th className="py-1 pr-2">Class</th><th className="py-1 pr-2">P</th><th className="py-1 pr-2">R</th><th className="py-1 pr-2">F1</th><th className="py-1">n</th></tr></thead><tbody>{Object.entries(job.metrics.perClass).map(([name, value]) => <tr key={name} className="border-t border-[#e3eadf]"><th className="py-1 pr-2 font-medium">{name}</th><td className="py-1 pr-2">{percent(value.precision)}</td><td className="py-1 pr-2">{percent(value.recall)}</td><td className="py-1 pr-2">{percent(value["f1-score"])}</td><td className="py-1">{value.support}</td></tr>)}</tbody></table></div><p className="mt-1 text-[10px] text-[var(--muted)]">Candidate evaluation on its saved test partition; see the recorded candidate artifact before approving.</p></details>}
      {job.candidatePath && <p className="mt-2 break-all font-mono text-[10px] text-[var(--muted)]">{job.candidatePath}</p>}
      {job.promotion?.status === "awaiting_approval" && job.promotion.eligible && job.metrics?.benchmark?.promote && <div className="mt-3 space-y-2 border-t border-[#e3eadf] pt-3">
        <p className="text-[11px] leading-5">Evaluation gates passed. Live vs candidate benchmark accuracy: {percent(job.metrics.benchmark.live?.accuracy ?? 0)} vs {percent(job.metrics.benchmark.candidate?.accuracy ?? 0)}; macro recall: {percent(job.metrics.benchmark.live?.macroRecall ?? 0)} vs {percent(job.metrics.benchmark.candidate?.macroRecall ?? 0)}.</p>
        {job.source !== "ml-lab" && <label className="admin-field">Promotion review rationale<textarea className="admin-input" minLength={20} maxLength={2000} value={approvalNotes[job._id] || ""} onChange={event => setApprovalNotes({ ...approvalNotes, [job._id]: event.target.value })} placeholder="Record why you approve this evaluated candidate" /></label>}
        <button className="admin-btn is-primary" disabled={approving === job._id || (job.source !== "ml-lab" && (approvalNotes[job._id] || "").trim().length < 20)} onClick={() => void approvePromotion(job)}>{approving === job._id ? "Recording approval…" : job.source === "ml-lab" ? "Approve new model" : "Approve promotion"}</button>
      </div>}
      {job.promotion?.approvedUsername && <p className="mt-2 text-[10px] text-[var(--muted)]">Approval by {job.promotion.approvedUsername} · {job.promotion.rationale}</p>}
      {job.promotion?.rollbackBackup && <p className="mt-2 break-all font-mono text-[10px] text-[var(--muted)]">Rollback snapshot: {job.promotion.rollbackBackup}</p>}
    </li>)}</ol>}
  </section>;
}

function Metric({ label, value }: { label: string; value: number }) {
  return <div className="rounded-xl bg-[#f3f6f1] px-3 py-2"><p className="text-[10px] text-[var(--muted)]">{label}</p><p className="text-[14px] font-semibold">{(value * 100).toFixed(2)}%</p></div>;
}

function ReviewCard({ report, classes, canSetEcology, canManageReferences, onSaved }: { report: Report; classes: Species[]; canSetEcology: boolean; canManageReferences: boolean; onSaved: () => Promise<void> }) {
  const [species, setSpecies] = useState(""), [reason, setReason] = useState(""), [confirmed, setConfirmed] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState("");
  const [referenceBusy, setReferenceBusy] = useState(false), [referenceMessage, setReferenceMessage] = useState("");
  const [mode, setMode] = useState<"quick" | "detailed" | "correct" | "reject" | "correction" | null>(null), [evidenceRequired, setEvidenceRequired] = useState(false), [evidence, setEvidence] = useState(""), [trainingEligible, setTrainingEligible] = useState(false), [referenceEligible, setReferenceEligible] = useState(false), [ecologicalStatus, setEcologicalStatus] = useState<"target_invasive" | "non_target" | "pending_ecological_review">("pending_ecological_review"), [ecologicalCitation, setEcologicalCitation] = useState(""), [ecologicalRationale, setEcologicalRationale] = useState(""), [ecologyConfirmed, setEcologyConfirmed] = useState(false);
  const [scientificName, setScientificName] = useState(""), [commonName, setCommonName] = useState(""), [notInvasive, setNotInvasive] = useState(false);
  const [description, setDescription] = useState(""), [citation, setCitation] = useState("");
  const awaiting = report.status === "recorded" || report.status === "pending" || report.status === "correction_requested";
  const prediction = report.prediction;
  const title = report.verifiedSpecies?.scientificName || (report.species && report.species !== "unknown" ? report.species : prediction?.candidates?.[0] ? `Not sure · possibly ${prediction.candidates[0].species.scientific_name}` : "Not sure");
  const photo = `/api/sightings/${report.id}/photo`;
  const submittedText = `${report.suggestedSpecies} ${report.reportedSpecies}`.toLocaleLowerCase();
  const quickSpecies = classes.find(entry => entry.acceptedCitation && entry.diagnosticDescription && [entry.id.replaceAll("_", " "), entry.scientific_name, entry.common_name].some(name => name && submittedText.includes(name.toLocaleLowerCase())) && prediction?.method === "model" && prediction.status === "identified" && prediction.species?.id === entry.id);
  const selectedClass = classes.find(entry => entry.id === species);
  async function review(action: "quick_verify" | "detailed_verify" | "correct_identification" | "reject" | "request_correction") {
    setBusy(true); setError("");
    const selectedSpecies = action === "quick_verify" ? quickSpecies?.id : species;
    try { const response = await fetch("/api/admin/review", { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: report.id, action, speciesId: selectedSpecies, notInvasive, rationale: reason, confirmed, trainingEligible: action === "quick_verify" ? false : trainingEligible, referenceEligible, ecologicalStatus, ecologicalCitation, ecologicalRationale, ecologyConfirmed, scientificName, commonName, description, citation, evidence, evidenceRequired }) }); const data = await response.json(); if (!response.ok) throw Error(data.detail); await onSaved(); } catch (e) { setError(e instanceof Error ? e.message : "Review failed"); } finally { setBusy(false); }
  }
  async function invalidateReference() {
    const rationale = window.prompt("Why should this image be removed from the visual reference index?")?.trim() || "";
    if (rationale.length < 10) return;
    if (!window.confirm("Deactivate this verified image reference? The audit record will be kept.")) return;
    setReferenceBusy(true); setReferenceMessage("");
    try { const response = await fetch(`/api/admin/references/${report.id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action: "invalidate", rationale }) }); const data = await response.json(); if (!response.ok) throw Error(data.detail); setReferenceMessage("Reference deactivated; audit history retained."); await onSaved(); }
    catch (e) { setReferenceMessage(e instanceof Error ? e.message : "Reference could not be deactivated."); }
    finally { setReferenceBusy(false); }
  }
  return <article className="surface-card review-card" aria-label={`Sighting ${report.id}`}>
    <header className="review-card-head">
      <div className="flex min-w-0 items-center gap-3"><span className={`admin-badge ${statusTone[report.status] ?? "tone-slate"}`}>{statusLabel[report.status] ?? report.status}</span><span className="truncate text-[13px] font-semibold italic">{title}</span></div>
      <span className="text-[11px] text-[var(--muted)]">Submitted {date(report.submittedAt)} · #{report.id.slice(-6)}</span>
    </header>
    <div className="review-card-body">
      <div className="space-y-3">
        <a className="review-photo" href={photo} target="_blank" rel="noopener noreferrer"><img src={photo} alt="Submitted plant photo" /><span><Maximize2 size={12} />Full size</span></a>
        <div className="flex flex-wrap gap-1.5"><span className={`admin-badge ${report.trainingConsent ? "tone-green" : "tone-slate"}`}>Training {report.trainingConsent ? "permitted" : "not permitted"}</span>{report.identificationDisagrees && <span className="admin-badge tone-rose">Contributor says CNN photo match is wrong</span>}{report.editCount > 0 && <span className="admin-badge tone-blue">{report.editCount} correction{report.editCount > 1 ? "s" : ""}</span>}</div>
        {(canManageReferences || report.referenceConsent) && <div className="rounded-xl border border-[#e3eadf] p-3">
          <div className="flex flex-wrap items-center gap-2"><span className="text-[11px] font-medium">Visual-reference index</span><span className={`admin-badge ${referenceStatusTone[report.referenceIndexStatus]}`}>{referenceStatusLabel[report.referenceIndexStatus]}</span></div>
          <p className="mt-1 text-[11px] text-[var(--muted)]">{report.referenceIndexMessage || (report.referenceConsent ? "Waiting for human verification and separate reference approval." : "Contributor has not permitted visual-reference use.")}</p>
          {canManageReferences && report.status === "verified" && report.referenceCandidateStatus === "approved" && report.referenceIndexStatus === "indexed" && <button type="button" className="admin-btn is-small is-danger mt-2" disabled={referenceBusy} onClick={() => void invalidateReference()}>{referenceBusy ? "Removing…" : "Remove from visual references"}</button>}
          {referenceMessage && <p role="status" className="mt-2 text-[11px]">{referenceMessage}</p>}
        </div>}
      </div>

      <div className="min-w-0 space-y-5 text-[13px]">
        <section className="review-prediction" aria-label="Original model prediction">
          <h3 className="flex items-center gap-1.5 admin-label"><Sparkles size={12} />ORIGINAL MODEL PREDICTION (UNCHANGED)</h3>
          {report.identificationDisagrees && <p className="mt-2 rounded-lg bg-[#fff0ec] p-2.5 text-[11px] leading-5 text-[#833c2f]">Contributor explicitly marked the CNN suggestion as not matching the photo. Keep this report pending until a human reviewer decides its species.</p>}
          {!prediction ? <p className="mt-2">No image-model identification was attached.</p>
            : prediction.method === "verified_reference" ? <p className="mt-2">Supporting evidence: similar to an earlier reviewed photo{prediction.species ? ` (${prediction.species.scientific_name})` : ""}. Similarity alone does not verify this sighting.</p>
            : <>
              <div className="mt-2 flex flex-wrap items-baseline justify-between gap-2"><strong className={`text-[15px] ${prediction.status === "identified" ? "italic" : ""}`}>{prediction.status === "identified" ? prediction.species?.scientific_name : "Uncertain"}</strong><span className="text-[11px] text-[var(--muted)]">{prediction.model_version}</span></div>
              {typeof prediction.confidence === "number" && <div className="review-score" aria-hidden="true"><span style={{ width: `${prediction.confidence * 100}%` }} /><i style={{ left: `${(prediction.confidence_threshold ?? 0) * 100}%` }} /></div>}
              <p className="mt-2 text-[11px] text-[var(--muted)]">Top score {typeof prediction.confidence === "number" ? percent(prediction.confidence) : "—"} · threshold {Math.round((prediction.confidence_threshold ?? 0) * 100)}%</p>
              {prediction.candidates?.length ? <div className="mt-3 flex flex-wrap gap-1.5" aria-label="Candidates">{prediction.candidates.map(c => <span key={c.species.scientific_name} className="review-chip"><em>{c.species.scientific_name}</em>{percent(c.confidence)}</span>)}</div> : null}
            </>}
        </section>

        {report.aiReview && <AiRecommendation ai={report.aiReview} classes={classes} onUse={awaiting ? (speciesId, why) => { if (speciesId) setSpecies(speciesId); setReason(why); } : undefined} />}

        {report.verifiedSpecies && <p className="review-confirmed"><CircleCheck size={17} className="shrink-0" /><span>Reviewer-confirmed species: <strong>{report.verifiedSpecies.scientificName}</strong>{report.verifiedSpecies.commonName ? ` (${report.verifiedSpecies.commonName})` : ""}</span></p>}

        <dl className="admin-dl">
          <div><dt><Leaf size={12} />Contributor's species</dt><dd>{report.suggestedSpecies || (report.reportedSpecies === "unknown" ? "None suggested" : report.reportedSpecies)}</dd></div>
          <div><dt><CalendarClock size={12} />Observed / submitted</dt><dd>{date(report.observedAt)}<br /><span className="text-[var(--muted)]">{date(report.submittedAt)}</span>{report.editCount ? <><br /><span className="text-[var(--muted)]">{report.editCount} contributor correction{report.editCount > 1 ? "s" : ""}, last {date(report.lastEditedAt!)}</span></> : null}</dd></div>
          <div className="is-wide"><dt><MapPin size={12} />Location</dt><dd>{report.placeName || "No place name"}<br /><span className="text-[var(--muted)]">{report.latitude}, {report.longitude} ({methodLabel[report.locationMethod] ?? report.locationMethod}{report.locationAccuracy !== null ? `, ±${Math.round(report.locationAccuracy)} m` : ""})</span><br /><a className="inline-flex items-center gap-1 text-[12px] font-semibold text-[var(--green)] underline underline-offset-4" href={`https://www.openstreetmap.org/?mlat=${report.latitude}&mlon=${report.longitude}#map=16/${report.latitude}/${report.longitude}`} target="_blank" rel="noopener noreferrer">Open in OpenStreetMap<ExternalLink size={12} /></a></dd></div>
          <div className="is-wide"><dt>Description</dt><dd className="whitespace-pre-wrap">{report.plantDescription || "None supplied"}</dd></div>
          {report.notes && <div className="is-wide"><dt>Notes</dt><dd className="whitespace-pre-wrap">{report.notes}</dd></div>}
        </dl>

        {report.reviewHistory.length > 0 && <section aria-label="Review history"><h3 className="flex items-center gap-1.5 admin-label"><History size={12} />REVIEW HISTORY</h3><ol className="admin-timeline">{report.reviewHistory.map((entry, index) => <li key={index}><strong>{actionLabel[entry.action] ?? entry.action} by {entry.reviewer}</strong>{entry.basis === "ai_review" && <span className="admin-badge tone-violet ml-1.5 !py-0.5">AI</span>}{entry.scientificName ? ` as ${entry.scientificName}` : ""} <span className="text-[var(--muted)]">· {date(entry.reviewedAt)}</span><br />{entry.rationale}</li>)}</ol></section>}

        {awaiting && <SimpleDecision report={report} classes={classes} onSaved={onSaved} />}
      </div>
    </div>
  </article>;
}

// Approve keeps the AI's species; Correct picks the right one (or types a new species); Reject is for non-plant or unusable photos.
function SimpleDecision({ report, classes, onSaved }: { report: Report; classes: Species[]; onSaved: () => Promise<void> }) {
  const prediction = report.prediction;
  const aiSpecies = prediction?.status === "identified" && !report.identificationDisagrees ? prediction.species : null;
  const [mode, setMode] = useState<"" | "correct" | "reject">(aiSpecies ? "" : "correct");
  const [species, setSpecies] = useState(""), [scientificName, setScientificName] = useState(""), [commonName, setCommonName] = useState(""), [note, setNote] = useState("");
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  async function send(action: "simple_approve" | "simple_correct" | "simple_reject") {
    setBusy(true); setError("");
    try {
      const response = await fetch("/api/admin/review", { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: report.id, action, speciesId: species === "new" ? undefined : species, scientificName, commonName, note }) });
      const data = await response.json(); if (!response.ok) throw Error(data.detail); await onSaved();
    } catch (e) { setError(e instanceof Error ? e.message : "Could not save."); } finally { setBusy(false); }
  }
  return <div className="review-decision">
    <fieldset disabled={busy} className="grid gap-3">
      {aiSpecies && mode === "" && <p className="text-[13px]">GeoFlora AI says <strong className="italic">{aiSpecies.scientific_name}</strong>. Is that right?</p>}
      {!aiSpecies && mode === "correct" && <p className="text-[13px]">{report.identificationDisagrees ? "The contributor said the AI result does not match." : "GeoFlora AI was not sure about this photo."} Choose the correct species.</p>}
      {mode === "" && <div className="flex flex-wrap gap-2.5">
        <button type="button" className="admin-btn is-primary" onClick={() => void send("simple_approve")}><CircleCheck size={16} />Approve</button>
        <button type="button" className="admin-btn" onClick={() => setMode("correct")}>Correct</button>
        <button type="button" className="admin-btn is-small !border-transparent text-[var(--muted)]" onClick={() => setMode("reject")}>Reject</button>
      </div>}
      {mode === "correct" && <>
        <label className="admin-field">Correct species<select className="admin-input" value={species} onChange={event => setSpecies(event.target.value)}><option value="">Choose the species</option>{classes.map(entry => <option key={entry.id} value={entry.id}>{entry.scientific_name} ({entry.common_name})</option>)}<option value="new">Another species (type its name)</option></select></label>
        {species === "new" && <div className="grid gap-3 sm:grid-cols-2"><label className="admin-field">Scientific name<input className="admin-input" value={scientificName} maxLength={150} placeholder="e.g. Hibiscus rosa-sinensis" onChange={event => setScientificName(event.target.value)} /></label><label className="admin-field">Common name (optional)<input className="admin-input" value={commonName} maxLength={120} onChange={event => setCommonName(event.target.value)} /></label></div>}
        <label className="admin-field">Note (optional)<input className="admin-input" value={note} maxLength={500} onChange={event => setNote(event.target.value)} placeholder="e.g. Leaves are smooth, not hairy" /></label>
        <div className="flex flex-wrap gap-2.5"><button type="button" className="admin-btn is-primary" disabled={!species || (species === "new" && !scientificName.trim())} onClick={() => void send("simple_correct")}><CircleCheck size={16} />Save correction</button>{aiSpecies && <button type="button" className="admin-btn" onClick={() => setMode("")}>Cancel</button>}{!aiSpecies && <button type="button" className="admin-btn is-small !border-transparent text-[var(--muted)]" onClick={() => setMode("reject")}>Reject</button>}</div>
        {report.trainingConsent && <p className="text-[11px] text-[var(--muted)]">This photo will be used to train the model after you save.</p>}
      </>}
      {mode === "reject" && <>
        <label className="admin-field">Reason (optional)<input className="admin-input" value={note} maxLength={500} onChange={event => setNote(event.target.value)} placeholder="e.g. Not a plant, too blurry" /></label>
        <div className="flex flex-wrap gap-2.5"><button type="button" className="admin-btn is-danger" onClick={() => void send("simple_reject")}><CircleX size={16} />Reject</button><button type="button" className="admin-btn" onClick={() => setMode(aiSpecies ? "" : "correct")}>Cancel</button></div>
      </>}
      {error && <p role="alert" className="content-notice is-error !mt-0">{error}</p>}
    </fieldset>
  </div>;
}
