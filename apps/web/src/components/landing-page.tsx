"use client";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { ArrowRight, ArrowUpRight, Camera, MapPinned, Menu, ScanSearch, ShieldCheck, Sparkles, Sprout, Users, X } from "lucide-react";

interface LandingStats { verifiedSightings: number | null; catalogRecords: number | null; model: { ready: boolean; species: number | null } }

const tags = ["Snap", "Identify", "Pin", "Verify", "Map", "Protect"];
const links = [{ href: "#mission", label: "Mission" }, { href: "#species", label: "Species" }, { href: "#how", label: "How it works" }];

const species: { name: string; scientific: string; photo: string; copy: string; credit?: { who: string; url: string } }[] = [
  { name: "Hagonoy", scientific: "Chromolaena odorata", photo: "/landing/hagonoy.jpg", copy: "A fast-growing shrub that crowds out pasture and forest edges." },
  { name: "Lantana", scientific: "Lantana camara", photo: "/landing/lantana.jpg", copy: "Colourful, toxic to livestock, and spreading through open land.", credit: { who: "Beah Vega", url: "https://www.gbif.org/occurrence/3097058524" } },
  { name: "Water hyacinth", scientific: "Pontederia crassipes", photo: "/landing/hyacinth.jpg", copy: "Floating mats that choke rivers, lakes and fishing grounds.", credit: { who: "Greg III Espera", url: "https://www.gbif.org/occurrence/1847451448" } },
  { name: "More species", scientific: "Coming as reviewed photos grow", photo: "/landing/hillside.jpg", copy: "The catalog already tracks introduced plants across the islands." },
];

const steps: { icon: ReactNode; title: string; copy: string }[] = [
  { icon: <Camera size={18} />, title: "Snap a photo", copy: "Leaves and flowers in clear view, one plant per photo." },
  { icon: <Sparkles size={18} />, title: "Get an AI suggestion", copy: "Low-confidence results are marked uncertain, never guessed." },
  { icon: <ShieldCheck size={18} />, title: "Reviewer verifies", copy: "A person confirms or rejects every sighting before it counts." },
  { icon: <MapPinned size={18} />, title: "It joins the map", copy: "Verified sightings build a shared picture of the spread." },
];

// CC BY photos must stay attributed; CC0 photos need no credit.
function Credit({ who, url }: { who: string; url: string }) {
  return <a className="lp-credit" href={url} target="_blank" rel="noreferrer">© {who} · CC BY</a>;
}

const count = (value: number | null | undefined) => value === null || value === undefined ? "—" : value.toLocaleString();

