// Part 8 browser checks against an isolated 5174 app (empty geoflora_part8_ui_validation database) and Chrome CDP on 9317.
// Usage: node scripts/smoke_part8_ui.mjs <path-to-test-photo.png>
// Map-pin placement in the report form, owner correction and withdrawal on a 390px mobile viewport.
import { writeFile } from "node:fs/promises";
import { randomBytes } from "node:crypto";

const BASE = "http://127.0.0.1:5174", photoPath = process.argv[2];
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
const fits = "document.documentElement.scrollWidth <= 390";
async function tapMap(selector, dx = 0, dy = 0) {
  await evaluate(`document.querySelector(${JSON.stringify(selector)}).scrollIntoView({ block: "center" })`); await pause(300);
  const box = await evaluate(`(() => { const r = document.querySelector(${JSON.stringify(selector)}).getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; })()`);
  for (const type of ["mousePressed", "mouseReleased"]) await command("Input.dispatchMouseEvent", { type, x: box.x + dx, y: box.y + dy, button: "left", clickCount: 1 });
}

await command("Page.enable"); await command("DOM.enable");
await command("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 2, mobile: true });
await command("Page.navigate", { url: BASE });
// Signed-out visitors land on the landing page first.
await wait("Array.from(document.querySelectorAll('button')).some(b => b.textContent.trim().startsWith('Set up workspace'))");
await evaluate("Array.from(document.querySelectorAll('button')).find(b => b.textContent.trim().startsWith('Set up workspace')).click()");
await wait("/^Set up your\\s*workspace/.test(document.querySelector('h1')?.textContent ?? '')");
await type("input[type=email]", "field_owner@example.test"); await type("input[autocomplete=username]", "field_owner"); await type("input[type=password]", randomBytes(15).toString("hex"));
await evaluate("document.querySelector('form').requestSubmit()");
await wait("!!document.querySelector('.flora-nav-item')");
await evaluate("document.querySelector('[aria-label=\"Open navigation\"]').click()"); await pause(300);
// Reports are created from an identification: photo -> Identify -> create report.
await clickText("Identify a plant"); await wait("!!document.querySelector('.identify-page')");
const root = await command("DOM.getDocument"); const input = await command("DOM.querySelector", { nodeId: root.root.nodeId, selector: ".identify-page input[type=file]:not([capture])" });
await command("DOM.setFileInputFiles", { nodeId: input.nodeId, files: [photoPath] });
await wait("!!document.querySelector('.identify-preview img')"); await evaluate("document.querySelector('.identify-submit').click()");
const createReport = "Array.from(document.querySelectorAll('button')).find(b => /^(Create report for this plant|Submit for review and create report)$/.test(b.textContent.trim()))";
await wait(`!!${createReport}`);
if (await evaluate("!!document.querySelector('.identify-feedback textarea')")) await type(".identify-feedback textarea", "Low shrub with clustered orange and pink flowers.");
await evaluate(`${createReport}.click()`); await wait("!!document.querySelector('.location-picker .leaflet-container, .location-picker.leaflet-container')");
await tapMap(".location-picker");
await wait("document.querySelector('input[name=latitude]').value !== '' && !!document.querySelector('.location-pin')");
check(await evaluate("document.body.textContent.includes('Location chosen on the map')"), "tapping the map drops a pin and fills the coordinates");
const first = await evaluate("document.querySelector('input[name=latitude]').value + ',' + document.querySelector('input[name=longitude]').value");
await tapMap(".location-picker", 40, -30);
await wait(`document.querySelector('input[name=latitude]').value + ',' + document.querySelector('input[name=longitude]').value !== ${JSON.stringify(first)}`);
check(true, "tapping again moves the pin and updates the coordinates");
check(await evaluate(fits), "report form with the map picker fits 390px");
await screenshot("part8-map-pin-mobile");
await type("textarea[name=plantDescription]", "Low shrub with clustered orange and pink flowers.");
await evaluate("document.querySelector('input[name=consent]').click(); document.querySelector('form').requestSubmit()");
await wait("document.querySelector('h1')?.textContent.includes('recorded')");
await clickText("View result report"); await wait("document.body.textContent.includes('Identification record')");
check(await evaluate("document.body.textContent.includes('Pin placed on map')"), "saved report shows the map-pin location method");
check(await evaluate("document.body.textContent.includes('Identification record') && document.body.textContent.includes('Model result:')"), "report carries the identification it was created from");

await clickText("Correct report"); await wait("!!document.querySelector('form[aria-label=\"Correct report\"]')");
await evaluate("document.querySelector('form[aria-label=\"Correct report\"] input[maxlength=\"200\"]').focus()");
await command("Input.insertText", { text: "Riverside trail marker 3" });
await evaluate("document.querySelector('form[aria-label=\"Correct report\"]').requestSubmit()");
await wait("!document.querySelector('form[aria-label=\"Correct report\"]') && document.body.textContent.includes('Riverside trail marker 3')");
check(await evaluate("document.body.textContent.includes('Last corrected')"), "owner correction saves and shows the last-corrected time");
check(await evaluate(fits), "corrected report fits 390px");

await clickText("Withdraw report"); await wait("!!document.querySelector('[role=alertdialog]')");
check(await evaluate("document.querySelector('[role=alertdialog]').textContent.includes('cannot be undone')"), "withdrawal asks for confirmation and explains the deletion");
await evaluate("document.querySelector('[role=alertdialog]').scrollIntoView({ block: 'center' })"); await pause(200);
await screenshot("part8-withdraw-confirm-mobile");
await clickText("Yes, withdraw and delete"); await wait("document.body.textContent.includes('Your report was withdrawn.')");
check(true, "withdrawal completes and confirms what was deleted");
await screenshot("part8-withdrawn-mobile");

await writeFile("docs/part-8-sightings-browser-smoke.json", JSON.stringify({ checkedAt: new Date().toISOString(), viewport: "390x844 mobile emulation", checks, screenshots: ["part8-map-pin-mobile", "part8-withdraw-confirm-mobile", "part8-withdrawn-mobile"].map(name => `storage/logs/ui-preview/${name}.png`) }, null, 2));
socket.close();
