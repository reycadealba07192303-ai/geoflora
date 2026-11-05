import { PDFDocument, StandardFonts, rgb, type PDFFont, type PDFImage, type PDFPage, type RGB } from "pdf-lib";
import sharp from "sharp";
import { RESULT_LABEL, type ReportResult } from "./ai-result";
import type { reportSummary } from "./sightings";
import { speciesInformation, type SpeciesInformation } from "../features/identification/species-information";

// ---------- Location map (OpenStreetMap tiles around the point, or an offline diagram) ----------
const tileCache = new Map<string, Buffer>();
async function locationMap(latitude: number, longitude: number, photo: Buffer) {
  const z = 14, scale = 2 ** z, lat = Math.max(-85, Math.min(85, latitude)) * Math.PI / 180;
  const worldX = (longitude + 180) / 360 * scale, worldY = (1 - Math.asinh(Math.tan(lat)) / Math.PI) / 2 * scale;
  const x = Math.floor(worldX), y = Math.floor(worldY);
  const tiles: { input: Buffer; left: number; top: number }[] = [];
  let streetMap = process.env.GEOFLORA_OFFLINE_MAP !== "1";
  if (streetMap) {
    const fetched = await Promise.allSettled([-1, 0, 1].flatMap(dy => [-1, 0, 1].map(async dx => {
      const tx = ((x + dx) % scale + scale) % scale, ty = Math.max(0, Math.min(scale - 1, y + dy));
      const url = `https://tile.openstreetmap.org/${z}/${tx}/${ty}.png`;
      let input = tileCache.get(url);
      if (!input) {
        const response = await fetch(url, { headers: { "User-Agent": "GeoFlora/0.1 local research report export" }, signal: AbortSignal.timeout(4000) });
        if (!response.ok) throw Error("Map tile unavailable");
        input = await sharp(Buffer.from(await response.arrayBuffer()), { limitInputPixels: 1_000_000 }).resize(256, 256).png().toBuffer();
        if (tileCache.size >= 128) tileCache.delete(tileCache.keys().next().value!);
        tileCache.set(url, input);
      }
      return { input, left: (dx + 1) * 256, top: (dy + 1) * 256 };
    })));
    streetMap = fetched.every(result => result.status === "fulfilled");
    for (const result of fetched) if (result.status === "fulfilled") tiles.push(result.value);
  }
  const px = (worldX - x + 1) * 256, py = (worldY - y + 1) * 256;
  const pin = Buffer.from(`<svg width="768" height="768"><circle cx="${px}" cy="${py}" r="44" fill="white" stroke="#0d2618" stroke-width="5"/></svg>`);
  const thumbnail = await sharp(photo).resize(76, 76, { fit: "cover" }).ensureAlpha().composite([{ input: Buffer.from('<svg width="76" height="76"><circle cx="38" cy="38" r="38" fill="white"/></svg>'), blend: "dest-in" }]).png().toBuffer();
  const base = sharp({ create: { width: 768, height: 768, channels: 3, background: "#eaf0e4" } });
  const composite = await base.composite([...(streetMap ? tiles : []), { input: pin, left: 0, top: 0 }, { input: thumbnail, left: Math.round(px - 38), top: Math.round(py - 38) }]).png().toBuffer();
  const image = await sharp(composite).extract({ left: Math.round(Math.max(0, Math.min(256, px - 256))), top: Math.round(Math.max(0, Math.min(468, py - 150))), width: 512, height: 300 }).png().toBuffer();
  return { image, streetMap };
}

