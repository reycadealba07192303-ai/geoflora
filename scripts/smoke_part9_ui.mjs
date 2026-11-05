// Part 9 browser checks against an isolated 5174 app (geoflora_part9_ui_validation, seeded catalog sample) and Chrome CDP on 9317.
// Verification queue actions, catalog browsing indicators and live Overview counts.
import { writeFile } from "node:fs/promises";
import { randomBytes } from "node:crypto";

const BASE = "http://127.0.0.1:5174";
const tabs = await (await fetch("http://127.0.0.1:9317/json/list")).json();
const socket = new WebSocket(tabs.find(tab => tab.type === "page").webSocketDebuggerUrl);
await new Promise((done, reject) => { socket.onopen = done; socket.onerror = reject; });
let sequence = 0;
const tasks = new Map();
socket.onmessage = event => { const value = JSON.parse(event.data); if (value.id) { const task = tasks.get(value.id); tasks.delete(value.id); value.error ? task.reject(Error(value.error.message)) : task.done(value.result); } };
const command = (method, params = {}) => new Promise((done, reject) => { const id = ++sequence; tasks.set(id, { done, reject }); socket.send(JSON.stringify({ id, method, params })); });
const evaluate = async expression => { const result = await command("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true }); if (result.exceptionDetails) throw Error("Browser script failed: " + result.exceptionDetails.text); return result.result.value; };
const pause = ms => new Promise(done => setTimeout(done, ms));
const wait = async expression => { for (let index = 0; index < 150; index++) { if (await evaluate(expression)) return; await pause(100); } throw Error("UI timeout: " + expression); };
const checks = [];
function check(value, message) { if (!value) throw Error(message); checks.push(message); console.log("PASS", message); }
async function type(expression, text) { await evaluate(`${expression}.focus()`); await command("Input.insertText", { text }); }
const clickText = (text, scope = "document") => evaluate(`Array.from(${scope}.querySelectorAll('button')).find(b => b.textContent.trim().startsWith(${JSON.stringify(text)})).click()`);
async function screenshot(name) { const result = await command("Page.captureScreenshot", { format: "png" }); await writeFile(`storage/logs/ui-preview/${name}.png`, Buffer.from(result.data, "base64")); }
const card = index => `document.querySelectorAll('article[aria-label^="Sighting"]')[${index}]`;

await command("Page.enable");
await command("Emulation.setDeviceMetricsOverride", { width: 1440, height: 1100, deviceScaleFactor: 1, mobile: false });
await command("Page.navigate", { url: BASE });
await wait("document.querySelector('h1')?.textContent === 'Set up your workspace'");
await type("document.querySelector('input[autocomplete=username]')", "owner_review"); await type("document.querySelector('input[type=password]')", randomBytes(15).toString("hex"));
await evaluate("document.querySelector('form').requestSubmit()");
await wait("!!document.querySelector('.flora-nav-item')");
const created = await evaluate(`(async () => {
  const ids = [];
  for (const [index, place] of ["Creek A", "Roadside B"].entries()) {
    const canvas = document.createElement("canvas"); canvas.width = canvas.height = 160;
    const context = canvas.getContext("2d"); context.fillStyle = index ? "#2f6b2f" : "#6b8f2f"; context.fillRect(0, 0, 160, 160); context.fillStyle = "#fff"; context.fillRect(index * 40, 30, 50, 90);
    const blob = await new Promise(done => canvas.toBlob(done, "image/png"));
    const form = new FormData();
    for (const [key, value] of Object.entries({ requestId: crypto.randomUUID(), species: "unknown", plantDescription: "Shrub with orange flower clusters.", latitude: "14.6", longitude: "121.0" + index, locationMethod: "map_pin", placeName: place, observedAt: new Date(Date.now() - 3600e3).toISOString(), consent: "yes" })) form.set(key, value);
    form.set("image", blob, "plant.png");
    const response = await fetch("/api/sightings", { method: "POST", body: form }); ids.push((await response.json()).id);
  }
  return ids;
})()`);
check(created.length === 2 && created.every(Boolean), "two fixture sightings submitted from the browser session");

await clickText("Review & training"); await wait(`document.querySelectorAll('article[aria-label^="Sighting"]').length === 2`);
check(await evaluate("document.body.textContent.includes('Awaiting review2')"), "queue tab shows two sightings awaiting review");
check(await evaluate(`${card(0)}.textContent.includes('ORIGINAL MODEL PREDICTION') && ${card(0)}.textContent.includes('map pin') && ${card(0)}.textContent.includes('Creek A')`), "card shows the original prediction section, location method and place");
await type(`${card(0)}.querySelector('textarea[placeholder^="Why"]')`, "Please add the barangay name.");
await clickText("Request correction", card(0));
await wait("document.body.textContent.includes('Correction requested') && document.body.textContent.includes('Awaiting review2')");
check(true, "request correction keeps the sighting in the awaiting queue, marked as correction requested");
const second = `Array.from(document.querySelectorAll('article[aria-label^="Sighting"]')).find(a => a.textContent.includes('Roadside B'))`;
await evaluate(`(() => { const select = ${second}.querySelector('select'); Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set.call(select, 'lantana_camara'); select.dispatchEvent(new Event('change', { bubbles: true })); })()`);
await type(`${second}.querySelector('textarea[placeholder^="Why"]')`, "Flower clusters and leaves match Lantana.");
await evaluate(`${second}.querySelector('input[type=checkbox]').click()`);
await clickText("Verify sighting", second);
await wait("document.body.textContent.includes('Awaiting review1') && document.body.textContent.includes('Verified1')");
check(true, "verifying a sighting moves it out of the awaiting queue");
await clickText("Verified1"); await wait("document.body.textContent.includes('Reviewer-confirmed species: Lantana camara')");
check(await evaluate("document.body.textContent.includes('Verified by owner_review')"), "verified view shows the confirmed species and the audit entry");
await screenshot("part9-review-verified-desktop");

await clickText("Species catalog"); await wait("document.querySelectorAll('#workspace-content li.surface-card').length > 0");
check(await evaluate("document.body.textContent.includes('Catalog: approved (owner attestation)') && document.body.textContent.includes('not independent per-record taxonomic review')"), "catalog shows owner-attested approval and its limits");
await clickText("Live model species"); await wait("document.querySelectorAll('#workspace-content li.surface-card').length === 3");
check(await evaluate("Array.from(document.querySelectorAll('#workspace-content li.surface-card')).every(li => li.textContent.includes('Live AI model'))"), "live-model filter shows the three supported species with the AI badge");
await clickText("Lantana camara"); await wait("document.body.textContent.includes('References')");
check(await evaluate("Array.from(document.querySelectorAll('#workspace-content a')).some(a => a.href.startsWith('https://doi.org/')) && document.body.textContent.includes('1 verified sighting')"), "expanded entry links its DOI reference and counts the verified sighting");
await screenshot("part9-catalog-desktop");
await command("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 2, mobile: true }); await pause(300);
check(await evaluate("document.documentElement.scrollWidth <= 390"), "catalog fits a 390px mobile viewport");
await screenshot("part9-catalog-mobile");

await command("Emulation.setDeviceMetricsOverride", { width: 1440, height: 1100, deviceScaleFactor: 1, mobile: false });
await evaluate("document.querySelector('[aria-label=\"GeoFlora overview\"]').click()");
await wait("document.body.textContent.includes('Verified field sightings') && !document.body.textContent.includes('…')");
check(await evaluate("!document.body.textContent.includes('18,718') && !document.body.textContent.includes('Image upload is not connected')"), "overview no longer shows the old static counts");
check(await evaluate("(() => { const cards = Array.from(document.querySelectorAll('.metric-card')); const value = label => cards.find(c => c.textContent.includes(label))?.querySelector('.metric-value')?.textContent; return value('Verified field sightings') === '1' && value('Sightings awaiting review') === '1' && value('AI species supported') === '3'; })()"), "overview metric cards show live verified, awaiting and model values");
await screenshot("part9-overview-desktop");

await writeFile("docs/part-9-review-catalog-browser-smoke.json", JSON.stringify({ checkedAt: new Date().toISOString(), checks, screenshots: ["part9-review-verified-desktop", "part9-catalog-desktop", "part9-catalog-mobile", "part9-overview-desktop"].map(name => `storage/logs/ui-preview/${name}.png`) }, null, 2));
socket.close();
