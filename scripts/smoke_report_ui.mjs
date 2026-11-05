// Run against the isolated 5174 validation app and a loopback-only Chrome CDP on 9317.
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { resolve } from "node:path";
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
async function clickText(text) { await evaluate(`Array.from(document.querySelectorAll('button')).find(button => button.textContent.trim() === ${JSON.stringify(text)}).click()`); }
async function type(expression, text) { await evaluate(`${expression}.focus()`); await command("Input.dispatchKeyEvent", { type: "keyDown", key: "a", code: "KeyA", modifiers: 2 }); await command("Input.dispatchKeyEvent", { type: "keyUp", key: "a", code: "KeyA", modifiers: 2 }); await command("Input.insertText", { text }); }
async function screenshot(name) { const result = await command("Page.captureScreenshot", { format: "png" }); await writeFile(`storage/logs/ui-preview/${name}.png`, Buffer.from(result.data, "base64")); }
async function upload(path) { const root = await command("DOM.getDocument"); const input = await command("DOM.querySelector", { nodeId: root.root.nodeId, selector: ".identify-page input[type=file]" }); await command("DOM.setFileInputFiles", { nodeId: input.nodeId, files: [path] }); await wait("!!document.querySelector('.identify-preview img')"); await evaluate("document.querySelector('.identify-submit').click()"); await wait("document.querySelector('h1')?.textContent.includes('discovery') || document.querySelector('h1')?.textContent.includes('find out')"); }
async function signOut() { if (await evaluate("innerWidth < 1024")) { await evaluate("document.querySelector('[aria-label=\"Open navigation\"]').click()"); await pause(250); } await clickText("Sign out"); await wait("!!document.querySelector('input[type=password]')"); }