// ---------- Design ----------
const W = 595, H = 842, M = 40, CW = W - 2 * M;
const INK = rgb(0.05, 0.15, 0.09), TEXT = rgb(0.2, 0.26, 0.23), MUTED = rgb(0.4, 0.45, 0.41), LINE = rgb(0.87, 0.9, 0.85), PAPER = rgb(0.95, 0.96, 0.94), LIME = rgb(0.78, 0.86, 0.68), WHITE = rgb(1, 1, 1);
const STRONG: Record<ReportResult, RGB> = { target: rgb(0.72, 0.13, 0.13), other: rgb(0.08, 0.36, 0.68), uncertain: rgb(0.62, 0.42, 0.06), rejected: rgb(0.45, 0.45, 0.45) };
const SOFT: Record<ReportResult, RGB> = { target: rgb(0.99, 0.93, 0.93), other: rgb(0.92, 0.95, 0.99), uncertain: rgb(1, 0.96, 0.88), rejected: rgb(0.94, 0.94, 0.94) };
const HEADLINE: Record<ReportResult, string> = { target: "TARGET INVASIVE SPECIES", other: "NOT A TARGET SPECIES", uncertain: "NOT SURE", rejected: "REJECTED BY AN ADMINISTRATOR" };

type Fonts = { regular: PDFFont; bold: PDFFont; italic: PDFFont };
type Report = ReturnType<typeof reportSummary>;
interface Candidate { species?: { id?: string; scientific_name?: string; common_name?: string }; confidence?: number }
interface Prediction { status?: string; method?: string; confidence?: number | null; confidence_threshold?: number; model_version?: string; species?: { id?: string; scientific_name?: string; common_name?: string } | null; candidates?: Candidate[] }

class Writer {
  page!: PDFPage;
  y = 0;
  pages = 0;
  constructor(private pdf: PDFDocument, private f: Fonts, private clean: (value: string) => string) { this.newPage(); }
  newPage() {
    this.page = this.pdf.addPage([W, H]); this.pages++;
    this.y = H - M;
    if (this.pages > 1) { this.page.drawRectangle({ x: 0, y: H - 6, width: W, height: 6, color: INK }); this.y = H - 34; }
  }
  ensure(height: number) { if (this.y - height < 50) this.newPage(); }
  lines(value: string, font: PDFFont, size: number, width: number) {
    const out: string[] = [];
    for (const paragraph of this.clean(value).split("\n")) {
      let line = "";
      for (const word of paragraph.split(/\s+/).filter(Boolean)) {
        for (const segment of word.match(/.{1,95}/g) ?? [""]) {
          const next = line ? `${line} ${segment}` : segment;
          if (font.widthOfTextAtSize(next, size) > width && line) { out.push(line); line = segment; } else line = next;
        }
      }
      out.push(line);
    }
    return out;
  }
  // Wrapped text at the cursor; returns the height used.
  para(value: string, { x = M, width = CW, size = 10, font = this.f.regular, color = TEXT, leading = 1.45, after = 6 } = {}) {
    const lines = this.lines(value, font, size, width);
    for (const line of lines) { this.ensure(size * leading); this.page.drawText(line, { x, y: this.y - size, size, font, color }); this.y -= size * leading; }
    this.y -= after;
  }
  heading(value: string) {
    this.ensure(40); this.y -= 6;
    this.page.drawText(this.clean(value.toUpperCase()), { x: M, y: this.y - 9, size: 9, font: this.f.bold, color: INK });
    this.page.drawLine({ start: { x: M, y: this.y - 15 }, end: { x: M + CW, y: this.y - 15 }, thickness: 0.8, color: LINE });
    this.y -= 26;
  }
  bullets(items: string[], size = 9.5) {
    for (const item of items) {
      const lines = this.lines(item, this.f.regular, size, CW - 14);
      this.ensure(lines.length * size * 1.45);
      this.page.drawCircle({ x: M + 4, y: this.y - size * 0.62, size: 1.6, color: MUTED });
      for (const line of lines) { this.page.drawText(line, { x: M + 14, y: this.y - size, size, font: this.f.regular, color: TEXT }); this.y -= size * 1.45; }
      this.y -= 2;
    }
    this.y -= 4;
  }
}

const speciesId = (name?: string | null) => (name ?? "").trim().toLowerCase().replace(/\s+/g, "_");
const fit = (image: PDFImage, width: number, height: number) => image.scaleToFit(width, height);

