"use client";
import { useEffect, useState } from "react";
import { BookOpen, Search, Sparkles } from "lucide-react";

interface Listing { title: string; status: string; citation: string; doi: string }
interface Entry { id: string; scientificName: string; family: string; reviewStatus: string; reviewBasis: string; occurrenceCount: number; activeModel: boolean; sourceListings: Listing[]; verifiedSightings: number; gbif: { citation: string; doi: string; usages: { name: string; status: string }[] }; iucn: string[]; verifiedEcologicalStatuses: { status: string; geographicScope: string }[] }
interface Result { total: number; catalogTotal: number; reviewCounts: Record<string, number>; page: number; pageSize: number; activeModel: { version: string; species: number }; species: Entry[] }
const FILTERS = [{ id: "all", label: "All species" }, { id: "model", label: "Live model species" }, { id: "listed", label: "Listed by introduced/naturalized sources" }, { id: "verified", label: "Has verified sightings" }];
const doiLink = (doi: string) => `https://doi.org/${doi}`;

export default function CatalogView() {
  const [query, setQuery] = useState(""), [submitted, setSubmitted] = useState(""), [filter, setFilter] = useState("all"), [page, setPage] = useState(1);
  const [result, setResult] = useState<Result | null>(null), [error, setError] = useState(""), [loading, setLoading] = useState(true), [open, setOpen] = useState("");
  useEffect(() => {
    const abort = new AbortController(); setLoading(true);
    fetch(`/api/catalog?${new URLSearchParams({ q: submitted, filter, page: String(page) })}`, { cache: "no-store", signal: abort.signal })
      .then(async response => { const data = await response.json(); if (!response.ok) throw Error(data.detail); setResult(data); setError(""); })
      .catch(e => { if (!abort.signal.aborted) setError(e.message); }).finally(() => { if (!abort.signal.aborted) setLoading(false); });
    return () => abort.abort();
  }, [submitted, filter, page]);
  const pages = result ? Math.max(1, Math.ceil(result.total / result.pageSize)) : 1;
  return <section className="pg"><header className="pg-head"><div><span className="content-eyebrow">Species catalog</span><h1>Philippine plant <span className="lp-photo-text">catalog</span></h1></div>{result && <div className="pg-actions"><span className="id-chip">{result.catalogTotal.toLocaleString()} records</span><span className="identify-status is-ready">Live model · {result.activeModel.species} species</span></div>}</header>
    <p className="pg-card !py-4 text-[13px] leading-6 text-[#33433a]">Candidate species from the GBIF Philippines occurrence species list{result ? ` (${result.catalogTotal.toLocaleString()} records: ${(result.reviewCounts.approved ?? 0).toLocaleString()} approved, ${(result.reviewCounts.pending ?? 0).toLocaleString()} pending)` : ""}. Approval by <strong>owner attestation</strong> admits a record to the catalog; it is not independent per-record taxonomic review. Appearing here, or in a source listing, does not establish native, naturalized or invasive status, and does not mean the AI can identify the species.</p>
    <div className="admin-toolbar"><div className="admin-tabs" role="group" aria-label="Catalog filters">{FILTERS.map(item => <button key={item.id} aria-pressed={filter === item.id} onClick={() => { setFilter(item.id); setPage(1); }} className="admin-tab">{item.label}</button>)}</div>
    <form className="flex min-w-[min(100%,22rem)] flex-1 gap-2 sm:max-w-md" onSubmit={event => { event.preventDefault(); setPage(1); setSubmitted(query); }} role="search"><label className="sr-only" htmlFor="catalog-search">Search species or family</label><span className="admin-search flex-1"><Search size={14} aria-hidden="true" /><input id="catalog-search" placeholder="Search a scientific name or family" maxLength={100} value={query} onChange={e => setQuery(e.target.value)} /></span><button className="admin-btn is-primary">Search</button></form></div>
    {error && <p role="alert" className="content-notice is-error !mt-0">{error}</p>}
    {loading && !result && <p role="status" className="pg-card text-[14px]">Loading the catalog…</p>}
    {result && <><p className="pg-hint px-1" role="status">{result.total.toLocaleString()} matching species · live model {result.activeModel.version || "unavailable"} supports {result.activeModel.species}</p>
      {result.total === 0 && <div className="pg-card admin-empty"><h3>No species match</h3><p>Try another name, family or filter.</p></div>}
      <ul className="grid gap-2.5">{result.species.map(entry => <li key={entry.id} className="surface-card catalog-row text-[14px]">
        <button className="flex w-full flex-wrap items-start justify-between gap-3 text-left" aria-expanded={open === entry.id} onClick={() => setOpen(open === entry.id ? "" : entry.id)}>
          <span className="min-w-0"><span className="block text-[16px] font-semibold italic">{entry.scientificName}</span><span className="text-[12px] text-[#5f6b62]">{entry.family || "Family not recorded"} · {entry.occurrenceCount.toLocaleString()} GBIF PH occurrences</span></span>
          <span className="flex flex-wrap gap-1.5">
            <span className={`admin-badge ${entry.reviewStatus === "approved" ? "tone-green" : "tone-amber"}`}>Catalog: {entry.reviewStatus}{entry.reviewBasis === "owner_attestation" ? " (owner attestation)" : ""}</span>
            {entry.activeModel && <span className="admin-badge !bg-[#0d2618] !text-[#c6dcae]"><Sparkles size={11} />Live AI model</span>}
            {entry.sourceListings.length > 0 && <span className="admin-badge tone-blue">{entry.sourceListings.length} source listing{entry.sourceListings.length > 1 ? "s" : ""}</span>}
            {entry.verifiedSightings > 0 && <span className="admin-badge tone-green">{entry.verifiedSightings} verified sighting{entry.verifiedSightings > 1 ? "s" : ""}</span>}
          </span>
        </button>
        {open === entry.id && <div className="mt-4 space-y-3 border-t border-[#e4e9e0] pt-4 leading-7">
          <div><h3 className="flex items-center gap-2 font-semibold"><BookOpen size={14} />References</h3><p className="mt-1">GBIF: {entry.gbif.doi ? <a className="text-[var(--green)] underline" href={doiLink(entry.gbif.doi)} target="_blank" rel="noopener noreferrer">{entry.gbif.citation || entry.gbif.doi}</a> : entry.gbif.citation || "Not recorded"}</p>
            {entry.sourceListings.map(listing => <p key={listing.title} className="mt-1">{listing.title}{listing.status ? ` — reports “${listing.status}”` : " — listed"} (unverified source claim){listing.doi && <> · <a className="text-[var(--green)] underline" href={doiLink(listing.doi)} target="_blank" rel="noopener noreferrer">{listing.doi}</a></>}</p>)}</div>
          <p><span className="font-semibold">Verified ecological status: </span>{entry.verifiedEcologicalStatuses.length ? entry.verifiedEcologicalStatuses.map(item => `${item.status} (${item.geographicScope})`).join("; ") : "None recorded. Source listings above are not verification."}</p>
          <p><span className="font-semibold">AI identification: </span>{entry.activeModel ? `Supported by the live experimental model ${result.activeModel.version}. Scores still need field confirmation.` : "Not supported by the live model."}</p>
          {entry.gbif.usages.length > 1 && <p><span className="font-semibold">Names in source: </span>{entry.gbif.usages.map(usage => `${usage.name} (${usage.status.toLowerCase()})`).join("; ")}</p>}
          {entry.iucn.length > 0 && <p><span className="font-semibold">IUCN category in source: </span>{entry.iucn.join(", ")}</p>}
        </div>}
      </li>)}</ul>
      {result.total > result.pageSize && <nav className="flex items-center justify-between px-1 text-[13px]" aria-label="Catalog pages"><button className="admin-btn is-small" disabled={page <= 1 || loading} onClick={() => setPage(page - 1)}>Previous</button><span>Page {page} of {pages}</span><button className="admin-btn is-small" disabled={page >= pages || loading} onClick={() => setPage(page + 1)}>Next</button></nav>}
    </>}
  </section>;
}