export default function LandingPage({ onGetStarted, setupRequired }: { onGetStarted: () => void; setupRequired: boolean }) {
  const startLabel = setupRequired ? "Set up workspace" : "Get started";
  const [stats, setStats] = useState<LandingStats | null>(null);
  const [scrolled, setScrolled] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const abort = new AbortController();
    fetch("/api/landing", { cache: "no-store", signal: abort.signal }).then(async response => { if (response.ok) setStats(await response.json()); }).catch(() => {});
    return () => abort.abort();
  }, []);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 40);
    onScroll(); window.addEventListener("scroll", onScroll, { passive: true });
    const observer = new IntersectionObserver(entries => entries.forEach(entry => { if (entry.isIntersecting) { entry.target.classList.add("is-visible"); observer.unobserve(entry.target); } }), { threshold: 0.15 });
    root.current?.querySelectorAll(".reveal").forEach(element => observer.observe(element));
    return () => { window.removeEventListener("scroll", onScroll); observer.disconnect(); };
  }, []);

  return <div ref={root} className="lp">
    <header className={`lp-topbar ${scrolled ? "is-scrolled" : ""}`}>
      <a href="#top" className="lp-wordmark text-[24px] text-[#0d2618]" aria-label="GeoFlora home" onClick={() => setMenuOpen(false)}>geoflora<span className="text-[#7fa96f]">.</span></a>
      <nav aria-label="Landing page" className="hidden items-center gap-8 md:flex">
        {links.map(link => <a key={link.href} className="lp-topbar-link" href={link.href}>{link.label}</a>)}
      </nav>
      <div className="flex items-center gap-2">
        <button className="lp-pill lp-pill-dark" onClick={onGetStarted}>{startLabel}<ArrowRight size={14} /></button>
        <button className="lp-menu-button md:hidden" aria-label={menuOpen ? "Close menu" : "Open menu"} aria-expanded={menuOpen} aria-controls="lp-mobile-menu" onClick={() => setMenuOpen(!menuOpen)}>{menuOpen ? <X size={20} /> : <Menu size={20} />}</button>
      </div>
      {menuOpen && <nav id="lp-mobile-menu" aria-label="Landing page" className="lp-mobile-menu md:hidden">
        {links.map(link => <a key={link.href} href={link.href} onClick={() => setMenuOpen(false)}>{link.label}</a>)}
      </nav>}
    </header>

    <section id="top" className="lp-hero">
      <img className="lp-hero-photo" src="/landing/hero.jpg" alt="Water hyacinth spreading across a lake, with a fisher in a small boat" />
      <div className="lp-hero-shade" />
      <Credit who="Gijs Romijn" url="https://www.gbif.org/occurrence/5133247902" />

      <div className="lp-scan" aria-hidden="true">
        <i /><i /><i /><i />
        <span className="lp-scan-label"><ScanSearch size={13} />Pontederia crassipes · invasive</span>
      </div>

      <div className="lp-hero-copy">
        <span className="lp-live"><span />{stats?.model.ready ? `AI identification live · ${stats.model.species} species` : "Invasive plant monitoring · Philippines"}</span>
        <h1 className="lp-display lp-hero-title"><span>Spot the</span><span>spread.</span></h1>
        <div className="flex flex-col gap-6 md:flex-row md:items-end md:justify-between">
          <p className="max-w-[460px] text-[15px] leading-7 text-white/85">
            GeoFlora helps researchers and communities identify invasive plants from a photo, pin where they grow, and build a verified map of Philippine flora.
          </p>
          <div className="flex flex-wrap gap-2.5">
            <button className="lp-pill lp-pill-light lp-pill-lg" onClick={onGetStarted}>{startLabel}<ArrowRight size={16} /></button>
            <a className="lp-pill lp-pill-ghost lp-pill-lg" href="#how">See how it works</a>
          </div>
        </div>
      </div>
    </section>

    <div className="lp-marquee" aria-hidden="true">
      <div>{[...tags, ...tags, ...tags, ...tags].map((tag, index) => <span key={index}>{tag}<Sprout size={18} /></span>)}</div>
    </div>

    <section id="mission" className="lp-section grid gap-12 lg:grid-cols-[0.9fr_1.1fr] lg:items-end">
      <div className="reveal">
        <div className="flex flex-wrap gap-2">{tags.map(tag => <span key={tag} className="lp-tag">{tag}</span>)}</div>
        <p className="mt-7 max-w-[420px] text-[17px] leading-8 text-[#33433a]">
          Invasive plants spread quietly: across pastures, hillsides and waterways. GeoFlora turns everyday field photos into reviewed records, so action starts with evidence.
        </p>
      </div>
      <h2 className="lp-display lp-statement reveal">
        Know what<br /><span className="lp-photo-text">grows</span> before<br />it <span className="lp-photo-text">takes over.</span>
      </h2>
    </section>

    <section className="lp-section !pt-12 grid gap-4 md:grid-cols-[1fr_1fr_1.2fr]">
      <article className="lp-card reveal">
        <p className="lp-display text-[56px] leading-none text-[#0d2618]">{count(stats?.catalogRecords)}</p>
        <p className="mt-2 text-[14px] text-[#5f6b62]">Plant records in the species catalog</p>
        <dl className="mt-7 grid gap-3 text-[13px]">
          <div className="lp-leader"><dt>AI-identified species</dt><dd>{count(stats?.model.species)}</dd></div>
          <div className="lp-leader"><dt>Reviewer-verified sightings</dt><dd>{count(stats?.verifiedSightings)}</dd></div>
          <div className="lp-leader"><dt>Coverage</dt><dd>Philippines</dd></div>
        </dl>
      </article>
      <article className="lp-card reveal flex flex-col justify-between" style={{ transitionDelay: "90ms" }}>
        <span className="grid h-12 w-12 place-items-center rounded-full bg-[#0d2618] text-[#c6dcae]"><Users size={20} /></span>
        <p className="mt-10 text-[22px] font-medium leading-[1.35] tracking-[-0.02em] text-[#0d2618]">
          <span className="text-[#6f8f62]">Researchers</span>, <span className="text-[#6f8f62]">reviewers</span> and <span className="text-[#6f8f62]">local communities</span> mapping the islands together.
        </p>
      </article>
      <article className="lp-card lp-photo-card reveal min-h-[280px]" style={{ transitionDelay: "180ms" }}>
        <img src="/landing/hagonoy-bloom.jpg" alt="Pale blue Hagonoy flower heads" />
        <span className="lp-photo-card-label">Every record starts in the field</span>
      </article>
    </section>

    <section id="species" className="lp-section lp-section-wide">
      <div className="lp-species-panel reveal">
        <p className="text-center text-[12px] font-semibold uppercase tracking-[0.2em] text-[#c6dcae]">What the AI identifies today</p>
        <h2 className="lp-display mt-4 text-center text-[clamp(38px,6vw,76px)] leading-[0.92] text-white">Get to know<br />what we track</h2>
        <div className="mt-12 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {species.map(item => <article key={item.name} className="lp-species-card">
            <img src={item.photo} alt={`${item.name}, ${item.scientific}`} />
            <div className="lp-species-copy">
              <h3 className="lp-display text-[26px] leading-[1] text-white">{item.name}</h3>
              <p className="mt-1.5 text-[12px] italic text-white/70">{item.scientific}</p>
              <p className="mt-4 text-[13px] leading-6 text-white/85">{item.copy}</p>
            </div>
            <span className="lp-species-arrow"><ArrowUpRight size={16} /></span>
            {item.credit && <Credit {...item.credit} />}
          </article>)}
        </div>
        <p className="mt-8 text-center text-[12px] text-white/55">The identification model is experimental. Uncertain results are flagged and every sighting is checked by a person.</p>
      </div>
    </section>

    <section id="how" className="lp-section">
      <div className="grid gap-10 lg:grid-cols-[0.8fr_1.2fr] lg:items-start">
        <div className="reveal">
          <span className="lp-tag">How it works</span>
          <h2 className="lp-display mt-6 text-[clamp(38px,5vw,64px)] leading-[0.95] text-[#0d2618]">From the field to the map.</h2>
          <p className="mt-5 max-w-[380px] text-[15px] leading-7 text-[#5f6b62]">You don't need to be a botanist. Take a photo, let GeoFlora suggest a species, and send it for review.</p>
        </div>
        <ol className="grid gap-4 sm:grid-cols-2">
          {steps.map((step, index) => <li key={step.title} className="lp-step reveal" style={{ transitionDelay: `${index * 80}ms` }}>
            <div className="flex items-center justify-between">
              <span className="grid h-11 w-11 place-items-center rounded-full bg-[#c6dcae] text-[#0d2618]">{step.icon}</span>
              <span className="lp-display text-[40px] leading-none text-white/15">{String(index + 1).padStart(2, "0")}</span>
            </div>
            <h3 className="mt-8 text-[18px] font-semibold text-white">{step.title}</h3>
            <p className="mt-2 text-[13px] leading-6 text-white/70">{step.copy}</p>
          </li>)}
        </ol>
      </div>
    </section>

    <section className="lp-section lp-section-wide">
      <div className="lp-banner reveal">
        <img src="/landing/spread.jpg" alt="A dense mat of water hyacinth covering a pond" />
        <div className="lp-banner-shade" />
        <Credit who="Greg III Espera" url="https://www.gbif.org/occurrence/3058967605" />
        <span className="lp-banner-chip">Water hyacinth can double its cover in weeks</span>
        <h2 className="lp-display lp-banner-title">Map the<br />spread.</h2>
      </div>
    </section>

    <footer className="lp-footer">
      <div className="lp-footer-cta">
        <h2 className="lp-display text-[clamp(36px,5.5vw,84px)] leading-[0.9] text-white">Ready to record<br />your first <span className="text-[#c6dcae]">sighting?</span></h2>
        <div className="flex flex-col items-start gap-5 lg:items-end lg:text-right">
          <p className="max-w-[340px] text-[15px] leading-7 text-white/70">{setupRequired ? "Create the first administrator account to open this workspace." : "Join as a contributor and help map invasive plants across the islands."}</p>
          <button className="lp-pill lp-pill-lime lp-pill-lg" onClick={onGetStarted}>{startLabel}<ArrowRight size={16} /></button>
        </div>
      </div>
      <div className="lp-footer-base">
        <span className="lp-wordmark text-[20px] text-white">geoflora<span className="text-[#c6dcae]">.</span></span>
        <span>Philippine plant intelligence · Research workspace</span>
      </div>
    </footer>
  </div>;
}
