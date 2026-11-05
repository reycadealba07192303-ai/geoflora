"use client";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { CheckCircle2, FilePlus2, FileText, MapPin, LocateFixed, CalendarClock, ArrowLeft } from "lucide-react";
import type { ReportHandoff } from "../identification/identification-view";
import LocationPicker from "./location-picker";

function localTime(value = new Date().toISOString()) { const date = new Date(value); return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 19); }
export default function ReportForm({ handoff, onViewReport, onAnother }: { handoff: ReportHandoff; onViewReport: (id: string) => void; onAnother: () => void }) {
  const file = handoff.file, [preview, setPreview] = useState("");
  const [latitude, setLatitude] = useState(handoff.latitude ?? ""), [longitude, setLongitude] = useState(handoff.longitude ?? "");
  const [method, setMethod] = useState<"gps" | "manual" | "map_pin">(handoff.locationMethod ?? "manual"), [accuracy, setAccuracy] = useState<number | null>(handoff.accuracy ?? null);
  const [observedAt, setObservedAt] = useState(() => localTime(handoff.observedAt));
  const [description, setDescription] = useState(handoff.plantDescription ?? ""), [suggestion, setSuggestion] = useState(handoff.suggestedSpecies ?? "");
  const [busy, setBusy] = useState(false), [locating, setLocating] = useState(false), [error, setError] = useState("");
  const [savedId, setSavedId] = useState(""), [pending, setPending] = useState(false);
  const requestId = useRef<string | null>(null);
  const known = handoff.species !== "unknown";
  useEffect(() => { const url = URL.createObjectURL(file); setPreview(url); return () => URL.revokeObjectURL(url); }, [file]);
  function gps() {
    requestId.current = null;
    if (!navigator.geolocation) { setError("Location is unavailable. Enter coordinates below."); return; }
    setLocating(true); setError("");
    navigator.geolocation.getCurrentPosition(position => { setLatitude(String(position.coords.latitude)); setLongitude(String(position.coords.longitude)); setAccuracy(position.coords.accuracy); setMethod("gps"); setLocating(false); }, () => { setLocating(false); setError("Location access is unavailable. Enter where the plant was found manually."); }, { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 });
  }
  useEffect(() => {
    if (handoff.latitude || !navigator.permissions) return;
    let cancelled = false;
    navigator.permissions.query({ name: "geolocation" }).then(permission => { if (!cancelled && permission.state === "granted") gps(); }).catch(() => {});
    return () => { cancelled = true; };
  }, [handoff.latitude]);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (busy || locating) return;
    setBusy(true); setError(""); requestId.current ??= crypto.randomUUID();
    const data = new FormData(event.currentTarget);
    data.set("image", file); data.set("requestId", requestId.current); data.set("latitude", latitude); data.set("longitude", longitude); data.set("locationMethod", method); data.set("observedAt", new Date(observedAt).toISOString()); data.set("plantDescription", description); data.set("suggestedSpecies", suggestion); data.set("species", known ? handoff.species : suggestion.trim() || "unknown");
    if (accuracy !== null) data.set("accuracy", String(accuracy));
    if (handoff.identificationId) data.set("identificationId", handoff.identificationId);
    if (handoff.identificationDisagrees) data.set("identificationDisagrees", "yes");
    try { const response = await fetch("/api/sightings", { method: "POST", body: data }); const result = await response.json(); if (!response.ok) throw Error(result.detail); setSavedId(result.id); setPending(!known || handoff.cnnSuggestionOnly === true || handoff.identificationDisagrees === true); }
    catch (e) { setError(e instanceof Error ? e.message : "The report could not be saved. Please retry."); } finally { setBusy(false); }
  }
  if (savedId) return <section className="pg">
    <div className="pg-ink mx-auto w-full max-w-3xl text-center sm:!p-12">
      <span className="mx-auto grid h-14 w-14 place-items-center rounded-full bg-[#c6dcae] text-[#0d2618]"><CheckCircle2 size={26} /></span>
      <p className="mt-6 text-[11px] font-semibold uppercase tracking-[0.18em] text-[#c6dcae]">Report saved</p>
      <h1 className="lp-display mt-3 text-[clamp(36px,4.4vw,60px)] leading-[0.92]">Your sighting<br />is recorded.</h1>
      <p className="mx-auto mt-5 max-w-md text-[14px] leading-7 text-white/75">{pending ? "Your photo and description have been sent for administrator review. You can view the report now and return for the verified label." : "Your photo, species information, location, date and time have been saved."}</p>
      <div className="mt-7 flex flex-wrap justify-center gap-2.5"><button className="lp-pill lp-pill-lime lp-pill-lg" onClick={() => onViewReport(savedId)}><FileText size={17} />View result report</button><button className="lp-pill lp-pill-ghost lp-pill-lg" onClick={onAnother}><FilePlus2 size={17} />Create another report</button></div>
      <p className="mt-6 break-all text-[11px] text-white/50">Reference: {savedId}</p>
    </div>
  </section>;
  return <section className="pg">
    <header className="pg-head"><div><span className="content-eyebrow">Step 3 · Field report</span><h1>Create a field <span className="lp-photo-text">report</span></h1><p>{handoff.cnnSuggestionOnly ? "Your photo and tentative CNN suggestion will remain pending until reviewed." : known ? "Confirm where and when the plant was found, then save your report." : "Describe the plant so an administrator can check the photo and confirm its species."}</p></div></header>
    <form onSubmit={submit} onChange={() => { requestId.current = null; }}><fieldset disabled={busy} className="grid items-start gap-3 lg:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)]">
      <aside className="pg-ink lg:sticky lg:top-24">
        {preview && <img src={preview} alt="Plant for this report" className="h-[clamp(220px,38svh,360px)] w-full rounded-[20px] bg-black/20 object-contain" />}
        <p className="mt-5 text-[11px] font-semibold uppercase tracking-[0.18em] text-[#c6dcae]">{handoff.cnnSuggestionOnly ? "Tentative CNN suggestion · pending review" : known ? "Administrator-verified species" : "Awaiting identification"}</p>
        <h2 className="mt-2 text-[24px] font-semibold italic leading-tight">{known ? handoff.species : suggestion.trim() || "Plant awaiting identification"}</h2>
        {handoff.cnnSuggestionOnly && <p className="mt-2 rounded-xl bg-white/10 p-3 text-[12px] leading-5 text-white/80">This is the model&apos;s tentative class suggestion, not a verified identification.</p>}
        {known && handoff.information?.description && <p className="mt-3 text-[13px] leading-6 text-white/75">{handoff.cnnSuggestionOnly ? `About the suggested species, not established facts about your photo: ${handoff.information.description}` : handoff.information.description}</p>}
        {!handoff.cnnSuggestionOnly && handoff.information?.source?.url && <a className="mt-3 block break-all text-[12px] text-[#c6dcae] underline underline-offset-4" href={handoff.information.source.url} target="_blank" rel="noopener noreferrer">{handoff.information.source.label}</a>}
        <button type="button" onClick={onAnother} className="mt-5 inline-flex items-center gap-2 rounded-full bg-white px-4 py-2 text-[12px] font-semibold text-[#0d2618] transition hover:bg-[#c6dcae]"><ArrowLeft size={14} />Choose another plant</button>
      </aside>

      <div className="grid gap-3">
        <article className="pg-card space-y-4"><h2 className="pg-card-title"><span className="pg-num">01</span>{known ? "Your observations" : "Help identify this plant"}</h2>
          {(handoff.cnnSuggestionOnly || !known) && <label className="admin-field">What does the photo show? {!known && "(required)"}<textarea name="plantDescription" required={!known} maxLength={2000} rows={3} value={description} onChange={e => setDescription(e.target.value)} className="admin-input" placeholder="Describe its leaves, colours, flowers, size and habitat" /></label>}
          {!known && <label className="admin-field">Suggested name (optional)<input name="suggestedSpecies" maxLength={120} className="admin-input" value={suggestion} onChange={e => setSuggestion(e.target.value)} /></label>}
        </article>

        <article className="pg-card space-y-4"><div className="flex flex-wrap items-center justify-between gap-3"><h2 className="pg-card-title"><span className="pg-num">02</span><MapPin size={17} />Where it was found</h2><button className="admin-btn is-small" type="button" disabled={locating} onClick={gps}><LocateFixed size={15} />{locating ? "Getting location..." : "Use my location"}</button></div>
          <p className="pg-hint">{method === "gps" ? `Location captured automatically${accuracy !== null ? ` (estimated accuracy +/-${Math.round(accuracy)} m)` : ""}. Check that this is where the plant was found.` : method === "map_pin" ? "Location chosen on the map. Drag the pin to adjust it." : "Use your location, tap the map to drop a pin, or type the coordinates."}</p>
          <LocationPicker latitude={latitude} longitude={longitude} onPick={(lat, lng) => { setLatitude(String(lat)); setLongitude(String(lng)); setMethod("map_pin"); setAccuracy(null); requestId.current = null; }} />
          <div className="grid gap-3 sm:grid-cols-2"><label className="admin-field">Latitude<input name="latitude" type="number" min="-90" max="90" step="any" required className="admin-input" value={latitude} onChange={e => { setLatitude(e.target.value); setMethod("manual"); setAccuracy(null); }} /></label><label className="admin-field">Longitude<input name="longitude" type="number" min="-180" max="180" step="any" required className="admin-input" value={longitude} onChange={e => { setLongitude(e.target.value); setMethod("manual"); setAccuracy(null); }} /></label></div>
          <label className="admin-field">Place or landmark (optional)<input name="placeName" maxLength={200} className="admin-input" placeholder="Barangay, municipality or landmark" /></label>
          <p className="pg-hint">The map needs an internet connection for its background. Coordinates can always be typed.</p>
        </article>

        <article className="pg-card space-y-4"><h2 className="pg-card-title"><span className="pg-num">03</span><CalendarClock size={17} />Date and time</h2>
          <div className="grid gap-3 sm:grid-cols-2"><label className="admin-field">When the plant was observed<input name="localTime" type="datetime-local" step="1" required value={observedAt} onChange={e => setObservedAt(e.target.value)} className="admin-input" /><small>Filled from your device time. Change it if the photo was taken earlier.</small></label>
            <label className="admin-field">Additional notes (optional)<textarea name="notes" maxLength={2000} rows={2} className="admin-input !min-h-[42px]" /></label></div>
        </article>

        <article className="pg-card space-y-3"><h2 className="pg-card-title"><span className="pg-num">04</span>Confirm and submit</h2>
          <label className="admin-check"><input type="checkbox" name="consent" value="yes" required /><span>I confirm submission of this photo and its location for the report.</span></label>
          <label className="admin-check"><input type="checkbox" name="referenceConsent" value="yes" /><span>I allow this photo to be considered as a visual reference after a human verifies its species and an administrator checks its quality and provenance. Optional; separate from training consent.</span></label>
          <label className="admin-check"><input type="checkbox" name="trainingConsent" value="yes" /><span>I allow the photo to be used for future training after the species label is reviewed. Optional.</span></label>
          {error && <p role="alert" className="content-notice is-error !mt-0">{error}</p>}
          <button className="content-primary-button justify-center" disabled={busy || locating} type="submit">{busy ? "Saving your report..." : "Submit plant report"}</button>
        </article>
      </div>
    </fieldset></form>
  </section>;
}