const username = "browser_flow_" + randomBytes(6).toString("hex"), password = randomBytes(20).toString("hex");
const inputs = JSON.parse(await readFile("storage/logs/ui-preview/content-inputs.json", "utf8"));
const downloads = resolve("storage/logs/ui-preview/report-downloads");
await mkdir(downloads, { recursive: true });
try {
  await command("Page.enable"); await command("DOM.enable");
  await command("Emulation.setDeviceMetricsOverride", { width: 1440, height: 1050, deviceScaleFactor: 1, mobile: false });
  await command("Browser.setDownloadBehavior", { behavior: "allow", downloadPath: downloads });
  await command("Page.navigate", { url: "http://127.0.0.1:5174" });
  await wait("!!document.querySelector('input[type=password]') || !!document.querySelector('.flora-nav-item')");
  if (await evaluate("!!document.querySelector('.flora-nav-item')")) await signOut();
  await evaluate("Array.from(document.querySelectorAll('button')).find(button=>button.textContent.includes('New here?')).click()");
  await type("document.querySelector('input[autocomplete=username]')", username); await type("document.querySelector('input[type=password]')", password);
  await evaluate("document.querySelector('form').requestSubmit()"); await wait("!!document.querySelector('.identify-page')");
  await upload(inputs.chromolaena_odorata);
  check(await evaluate("document.querySelector('h2').textContent==='Chromolaena odorata'"), "upload opens a dedicated identified-result screen");
  check(await evaluate("Array.from(document.querySelectorAll('#workspace-content a')).some(link=>link.href.includes('iucngisd.org'))"), "result includes a species citation");
  await screenshot("report-flow-result-desktop");
  await command("Browser.grantPermissions", { origin: "http://127.0.0.1:5174", permissions: ["geolocation"] });
  await command("Emulation.setGeolocationOverride", { latitude: 14.5995, longitude: 120.9842, accuracy: 12 });
  await clickText("Create report for this plant"); await wait("!!document.querySelector('input[name=latitude]')");
  check(await evaluate("document.querySelector('input[name=latitude]').value==='14.5995' && !!document.querySelector('input[name=localTime]').value"), "GPS and observation time fill automatically");
  await evaluate("document.querySelector('input[name=consent]').click(); document.querySelector('form').requestSubmit()");
  await wait("document.querySelector('h1')?.textContent.includes('recorded')");
  check(await evaluate("document.querySelectorAll('#workspace-content button').length===2"), "success screen offers View result report and Create another report");
  await screenshot("report-flow-success-desktop"); await clickText("View result report");
  await wait("!!document.querySelector('#workspace-content .report-location-map')");
  const reportId = await evaluate("new URL(location.href).searchParams.get('report')");
  check(!!reportId && await evaluate("document.querySelector('#workspace-content').textContent.includes('Description') && document.querySelector('.report-location-map').dataset.latitude==='14.5995'"), "saved report includes species, description, location map and timestamps");
  await evaluate("document.querySelector('#workspace-content a[href$=\"/pdf\"]').click()");
  let pdf;
  for (let index = 0; index < 60; index++) { try { pdf = await readFile(resolve(downloads, `geoflora-report-${reportId}.pdf`)); break; } catch { await pause(150); } }
  check(pdf?.subarray(0, 5).toString() === "%PDF-", "Download PDF button saves a real PDF file");
  await command("Page.reload"); await wait("!!document.querySelector('#workspace-content .report-location-map')");
  check(await evaluate("document.querySelector('h1').textContent==='Chromolaena odorata'"), "saved report survives refresh using its report URL");
  await screenshot("report-flow-view-desktop"); await command("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 1, mobile: true }); await pause(250);
  check(await evaluate("document.documentElement.scrollWidth<=390"), "saved report fits a 390px mobile viewport"); await screenshot("report-flow-view-mobile");
  await clickText("Create another report"); await wait("!!document.querySelector('.identify-dropzone')");
  check(await evaluate("!location.search.includes('report=')"), "Create another report resets the upload workflow");
  await upload(inputs.pontederia_crassipes);
  check(await evaluate("document.querySelector('h1').textContent.includes('find out') && document.querySelector('#workspace-content .content-primary-button').disabled"), "uncertain result requires a user description");
  const description = "Floating green plant with rounded leaves and spongy stalks. Browser review fixture " + randomBytes(4).toString("hex");
  await type("document.querySelector('.identify-feedback textarea')", description);
  await screenshot("report-flow-unknown-mobile"); await clickText("Submit for review and create report"); await wait("!!document.querySelector('input[name=latitude]')");
  await evaluate("document.querySelector('input[name=consent]').click(); document.querySelector('form').requestSubmit()"); await wait("document.querySelector('h1')?.textContent.includes('recorded')");
  await clickText("View result report"); await wait("!!document.querySelector('#workspace-content .report-location-map')"); await signOut();
  await command("Emulation.setDeviceMetricsOverride", { width: 1440, height: 1050, deviceScaleFactor: 1, mobile: false });
  await type("document.querySelector('input[autocomplete=username]')", "fixture_admin"); await type("document.querySelector('input[type=password]')", "GeoFlora-Smoke-Only-2026");
  await evaluate("document.querySelector('form').requestSubmit()");
  // A report URL may have survived sign-out; open the admin destination explicitly.
  await wait("!!document.querySelector('.flora-nav-item')");
  await evaluate("Array.from(document.querySelectorAll('.flora-nav-item')).find(button=>button.textContent.includes('Review & training')).click()");
  await wait(`Array.from(document.querySelectorAll('article')).some(article=>article.textContent.includes(${JSON.stringify(description)}))`);
  await evaluate(`window.reviewCard=Array.from(document.querySelectorAll('article')).find(article=>article.textContent.includes(${JSON.stringify(description)})); true`);
  check(await evaluate("window.reviewCard.textContent.includes('Not granted - label review only')"), "Admin can review an unknown report without training consent");
  await evaluate("window.reviewCard.querySelector('select').value='pontederia_crassipes'; window.reviewCard.querySelector('select').dispatchEvent(new Event('change',{bubbles:true}))");
  await type("window.reviewCard.querySelectorAll('textarea')[1]", "Verified water hyacinth in an existing labeled photo; isolated browser workflow check.");
  await evaluate("window.reviewCard.querySelector('input[type=checkbox]').click()"); await screenshot("report-flow-admin-review");
  await evaluate("Array.from(window.reviewCard.querySelectorAll('button')).find(button=>button.textContent.includes('Approve species')).click()"); await wait("!window.reviewCard.isConnected");
  check(true, "Admin approves the species description through the UI");
  await signOut(); await type("document.querySelector('input[autocomplete=username]')", username); await type("document.querySelector('input[type=password]')", password);
  await evaluate("document.querySelector('form').requestSubmit()"); await wait("!!document.querySelector('.identify-page')"); await upload(inputs.pontederia_crassipes);
  check(await evaluate("document.querySelector('#workspace-content').textContent.includes('ADMIN-REVIEWED PHOTO MATCH') && !document.querySelector('.identify-confidence')"), "same approved photo is identified as a reviewed reference, without a fabricated model score");
  await screenshot("report-flow-reviewed-result");
  await writeFile("docs/report-flow-browser-smoke.json", JSON.stringify({ passed: true, database: "geoflora_report_flow_validation_run2", checks }, null, 2));
} finally { await command("Browser.close").catch(() => {}); socket.close(); }
