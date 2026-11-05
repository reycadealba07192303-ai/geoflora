// Part 11 accessibility, mobile-layout and denied-GPS audit against an isolated 5174 app and Chrome CDP on 9317.
// Usage: node scripts/audit_accessibility_part11.mjs <path to axe.min.js> <identifiable plant photo>
// Runs axe-core (WCAG 2.0/2.1 A and AA rules) on each main page at 1440px desktop and 390px mobile.
import { readFile, writeFile } from "node:fs/promises";
import { randomBytes } from "node:crypto";

const [axePath, photoPath] = process.argv.slice(2);
const BASE = "http://127.0.0.1:5174", axeSource = await readFile(axePath, "utf8");
const tabs = await (await fetch("http://127.0.0.1:9317/json/list")).json();
const socket = new WebSocket(tabs.find(tab => tab.type === "page").webSocketDebuggerUrl);
await new Promise((done, reject) => { socket.onopen = done; socket.onerror = reject; });
let sequence = 0;
const tasks = new Map();
socket.onmessage = event => { const value = JSON.parse(event.data); if (value.id) { const task = tasks.get(value.id); tasks.delete(value.id); value.error ? task.reject(Error(value.error.message)) : task.done(value.result); } };
const command = (method, params = {}) => new Promise((done, reject) => { const id = ++sequence; tasks.set(id, { done, reject }); socket.send(JSON.stringify({ id, method, params })); });
const evaluate = async expression => { const result = await command("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true }); if (result.exceptionDetails) throw Error("Browser script failed: " + (result.exceptionDetails.exception?.description ?? result.exceptionDetails.text)); return result.result.value; };
const pause = ms => new Promise(done => setTimeout(done, ms));
const wait = async expression => { for (let index = 0; index < 200; index++) { if (await evaluate(expression)) return; await pause(100); } throw Error("UI timeout: " + expression); };
async function type(selector, text) { await evaluate(`document.querySelector(${JSON.stringify(selector)}).focus()`); await command("Input.insertText", { text }); }
const clickText = text => evaluate(`Array.from(document.querySelectorAll('button')).find(b => b.textContent.trim().startsWith(${JSON.stringify(text)}) && b.getClientRects().length).click()`);
const viewports = { desktop: { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false }, mobile: { width: 390, height: 844, deviceScaleFactor: 2, mobile: true } };
const results = [], checks = [];
function check(value, message) { if (!value) throw Error(message); checks.push(message); console.log("PASS", message); }

async function audit(page) {
  for (const [name, metrics] of Object.entries(viewports)) {
    await command("Emulation.setDeviceMetricsOverride", metrics); await pause(500);
    if (!await evaluate("typeof axe !== 'undefined'")) await evaluate(axeSource + ";true");
    const outcome = await evaluate(`axe.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] } }).then(r => r.violations.map(v => ({ id: v.id, impact: v.impact, help: v.help, nodes: v.nodes.length, targets: v.nodes.map(n => n.target.join(" ") + (n.any?.[0]?.data?.fgColor ? " [" + n.any[0].data.fgColor + " on " + n.any[0].data.bgColor + ", " + n.any[0].data.contrastRatio + ":1]" : "")) })))`);
    const overflow = await evaluate(`document.documentElement.scrollWidth - ${metrics.width}`);
    results.push({ page, viewport: name, overflowPx: Math.max(0, overflow), violations: outcome });
    console.log(page, name, "overflow", Math.max(0, overflow), "violations", outcome.map(v => `${v.id}(${v.impact}x${v.nodes})`).join(", ") || "none");
  }
  await command("Emulation.setDeviceMetricsOverride", viewports.desktop);
}
async function nav(label) { await evaluate("window.scrollTo(0,0)"); if (await evaluate("innerWidth < 1024")) { await evaluate("document.querySelector('[aria-label=\"Open navigation\"]').click()"); await pause(250); } await clickText(label); await pause(800); }

await command("Page.enable"); await command("DOM.enable");
await command("Emulation.setDeviceMetricsOverride", viewports.desktop);
await command("Page.navigate", { url: BASE });
await wait("document.querySelector('h1')?.textContent === 'Set up your workspace'");
await audit("Setup / sign-in");
await type("input[autocomplete=username]", "a11y_admin"); await type("input[type=password]", randomBytes(15).toString("hex"));
await evaluate("document.querySelector('form').requestSubmit()");
await wait("!!document.querySelector('.flora-nav-item')");
await nav("Overview"); await wait("document.body.textContent.includes('Verified field sightings')"); await audit("Overview");
await nav("Identify a plant"); await wait("!!document.querySelector('.identify-page')"); await audit("Identify");

// Denied GPS: identification -> report hands off without coordinates and explains the manual fallback.
await command("Browser.setPermission", { permission: { name: "geolocation" }, setting: "denied", origin: BASE });
const root = await command("DOM.getDocument"); const input = await command("DOM.querySelector", { nodeId: root.root.nodeId, selector: ".identify-page input[type=file]:not([capture])" });
await command("DOM.setFileInputFiles", { nodeId: input.nodeId, files: [photoPath] });
await wait("!!document.querySelector('.identify-preview img')"); await evaluate("document.querySelector('.identify-submit').click()");
await wait("document.querySelector('h1')?.textContent.includes('discovery') || document.querySelector('h1')?.textContent.includes('find out')");
await audit("Identification result");
await evaluate("Array.from(document.querySelectorAll('textarea')).forEach(t => t.focus())"); await command("Input.insertText", { text: "Shrub with clustered small flowers near the road." });
await clickText(await evaluate("Array.from(document.querySelectorAll('button')).some(b => b.textContent.includes('Create report for this plant')) ? 'Create report for this plant' : 'Submit for review'"));
await wait("!!document.querySelector('input[name=latitude]')");
check(await evaluate("document.querySelector('input[name=latitude]').value === '' && document.querySelector('input[name=longitude]').value === ''"), "denied GPS hands off to the report form without coordinates");
await clickText("Use my location"); await wait("document.body.textContent.includes('Location access is unavailable')");
check(await evaluate("!!document.querySelector('.location-picker') && document.body.textContent.includes('Enter where the plant was found manually')"), "denied GPS shows a clear message and the map-pin/typed fallback");
await audit("Report form (GPS denied)");
await type("input[name=latitude]", "14.6512"); await type("input[name=longitude]", "121.0491");
await evaluate("document.querySelector('input[name=consent]').click(); document.querySelector('form').requestSubmit()");
await wait("document.querySelector('h1')?.textContent.includes('recorded')");
check(true, "report saves with manually entered coordinates after GPS was denied");
await clickText("View result report"); await wait("document.body.textContent.includes('Identification record')"); await audit("Report view");
await nav("Occurrence map"); await wait("document.body.textContent.includes('Reports in these filters')"); await audit("Occurrence map");
await nav("Review & training"); await wait("document.querySelectorAll('article[aria-label^=\"Sighting\"]').length > 0"); await audit("Review queue");
await nav("Species catalog"); await wait("document.querySelectorAll('#workspace-content li.surface-card').length > 0"); await audit("Species catalog");
// Administrators have no Account settings page; contributors and reviewers keep it (see smoke_access_ui.mjs).
await nav("Manage accounts"); await wait("document.body.textContent.includes('a11y_admin')"); await audit("Manage accounts");
await nav("Usability study"); await wait("document.querySelector('h1')?.textContent === 'Usability study'"); await evaluate("document.querySelector('input[type=checkbox]').click()"); await pause(200); await audit("Usability study (consent ticked)");

const serious = results.flatMap(r => r.violations.filter(v => ["serious", "critical"].includes(v.impact)).map(v => ({ page: r.page, viewport: r.viewport, ...v })));
await writeFile("docs/part-11-accessibility-audit.json", JSON.stringify({ checkedAt: new Date().toISOString(), tool: "axe-core 4.10.2 (WCAG 2.0/2.1 A and AA tags)", checks, pages: results, seriousOrCritical: serious.length, overflowing: results.filter(r => r.overflowPx > 0).map(r => `${r.page} (${r.viewport}) +${r.overflowPx}px`) }, null, 2));
console.log("serious/critical:", serious.length, "overflowing:", results.filter(r => r.overflowPx > 0).length);
socket.close();
