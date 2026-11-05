"use client";
import { useEffect, useRef, useState } from "react";
import { CalendarClock, CheckCircle2, FilePlus2, FileText, LoaderCircle, LocateFixed, MapPin } from "lucide-react";
import LocationPicker from "../sightings/location-picker";
import type { PhotoExif } from "./photo-exif";

type Method = "gps" | "manual" | "map_pin" | "photo_gps";
const SOURCE: Record<Method, string> = { photo_gps: "the GPS saved in the photo", gps: "your device location", map_pin: "the pin on the map", manual: "the typed coordinates" };

function nowLocal() { const d = new Date(); return new Date(d.getTime() - d.getTimezoneOffset() * 60_000).toISOString().slice(0, 19); }

// Saves the identified photo as a sighting report from the result screen: date, time and location are filled from the
// photo when the camera recorded them, otherwise from the device. Only the location has to be confirmed.
export default function QuickReport({ file, exif, species, identificationId, disagrees, description, suggestedName, onViewReport, onAnother }: {
  file: File; exif: PhotoExif; species: string; identificationId?: string; disagrees: boolean; description: string; suggestedName: string;
  onViewReport: (id: string) => void; onAnother: () => void;
}) {
  const fromPhoto = exif.latitude !== undefined && exif.longitude !== undefined;
  const [latitude, setLatitude] = useState(fromPhoto ? String(exif.latitude) : "");
  const [longitude, setLongitude] = useState(fromPhoto ? String(exif.longitude) : "");
  const [method, setMethod] = useState<Method>(fromPhoto ? "photo_gps" : "manual");
  const [accuracy, setAccuracy] = useState<number | null>(null);
  const [observedAt, setObservedAt] = useState(exif.takenAt ?? nowLocal());
  const [placeName, setPlaceName] = useState(""), [notes, setNotes] = useState("");
  // Training use is on by default (owner decision 2026-11-05); the contributor can turn it off below.
  const [trainingConsent, setTrainingConsent] = useState(true), [referenceConsent, setReferenceConsent] = useState(false);
  const [locating, setLocating] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState("");
  const [savedId, setSavedId] = useState("");
  const requestId = useRef<string | null>(null);

  function useDevice() {
    if (!navigator.geolocation) { setError("This browser cannot share its location. Tap the map or type the coordinates."); return; }
    setLocating(true); setError("");
    navigator.geolocation.getCurrentPosition(
      position => { setLatitude(String(position.coords.latitude)); setLongitude(String(position.coords.longitude)); setAccuracy(position.coords.accuracy); setMethod("gps"); setLocating(false); },
      () => { setLocating(false); setError("Location access is off. Tap the map to drop a pin, or type the coordinates."); },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 },
    );
  }
  // Without photo GPS, use the device location straight away when the browser already allows it (no prompt).
  useEffect(() => {
    if (fromPhoto || !navigator.permissions) return;
    let cancelled = false;
    navigator.permissions.query({ name: "geolocation" }).then(permission => { if (!cancelled && permission.state === "granted") useDevice(); }).catch(() => {});
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  // Any change to the details is a new submission.
  useEffect(() => { requestId.current = null; }, [latitude, longitude, observedAt, placeName, notes, trainingConsent, referenceConsent, description, suggestedName, disagrees]);

  async function save() {
    if (busy || locating) return;
    if (!latitude || !longitude) { setError("Add where the plant was found: use your location, tap the map, or type the coordinates."); return; }
    setBusy(true); setError(""); requestId.current ??= crypto.randomUUID();
    const data = new FormData();
    data.set("image", file); data.set("requestId", requestId.current); data.set("species", species);
    data.set("latitude", latitude); data.set("longitude", longitude); data.set("locationMethod", method);
    if (accuracy !== null && method === "gps") data.set("accuracy", String(accuracy));
    data.set("observedAt", new Date(observedAt).toISOString());
    data.set("placeName", placeName.trim()); data.set("notes", notes.trim());
    data.set("plantDescription", description.trim()); data.set("suggestedSpecies", suggestedName.trim());
    data.set("consent", "yes");
    if (trainingConsent) data.set("trainingConsent", "yes");
    if (referenceConsent) data.set("referenceConsent", "yes");
    if (identificationId) data.set("identificationId", identificationId);
    if (disagrees) data.set("identificationDisagrees", "yes");
    try {
      const response = await fetch("/api/sightings", { method: "POST", body: data });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw Error(body.detail || "The report could not be saved. Please retry.");
      setSavedId(body.id);
    } catch (e) { setError(e instanceof Error ? e.message : "The report could not be saved. Please retry."); }
    finally { setBusy(false); }
  }

  if (savedId) return <article className="id-card quick-report is-saved" aria-live="polite">
    <h2 className="flex items-center gap-2 text-[18px] font-semibold text-[#0d2618]"><CheckCircle2 size={20} className="text-[var(--green)]" />Report saved</h2>
    <p className="mt-2 text-[14px] leading-6 text-[#33433a]">Your photo, the AI result, location, date and time are saved. It is now on the map.</p>
    <div className="mt-4 flex flex-wrap gap-2"><button type="button" className="admin-btn" onClick={() => onViewReport(savedId)}><FileText size={15} />View report</button><button type="button" className="admin-btn" onClick={onAnother}><FilePlus2 size={15} />Identify another plant</button></div>
  </article>;

  return <article className="id-card quick-report" aria-label="Save as a sighting report">
    <h2 className="text-[18px] font-semibold text-[#0d2618]">Save as a sighting report</h2>

    <label className="admin-field mt-4"><span className="flex items-center gap-1.5"><CalendarClock size={14} />Date and time seen</span>
      <input type="datetime-local" step="1" required className="admin-input" value={observedAt} onChange={e => setObservedAt(e.target.value)} max={nowLocal()} />
      <small>{exif.takenAt ? "From the photo (camera date and time)." : "No date in the photo, so this is now. Change it if needed."}</small>
    </label>

    <div className="mt-4">
      <div className="flex flex-wrap items-center justify-between gap-2"><span className="flex items-center gap-1.5 text-[13px] font-semibold text-[#33433a]"><MapPin size={14} />Where was it found?</span>
        <button className="admin-btn is-small" type="button" disabled={locating} onClick={useDevice}><LocateFixed size={14} />{locating ? "Getting location..." : "Use my location"}</button></div>
      <p className="pg-hint mt-1">{latitude && longitude ? `Location from ${SOURCE[method]}${method === "gps" && accuracy !== null ? ` (about ±${Math.round(accuracy)} m)` : ""}. Tap the map to move it.` : "Use your location, or tap the map to drop a pin."}</p>
      <div className="mt-2"><LocationPicker latitude={latitude} longitude={longitude} onPick={(lat, lng) => { setLatitude(String(lat)); setLongitude(String(lng)); setMethod("map_pin"); setAccuracy(null); }} /></div>
      <details className="mt-2 text-[12px] text-[#5f6b62]"><summary className="cursor-pointer">Type coordinates instead</summary>
        <div className="mt-2 grid gap-2 sm:grid-cols-2"><label className="admin-field">Latitude<input type="number" min="-90" max="90" step="any" className="admin-input" value={latitude} onChange={e => { setLatitude(e.target.value); setMethod("manual"); setAccuracy(null); }} /></label>
          <label className="admin-field">Longitude<input type="number" min="-180" max="180" step="any" className="admin-input" value={longitude} onChange={e => { setLongitude(e.target.value); setMethod("manual"); setAccuracy(null); }} /></label></div>
      </details>
    </div>

    <div className="mt-4 grid gap-3 sm:grid-cols-2">
      <label className="admin-field">Place name (optional)<input maxLength={200} className="admin-input" value={placeName} onChange={e => setPlaceName(e.target.value)} placeholder="Barangay, town, province" /></label>
      <label className="admin-field">Notes (optional)<input maxLength={2000} className="admin-input" value={notes} onChange={e => setNotes(e.target.value)} placeholder="e.g. many plants along the creek" /></label>
    </div>

    <details className="mt-3 text-[12px] text-[#5f6b62]"><summary className="cursor-pointer">Photo use: {trainingConsent ? "helps train GeoFlora" : "report only"}{referenceConsent ? ", reference photo" : ""}</summary>
      <label className="admin-check mt-2"><input type="checkbox" checked={referenceConsent} onChange={e => setReferenceConsent(e.target.checked)} /><span>Use it as a reference photo for this species.</span></label>
      <label className="admin-check"><input type="checkbox" checked={trainingConsent} onChange={e => setTrainingConsent(e.target.checked)} /><span>Use it to train future GeoFlora models.</span></label>
    </details>

    {error && <p role="alert" className="content-notice is-error mt-3">{error}</p>}
    <button type="button" className="content-primary-button mt-4 w-full justify-center" disabled={busy || locating} onClick={save}>{busy ? <LoaderCircle size={18} className="animate-spin" /> : <FileText size={18} />}{busy ? "Saving..." : "Save report"}</button>
    <p className="mt-2 text-[11px] leading-5 text-[#5f6b62]">Saving submits this photo with the AI result, its location, date and time.</p>
  </article>;
}
