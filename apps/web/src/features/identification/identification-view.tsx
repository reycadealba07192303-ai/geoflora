"use client";

import { useEffect, useRef, useState, type ChangeEvent, type DragEvent } from "react";
import { AlertCircle, ArrowRight, Camera, CheckCircle2, Focus, ImagePlus, Leaf, LoaderCircle, ScanLine, ShieldCheck, Sun, Upload, X } from "lucide-react";
import IdentificationResultScreen from "./identification-result";
import { shrinkPhoto } from "./shrink-photo";
import { readPhotoExif, type PhotoExif } from "./photo-exif";
import type { SpeciesInformation } from "./species-information";

const MAX_UPLOAD_BYTES = 20 * 1024 * 1024;
const SUPPORTED_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);
// Slightly longer than the server-side inference timeout so the server's message arrives first.
const CLIENT_TIMEOUT_MS = 75_000;

interface ModelHealth {
  ready: boolean;
  model_version?: string | null;
  reason?: string | null;
  species?: Species[];
}

interface Species {
  id: string;
  scientific_name: string;
  common_name: string;
  // "lookalike" for non-invasive plants the model learned so it can tell them apart from the invasive ones.
  role?: string;
}

interface Candidate {
  species: Species;
  confidence: number;
}

export interface IdentificationResult {
  status: "identified" | "uncertain";
  species: Species | null;
  confidence: number | null;
  identification_id?: string;
  method?: "model" | "verified_reference" | "visual_similarity";
  similaritySuggestions?: { species: { id: string; scientific_name: string; common_name: string }; similarity: number; score_type: string; reference_count: number; botanical_citation: string; ecological_status: string; ecological_citation: string; provenance?: { source?: string; observation_id?: string } }[];
  similarityNote?: string;
  cnnPrediction?: { status: string; species?: { scientific_name?: string } | null; confidence?: number; confidence_threshold?: number; model_version?: string };
  referenceSource?: { type: string; botanicalCitation?: string; ecologicalStatus?: string; ecologicalCitation?: string; sourceObservationId?: string };
  information?: (Partial<SpeciesInformation> & { description: string; source: { label: string; url: string } }) | null;
  confidence_threshold: number;
  candidates: Candidate[];
  model_version: string;
}

// Data handed off to the report step (step 3 of identification)
export interface ReportHandoff {
  identificationId?: string;
  identificationDisagrees?: boolean;
  cnnSuggestionOnly?: boolean;
  observedAt?: string;
  information?: IdentificationResult["information"];
  plantDescription?: string;
  suggestedSpecies?: string;
  file: File;
  species: string;
  latitude: string;
  longitude: string;
  locationMethod: "gps" | "manual";
  accuracy: number | null;
}

function validateImage(file: File): string | null {
  if (!SUPPORTED_TYPES.has(file.type)) return "Choose a JPEG, PNG, or WebP image.";
  if (file.size > MAX_UPLOAD_BYTES) return "Image must be 20 MB or smaller.";
  return null;
}

