const fs = require("node:fs");
const { PDFDocument, PDFRawStream, PDFName, decodePDFRawStream } = require("../apps/web/node_modules/pdf-lib");

(async () => {
  const document = await PDFDocument.load(fs.readFileSync(process.argv[2]));
  let images = 0, text = "";
  for (const [, object] of document.context.enumerateIndirectObjects()) {
    if (!(object instanceof PDFRawStream)) continue;
    if (object.dict.get(PDFName.of("Subtype")) === PDFName.of("Image")) { images++; continue; }
    try {
      const stream = Buffer.from(decodePDFRawStream(object).decode()).toString("latin1");
      for (const match of stream.matchAll(/<([0-9A-F]+)>/gi)) text += Buffer.from(match[1], "hex").toString("latin1") + "\n";
    } catch { /* Non-text resources do not affect report content checks. */ }
  }
  for (const expected of ["FIELD REPORT", "Description", "Coordinates:", "Observed:", "Report created:", "Where the plant was found", "Species references", "iucngisd.org"]) {
    if (!text.includes(expected)) throw Error(`PDF is missing ${expected}`);
  }
  if (images < 2) throw Error("PDF needs both plant photograph and location map");
  console.log(JSON.stringify({ pages: document.getPageCount(), images, requiredTextPresent: true, mapMode: text.includes("Map data (c) OpenStreetMap") ? "street_map" : "offline_location_diagram" }));
})().catch(error => { console.error(error.message); process.exit(1); });
