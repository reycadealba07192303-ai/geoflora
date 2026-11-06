"use client";
import { useEffect, useState, type FormEvent } from "react";
import { BookOpen, CalendarClock, Download, ExternalLink, FilePlus2, MapPin, Pencil, ScanLine, Trash2 } from "lucide-react";
import ReportLocationMap from "./report-location-map";
import LocationPicker from "./location-picker";
import { RESULT_LABEL, RESULT_TONE, type ReportResult } from "../../lib/ai-result";
import { speciesInformation } from "../identification/species-information";

const infoFor = (name?: string | null) => speciesInformation[(name ?? "").trim().toLowerCase().replace(/\s+/g, "_")];

interface Prediction { status?: string; method?: string; confidence?: number | null; confidence_threshold?: number; model_version?: string; species?: { scientific_name: string } | null }
interface Report { id: string; species: string; result: ReportResult; possibleSpecies: string | null; description: string; citations: string[]; observedAt: string; submittedAt: string; placeName: string; latitude: number; longitude: number; labelSource: string; identificationDisagrees: boolean; trainingCandidateStatus: string; labelReviewStatus: string; status: string; notes?: string; plantDescription: string; suggestedSpecies: string; prediction: Prediction | null; locationMethod: string; locationAccuracy: number | null; lastEditedAt: string | null; editable: boolean; verifiedSpecies: { scientificName: string; commonName: string } | null; verifiedAt: string | null; latestReview: { action: string; rationale: string; reviewedAt: string; byAi?: boolean } | null }
const reportName = (report: Report) => report.species !== "unknown" ? report.species : report.possibleSpecies ? `Possibly ${report.possibleSpecies}` : "Unidentified plant";
const methodLabel: Record<string, string> = { gps: "Device GPS", manual: "Typed coordinates", map_pin: "Pin placed on map", photo_gps: "GPS saved in the photo" };
const date = (value: string) => new Date(value).toLocaleString("en-PH", { timeZone: "Asia/Manila" });
function localTime(value: string) { const d = new Date(value); return new Date(d.getTime() - d.getTimezoneOffset() * 60_000).toISOString().slice(0, 19); }

