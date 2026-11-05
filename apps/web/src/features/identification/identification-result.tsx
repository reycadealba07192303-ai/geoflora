"use client";
import { ArrowLeft, BookOpen, CheckCircle2, Leaf, ShieldCheck, TriangleAlert } from "lucide-react";
import { useEffect, useState } from "react";
import AiSuggestion from "./ai-suggestion";
import type { IdentificationResult } from "./identification-view";
import type { PhotoExif } from "./photo-exif";
import QuickReport from "./quick-report";
import { speciesInformation } from "./species-information";

// One screen, like the ML lab demo: the result (target invasive / not a target / not sure), the model's top scores, the
// species description, and the sighting report.
export default function IdentificationResultScreen({ result, file, preview, exif, onAnother, onViewReport }: {
  result: IdentificationResult; file: File; preview: string; exif: PhotoExif; onAnother: () => void; onViewReport: (id: string) => void;
}) {
  // Start the result at the top: the identify page may have been scrolled down to the Identify button.
  useEffect(() => { window.scrollTo({ top: 0 }); }, [result]);
  const [disagrees, setDisagrees] = useState(false);
  const [description, setDescription] = useState("");
  const [suggestedName, setSuggestedName] = useState("");
  const reference = result.method === "verified_reference";
  const cnnClass = result.status === "identified" && result.species ? result.species : null;
  const known = !!cnnClass && !disagrees;
  const target = known && cnnClass!.role !== "lookalike";
  const closest = result.candidates[0]?.species ?? null;
  const shown = known ? cnnClass! : disagrees ? null : closest;
  const info = known ? result.information : shown ? speciesInformation[shown.id] ?? null : null;
  const name = (s: { common_name?: string; scientific_name: string }) => s.common_name || s.scientific_name;
  const threshold = Math.round(result.confidence_threshold * 100);

  return <section className="id-result pg">
    <header className="pg-head">
      <div>
        <span className="content-eyebrow">Your result</span>
        <h1>{known ? <>It looks like <span className="lp-photo-text">{name(cnnClass!)}.</span></> : <>Not sure <span className="lp-photo-text">yet.</span></>}</h1>
      </div>
      <div className="pg-actions"><button className="content-secondary-button !mt-0" onClick={onAnother}><ArrowLeft size={15} />Identify another plant</button></div>
    </header>

    <div className="grid items-start gap-3 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
      <figure className="id-result-photo lg:sticky lg:top-24">
        <img src={preview} alt="Plant you uploaded for identification" />
        <figcaption><Leaf size={13} />{known ? name(cnnClass!) : "Needs checking"}</figcaption>
      </figure>

      <div className="grid gap-3">
        <article className={`id-verdict ${target ? "is-target" : known ? "is-other" : "is-unsure"}`} aria-live="polite">
          {known ? <>
            <p className="id-verdict-label"><CheckCircle2 size={16} />{reference ? "Matches a verified reference photo" : "The model is sure"}</p>
            <h2>{name(cnnClass!)} <i>{cnnClass!.scientific_name}</i></h2>
            <span className={`id-status-pill ${target ? "is-target" : "is-other"}`}>{target ? "Target invasive species" : "Not a target species"}</span>
            <p className="mt-3">{target ? "This is one of GeoFlora's target invasive species" : "This is not one of GeoFlora's target invasive species"}{target && info?.ecologicalStatus === "target_invasive" ? ", listed in DENR-BMB's NISSAP 2020-2030." : !target && info?.ecologicalStatus === "unresolved" ? ". Its ecological status in the Philippines is still unresolved." : "."}</p>
          </> : <>
            <p className="id-verdict-label"><TriangleAlert size={16} />{disagrees ? "You said this is not a match" : "The model is not sure"}</p>
            <h2>{shown ? <>Possibly {name(shown)} <i>{shown.scientific_name}</i></> : "Unknown plant"}</h2>
            <p className="mt-3">{disagrees ? "The report will be saved as \u201cNot sure\u201d. Add what you know below if you like." : "This may be a plant the model was not trained on. You can still save it; it will be recorded as \u201cNot sure\u201d."}</p>
          </>}
          {cnnClass && result.method === "model" && <button type="button" className="id-verdict-link" onClick={() => setDisagrees(!disagrees)}>{disagrees ? "Undo: keep the AI result" : "This doesn\u2019t match my plant"}</button>}
        </article>

        {!reference && result.candidates.length > 0 && <article className="id-card">
          <h2 className="id-card-title">Model scores (0-100)</h2>
          <ul className="identify-candidates mt-2">{result.candidates.map(candidate => <li key={candidate.species.id}><div><span>{name(candidate.species)} <i className="text-[#5f6b62]">{candidate.species.scientific_name}</i></span><strong>{(candidate.confidence * 100).toFixed(1)}</strong></div><div className="candidate-track" aria-hidden="true"><span style={{ width: `${candidate.confidence * 100}%` }} /></div></li>)}</ul>
          <p className="mt-2 text-[11px] leading-5 text-[#5f6b62]">The model counts as sure from {threshold}. Scores are model outputs, not the chance that the answer is right, and the model only knows a limited set of species.</p>
        </article>}

        {/* When GeoFlora's own model is not sure, a general AI vision model gives a second opinion (saved with the report). */}
        {!known && !reference && !disagrees && <AiSuggestion file={file} description={description} usedName={suggestedName} onUseName={setSuggestedName} onDraft={setDescription} />}

        <details className="id-card id-optional" open={disagrees}>
          <summary>Add your own description or species name <span>(optional)</span></summary>
          <label className="admin-field mt-3">What does the plant look like?<textarea rows={3} maxLength={2000} className="admin-input" value={description} onChange={e => setDescription(e.target.value)} placeholder="Leaf shape, colours, flowers, size, where it grows" /></label>
          <label className="admin-field mt-3">Species name, if you know it<input maxLength={120} className="admin-input" value={suggestedName} onChange={e => setSuggestedName(e.target.value)} /></label>
        </details>

        <QuickReport file={file} exif={exif} species={known ? cnnClass!.scientific_name : suggestedName.trim() || "unknown"} identificationId={result.identification_id} disagrees={disagrees} description={description} suggestedName={suggestedName} onViewReport={onViewReport} onAnother={onAnother} />

        {info && (info.description || info.features?.length) && <article className="id-card species-about">
          <h2 className="text-[18px] font-semibold text-[#0d2618]">{known ? "About " : "About the closest match: "}<i>{shown ? shown.scientific_name : ""}</i>{info.reviewStatus && info.reviewStatus !== "reviewed" && <span className="species-draft">Draft, not yet verified</span>}</h2>
          {(info.commonNames?.length || info.family) && <p className="mt-1 text-[12px] text-[#5f6b62]">{[info.commonNames?.join(" · "), info.family, info.nativeRange && `native to ${info.nativeRange}`].filter(Boolean).join(" · ")}</p>}
          {info.description && <p className="mt-3 text-[14px] leading-7 text-[#33433a]">{info.description}</p>}
          {info.features?.length ? <><h3>How to recognise it</h3><ul className="species-list">{info.features.map(feature => <li key={feature}>{feature}</li>)}</ul></> : info.appearance ? <><h3>How to recognise it</h3><p>{info.appearance}</p></> : null}
          {info.impact && <><h3>Why it matters</h3><p>{info.impact}</p></>}
          {!!info.lookalikes?.length && <><h3>Easily confused with</h3><ul className="species-list">{info.lookalikes.map(other => <li key={other.name}><i>{other.name}</i>: {other.howToTell}</li>)}</ul></>}
          <h3 className="flex items-center gap-1.5"><BookOpen size={13} />References</h3>
          <ul className="species-list species-refs">{info.source?.url && <li><a href={info.source.url} target="_blank" rel="noopener noreferrer">{info.source.label}</a></li>}{(info.references ?? []).filter(ref => !info.source?.url || !ref.includes(info.source.url)).map(ref => <li key={ref}>{ref}</li>)}</ul>
        </article>}

        {reference && <p className="flex items-start gap-2 px-2 text-[12px] leading-6 text-[#5f6b62]"><ShieldCheck size={15} className="mt-1 shrink-0" />This exact photo matches an administrator-verified reference photo.</p>}
      </div>
    </div>
  </section>;
}