export default function IdentificationView({
  onViewReport,
}: {
  onViewReport: (id: string) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const cameraRef = useRef<HTMLInputElement>(null);
  const [health, setHealth] = useState<ModelHealth | null>(null);
  const [healthLoading, setHealthLoading] = useState(true);
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<IdentificationResult | null>(null);
  // Camera date/time and GPS, read from the original photo before it is shrunk.
  const [exif, setExif] = useState<PhotoExif>({});
  const [isDragging, setIsDragging] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/identify", { cache: "no-store", signal: controller.signal })
      .then(async (response) => {
        const body = (await response.json()) as ModelHealth;
        setHealth(body);
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setHealth({
            ready: false,
            reason: "The local ML inference service is not reachable.",
          });
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setHealthLoading(false);
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!file) {
      setPreviewUrl(null);
      return;
    }
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  async function selectFile(chosen: File | undefined) {
    if (!chosen) return;
    const [selected, metadata] = SUPPORTED_TYPES.has(chosen.type) ? await Promise.all([shrinkPhoto(chosen), readPhotoExif(chosen)]) : [chosen, {}];
    const validationError = validateImage(selected);
    setResult(null);
    setExif(metadata);
    if (validationError) {
      setFile(null);
      setError(validationError);
      return;
    }
    setError(null);
    setFile(selected);
  }

  function onFileChange(event: ChangeEvent<HTMLInputElement>) {
    selectFile(event.currentTarget.files?.[0]);
    event.currentTarget.value = "";
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setIsDragging(false);
    if (isSubmitting) return;
    selectFile(event.dataTransfer.files[0]);
  }

  async function identifyPlant() {
    if (!file) return;
    setError(null);
    setResult(null);
    setIsSubmitting(true);
    try {
      const body = new FormData();
      body.set("image", file);
      const response = await fetch("/api/identify", {
        method: "POST",
        body,
        signal: AbortSignal.timeout(CLIENT_TIMEOUT_MS),
      });
      const payload = (await response.json().catch(() => null)) as IdentificationResult | { detail?: string } | null;
      if (!response.ok || !payload || !("status" in payload)) {
        const detail = payload && "detail" in payload && typeof payload.detail === "string" ? payload.detail : null;
        throw new Error(
          detail ?? (response.status === 413 ? "Image must be 20 MB or smaller." : "Identification failed. No prediction was made."),
        );
      }
      setResult(payload);
    } catch (caught) {
      setError(
        caught instanceof DOMException && caught.name === "TimeoutError"
          ? "Identification took too long. No prediction was made; please try again."
          : caught instanceof TypeError
            ? "Couldn't reach GeoFlora. Check your connection and try again."
            : caught instanceof Error
              ? caught.message
              : "Identification failed. No prediction was made.",
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  const modelAvailable = health?.ready === true;
  const targets = (health?.species ?? []).filter(entry => entry.role !== "lookalike");
  const others = (health?.species ?? []).filter(entry => entry.role === "lookalike");

  if (result && file) return <IdentificationResultScreen result={result} file={file} preview={previewUrl ?? ""} exif={exif} onViewReport={onViewReport} onAnother={() => { setResult(null); setFile(null); setExif({}); setError(null); }} />;

  const busy = isSubmitting;
  const steps = [{ name: "Add a photo", complete: !!file, active: !file }, { name: "Identify", complete: false, active: !!file }, { name: "Save a report", complete: false, active: false }];
  return (
    <section className="identify-page pg">
      <header className="pg-head">
        <div>
          <span className="content-eyebrow"><ScanLine size={13} />Identify a plant</span>
          <h1>What&apos;s growing <span className="lp-photo-text">here?</span></h1>
          <p>Start with a clear photo. Get a possible match, learn about the plant, and record where you found it.</p>
        </div>
        <div className="pg-actions">
          <span className={`identify-status ${modelAvailable ? "is-ready" : "is-waiting"}`}>
            {healthLoading ? <LoaderCircle size={13} className="animate-spin" /> : modelAvailable ? <CheckCircle2 size={13} /> : <AlertCircle size={13} />}
            {healthLoading ? "Checking" : modelAvailable ? "Model ready" : "Unavailable"}
          </span>
          <span className="id-chip">Experimental model{health?.model_version ? ` · ${health.model_version}` : ""}</span>
        </div>
      </header>
      <span className="sr-only" role="status" aria-live="polite">{isSubmitting ? "Analyzing your photo" : file ? "Photo ready to identify" : "Waiting for a photo"}</span>

      <div className={`identify-grid ${isDragging ? "is-dragging" : ""}`}
        onDragEnter={event => { event.preventDefault(); if (!busy) setIsDragging(true); }}
        onDragOver={event => event.preventDefault()}
        onDragLeave={event => { if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setIsDragging(false); }}
        onDrop={onDrop}>
        <div className="id-stage">
          <ol className="id-steps" aria-label="Identification workflow">
            {steps.map((step, i) => <li key={step.name} className={step.complete ? "is-complete" : step.active ? "is-current" : ""} aria-current={step.active ? "step" : undefined}><span>{step.complete ? <CheckCircle2 size={14} /> : `0${i + 1}`}</span>{step.name}</li>)}
          </ol>
          <input accept="image/jpeg,image/png,image/webp" aria-label="Choose a plant photo" className="sr-only" onChange={onFileChange} disabled={busy} ref={inputRef} type="file" />
          {/* On phones this opens the rear camera; desktops fall back to the file chooser. */}
          <input accept="image/jpeg,image/png,image/webp" aria-label="Take a plant photo" capture="environment" className="sr-only" onChange={onFileChange} disabled={busy} ref={cameraRef} type="file" />
          {previewUrl ? <div className={`identify-preview ${isSubmitting ? "is-analyzing" : ""}`}>
            <img alt="Selected plant for identification" src={previewUrl} />
            <div className="id-scan" aria-hidden="true"><i /><i /><i /><i /></div>
            {isSubmitting && <span className="id-scan-label"><ScanLine size={14} />Taking a closer look…</span>}
            <button aria-label="Remove selected photo" className="id-remove" disabled={busy} onClick={() => { setFile(null); setError(null); setResult(null); setExif({}); }} type="button"><X size={17} /></button>
            <div className="id-preview-bar"><span title={file?.name}>{file?.name}</span><span className="identify-preview-actions"><button disabled={busy} onClick={() => cameraRef.current?.click()} type="button"><Camera size={14} />Retake</button><button disabled={busy} onClick={() => inputRef.current?.click()} type="button"><ImagePlus size={14} />Change photo</button></span></div>
          </div> : <button className="identify-dropzone" onClick={() => inputRef.current?.click()} type="button">
            <span className="id-drop-icon" aria-hidden="true"><Upload size={21} /></span>
            <strong className="lp-display">Drop a photo<br /><span className="text-[#c6dcae]">of the plant</span></strong>
            <span className="dropzone-copy">Drag it here, or choose one from your device.</span>
            <span className="id-drop-button"><ImagePlus size={16} />Choose a photo<ArrowRight size={15} /></span>
            <span className="dropzone-formats">JPG · PNG · WEBP · UP TO 20 MB</span>
          </button>}
          {!healthLoading && !modelAvailable && <div className="content-notice !mt-0" role="status"><AlertCircle size={17} /><span>{health?.reason || "Identification is unavailable right now. Please try again later."}</span></div>}
          {error && <div className="content-notice is-error !mt-0" role="alert"><AlertCircle size={17} /><span>{error}</span></div>}
          <div className={`id-actions ${file ? "" : "has-camera"}`}>
            {!file && <button className="content-secondary-button identify-camera-button" disabled={busy} onClick={() => cameraRef.current?.click()} type="button"><Camera size={16} />Take a photo</button>}
            <button className="content-primary-button identify-submit" disabled={!file || !modelAvailable || isSubmitting} onClick={identifyPlant} type="button">
              {isSubmitting ? <LoaderCircle size={19} className="animate-spin" /> : <ScanLine size={19} />}
              {isSubmitting ? "Taking a closer look..." : "Identify plant"}
              {!isSubmitting && <ArrowRight size={18} className="ml-auto" />}
            </button>
          </div>
          <p className="identify-privacy"><ShieldCheck size={13} />Your photo is only saved when you submit a report.</p>
        </div>

        <aside className="id-side" aria-busy={isSubmitting}>
          <div className="id-card id-guide">
            <h2 className="id-card-title">Photo tips</h2>
            <ul className="id-tips">{tips.map(tip => <li key={tip.text}><span><tip.icon size={16} /></span>{tip.text}</li>)}</ul>
            <div className="id-divider" />
            <div className="flex items-center justify-between gap-2"><h2 className="id-card-title">What the model knows</h2><span className="id-chip !bg-[#eef1ea] !py-1.5">{health?.species?.length ? `${health.species.length} species` : "—"}</span></div>
            {targets.length > 0 && <>
              <p className="mt-3 text-[11px] font-semibold uppercase tracking-[0.12em] text-[#9b2c2c]">Target invasive · {targets.length}</p>
              <ul className="id-scope">{targets.map(entry => <li key={entry.id}>{photos[entry.id] ? <img src={photos[entry.id]} alt="" /> : <span className="id-scope-icon" aria-hidden="true"><Leaf size={16} /></span>}<div><strong>{entry.common_name}</strong><p>{entry.scientific_name}</p></div></li>)}</ul>
            </>}
            {others.length > 0 && <>
              <p className="mt-4 text-[11px] font-semibold uppercase tracking-[0.12em] text-[#2f5d8a]">Also recognised, not targets · {others.length}</p>
              <p className="mt-1.5 text-[12px] leading-5 text-[#5f6b62]">{others.map(entry => entry.common_name).join(" · ")}</p>
            </>}
            <p className="mt-auto pt-4 text-[12px] leading-5 text-[#5f6b62]">Plants outside this list can still get a high score. Model scores aren&apos;t a guarantee of identity.</p>
          </div>
        </aside>
      </div>
    </section>
  );
}

const tips = [
  { icon: Sun, text: "Natural light, no harsh shadows" },
  { icon: Leaf, text: "Leaves and flowers in clear view" },
  { icon: Focus, text: "Sharp focus, one plant per photo" },
];

const photos: Record<string, string> = {
  chromolaena_odorata: "/landing/hagonoy.jpg",
  lantana_camara: "/landing/lantana.jpg",
  pontederia_crassipes: "/landing/hyacinth.jpg",
};
