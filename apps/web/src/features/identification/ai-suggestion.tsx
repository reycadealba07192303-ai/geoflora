"use client";
import { useEffect, useState } from "react";
import { Bot, Check, Info, LoaderCircle, MapPin, ShieldAlert } from "lucide-react";

interface Suggestion { is_plant: boolean; scientific_name: string | null; rank: string; common_names: string[]; confidence: number; identifying_features: string; description: string; look_alikes: string[] }
interface Catalog { recordedInPhilippines: boolean; speciesInCatalog: string[]; tracked: boolean; introducedListings: { name: string; sources: string[] }[] }
interface Answer { suggestion: Suggestion | null; model: string; note: string; catalog: Catalog | null }

// What a broad vision model thinks the plant is, shown when GeoFlora's own classifier is uncertain. Never a verified label.
export default function AiSuggestion({ file, description, onUseName, usedName, onDraft }: { file: File; description: string; onUseName: (name: string) => void; usedName: string; onDraft: (text: string) => void }) {
  const [answer, setAnswer] = useState<Answer | null>(null), [error, setError] = useState(""), [loading, setLoading] = useState(true);
  useEffect(() => {
    const abort = new AbortController();
    const form = new FormData(); form.set("image", file); form.set("description", description);
    setLoading(true); setError("");
    fetch("/api/identify/suggest", { method: "POST", body: form, signal: abort.signal })
      .then(async response => {
        const body = await response.json() as Answer & { detail?: string }; if (!response.ok) throw Error(body.detail); setAnswer(body);
        // Fill an empty description with what the AI sees; the person reviews and edits it before submitting.
        if (body.suggestion?.is_plant && body.suggestion.description?.trim() && !description.trim()) onDraft(body.suggestion.description.trim());
      })
      .catch(e => { if (!abort.signal.aborted) setError(e instanceof Error ? e.message : "The AI suggestion is unavailable right now."); })
      .finally(() => { if (!abort.signal.aborted) setLoading(false); });
    return () => abort.abort();
    // Asked once per photo; later description edits do not re-run it.
  }, [file]);

  const suggestion = answer?.suggestion, catalog = answer?.catalog;
  const name = suggestion?.scientific_name ?? "";
  const label = suggestion?.common_names[0] || name;
  return <article className="id-card" aria-live="polite" aria-label="AI plant suggestion">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <h2 className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.16em] text-[#33433a]"><Bot size={15} />What the AI thinks it is</h2>
      <span className="rounded-full bg-[#fff3df] px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.08em] text-[#7a5414]">Second opinion</span>
    </div>
    {loading && <p className="mt-4 flex items-center gap-2 text-[14px] text-[#5f6b62]"><LoaderCircle size={16} className="animate-spin" />Asking a broader plant identification model…</p>}
    {!loading && error && <p className="mt-4 text-[13px] leading-6 text-[#5f6b62]">{error}</p>}
    {!loading && answer && !suggestion?.is_plant && <p className="mt-4 text-[14px] leading-7">This photo doesn&apos;t look like a plant to the AI. Try a closer photo of the leaves or flowers.</p>}
    {!loading && suggestion?.is_plant && !name && <p className="mt-4 text-[14px] leading-7">The AI could not name this plant from the photo. {suggestion.identifying_features}</p>}
    {!loading && suggestion?.is_plant && name && <>
      <div className="mt-4 flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <p className="lp-display text-[clamp(28px,2.8vw,40px)] leading-[0.95] text-[#0d2618]">{label}</p>
          <p className="mt-1.5 text-[14px] italic text-[#33433a]">{name}{suggestion.rank !== "species" ? ` (${suggestion.rank} only)` : ""}</p>
          {suggestion.common_names.length > 1 && <p className="mt-1 text-[12px] text-[#5f6b62]">Also called {suggestion.common_names.slice(1, 4).join(", ")}</p>}
        </div>
        <span className="lp-display text-[30px] leading-none text-[#9cbf86]">{Math.round(suggestion.confidence * 100)}<small className="text-[14px]">%</small></span>
      </div>
      <p className="mt-3 text-[14px] leading-7 text-[#33433a]">{suggestion.identifying_features}</p>
      {catalog && <ul className="mt-4 grid gap-2 text-[13px] leading-6">
        <li className="flex items-start gap-2 rounded-2xl bg-[#eef1ea] px-3.5 py-2.5">{catalog.tracked ? <ShieldAlert size={16} className="mt-1 shrink-0 text-[#874a37]" /> : <Info size={16} className="mt-1 shrink-0 text-[#3d6a3f]" />}<span>{catalog.tracked ? "This is one of the invasive species GeoFlora tracks. Retake a clearer photo so the model can confirm it." : "Not one of the invasive species GeoFlora currently tracks."}</span></li>
        <li className="flex items-start gap-2 rounded-2xl bg-[#eef1ea] px-3.5 py-2.5"><MapPin size={16} className="mt-1 shrink-0 text-[#3d6a3f]" /><span>{catalog.recordedInPhilippines ? `Recorded in the Philippines in GBIF${catalog.speciesInCatalog.length > 1 ? ` (${catalog.speciesInCatalog.length} species in this group)` : ""}.` : "Not found in GeoFlora's Philippine plant catalog."}</span></li>
        {catalog.introducedListings.length > 0 && <li className="flex items-start gap-2 rounded-2xl bg-[#fff3df] px-3.5 py-2.5 text-[#7a5414]"><ShieldAlert size={16} className="mt-1 shrink-0" /><span>Listed as introduced or naturalized by {catalog.introducedListings.map(entry => `${entry.sources.join(", ")} (${entry.name})`).join("; ")}. A source listing is not proof of invasive status.</span></li>}
      </ul>}
      {suggestion.look_alikes.length > 0 && <p className="mt-3 text-[12px] leading-6 text-[#5f6b62]">Could be confused with: {suggestion.look_alikes.slice(0, 3).join(", ")}.</p>}
      <button type="button" className="mt-4 inline-flex items-center gap-2 rounded-full bg-[#0d2618] px-4 py-2 text-[13px] font-semibold text-white transition hover:bg-[#1b3d28] disabled:bg-[#3d6a3f]" disabled={usedName === name} onClick={() => onUseName(name)}>{usedName === name ? <><Check size={14} />Name added to your report</> : "Save this name with my report"}</button>
    </>}
    <p className="mt-4 text-[11px] leading-5 text-[#5f6b62]">{answer?.model ? `Second opinion from ${answer.model}, a general AI vision model.` : "Second opinion from a general AI vision model."} A name you save is kept with your report as a possible name.</p>
  </article>;
}