export default function ReportView({ id, onAnother }: { id: string; onAnother: () => void }) {
  const [report, setReport] = useState<Report | null>(null), [error, setError] = useState("");
  const [editing, setEditing] = useState(false), [confirmWithdraw, setConfirmWithdraw] = useState(false), [busy, setBusy] = useState(false), [actionError, setActionError] = useState("");
  const [withdrawn, setWithdrawn] = useState(false);
  useEffect(() => {
    setReport(null); setError(""); setWithdrawn(false);
    const abort = new AbortController();
    const load = () => fetch(`/api/sightings/${id}`, { cache: "no-store", signal: abort.signal }).then(async response => { const data = await response.json(); if (!response.ok) throw Error(data.detail); setReport(data); setError(""); }).catch(error => { if (!abort.signal.aborted) setError(error.message); });
    void load(); const timer = setInterval(() => void load(), 15000);
    return () => { abort.abort(); clearInterval(timer); };
  }, [id]);
  async function withdraw() {
    setBusy(true); setActionError("");
    try { const response = await fetch(`/api/sightings/${id}`, { method: "DELETE" }); const data = await response.json(); if (!response.ok) throw Error(data.detail); setWithdrawn(true); setReport(null); }
    catch (e) { setActionError(e instanceof Error ? e.message : "The report could not be withdrawn."); } finally { setBusy(false); }
  }
  if (withdrawn) return <section role="status" className="pg"><div className="pg-ink mx-auto w-full max-w-2xl text-center sm:!p-12"><p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#c6dcae]">Report withdrawn</p><h1 className="lp-display mt-3 text-[clamp(32px,4vw,52px)] leading-[0.92]">Your report was withdrawn.</h1><p className="mx-auto mt-4 max-w-md text-[14px] leading-7 text-white/75">Its photo, location, description and identification were deleted. Only the reference number and submission and withdrawal times are kept.</p><button className="lp-pill lp-pill-lime lp-pill-lg mx-auto mt-6" onClick={onAnother}><FilePlus2 size={16} />Create another report</button></div></section>;
  if (error) return <section className="pg"><p role="alert" className="content-notice is-error">{error}</p></section>;
  if (!report) return <section className="pg"><p role="status" className="pg-card text-[14px]">Loading your saved report...</p></section>;
  const link = `https://www.openstreetmap.org/?mlat=${report.latitude}&mlon=${report.longitude}#map=15/${report.latitude}/${report.longitude}`;
  const prediction = report.prediction;
  return <section className="pg">
    <header className="pg-head">
      <div><span className="content-eyebrow">Field report · {RESULT_LABEL[report.result].toUpperCase()}</span><h1 className="!normal-case !tracking-[-0.035em]"><span className={report.species === "unknown" ? "" : "italic"}>{reportName(report)}</span></h1></div>
      <div className="pg-actions"><a className="flora-create-button" href={`/api/sightings/${id}/pdf`}><Download size={17} />Download PDF</a></div>
    </header>

    {report.latestReview && ["verified", "rejected", "correction_requested"].includes(report.status) && <article role="status" className={`pg-card border-l-4 ${report.status === "verified" ? "border-[#4f7a3f]" : "border-[#d49a46]"}`}><h2 className="text-[16px] font-semibold">{report.status === "verified" ? `Verified as ${report.verifiedSpecies?.scientificName ?? report.species}` : report.status === "correction_requested" ? "A reviewer asked you to correct this report" : "A reviewer could not verify this report"}</h2><p className="mt-2 whitespace-pre-wrap text-[14px] leading-7">{report.latestReview.rationale}</p><p className="pg-hint mt-2">{report.latestReview.byAi ? "Reviewed automatically by the GeoFlora AI reviewer · " : ""}{date(report.latestReview.reviewedAt)} (Philippine time){report.status === "correction_requested" ? " · Use Correct report below; saving sends it back for review." : ""}</p></article>}

    <div className="grid items-start gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <div className="grid gap-3">
        <figure className="relative m-0 overflow-hidden rounded-[28px] bg-[#0d2618]"><img src={`/api/sightings/${id}/photo`} alt="Plant photographed in this report" className="h-[clamp(300px,52svh,520px)] w-full object-contain" /><figcaption className={`admin-badge absolute bottom-4 left-4 !px-3 !py-1.5 ${RESULT_TONE[report.result]}`}>{RESULT_LABEL[report.result].toUpperCase()}</figcaption></figure>
        <article className="overflow-hidden rounded-[28px] bg-white"><h2 className="pg-card-title px-6 pb-4 pt-5"><MapPin size={17} />Where the plant was found</h2><ReportLocationMap key={`${report.latitude},${report.longitude}`} id={id} latitude={report.latitude} longitude={report.longitude} /><a className="flex items-center gap-1.5 px-6 py-4 text-[13px] font-semibold text-[#3d6a3f] underline underline-offset-4" href={link} target="_blank" rel="noopener noreferrer">View location in OpenStreetMap<ExternalLink size={13} /></a></article>
      </div>

      <div className="grid gap-3">
        <article className="pg-card">
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#3d6a3f]">{report.labelSource === "admin_review" ? "Reviewed by an administrator" : report.labelSource === "verified_reference" ? "Exact match to an administrator-reviewed photo" : report.result === "uncertain" ? "AI identification · the model was not sure" : "Identified by GeoFlora AI"}</p>
          {report.description && <><h2 className="mt-4 text-[13px] font-semibold uppercase tracking-[0.1em] text-[#5f6b62]">{report.species === "unknown" ? "About the closest match" : "About this species"}</h2><p className="mt-1.5 whitespace-pre-wrap text-[14px] leading-7">{report.description}</p></>}
          <dl className="admin-dl mt-5 border-t border-[#e4e9e0] pt-5">
            <div><dt><CalendarClock size={12} />Observed</dt><dd>{date(report.observedAt)} (Philippine time)</dd></div>
            <div><dt>Report created</dt><dd>{date(report.submittedAt)} (Philippine time)</dd></div>
            {report.lastEditedAt && <div><dt>Last corrected</dt><dd>{date(report.lastEditedAt)} (Philippine time)</dd></div>}
            <div><dt><MapPin size={12} />Location</dt><dd>{report.placeName || "Recorded coordinates"}<br />{report.latitude.toFixed(5)}, {report.longitude.toFixed(5)}<br /><span className="text-[12px] text-[#5f6b62]">{methodLabel[report.locationMethod] ?? report.locationMethod}{report.locationAccuracy !== null ? ` · ±${Math.round(report.locationAccuracy)} m` : ""}</span></dd></div>
            {report.suggestedSpecies && <div><dt>Name suggested by the AI vision model</dt><dd>{report.suggestedSpecies}</dd></div>}
            {report.notes && <div className="is-wide"><dt>Notes</dt><dd className="whitespace-pre-wrap">{report.notes}</dd></div>}
          </dl>
        </article>

        <article className="pg-ink" aria-label="Identification record"><h2 className="flex items-center gap-2 text-[16px] font-semibold"><ScanLine size={17} className="text-[#c6dcae]" />Identification record</h2><div className="mt-3 space-y-2 text-[14px] leading-6 text-white/85">{report.identificationDisagrees && <p className="rounded-xl bg-white/10 p-3">You marked the model result as not matching your plant, so this report is saved as "not sure". The original model suggestion ({prediction?.species?.scientific_name ?? "species"}) is kept.</p>}{!prediction ? <p className="text-white/70">No image-model identification was attached to this report.</p> : prediction.method === "verified_reference" ? <p>Matched an administrator-reviewed photo{prediction.species ? `: ${prediction.species.scientific_name}` : ""}. No model score applies.</p> : <><p>Model result: <strong className="text-white">{prediction.status === "identified" ? prediction.species?.scientific_name : "Uncertain (no species assigned)"}</strong></p><p>Top model score {typeof prediction.confidence === "number" ? `${(prediction.confidence * 100).toFixed(1)}%` : "—"} · threshold {typeof prediction.confidence_threshold === "number" ? `${Math.round(prediction.confidence_threshold * 100)}%` : "—"} · model {prediction.model_version ?? "unknown"}</p></>}{report.verifiedSpecies && <p className="rounded-2xl bg-white/10 p-3">Reviewer-confirmed species: <strong className="text-[#c6dcae]">{report.verifiedSpecies.scientificName}</strong>{report.verifiedSpecies.commonName ? ` (${report.verifiedSpecies.commonName})` : ""}</p>}</div></article>

        {report.editable && <article className="pg-card space-y-3"><h2 className="pg-card-title">Manage your report</h2><p className="pg-hint !text-[13px]">You can correct the place, time or notes, or withdraw this report. The photo and the AI identification can't be changed; withdraw and save a new report instead.</p>
          {!editing && !confirmWithdraw && <div className="flex flex-wrap gap-2"><button className="admin-btn" onClick={() => { setEditing(true); setActionError(""); }}><Pencil size={15} />Correct report</button><button className="admin-btn is-danger" onClick={() => { setConfirmWithdraw(true); setActionError(""); }}><Trash2 size={15} />Withdraw report</button></div>}
          {confirmWithdraw && <div role="alertdialog" aria-label="Confirm withdrawal" className="space-y-3 rounded-2xl border border-[#ecdcbf] bg-[#fff8ec] p-4 text-[13px] leading-6"><p>Withdrawing permanently deletes this report's photo, location, description and identification. This cannot be undone.</p><div className="flex flex-wrap gap-2"><button className="admin-btn is-danger" disabled={busy} onClick={() => void withdraw()}>{busy ? "Withdrawing..." : "Yes, withdraw and delete"}</button><button className="admin-btn" disabled={busy} onClick={() => setConfirmWithdraw(false)}>Keep report</button></div></div>}
          {editing && <CorrectionForm report={report} onCancel={() => setEditing(false)} onSaved={updated => { setReport(updated); setEditing(false); }} />}
          {actionError && <p role="alert" className="content-notice is-error !mt-0">{actionError}</p>}
        </article>}

        <SpeciesAbout report={report} />
        {report.citations.length > 0 && <article className="pg-card space-y-2"><h2 className="pg-card-title"><BookOpen size={17} />Species references</h2>{report.citations.map(url => <a key={url} className="block break-all text-[13px] text-[#3d6a3f] underline underline-offset-4" href={url} target="_blank" rel="noopener noreferrer">{url}</a>)}</article>}
      </div>
    </div>

    <div className="flex flex-wrap items-center gap-2 px-1"><button className="flora-create-button" onClick={onAnother}><FilePlus2 size={16} />Identify another plant</button><a className="admin-btn !min-h-[46px]" href={`/api/sightings/${id}/pdf`}><Download size={16} />Download PDF</a><p className="ml-auto break-all text-[11px] text-[#5f6b62]">Reference: {id}</p></div>
  </section>;
}

function CorrectionForm({ report, onCancel, onSaved }: { report: Report; onCancel: () => void; onSaved: (report: Report) => void }) {
  const [placeName, setPlaceName] = useState(report.placeName), [notes, setNotes] = useState(report.notes ?? ""), [description, setDescription] = useState(report.plantDescription), [suggestion, setSuggestion] = useState(report.suggestedSpecies);
  const [observedAt, setObservedAt] = useState(localTime(report.observedAt)), [latitude, setLatitude] = useState(String(report.latitude)), [longitude, setLongitude] = useState(String(report.longitude)), [method, setMethod] = useState(report.locationMethod);
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  const userLabel = report.labelSource === "user_suggestion";
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    const moved = latitude !== String(report.latitude) || longitude !== String(report.longitude);
    const body = { placeName, notes, plantDescription: description, ...(userLabel ? { suggestedSpecies: suggestion } : {}), observedAt: new Date(observedAt).toISOString(), ...(moved ? { latitude, longitude, locationMethod: method === "gps" ? "manual" : method } : {}) };
    try { const response = await fetch(`/api/sightings/${report.id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }); const data = await response.json(); if (!response.ok) throw Error(data.detail); onSaved(data); }
    catch (e) { setError(e instanceof Error ? e.message : "The correction could not be saved."); } finally { setBusy(false); }
  }
  return <form onSubmit={submit} aria-label="Correct report"><fieldset disabled={busy} className="grid gap-3">
    <div className="grid gap-3 sm:grid-cols-2"><label className="admin-field">Place or landmark<input className="admin-input" maxLength={200} value={placeName} onChange={e => setPlaceName(e.target.value)} /></label>
      <label className="admin-field">When the plant was observed<input className="admin-input" type="datetime-local" step="1" required value={observedAt} onChange={e => setObservedAt(e.target.value)} /></label></div>
    <label className="admin-field">Plant description (optional)<textarea className="admin-input" rows={3} maxLength={2000} value={description} onChange={e => setDescription(e.target.value)} /></label>
    {userLabel && <label className="admin-field">Suggested name (optional)<input className="admin-input" maxLength={120} value={suggestion} onChange={e => setSuggestion(e.target.value)} /></label>}
    <label className="admin-field">Notes<textarea className="admin-input !min-h-[42px]" rows={2} maxLength={2000} value={notes} onChange={e => setNotes(e.target.value)} /></label>
    <div className="grid gap-3 sm:grid-cols-2"><label className="admin-field">Latitude<input className="admin-input" name="latitude" type="number" min="-90" max="90" step="any" required value={latitude} onChange={e => { setLatitude(e.target.value); setMethod("manual"); }} /></label><label className="admin-field">Longitude<input className="admin-input" name="longitude" type="number" min="-180" max="180" step="any" required value={longitude} onChange={e => { setLongitude(e.target.value); setMethod("manual"); }} /></label></div>
    <LocationPicker latitude={latitude} longitude={longitude} onPick={(lat, lng) => { setLatitude(String(lat)); setLongitude(String(lng)); setMethod("map_pin"); }} />
    {error && <p role="alert" className="content-notice is-error !mt-0">{error}</p>}
    <div className="flex flex-wrap gap-2"><button className="admin-btn is-primary" type="submit">{busy ? "Saving..." : "Save correction"}</button><button className="admin-btn" type="button" onClick={onCancel}>Cancel</button></div>
  </fieldset></form>;
}

// The species' description, how to recognise it, why it matters and its look-alikes (same content as the result screen).
function SpeciesAbout({ report }: { report: Report }) {
  const name = report.verifiedSpecies?.scientificName || (report.species !== "unknown" ? report.species : report.possibleSpecies);
  const info = infoFor(name);
  if (!info) return null;
  const closest = !report.verifiedSpecies && report.species === "unknown";
  return <article className="pg-card species-about" aria-label="About this species">
    <h2 className="text-[18px] font-semibold text-[#0d2618]">{closest ? "About the closest match: " : "About "}<i>{name}</i></h2>
    {(info.commonNames?.length || info.family) && <p className="mt-1 text-[12px] text-[#5f6b62]">{[info.commonNames?.join(" · "), info.family, info.nativeRange && `native to ${info.nativeRange}`].filter(Boolean).join(" · ")}</p>}
    {info.statusText && <p className={`mt-3 rounded-xl p-3 text-[12px] font-medium leading-5 ${info.ecologicalStatus === "target_invasive" ? "bg-[#fdecec] text-[#8a2424]" : "bg-[#e9f1f8] text-[#24496e]"}`}>{info.statusText}.</p>}
    {info.description && <p className="mt-3 text-[14px] leading-7 text-[#33433a]">{info.description}</p>}
    {info.features?.length ? <><h3>How to recognise it</h3><ul className="species-list">{info.features.map(feature => <li key={feature}>{feature}</li>)}</ul></> : info.appearance ? <><h3>How to recognise it</h3><p>{info.appearance}</p></> : null}
    {info.impact && <><h3>Why it matters</h3><p>{info.impact}</p></>}
    {!!info.lookalikes?.length && <><h3>Easily confused with</h3><ul className="species-list">{info.lookalikes.map(other => <li key={other.name}><i>{other.name}</i>: {other.howToTell}</li>)}</ul></>}
    {!!info.references?.length && <><h3>References</h3><ul className="species-list species-refs">{info.source?.url && <li><a href={info.source.url} target="_blank" rel="noopener noreferrer">{info.source.label}</a></li>}{info.references.filter(ref => !info.source?.url || !ref.includes(info.source.url)).map(ref => <li key={ref}>{ref}</li>)}</ul></>}
  </article>;
}
