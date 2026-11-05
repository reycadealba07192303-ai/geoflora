// Part 10 browser checks against an isolated 5174 app (geoflora_part10_ui_validation seeded with the Part 10 fixture
// reports) and Chrome CDP on 9317: clustering, filters, pending layer, density grid, charts, empty state, mobile fit.
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
async function type(selector, text) { await evaluate(`document.querySelector(${JSON.stringify(selector)}).focus()`); await command("Input.insertText", { text }); }
const clickText = text => evaluate(`Array.from(document.querySelectorAll('button')).find(b => b.textContent.trim() === ${JSON.stringify(text)}).click()`);
async function screenshot(name) { const result = await command("Page.captureScreenshot", { format: "png" }); await writeFile(`storage/logs/ui-preview/${name}.png`, Buffer.from(result.data, "base64")); }
const stat = label => `Array.from(document.querySelectorAll('[aria-label="Occurrence analytics"] .surface-card')).find(c => c.textContent.startsWith(${JSON.stringify(label)}))?.querySelector('.text-2xl')?.textContent`;
const setSelect = (selector, value) => evaluate(`(() => { const s = document.querySelector(${JSON.stringify(selector)}); Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set.call(s, ${JSON.stringify(value)}); s.dispatchEvent(new Event('change', { bubbles: true })); })()`);
const setDate = (label, value) => evaluate(`(() => { const input = Array.from(document.querySelectorAll('form[aria-label="Map filters"] label')).find(l => l.textContent.startsWith(${JSON.stringify(label)})).querySelector('input'); Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, ${JSON.stringify(value)}); input.dispatchEvent(new Event('input', { bubbles: true })); })()`);

await command("Page.enable");
await command("Emulation.setDeviceMetricsOverride", { width: 1440, height: 1100, deviceScaleFactor: 1, mobile: false });
await command("Page.navigate", { url: BASE });
await wait("document.querySelector('h1')?.textContent === 'Set up your workspace'");
await type("input[autocomplete=username]", "map_owner"); await type("input[type=password]", randomBytes(15).toString("hex"));
await evaluate("document.querySelector('form').requestSubmit()");
await wait("!!document.querySelector('.flora-nav-item')");
await clickText("Occurrence map"); await wait(`${stat("Reports in these filters")} === '14'`);
check(true, "verified layer is the default and counts the 14 verified fixture reports");
await wait("document.querySelectorAll('.occurrence-cluster').length > 0");
const clusters = await evaluate("document.querySelectorAll('.occurrence-cluster').length"), singles = await evaluate("document.querySelectorAll('.sighting-photo-marker').length");
check(clusters >= 1, `nearby reports are clustered at the overview zoom (${clusters} clusters, ${singles} single markers)`);
await evaluate("Array.from(document.querySelectorAll('.occurrence-cluster')).sort((a, b) => Number(b.textContent) - Number(a.textContent))[0].click()");
await wait(`document.querySelectorAll('.sighting-photo-marker').length > ${singles}`);
check(true, "selecting a cluster zooms in and splits it into individual markers");
check(await evaluate("document.querySelectorAll('[aria-label=\"Occurrence analytics\"] figure:first-of-type li').length === 3 && document.querySelectorAll('[role=listitem][aria-label*=\"reports\"]').length === 3"), "species bars and monthly columns render from the analytics");
await evaluate("Array.from(document.querySelectorAll('input[type=checkbox]')).find(i => i.parentElement.textContent.includes('density grid')).click()");
await wait("document.querySelectorAll('.leaflet-overlay-pane path').length === 2");
check(await evaluate("document.body.textContent.includes('1 sparse cell (2 reports) hidden')"), "density grid draws the 2 generalized cells and reports the suppressed sparse cell");
await screenshot("part10-map-desktop");

await setSelect('form[aria-label="Map filters"] select', "lantana camara");
await wait(`${stat("Reports in these filters")} === '7'`);
check(await evaluate("document.querySelectorAll('[aria-label=\"Matching reports\"] button').length === 7"), "species filter narrows both the map list and the analytics");
await evaluate("Array.from(document.querySelectorAll('input[name=layer]'))[1].click()");
await wait(`${stat("Reports in these filters")} === '8'`);
check(await evaluate("document.body.textContent.includes('Unverified layer on') && document.body.textContent.includes('Includes unverified (pending) reports.')"), "including the unverified layer is labeled on the map and in the analytics");
await clickText("Clear filters"); await wait(`${stat("Reports in these filters")} === '17'`);
check(true, "clearing filters keeps the chosen layer (14 verified + 3 awaiting review)");
await setDate("Observed from", "2025-01-01"); await setDate("to", "2025-01-31");
await wait("document.body.textContent.includes('No reports match these filters')");
check(await evaluate(`${stat("Reports in these filters")} === '0'`), "an empty date range shows clear empty states");
await clickText("Clear filters"); await wait(`${stat("Reports in these filters")} === '17'`);
await clickText("Show data table"); await wait("document.querySelectorAll('table').length === 2");
check(await evaluate("document.querySelectorAll('table')[1].textContent.includes('2026-10')"), "data table view lists species and month counts");

await command("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 2, mobile: true }); await pause(400);
check(await evaluate("document.documentElement.scrollWidth <= 390"), "map page with filters and charts fits a 390px mobile viewport");
await evaluate("document.querySelector('[aria-label=\"Occurrence analytics\"]').scrollIntoView()"); await pause(200);
await screenshot("part10-analytics-mobile");
await writeFile("docs/part-10-map-analytics-browser-smoke.json", JSON.stringify({ checkedAt: new Date().toISOString(), checks, screenshots: ["part10-map-desktop", "part10-analytics-mobile"].map(name => `storage/logs/ui-preview/${name}.png`) }, null, 2));
socket.close();
