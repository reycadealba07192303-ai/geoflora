"use client";
import { useEffect, useMemo, useState } from "react";
import { FilePlus2, Search } from "lucide-react";
import { canModerate, useAccount } from "../../components/auth-gate";
import { RESULT_LABEL, RESULT_TONE, type ReportResult } from "../../lib/ai-result";

interface Report { id: string; species: string; status: string; result: ReportResult; possibleSpecies: string | null; placeName: string; latitude: number; longitude: number; observedAt: string; submittedAt: string; latestReview: { action: string; rationale: string } | null; editable: boolean }
const FILTERS: { id: "all" | ReportResult; label: string }[] = [{ id: "all", label: "All" }, { id: "target", label: "Target invasive" }, { id: "other", label: "Not a target" }, { id: "uncertain", label: "Not sure" }, { id: "rejected", label: "Rejected" }];
const name = (row: Report) => row.species !== "unknown" ? row.species : row.possibleSpecies ? `Possibly ${row.possibleSpecies}` : "Unidentified plant";
const date = (value: string) => new Date(value).toLocaleString("en-PH", { timeZone: "Asia/Manila", dateStyle: "medium", timeStyle: "short" });

// Every report the viewer can see, in any status: contributors see their own, reviewers and administrators the workspace.
export default function ReportsList({ onViewReport, onNew }: { onViewReport: (id: string) => void; onNew: () => void }) {
  const { user } = useAccount();
  const [reports, setReports] = useState<Report[] | null>(null), [error, setError] = useState(""), [status, setStatus] = useState("all"), [query, setQuery] = useState("");
  useEffect(() => {
    const abort = new AbortController();
    fetch("/api/sightings", { cache: "no-store", signal: abort.signal }).then(async response => { const body = await response.json(); if (!response.ok) throw Error(body.detail); setReports(body.reports); }).catch(e => { if (!abort.signal.aborted) setError(e.message); });
    return () => abort.abort();
  }, []);
  const counts = useMemo(() => (reports ?? []).reduce<Record<string, number>>((all, row) => ({ ...all, [row.result]: (all[row.result] ?? 0) + 1 }), {}), [reports]);
  const shown = (reports ?? []).filter(row => (status === "all" || row.result === status) &&
    (!query.trim() || `${name(row)} ${row.placeName}`.toLowerCase().includes(query.trim().toLowerCase())));
  const count = (id: string) => id === "all" ? reports?.length ?? 0 : counts[id] ?? 0;
  return <section className="pg">
    <header className="pg-head"><div><span className="content-eyebrow">Field notebook</span><h1>{canModerate(user.role) ? "All reports" : "My reports"}</h1><p>{canModerate(user.role) ? "Every report in the workspace, newest first." : "Every report you submitted, newest first."} Results are AI identifications. Select a report to view it, correct it, or download its PDF.</p></div><div className="pg-actions"><button className="flora-create-button" onClick={onNew}><FilePlus2 size={16} />New report</button></div></header>
    <div className="admin-toolbar"><div className="admin-tabs" role="group" aria-label="Filter by result">{FILTERS.filter(item => item.id !== "rejected" || count("rejected") > 0).map(item => <button key={item.id} aria-pressed={status === item.id} onClick={() => setStatus(item.id)} className="admin-tab">{item.label} <span className="pg-count">({count(item.id)})</span></button>)}</div>
      <label className="admin-search"><Search size={14} aria-hidden="true" /><span className="sr-only">Search reports</span><input placeholder="Search species or place" value={query} onChange={e => setQuery(e.target.value)} /></label></div>
    {error && <p role="alert" className="content-notice is-error !mt-0">{error}</p>}
    {!reports && !error && <p role="status" className="pg-card text-[14px]">Loading reports…</p>}
    {reports && reports.length === 0 && <div className="pg-card admin-empty"><h3>No reports yet</h3><p>Identify a plant, then create your first report.</p></div>}
    {reports && reports.length > 0 && shown.length === 0 && <div className="pg-card admin-empty"><h3>No reports match this filter</h3><p>Try another result or search term.</p></div>}
    <ul className="grid gap-2.5 md:grid-cols-2">{shown.map(row => <li key={row.id}><button onClick={() => onViewReport(row.id)} className="report-row">
      <img src={`/api/sightings/${row.id}/photo?thumbnail=1`} alt="" />
      <span className="min-w-0 flex-1"><span className="flex items-start justify-between gap-2"><span className={`block truncate text-[15px] font-semibold ${row.species === "unknown" ? "" : "italic"}`}>{name(row)}</span><span className={`admin-badge shrink-0 ${RESULT_TONE[row.result]}`}>{RESULT_LABEL[row.result]}</span></span>
        <span className="mt-1.5 block truncate text-[12px] text-[#5f6b62]">{row.placeName || `${row.latitude.toFixed(4)}, ${row.longitude.toFixed(4)}`}</span>
        <span className="mt-0.5 block text-[12px] text-[#5f6b62]">Observed {date(row.observedAt)}</span>
        {row.status === "correction_requested" && row.latestReview && <span className="mt-1.5 block truncate text-[12px] text-[#874a37]">Reviewer: {row.latestReview.rationale}</span>}</span>
    </button></li>)}</ul>
    {reports && reports.length >= 500 && <p className="pg-hint px-1">Showing the latest 500 reports.</p>}
  </section>;
}
