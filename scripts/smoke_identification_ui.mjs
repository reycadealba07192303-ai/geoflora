// Part 6 browser checks against the isolated 5174 validation app and a loopback-only Chrome CDP on 9317.
// Mobile 390px: camera capture input, identified and uncertain result screens with model version/threshold.
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { randomBytes } from "node:crypto";

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
async function screenshot(name) { const result = await command("Page.captureScreenshot", { format: "png" }); await writeFile(`storage/logs/ui-preview/${name}.png`, Buffer.from(result.data, "base64")); }
async function upload(path, selector) { const root = await command("DOM.getDocument"); const input = await command("DOM.querySelector", { nodeId: root.root.nodeId, selector }); await command("DOM.setFileInputFiles", { nodeId: input.nodeId, files: [path] }); await wait("!!document.querySelector('.identify-preview img')"); await evaluate("document.querySelector('.identify-submit').click()"); await wait("document.querySelector('h1')?.textContent.includes('discovery') || document.querySelector('h1')?.textContent.includes('find out')"); }
const fits = "document.documentElement.scrollWidth<=390";

const inputs = JSON.parse(await readFile("storage/logs/ui-preview/identification-inputs.json", "utf8"));
const username = "browser_ident_" + randomBytes(6).toString("hex"), password = randomBytes(20).toString("hex");
await mkdir("storage/logs/ui-preview", { recursive: true });
await command("Page.enable"); await command("DOM.enable");
await command("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 2, mobile: true });
await command("Page.navigate", { url: "http://127.0.0.1:5174" });
await wait("!!document.querySelector('input[type=password]') || !!document.querySelector('.identify-page')");
if (await evaluate("!!document.querySelector('input[type=password]')")) {
  await evaluate("Array.from(document.querySelectorAll('button')).find(button=>button.textContent.includes('New here?'))?.click()");
  await type("document.querySelector('input[autocomplete=username]')", username); await type("document.querySelector('input[type=password]')", password);
  await evaluate("document.querySelector('form').requestSubmit()");
}
await wait("!!document.querySelector('.identify-page') && document.querySelector('.identify-status')?.textContent.includes('Model ready')");
check(await evaluate("document.querySelector('input[capture=environment]')?.accept==='image/jpeg,image/png,image/webp'"), "rear-camera capture input accepts only supported image types");
check(await evaluate("Array.from(document.querySelectorAll('button')).some(b=>b.textContent.trim()==='Take a photo')"), "Take a photo button is offered beside the file chooser");
check(await evaluate(fits), "identify page fits a 390px mobile viewport");
await screenshot("identification-mobile-start");

await upload(inputs.identified, "input[capture=environment]");
check(await evaluate("document.querySelector('h2')?.textContent==='Chromolaena odorata'"), "camera-input photo produces a real identified result");
check(await evaluate("document.body.textContent.includes('mobilenetv2_v3_seed42') && document.body.textContent.includes('suggestion threshold 80%')"), "identified result shows model version and threshold");
check(await evaluate(fits), "identified result fits 390px");
await screenshot("identification-mobile-identified");

await evaluate("Array.from(document.querySelectorAll('button')).find(b=>b.textContent.includes('Identify another plant')).click()");
await wait("!!document.querySelector('.identify-page')");
await upload(inputs.uncertain, ".identify-page input[type=file]:not([capture])");
check(await evaluate("document.querySelector('h2')?.textContent==='Plant awaiting review'"), "low-score photo is shown as uncertain with no species label");
check(await evaluate("document.body.textContent.includes('below the 80% needed') && document.querySelectorAll('[aria-label=\"Model candidate scores\"] li').length===3"), "uncertain result explains the threshold and lists closest candidates as not a label");
check(await evaluate(fits), "uncertain result fits 390px");
await evaluate("document.querySelector('[aria-label=\"Model candidate scores\"]').scrollIntoView({block:'center'})"); await pause(200);
await screenshot("identification-mobile-uncertain");

await writeFile("docs/part-6-identification-browser-smoke.json", JSON.stringify({ checkedAt: new Date().toISOString(), viewport: "390x844 mobile emulation", checks, screenshots: ["identification-mobile-start", "identification-mobile-identified", "identification-mobile-uncertain"].map(name => `storage/logs/ui-preview/${name}.png`) }, null, 2));
socket.close();
