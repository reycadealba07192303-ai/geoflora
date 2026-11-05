"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { LayerGroup, Map as LeafletMap } from "leaflet";
import "leaflet/dist/leaflet.css";
import { canModerate, useAccount } from "../../components/auth-gate";
import { RESULT_COLOR, RESULT_LABEL, type ReportResult } from "../../lib/ai-result";
import { speciesInformation } from "../identification/species-information";

const about = (species: string) => speciesInformation[species.trim().toLowerCase().replace(/\s+/g, "_")];

interface Point { id: string; species: string; status: string; result: ReportResult; latitude: number; longitude: number; observedAt: string; submittedAt: string; placeName: string }
interface Cell { south: number; west: number; north: number; east: number; centerLat: number; centerLng: number; reports: number; species: number }
interface Analytics { scope: string; layer: string; total: number; sparse: boolean; bySpecies: { species: string; reports: number }[]; byMonth: { month: string; reports: number }[]; byStatus: Record<string, number>; cells: Cell[]; hotspots: Cell[]; suppressed: { cells: number; reports: number }; method: { cellDegrees: number; minCellReports: number; hotspotMinReports: number; sparseBelow: number; meaning: string }; speciesOptions: string[] }
type Filters = { species: string; from: string; to: string; layer: "target" | "all"; bbox: string };
const EMPTY: Filters = { species: "", from: "", to: "", layer: "all", bbox: "" };
const date = (value: string) => new Date(value).toLocaleString("en-PH", { timeZone: "Asia/Manila" });
// Colours follow the AI result, as in the ML lab demo: red target invasive, blue not a target, amber not sure.
const resultColor = (point: Point) => RESULT_COLOR[point.result];
const resultText = (point: Point) => RESULT_LABEL[point.result].toLowerCase();
const label = (species: string) => species === "unknown" ? "Not sure (unidentified)" : species;
// Sequential single-hue ramp (light to dark green) for generalized report density.
const DENSITY = ["#dcebd5", "#b3d1a6", "#7fae70", "#4f7d4f", "#2f5531"];
// Shown when a report's photo cannot load, so the marker stays readable.
const PHOTO_FALLBACK = "data:image/svg+xml," + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 52 52"><rect width="52" height="52" fill="#eef3e8"/><path d="M26 40c0-12 4-20 12-24-1 10-5 18-12 24Zm0 0c0-9-3-15-9-18 0 8 3 14 9 18Z" fill="#6f9f62"/></svg>');
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export default function SightingsMap({ focusId, onViewReport }: { focusId?: string; onViewReport?: (id: string) => void }) {
  const { user } = useAccount();
  const moderator = canModerate(user.role);
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<LeafletMap | null>(null), markers = useRef<LayerGroup | null>(null), grid = useRef<LayerGroup | null>(null), leaflet = useRef<typeof import("leaflet") | null>(null);
  const [filters, setFilters] = useState<Filters>(EMPTY);
  const [points, setPoints] = useState<Point[]>([]), [truncated, setTruncated] = useState(false), [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [selected, setSelected] = useState<Point | null>(null), [showGrid, setShowGrid] = useState(false), [showTable, setShowTable] = useState(false);
  const [error, setError] = useState(""), [loading, setLoading] = useState(true), [ready, setReady] = useState(false);
  const fitted = useRef(false);

  useEffect(() => {
    const abort = new AbortController(); setLoading(true);
    const query = (extra: Record<string, string>) => new URLSearchParams(Object.entries({ ...filters, ...extra }).filter(([, value]) => value) as [string, string][]).toString();
    Promise.all([fetch(`/api/occurrences?${query({})}`, { cache: "no-store", signal: abort.signal }), fetch(`/api/analytics?${query({})}`, { cache: "no-store", signal: abort.signal })])
      .then(async ([pointsResponse, analyticsResponse]) => {
        const [pointBody, analyticsBody] = await Promise.all([pointsResponse.json(), analyticsResponse.json()]);
        if (!pointsResponse.ok) throw Error(pointBody.detail); if (!analyticsResponse.ok) throw Error(analyticsBody.detail);
        setPoints(pointBody.points); setTruncated(pointBody.truncated); setAnalytics(analyticsBody); setError("");
        setSelected(current => pointBody.points.find((p: Point) => p.id === (current?.id ?? focusId)) ?? null);
      }).catch(e => { if (!abort.signal.aborted) setError(e.message); }).finally(() => { if (!abort.signal.aborted) setLoading(false); });
    return () => abort.abort();
  }, [filters, focusId]);

  useEffect(() => {
    let disposed = false;
    import("leaflet").then(L => {
      if (disposed || !container.current) return;
      leaflet.current = L;
      const instance = L.map(container.current).setView([12.8797, 121.774], 6);
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors', maxZoom: 19 }).addTo(instance);
      grid.current = L.layerGroup().addTo(instance); markers.current = L.layerGroup().addTo(instance);
      map.current = instance; setReady(true);
    }).catch(() => setError("The map could not load. Report details remain available below."));
    return () => { disposed = true; map.current?.remove(); map.current = null; };
  }, []);

  // Screen-space clustering: points within the same 64px cell at the current zoom share one marker.
  const drawMarkers = useCallback(() => {
    const L = leaflet.current, instance = map.current, layer = markers.current;
    if (!L || !instance || !layer) return;
    layer.clearLayers();
    const groups = new Map<string, Point[]>();
    for (const point of points) {
      const pixel = instance.project([point.latitude, point.longitude], instance.getZoom());
      const key = `${Math.floor(pixel.x / 64)}:${Math.floor(pixel.y / 64)}`;
      groups.set(key, [...(groups.get(key) ?? []), point]);
    }
    for (const group of groups.values()) {
      if (group.length === 1) {
        const point = group[0], image = document.createElement("img");
        image.onerror = () => { image.onerror = null; image.src = PHOTO_FALLBACK; };
        image.src = `/api/sightings/${point.id}/photo?thumbnail=1`; image.alt = `Reported plant: ${label(point.species)}`; image.width = image.height = 52;
        image.style.cssText = `width:52px;height:52px;object-fit:cover;border:3px solid ${resultColor(point)};border-radius:12px;box-shadow:0 2px 8px #0005;background:white`;
        const icon = L.divIcon({ html: image, className: "sighting-photo-marker", iconSize: [52, 52], iconAnchor: [26, 26], tooltipAnchor: [0, -28] });
        L.marker([point.latitude, point.longitude], { icon, title: `View ${label(point.species)} report`, alt: `Reported plant: ${label(point.species)}` }).addTo(layer)
          .bindTooltip(`${label(point.species)} — ${point.placeName || "Reported location"} (${resultText(point)})`).on("click", () => setSelected(point));
      } else {
        const tone = group.some(point => point.result === "target") ? RESULT_COLOR.target : group.some(point => point.result === "other") ? RESULT_COLOR.other : RESULT_COLOR.uncertain;
        const targets = group.filter(point => point.result === "target").length;
        const lat = group.reduce((sum, p) => sum + p.latitude, 0) / group.length, lng = group.reduce((sum, p) => sum + p.longitude, 0) / group.length;
        const icon = L.divIcon({ html: `<span style="border-color:${tone}">${group.length}</span>`, className: "occurrence-cluster", iconSize: [44, 44], iconAnchor: [22, 22] });
        L.marker([lat, lng], { icon, title: `${group.length} reports here; select to zoom in`, alt: `${group.length} reports`, keyboard: true }).addTo(layer)
          .bindTooltip(`${group.length} reports (${targets} target invasive) — select to zoom in`)
          .on("click", () => instance.fitBounds(L.latLngBounds(group.map(p => [p.latitude, p.longitude] as [number, number])), { padding: [40, 40], maxZoom: 17 }));
      }
    }
  }, [points]);

  useEffect(() => {
    const instance = map.current;
    if (!ready || !instance) return;
    drawMarkers();
    instance.on("zoomend", drawMarkers);
    const focused = points.find(p => p.id === focusId);
    if (focused && !fitted.current) { instance.setView([focused.latitude, focused.longitude], 15); fitted.current = true; }
    else if (points.length && !fitted.current && leaflet.current) { instance.fitBounds(leaflet.current.latLngBounds(points.map(p => [p.latitude, p.longitude] as [number, number])), { padding: [30, 30], maxZoom: 14 }); fitted.current = true; }
    return () => { instance.off("zoomend", drawMarkers); };
  }, [ready, points, drawMarkers, focusId]);

  useEffect(() => {
    const L = leaflet.current, layer = grid.current;
    if (!ready || !L || !layer) return;
    layer.clearLayers();
    if (!showGrid || !analytics) return;
    const max = Math.max(1, ...analytics.cells.map(cell => cell.reports));
    for (const cell of analytics.cells) {
      const color = DENSITY[Math.min(DENSITY.length - 1, Math.floor((cell.reports / max) * (DENSITY.length - 1)))];
      L.rectangle([[cell.south, cell.west], [cell.north, cell.east]], { color: "#ffffff", weight: 2, fillColor: color, fillOpacity: 0.45 }).addTo(layer)
        .bindTooltip(`${cell.reports} reports, ${cell.species} species in this ${analytics.method.cellDegrees}° cell (generalized)`);
    }
  }, [ready, showGrid, analytics]);

  function limitToMapArea() {
    const bounds = map.current?.getBounds(); if (!bounds) return;
    const round = (value: number) => value.toFixed(4);
    setFilters(current => ({ ...current, bbox: [bounds.getWest(), bounds.getSouth(), bounds.getEast(), bounds.getNorth()].map(round).join(",") }));
  }
  const change = (patch: Partial<Filters>) => setFilters(current => ({ ...current, ...patch }));
  const filtered = filters.species || filters.from || filters.to || filters.bbox;
  const maxSpecies = Math.max(1, ...(analytics?.bySpecies.map(row => row.reports) ?? [1]));
  const maxMonth = Math.max(1, ...(analytics?.byMonth.map(row => row.reports) ?? [1]));
  return <section className="pg">
    <header className="pg-head"><div><span className="content-eyebrow">Field notebook</span><h1>Occurrence <span className="lp-photo-text">map</span></h1><p>{moderator ? "All workspace reports at their recorded locations." : "Your reports at their recorded locations. Workspace analytics below use reports from everyone, generalized to grid cells."} Results are identified by GeoFlora AI. Dates use Philippine time.</p></div>
      <div className="pg-actions"><span className="id-chip">{loading ? "Loading…" : `${points.length.toLocaleString()} report${points.length === 1 ? "" : "s"} shown`}</span></div></header>

    <form className="pg-card map-filters" aria-label="Map filters" onSubmit={event => event.preventDefault()}>
      <label className="admin-field">Species<select className="admin-input" value={filters.species} onChange={e => change({ species: e.target.value })}><option value="">All species</option>{(analytics?.speciesOptions ?? []).map(name => <option key={name} value={name.toLowerCase()}>{label(name)}</option>)}</select></label>
      <label className="admin-field">Observed from<input className="admin-input" type="date" value={filters.from} max={filters.to || undefined} onChange={e => change({ from: e.target.value })} /></label>
      <label className="admin-field">to<input className="admin-input" type="date" value={filters.to} min={filters.from || undefined} onChange={e => change({ to: e.target.value })} /></label>
      <fieldset className="admin-field"><legend className="mb-[7px]">Reports</legend><div className="admin-tabs !flex !w-full !bg-[#eef1ea]" role="radiogroup">{(["all", "target"] as const).map(layer => <label key={layer} className={`admin-tab flex-1 cursor-pointer justify-center !text-[12px] ${filters.layer === layer ? "is-on" : ""}`}><input className="sr-only" type="radio" name="layer" checked={filters.layer === layer} onChange={() => change({ layer })} />{layer === "all" ? "All results" : "Target invasive only"}</label>)}</div></fieldset>
      <div className="flex flex-wrap items-center gap-2 md:col-span-full">
        <button type="button" className="admin-btn is-small" onClick={limitToMapArea}>Limit to map area</button>
        {filtered && <button type="button" className="admin-btn is-small" onClick={() => setFilters({ ...EMPTY, layer: filters.layer })}>Clear filters</button>}
        <label className="ml-auto flex items-center gap-2 text-[13px] font-medium"><input type="checkbox" className="h-4 w-4 accent-[#0d2618]" checked={showGrid} onChange={e => setShowGrid(e.target.checked)} />Show generalized density grid</label>
      </div>
    </form>
    {filters.bbox && <p className="pg-hint px-1">Area filter: {filters.bbox.replaceAll(",", ", ")} (west, south, east, north).</p>}
    {error && <p role="alert" className="content-notice is-error !mt-0">{error}</p>}

    <div className="grid items-stretch gap-3 xl:grid-cols-[minmax(0,1fr)_360px]">
      <div className="overflow-hidden rounded-[28px] bg-white p-2">
        <div ref={container} className="relative z-0 h-[clamp(360px,62svh,600px)] overflow-hidden rounded-[22px]" aria-label="Map of reported plant sightings" />
        <p className="flex flex-wrap gap-x-4 gap-y-1 px-3 py-2.5 text-[12px] text-[#5f6b62]">{(["target", "other", "uncertain"] as const).map(result => <span key={result}><span className="mr-1.5 inline-block h-3 w-3 rounded-sm border-2 align-[-1px]" style={{ borderColor: RESULT_COLOR[result] }} />{RESULT_LABEL[result]}</span>)}<span>Numbered circles: several nearby reports; select to zoom in.</span>{showGrid && <span>Grid shading: report count per {analytics?.method.cellDegrees}° cell, light to dark.</span>}</p>
      </div>
      <aside className="flex max-h-[calc(clamp(360px,62svh,600px)+52px)] min-h-0 flex-col gap-3 overflow-hidden">
        {selected && <article className="pg-ink shrink-0 overflow-y-auto !p-4 max-h-[62%]"><img src={`/api/sightings/${selected.id}/photo`} alt={`Plant photographed for ${label(selected.species)} report`} className="h-28 w-full rounded-2xl bg-black/20 object-contain" /><h2 className="mt-3 text-[11px] font-semibold uppercase tracking-[0.16em] text-[#c6dcae]">Report details</h2><p className="mt-1 text-[17px] font-semibold italic">{label(selected.species)}</p><div className="mt-2 space-y-0.5 text-[12px] leading-5 text-white/75"><p>Result: {RESULT_LABEL[selected.result]} (AI identification)</p><p>Observed: {date(selected.observedAt)}</p><p>Report created: {date(selected.submittedAt)}</p><p>{selected.placeName || "Recorded coordinates"} ({selected.latitude.toFixed(5)}, {selected.longitude.toFixed(5)})</p></div>{about(selected.species)?.description && <p className="mt-2 line-clamp-4 text-[12px] leading-5 text-white/85">{about(selected.species)!.description}</p>}{onViewReport && <button className="lp-pill lp-pill-lime mt-3 w-full justify-center" onClick={() => onViewReport(selected.id)}>View report / download PDF</button>}</article>}
        <div className="min-h-[140px] flex-1 space-y-2 overflow-y-auto overflow-x-hidden rounded-[28px] bg-white p-3" role="region" aria-label="Matching reports">
          {loading && <p role="status" className="p-3 text-[13px]">Loading reports…</p>}
          {!loading && !error && points.length === 0 && <p className="p-3 text-[13px] leading-6">{filtered ? "No reports match these filters. Try a wider date range or clear the area filter." : filters.layer === "target" ? "No target invasive reports yet. Choose All results to see every report." : "No reports yet. Identify a plant and save your first report."}</p>}
          {points.map(point => <button key={point.id} onClick={() => { setSelected(point); map.current?.setView([point.latitude, point.longitude], 15); }} className={`map-row ${selected?.id === point.id ? "is-on" : ""}`}>
            <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: resultColor(point) }} aria-hidden="true" />
            <span className="min-w-0 flex-1"><strong className="block truncate text-[13px] italic">{label(point.species)}</strong> <span className="text-[11px] text-[#5f6b62]">({resultText(point)})</span><span className="block truncate text-[12px]">{point.placeName || `${point.latitude.toFixed(5)}, ${point.longitude.toFixed(5)}`}</span><span className="block text-[11px] text-[#5f6b62]">Observed {date(point.observedAt)}</span></span>
          </button>)}
        </div>
      </aside>
    </div>
    {truncated && <p className="pg-hint px-1">Showing the 2,000 most recent matching reports. Narrow the filters to see others.</p>}

    {analytics && <section className="grid gap-3" aria-label="Occurrence analytics">
      <div className="ov-section-head !mb-1"><h2 className="lp-display">Analytics</h2></div>
      <p className="content-notice !mt-0" role="note">{analytics.method.meaning} {analytics.layer === "target" ? "Only target invasive reports are counted." : "All results are counted."}</p>
      <div className="grid gap-3 sm:grid-cols-3">
        <Stat label="Reports in these filters" value={analytics.total} />
        <Stat label="Species" value={analytics.bySpecies.length} />
        <Stat label="Generalized cells shown" value={analytics.cells.length} note={analytics.suppressed.cells ? `${analytics.suppressed.cells} sparse cell${analytics.suppressed.cells > 1 ? "s" : ""} (${analytics.suppressed.reports} reports) hidden` : undefined} />
      </div>
      {analytics.total === 0 ? <p className="pg-card text-[14px]">No reports match these filters, so there is nothing to summarize.</p> : <>
        {analytics.sparse && <p className="px-1 text-[13px] text-[#8a6a2c]" role="note">Only {analytics.total} report{analytics.total > 1 ? "s" : ""} match. Below {analytics.method.sparseBelow} reports, distribution and trends are not meaningful.</p>}
        <div className="grid gap-3 lg:grid-cols-2">
          <figure className="surface-card m-0 space-y-4 p-6"><figcaption className="pg-card-title">Reports by species</figcaption>
            <ul className="space-y-2.5">{analytics.bySpecies.map(row => <li key={row.species} className="grid grid-cols-[minmax(0,10rem)_1fr] items-center gap-3 text-[12px]" title={`${label(row.species)}: ${row.reports} reports`}>
              <span className="truncate italic">{label(row.species)}</span>
              <span className="flex items-center gap-2"><span className="h-[16px] rounded-full bg-[#0d2618]" style={{ width: `${(row.reports / maxSpecies) * 85}%`, minWidth: 6 }} aria-hidden="true" /><span className="font-semibold">{row.reports}</span></span>
            </li>)}</ul></figure>
          <figure className="surface-card m-0 space-y-3 p-6"><figcaption className="pg-card-title">Reports by month observed</figcaption>
            <div className="flex h-44 items-end gap-[3px] overflow-x-auto border-b border-[#e4e9e0] pb-0" role="list">{analytics.byMonth.map(row => { const [year, month] = row.month.split("-"); return <div key={row.month} role="listitem" tabIndex={0} title={`${MONTHS[Number(month) - 1]} ${year}: ${row.reports} reports`} aria-label={`${MONTHS[Number(month) - 1]} ${year}: ${row.reports} reports`} className="flex h-full min-w-[34px] flex-1 flex-col items-center justify-end gap-1 rounded-t-lg text-[11px] font-semibold outline-none focus:bg-[#eef1ea]">
              <span>{row.reports}</span><span className="w-full max-w-[26px] rounded-t-[8px] bg-[#0d2618]" style={{ height: `${(row.reports / maxMonth) * 120}px`, minHeight: 4 }} />
            </div>; })}</div>
            <div className="flex gap-[3px] overflow-x-auto text-[11px] text-[#5f6b62]">{analytics.byMonth.map(row => { const [year, month] = row.month.split("-"); return <span key={row.month} className="min-w-[34px] flex-1 text-center">{MONTHS[Number(month) - 1]} {year.slice(2)}</span>; })}</div>
            <p className="pg-hint">Months without reports are not shown.</p></figure>
        </div>
        <section className="pg-card space-y-2 text-[14px]"><h3 className="pg-card-title">High report density cells</h3>
          {analytics.hotspots.length ? <ol className="list-decimal space-y-1 pl-5">{analytics.hotspots.map(cell => <li key={`${cell.south},${cell.west}`}>{cell.reports} reports, {cell.species} species — cell centred near {cell.centerLat.toFixed(2)}, {cell.centerLng.toFixed(2)} ({analytics.method.cellDegrees}° ≈ 11 km)</li>)}</ol>
            : <p className="text-[#5f6b62]">No cell has {analytics.method.hotspotMinReports} or more reports in these filters.</p>}
          <p className="pg-hint">A high-density cell means many reports were submitted there. It may reflect where people looked, not where the plant is most abundant or spreading.</p></section>
        <div><button className="admin-btn is-small" onClick={() => setShowTable(!showTable)} aria-expanded={showTable}>{showTable ? "Hide" : "Show"} data table</button></div>
        {showTable && <div className="grid gap-3 text-[13px] lg:grid-cols-2">
          <div className="pg-card !p-3"><table className="admin-table"><caption className="p-2 text-left font-semibold">By species</caption><thead><tr><th>Species</th><th className="!text-right">Reports</th></tr></thead><tbody>{analytics.bySpecies.map(row => <tr key={row.species}><td className="italic">{label(row.species)}</td><td className="text-right">{row.reports}</td></tr>)}</tbody></table></div>
          <div className="pg-card !p-3"><table className="admin-table"><caption className="p-2 text-left font-semibold">By month observed</caption><thead><tr><th>Month</th><th className="!text-right">Reports</th></tr></thead><tbody>{analytics.byMonth.map(row => <tr key={row.month}><td>{row.month}</td><td className="text-right">{row.reports}</td></tr>)}</tbody></table></div>
        </div>}
      </>}
    </section>}
  </section>;
}

function Stat({ label, value, note }: { label: string; value: number; note?: string }) {
  return <div className="surface-card ov-metric !min-h-[130px]"><span className="ov-metric-label">{label}</span><p className="text-2xl metric-value lp-display">{value.toLocaleString()}</p>{note && <p className="ov-metric-note">{note}</p>}</div>;
}