export async function createReportPdf(report: Report, photo: Buffer) {
  const pdf = await PDFDocument.create();
  pdf.setTitle(`GeoFlora sighting report ${report.id}`); pdf.setCreator("GeoFlora"); pdf.setAuthor("GeoFlora");
  const f: Fonts = { regular: await pdf.embedFont(StandardFonts.Helvetica), bold: await pdf.embedFont(StandardFonts.HelveticaBold), italic: await pdf.embedFont(StandardFonts.HelveticaOblique) };
  const characters = new Set(f.regular.getCharacterSet());
  const clean = (value: string) => [...value.replace(/[‘’]/g, "'").replace(/[“”]/g, '"').replace(/[–—]/g, "-").replace(/±/g, "+/-")].map(char => characters.has(char.codePointAt(0)!) || char === "\n" ? char : " ").join("");
  const w = new Writer(pdf, f, clean);
  const date = (value: string) => new Date(value).toLocaleString("en-PH", { timeZone: "Asia/Manila", dateStyle: "long", timeStyle: "short" });

  const result = report.result as ReportResult;
  const prediction = (report.prediction ?? null) as Prediction | null;
  const reviewed = report.verifiedSpecies?.scientificName;
  const scientific = reviewed || (report.species !== "unknown" ? report.species : report.possibleSpecies ?? "");
  const info: SpeciesInformation | undefined = speciesInformation[speciesId(scientific)] ?? speciesInformation[prediction?.species?.id ?? ""];
  const common = report.verifiedSpecies?.commonName || info?.commonNames?.[0] || prediction?.species?.common_name || "";
  const title = result === "uncertain" && !reviewed ? (scientific ? `Possibly ${common || scientific}` : "Unidentified plant") : common || scientific || "Unidentified plant";
  const score = typeof prediction?.confidence === "number" ? prediction.confidence * 100 : null;
  const threshold = typeof prediction?.confidence_threshold === "number" ? Math.round(prediction.confidence_threshold * 100) : null;

  // Header band
  w.page.drawRectangle({ x: 0, y: H - 86, width: W, height: 86, color: INK });
  w.page.drawText("geoflora", { x: M, y: H - 50, size: 24, font: f.bold, color: WHITE });
  w.page.drawText(".", { x: M + f.bold.widthOfTextAtSize("geoflora", 24), y: H - 50, size: 24, font: f.bold, color: LIME });
  w.page.drawText("Philippine invasive plant monitoring", { x: M, y: H - 68, size: 8.5, font: f.regular, color: rgb(0.8, 0.86, 0.8) });
  const right = (value: string, y: number, size: number, font: PDFFont, color: RGB) => w.page.drawText(clean(value), { x: W - M - font.widthOfTextAtSize(clean(value), size), y, size, font, color });
  right("PLANT SIGHTING REPORT", H - 40, 9, f.bold, LIME);
  right(`Reference ${report.id}`, H - 55, 8, f.regular, WHITE);
  right(`Generated ${date(new Date().toISOString())}`, H - 68, 8, f.regular, rgb(0.8, 0.86, 0.8));
  w.y = H - 86 - 22;

  // Result banner
  const bannerH = 96, top = w.y;
  w.page.drawRectangle({ x: M, y: top - bannerH, width: CW, height: bannerH, color: SOFT[result] });
  w.page.drawRectangle({ x: M, y: top - bannerH, width: 6, height: bannerH, color: STRONG[result] });
  w.page.drawText(HEADLINE[result], { x: M + 20, y: top - 22, size: 9, font: f.bold, color: STRONG[result] });
  w.page.drawText(clean(title).slice(0, 48), { x: M + 20, y: top - 48, size: 22, font: f.bold, color: INK });
  if (scientific && title !== scientific) w.page.drawText(clean(scientific), { x: M + 20, y: top - 66, size: 11, font: f.italic, color: TEXT });
  const statusLine = report.status === "verified" ? `Approved by an administrator${report.verifiedAt ? ` on ${date(report.verifiedAt)}` : ""}` : report.status === "rejected" ? "Rejected by an administrator" : `Identified by GeoFlora AI${prediction?.model_version ? ` (${prediction.model_version})` : ""}`;
  w.page.drawText(clean(statusLine), { x: M + 20, y: top - 84, size: 8.5, font: f.regular, color: MUTED });
  if (score !== null && prediction?.method !== "verified_reference") {
    const s = score.toFixed(1);
    w.page.drawText(s, { x: M + CW - 20 - f.bold.widthOfTextAtSize(s, 30), y: top - 52, size: 30, font: f.bold, color: STRONG[result] });
    const l1 = "AI score", l2 = threshold !== null ? `sure from ${threshold}` : "";
    w.page.drawText(l1, { x: M + CW - 20 - f.regular.widthOfTextAtSize(l1, 8.5), y: top - 68, size: 8.5, font: f.regular, color: MUTED });
    if (l2) w.page.drawText(l2, { x: M + CW - 20 - f.regular.widthOfTextAtSize(l2, 8.5), y: top - 80, size: 8.5, font: f.regular, color: MUTED });
  }
  w.y = top - bannerH - 18;

  // Photo + details
  const colTop = w.y, photoW = 250, photoH = 230;
  w.page.drawRectangle({ x: M, y: colTop - photoH, width: photoW, height: photoH, color: INK });
  const photograph = await pdf.embedJpg(Uint8Array.from(photo)), size = fit(photograph, photoW - 12, photoH - 12);
  w.page.drawImage(photograph, { x: M + (photoW - size.width) / 2, y: colTop - photoH + (photoH - size.height) / 2, width: size.width, height: size.height });
  const method: Record<string, string> = { gps: "device GPS", manual: "typed coordinates", map_pin: "pin placed on the map", photo_gps: "GPS saved in the photo" };
  const details: [string, string][] = [
    ["Date and time observed", `${date(report.observedAt)}`],
    ["Place", report.placeName || "Not named"],
    ["Coordinates", `${report.latitude?.toFixed(6)}, ${report.longitude?.toFixed(6)}`],
    ["Location from", `${method[report.locationMethod] ?? report.locationMethod}${report.locationAccuracy !== null ? ` (about +/-${Math.round(report.locationAccuracy)} m)` : ""}`],
    ["Report saved", date(report.submittedAt)],
    ...(info?.family ? [["Family", info.family] as [string, string]] : []),
    ...(info?.nativeRange ? [["Native to", info.nativeRange] as [string, string]] : []),
  ];
  let dy = colTop; const dx = M + photoW + 22, dWidth = CW - photoW - 22;
  for (const [label, value] of details) {
    w.page.drawText(label.toUpperCase(), { x: dx, y: dy - 8, size: 7.5, font: f.bold, color: MUTED });
    const lines = w.lines(value, f.regular, 10.5, dWidth);
    lines.forEach((line, i) => w.page.drawText(line, { x: dx, y: dy - 22 - i * 13, size: 10.5, font: f.regular, color: INK }));
    dy -= 22 + lines.length * 13 + 4;
  }
  w.y = Math.min(colTop - photoH, dy) - 20;

  // Map
  const map = await locationMap(report.latitude ?? 0, report.longitude ?? 0, photo);
  const mapImage = await pdf.embedPng(Uint8Array.from(map.image)), mapH = 210;
  w.ensure(mapH + 30);
  w.heading("Where the plant was found");
  w.page.drawImage(mapImage, { x: M, y: w.y - mapH, width: CW, height: mapH });
  w.page.drawRectangle({ x: M, y: w.y - mapH, width: CW, height: mapH, borderColor: LINE, borderWidth: 1 });
  w.y -= mapH + 6;
  w.para(`${map.streetMap ? "Map data (c) OpenStreetMap contributors." : "Offline location diagram; the photo marks the recorded coordinates."} Open in a browser: openstreetmap.org/?mlat=${report.latitude?.toFixed(6)}&mlon=${report.longitude?.toFixed(6)}`, { size: 7.5, color: MUTED });

  // About the species
  if (info) {
    w.heading(result === "uncertain" && !reviewed ? `About the closest match: ${scientific}` : `About ${common ? `${common} (${scientific})` : scientific}`);
    if (info.statusText) w.para(info.statusText + ".", { size: 9.5, font: f.bold, color: info.ecologicalStatus === "target_invasive" ? STRONG.target : STRONG.other });
    if (info.description) w.para(info.description);
    if (info.features?.length) { w.para("How to recognise it", { size: 9.5, font: f.bold, color: INK, after: 3 }); w.bullets(info.features); }
    if (info.impact) { w.para("Why it matters", { size: 9.5, font: f.bold, color: INK, after: 3 }); w.para(info.impact); }
    if (info.lookalikes?.length) { w.para("Easily confused with", { size: 9.5, font: f.bold, color: INK, after: 3 }); w.bullets(info.lookalikes.map(other => `${other.name}: ${other.howToTell}`)); }
  } else if (report.description) { w.heading("Description"); w.para(report.description); }

  // AI matches
  const candidates = (prediction?.candidates ?? []).filter(candidate => typeof candidate.confidence === "number").slice(0, 3);
  if (candidates.length) {
    w.heading("Top AI matches");
    for (const candidate of candidates) {
      w.ensure(26);
      const name = clean(`${candidate.species?.common_name || candidate.species?.scientific_name || "Unknown"}  ${candidate.species?.common_name ? candidate.species.scientific_name ?? "" : ""}`);
      const value = (candidate.confidence! * 100).toFixed(1);
      w.page.drawText(name, { x: M, y: w.y - 9, size: 9.5, font: f.regular, color: TEXT });
      w.page.drawText(value, { x: M + CW - f.bold.widthOfTextAtSize(value, 9.5), y: w.y - 9, size: 9.5, font: f.bold, color: INK });
      w.page.drawRectangle({ x: M, y: w.y - 17, width: CW, height: 4, color: PAPER });
      w.page.drawRectangle({ x: M, y: w.y - 17, width: Math.max(2, CW * candidate.confidence!), height: 4, color: INK });
      w.y -= 26;
    }
    if (threshold !== null) w.para(`GeoFlora counts the top match as sure from a score of ${threshold}.`, { size: 8, color: MUTED });
  }

  // Contributor notes
  if (report.plantDescription || report.notes || report.suggestedSpecies) {
    w.heading("Notes from the reporter");
    if (report.suggestedSpecies) w.para(`Species name given: ${report.suggestedSpecies}`);
    if (report.plantDescription && report.plantDescription !== info?.description) w.para(report.plantDescription);
    if (report.notes) w.para(report.notes);
  }

  // References
  const references = [...new Set([...(info?.source?.url ? [`${info.source.label}: ${info.source.url}`] : []), ...(info?.references ?? []), ...report.citations.filter(url => !info?.source?.url || url !== info.source.url)])];
  if (references.length) { w.heading("References"); w.bullets(references, 8.5); }

  const total = pdf.getPageCount();
  for (const [index, item] of pdf.getPages().entries()) {
    item.drawLine({ start: { x: M, y: 34 }, end: { x: W - M, y: 34 }, thickness: 0.6, color: LINE });
    item.drawText(clean(`GeoFlora  |  ${RESULT_LABEL[result]}  |  ${report.id}`), { x: M, y: 22, size: 7.5, font: f.regular, color: MUTED });
    const p = `Page ${index + 1} of ${total}`;
    item.drawText(p, { x: W - M - f.regular.widthOfTextAtSize(p, 7.5), y: 22, size: 7.5, font: f.regular, color: MUTED });
  }
  return pdf.save();
}
