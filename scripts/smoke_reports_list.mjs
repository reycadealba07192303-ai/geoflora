// Reports list checks against an isolated 5174 app (geoflora_reports_ui_validation seeded with the Part 10 fixtures)
// and Chrome CDP on 9317. Usage: node scripts/smoke_reports_list.mjs <path to axe.min.js>
import { readFile, writeFile } from "node:fs/promises";
import { randomBytes } from "node:crypto";

const BASE = "http://127.0.0.1:5174", axeSource = await readFile(process.argv[2], "utf8");
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
const clickText = text => evaluate(`Array.from(document.querySelectorAll('button')).find(b => b.textContent.trim().startsWith(${JSON.stringify(text)}) && b.getClientRects().length).click()`);
const rows = "document.querySelectorAll('#workspace-content ul li button').length";

await command("Page.enable");
await command("Emulation.setDeviceMetricsOverride", { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false });
await command("Page.navigate", { url: BASE });
await wait("document.querySelector('h1')?.textContent === 'Set up your workspace'");
await type("input[autocomplete=username]", "reports_admin"); await type("input[type=password]", randomBytes(15).toString("hex"));
await evaluate("document.querySelector('form').requestSubmit()");
await wait("!!document.querySelector('.flora-nav-item')");
await clickText("All reports"); await wait(`${rows} > 0`);
check(await evaluate(`${rows} === 18 && document.body.textContent.includes('All (18)') && document.body.textContent.includes('Awaiting review (2)') && document.body.textContent.includes('Correction requested (1)') && document.body.textContent.includes('Verified (14)') && document.body.textContent.includes('Not verified (1)')`), "lists every non-withdrawn report in all statuses with per-status counts");
await clickText("Awaiting review"); await wait(`${rows} === 2`);
check(await evaluate("Array.from(document.querySelectorAll('#workspace-content ul li')).every(li => li.textContent.includes('Awaiting review'))"), "status filter shows only reports awaiting review");
await clickText("All ("); await type("input[placeholder='Search species or place']", "pontederia"); await wait(`${rows} === 3`);
check(true, "search narrows the list by species");
await evaluate("document.querySelector('#workspace-content ul li button').click()");
await wait("document.body.textContent.includes('Identification record')");
check(await evaluate("location.search.includes('report=')"), "selecting a report opens its saved report page");
await evaluate("history.back()"); await pause(500);
await clickText("All reports"); await wait(`${rows} > 0`);
if (!await evaluate("typeof axe !== 'undefined'")) await evaluate(axeSource + ";true");
const violations = await evaluate(`axe.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] } }).then(r => r.violations.map(v => v.id + ":" + v.impact))`);
check(violations.length === 0, `no axe WCAG A/AA violations on the reports page (${violations.join(", ") || "none"})`);
await command("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 2, mobile: true }); await pause(400);
check(await evaluate("document.documentElement.scrollWidth <= 390 && Array.from(document.querySelectorAll('.flora-mobile-dock button')).some(b => b.textContent.includes('Reports'))"), "fits 390px and the mobile dock links to Reports");
const shot = await command("Page.captureScreenshot", { format: "png" }); await writeFile("storage/logs/ui-preview/reports-list-mobile.png", Buffer.from(shot.data, "base64"));
await writeFile("docs/reports-list-browser-smoke.json", JSON.stringify({ checkedAt: new Date().toISOString(), checks }, null, 2));
socket.close();
