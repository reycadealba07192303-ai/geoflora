"use client";
import { useEffect, useState, type FormEvent } from "react";
import { CheckCircle2, ClipboardList, LoaderCircle } from "lucide-react";
import { GROUPS, SURVEY_ITEMS, SURVEY_VERSION, SUS_ITEMS, susScore, type Group } from "./protocol";
import { UserSurveyResults } from "./study-recorder";
import { useAccount } from "../../components/auth-gate";

// The user's own questionnaire: the 10 System Usability Scale statements, 5 GeoFlora statements and comments.
export default function UserSurvey() {
  const { user } = useAccount();
  const [loading, setLoading] = useState(true), [busy, setBusy] = useState(false), [error, setError] = useState(""), [saved, setSaved] = useState<number | null>(null), [answeredBefore, setAnsweredBefore] = useState(false);
  const [consent, setConsent] = useState(false), [group, setGroup] = useState<Group | "">("");
  const [sus, setSus] = useState<number[]>(Array(10).fill(0)), [items, setItems] = useState<number[]>(Array(SURVEY_ITEMS.length).fill(0)), [comments, setComments] = useState("");
  useEffect(() => {
    fetch("/api/study/survey", { cache: "no-store" }).then(r => r.json()).then(body => {
      if (body.response) { setAnsweredBefore(true); setConsent(true); setGroup(body.response.group); setSus(body.response.sus); setItems(body.response.items); setComments(body.response.comments ?? ""); }
    }).catch(() => {}).finally(() => setLoading(false));
  }, []);
  const missing = sus.filter(v => !v).length + items.filter(v => !v).length;
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const response = await fetch("/api/study/survey", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ consent, consentVersion: SURVEY_VERSION, group, sus, items, comments }) });
      const body = await response.json(); if (!response.ok) throw Error(body.detail); setSaved(body.susScore); setAnsweredBefore(true); window.scrollTo({ top: 0 });
    } catch (e) { setError(e instanceof Error ? e.message : "Your answers could not be saved."); } finally { setBusy(false); }
  }
  const scale = (values: number[], set: (next: number[]) => void, index: number, name: string) => <span className="sus-scale">{[1, 2, 3, 4, 5].map(value => <label key={value} title={value === 1 ? "Strongly disagree" : value === 5 ? "Strongly agree" : undefined}><input className="sr-only" type="radio" name={`${name}-${index}`} checked={values[index] === value} onChange={() => set(values.map((old, i) => i === index ? value : old))} />{value}</label>)}</span>;
  if (loading) return <section className="pg"><p role="status" className="pg-card text-[14px]">Loading the survey…</p></section>;
  return <section className="admin-page">
    <header className="admin-header"><div><span className="content-eyebrow">FEEDBACK</span><h1>Feedback survey</h1>
      <p>Tell us how GeoFlora worked for you. It takes about 3 minutes. Your answers help the GeoFlora research team measure how easy the system is to use{answeredBefore ? "; you can update your answers any time" : ""}.</p></div></header>
    {user.role === "admin" && <UserSurveyResults />}
    {user.role === "admin" && <h2 className="px-1 pt-2 text-[15px] font-semibold text-[#0d2618]">Your own answers</h2>}
    {saved !== null && <p role="status" className="content-notice is-success !mt-0"><CheckCircle2 size={17} /><span>Thank you! Your answers are saved. Your usability score: <strong>{saved}</strong> out of 100.</span></p>}
    {error && <p role="alert" className="content-notice is-error !mt-0">{error}</p>}
    <form onSubmit={submit} className="space-y-5" aria-label="Feedback survey"><fieldset disabled={busy} className="space-y-5">
      <div className="surface-card admin-panel space-y-4">
        <h2 className="admin-panel-title"><span className="admin-step">1</span>About you</h2>
        <label className="admin-field max-w-sm">Which describes you best?<select className="admin-input" value={group} onChange={e => setGroup(e.target.value as Group)} required><option value="">Choose</option>{Object.entries(GROUPS).map(([key, name]) => <option key={key} value={key}>{name}</option>)}</select></label>
        <label className="admin-check"><input type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)} required /><span>I agree that my answers may be used in the GeoFlora research study. Results are reported without names or account details, and I can change my answers later.</span></label>
      </div>
      <div className="surface-card admin-panel">
        <h2 className="admin-panel-title"><span className="admin-step">2</span><span>Using the system<small>1 = strongly disagree, 5 = strongly agree</small></span></h2>
        <div className="mt-3">{SUS_ITEMS.map((item, index) => <div key={item} className="sus-row" role="radiogroup" aria-label={`Statement ${index + 1}: ${item}`}><span className="min-w-0 flex-1">{index + 1}. {item}</span>{scale(sus, setSus, index, "sus")}</div>)}</div>
      </div>
      <div className="surface-card admin-panel">
        <h2 className="admin-panel-title"><span className="admin-step">3</span><span>About GeoFlora<small>1 = strongly disagree, 5 = strongly agree</small></span></h2>
        <div className="mt-3">{SURVEY_ITEMS.map((item, index) => <div key={item} className="sus-row" role="radiogroup" aria-label={`GeoFlora statement ${index + 1}: ${item}`}><span className="min-w-0 flex-1">{index + 1}. {item}</span>{scale(items, setItems, index, "geo")}</div>)}</div>
      </div>
      <div className="surface-card admin-panel">
        <label className="admin-field"><span className="admin-panel-title"><span className="admin-step">4</span>Comments or suggestions (optional)</span><textarea className="admin-input" rows={3} maxLength={4000} value={comments} onChange={e => setComments(e.target.value)} placeholder="What was confusing? What would make GeoFlora better?" /></label>
      </div>
      <div className="admin-savebar"><span className="text-[12px] text-[var(--muted)]">{missing ? `${missing} statement${missing > 1 ? "s" : ""} left` : `All answered · usability score ${susScore(sus)}`}</span>
        <button className="admin-btn is-primary" type="submit" disabled={!consent || !group || missing > 0}>{busy ? <LoaderCircle size={16} className="animate-spin" /> : <ClipboardList size={16} />}{answeredBefore ? "Update my answers" : "Submit survey"}</button></div>
    </fieldset></form>
  </section>;
}
