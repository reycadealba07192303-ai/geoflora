"use client";
import { useEffect, useState } from "react";
import { ArrowRight, ArrowUpRight, ClipboardCheck, Info, ListChecks, ScanLine } from "lucide-react";
import { useAccount } from "../../components/auth-gate";
import type { PageId } from "../../components/app-shell";

interface OverviewCounts { catalog: { records: number; approved: number; pendingReview: number; listedBySources: number }; sightings: { total: number; target: number; other: number; uncertain: number; awaitingReview: number; verified: number; rejected: number; mine: number; canReview: boolean }; model: { ready: boolean; version: string | null; species: number } }

const number = (value: number | undefined) => value === undefined ? "—" : value.toLocaleString();

const actions: { page: PageId; title: string; copy: string; photo: string; credit?: { who: string; url: string } }[] = [
  { page: "identification", title: "Identify", copy: "Get an AI suggestion from a plant photo.", photo: "/landing/hagonoy-bloom.jpg" },
  { page: "reports", title: "Reports", copy: "Your sightings and where each one is in review.", photo: "/landing/hillside.jpg" },
  { page: "map", title: "Map", copy: "See reported sightings across the islands.", photo: "/landing/spread.jpg", credit: { who: "Greg III Espera", url: "https://www.gbif.org/occurrence/3058967605" } },
  { page: "catalog", title: "Catalog", copy: "Browse Philippine plant records and sources.", photo: "/landing/texture.jpg" },
];

const species = [
  { name: "Hagonoy", scientific: "Chromolaena odorata", photo: "/landing/hagonoy.jpg", copy: "A fast-growing shrub that crowds out pasture and forest edges." },
  { name: "Lantana", scientific: "Lantana camara", photo: "/landing/lantana.jpg", copy: "Colourful, toxic to livestock, and spreading through open land.", credit: { who: "Beah Vega", url: "https://www.gbif.org/occurrence/3097058524" } },
  { name: "Water hyacinth", scientific: "Pontederia crassipes", photo: "/landing/hyacinth.jpg", copy: "Floating mats that choke rivers, lakes and fishing grounds.", credit: { who: "Greg III Espera", url: "https://www.gbif.org/occurrence/1847451448" } },
];

const milestones = [
  { title: "Source & prepare data", done: true },
  { title: "Train & evaluate model", done: true },
  { title: "Connect live identification", done: true },
  { title: "Verify sightings & expand species", done: false },
];

// CC BY photos must stay attributed; CC0 photos need no credit.
function Credit({ who, url }: { who: string; url: string }) {
  return <a className="lp-credit" href={url} target="_blank" rel="noreferrer">© {who} · CC BY</a>;
}

function greeting() {
  const hour = Number(new Date().toLocaleString("en-US", { timeZone: "Asia/Manila", hour: "numeric", hour12: false }));
  return hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
}

export default function OverviewView({ onNavigate }: { onNavigate: (page: PageId) => void }) {
  const { user } = useAccount();
  const [counts, setCounts] = useState<OverviewCounts | null>(null);
  useEffect(() => {
    const abort = new AbortController();
    fetch("/api/overview", { cache: "no-store", signal: abort.signal }).then(async response => { if (response.ok) setCounts(await response.json()); }).catch(() => {});
    return () => abort.abort();
  }, []);
  const modelReady = counts?.model.ready === true;
  const [surveyDone, setSurveyDone] = useState(true);
  useEffect(() => { fetch("/api/study/survey", { cache: "no-store" }).then(r => r.ok ? r.json() : null).then(body => { if (body) setSurveyDone(body.answered); }).catch(() => {}); }, []);
  const today = new Date().toLocaleDateString("en-PH", { timeZone: "Asia/Manila", weekday: "long", month: "long", day: "numeric" });

  const metrics = [
    { label: "Target invasive sightings", value: number(counts?.sightings.target), note: "AI identifications and earlier reviewed reports", featured: true },
    { label: "All sightings", value: number(counts?.sightings.total), note: counts ? `${number(counts.sightings.other)} not a target · ${number(counts.sightings.uncertain)} not sure · ${number(counts.sightings.mine)} by you` : "Loading" },
    { label: "AI species supported", value: counts ? String(counts.model.species) : "—", note: counts ? modelReady ? `Live experimental model ${counts.model.version}` : "Identification service unavailable" : "Loading" },
    { label: "Catalog species records", value: number(counts?.catalog.records), note: counts ? `${number(counts.catalog.approved)} approved (owner attestation) · ${number(counts.catalog.pendingReview)} pending` : "Loading" },
  ];

  return <div className="ov">
    <section className="ov-hero" aria-labelledby="overview-title">
      <img className="ov-hero-photo" src="/landing/hero.jpg" alt="" />
      <div className="ov-hero-shade" />
      <Credit who="Gijs Romijn" url="https://www.gbif.org/occurrence/5133247902" />
      <div className="ov-hero-top">
        <span className="lp-live"><span />{counts ? modelReady ? `AI identification live · ${counts.model.species} species` : "Identification service unavailable" : "Checking identification service"}</span>
        <span className="ov-date">{today}</span>
      </div>
      <div className="ov-hero-copy">
        <p className="text-[15px] font-medium text-white/80">{greeting()}, {user.username}.</p>
        <h1 id="overview-title" className="lp-display ov-hero-title">Spot the<br /><span className="text-[#c6dcae]">spread.</span></h1>
        <div className="flex flex-col gap-5 md:flex-row md:items-end md:justify-between">
          <p className="max-w-[440px] text-[14px] leading-7 text-white/85">Identify invasive plants from a photo, pin where they grow, and map where invasive plants grow in the Philippines.</p>
          <div className="flex flex-wrap gap-2.5">
            <button className="lp-pill lp-pill-light lp-pill-lg" onClick={() => onNavigate("identification")}><ScanLine size={17} />Identify a plant<ArrowRight size={16} /></button>
            <button className="lp-pill lp-pill-ghost lp-pill-lg" onClick={() => onNavigate("map")}><ListChecks size={17} />Open the map</button>
          </div>
        </div>
      </div>
    </section>

    {!surveyDone && <section className="content-notice !mt-0 items-center" aria-label="Feedback survey">
      <span className="flex-1"><strong>Help the GeoFlora study:</strong> answer a 3-minute feedback survey about using the system.</span>
      <button className="admin-btn is-primary" onClick={() => onNavigate("survey")}>Answer the survey</button>
    </section>}

    <section aria-label="Workspace status" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {metrics.map(metric => <article key={metric.label} className={`metric-card ov-metric ${metric.featured ? "is-featured" : ""}`}>
        <p className="ov-metric-label">{metric.label}</p>
        <p className="metric-value lp-display">{metric.value}</p>
        <p className="ov-metric-note">{metric.note}</p>
      </article>)}
    </section>

    <section aria-labelledby="overview-actions">
      <div className="ov-section-head"><h2 id="overview-actions" className="lp-display">Jump back in</h2><p>Everything starts with a photo in the field.</p></div>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {actions.map(action => <article key={action.page} className="ov-action">
          <img src={action.photo} alt="" />
          <button className="ov-action-link" onClick={() => onNavigate(action.page)} aria-label={`${action.title}: ${action.copy}`}><span className="ov-action-arrow" aria-hidden="true"><ArrowUpRight size={17} /></span></button>
          {action.credit && <Credit {...action.credit} />}
          <div className="ov-action-copy"><h3 className="lp-display">{action.title}</h3><p>{action.copy}</p></div>
        </article>)}
      </div>
    </section>

    <section className="grid gap-3 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)]">
      <article className="lp-card">
        <span className="lp-tag">At a glance</span>
        <h2 className="lp-display mt-5 text-[clamp(30px,3.4vw,44px)] leading-[0.95] text-[#0d2618]">Your research<br />workspace</h2>
        <dl className="mt-7 grid gap-3.5 text-[13px]">
          <div className="lp-leader"><dt>Catalog records approved (owner attestation)</dt><dd>{number(counts?.catalog.approved)}</dd></div>
          <div className="lp-leader"><dt>Catalog records pending review</dt><dd>{number(counts?.catalog.pendingReview)}</dd></div>
          <div className="lp-leader"><dt>In introduced/naturalized source lists</dt><dd>{number(counts?.catalog.listedBySources)}</dd></div>
          <div className="lp-leader"><dt>Reports submitted by you</dt><dd>{number(counts?.sightings.mine)}</dd></div>
          <div className="lp-leader"><dt>Sightings the model was not sure about</dt><dd>{number(counts?.sightings.uncertain)}</dd></div>
          <div className="lp-leader"><dt>Identification model</dt><dd>{counts ? modelReady ? counts.model.version : "Unavailable" : "—"}</dd></div>
        </dl>
        <div className="mt-7 flex flex-wrap gap-2">
          <button className="lp-pill lp-pill-dark" onClick={() => onNavigate("reports")}>Open reports<ArrowRight size={14} /></button>
          <button className="lp-pill border-[#dbe2d6] bg-white" onClick={() => onNavigate("catalog")}>Explore species catalog</button>
        </div>
      </article>
      <article className="ov-milestones">
        <div className="flex items-center justify-between gap-3"><span className="text-[12px] font-semibold uppercase tracking-[0.18em] text-[#c6dcae]">Milestones</span><span className="rounded-full bg-white/10 px-3 py-1 text-[11px] font-semibold text-white/80">Phase 01</span></div>
        <h2 className="lp-display mt-5 text-[clamp(30px,3.4vw,44px)] leading-[0.95] text-white">A careful<br />science workflow</h2>
        <ol className="mt-7 grid gap-2.5">{milestones.map((step, index) => <li key={step.title} className={`ov-milestone ${step.done ? "is-done" : "is-active"}`}>
          <span className="lp-display text-[22px] leading-none">{String(index + 1).padStart(2, "0")}</span>
          <span className="flex-1 text-[13px] font-medium">{step.title}</span>
          <span className="ov-milestone-state">{step.done ? "Done" : "In progress"}</span>
        </li>)}</ol>
      </article>
    </section>

    <section className="lp-species-panel" aria-labelledby="overview-species">
      <p className="text-center text-[12px] font-semibold uppercase tracking-[0.2em] text-[#c6dcae]">What the AI identifies today</p>
      <h2 id="overview-species" className="lp-display mt-4 text-center text-[clamp(34px,5vw,64px)] leading-[0.92] text-white">Get to know<br />what we track</h2>
      <div className="mt-10 grid gap-3 md:grid-cols-3">
        {species.map(item => <article key={item.name} className="lp-species-card !min-h-[360px]">
          <img src={item.photo} alt={`${item.name}, ${item.scientific}`} />
          <div className="lp-species-copy">
            <h3 className="lp-display text-[26px] leading-[1] text-white">{item.name}</h3>
            <p className="mt-1.5 text-[12px] italic text-white/70">{item.scientific}</p>
            <p className="mt-3 text-[13px] leading-6 text-white/85">{item.copy}</p>
          </div>
          {item.credit && <Credit {...item.credit} />}
        </article>)}
      </div>
      <p className="mx-auto mt-8 flex max-w-xl items-start justify-center gap-2 text-center text-[12px] leading-6 text-white/60"><Info size={14} className="mt-1 shrink-0" />Model scores are experimental suggestions; a reviewer confirms each sighting.</p>
      <div className="mt-5 flex justify-center"><button className="lp-pill lp-pill-lime lp-pill-lg" onClick={() => onNavigate("identification")}>Try identification<ArrowRight size={16} /></button></div>
    </section>
  </div>;
}
