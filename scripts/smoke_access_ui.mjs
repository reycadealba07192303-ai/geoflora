// Part 7 browser checks against an isolated 5174 app (empty geoflora_access_ui_validation database) and Chrome CDP on 9317.
// Admin setup, Manage accounts (promote + reset code), reset-code sign-in on mobile, reviewer navigation.
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
const hasButton = text => evaluate(`Array.from(document.querySelectorAll('button')).some(b => b.textContent.trim() === ${JSON.stringify(text)} && b.getClientRects().length > 0)`);
async function screenshot(name) { const result = await command("Page.captureScreenshot", { format: "png" }); await writeFile(`storage/logs/ui-preview/${name}.png`, Buffer.from(result.data, "base64")); }

const adminPassword = randomBytes(15).toString("hex"), reviewerPassword = randomBytes(15).toString("hex"), newPassword = randomBytes(15).toString("hex");
const registered = await fetch(BASE + "/api/auth", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action: "register", username: "rita_ui", password: reviewerPassword }) });
await command("Page.enable");
await command("Emulation.setDeviceMetricsOverride", { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false });
await command("Page.navigate", { url: BASE });
await wait("document.querySelector('h1')?.textContent === 'Set up your workspace'");
check(registered.status === 409, "registration is unavailable before the first administrator exists");
await type("input[autocomplete=username]", "owner_ui"); await type("input[type=password]", adminPassword);
await evaluate("document.querySelector('form').requestSubmit()");
await wait("!!document.querySelector('.flora-nav-item')");
check(await hasButton("Manage accounts") && await hasButton("Review & training"), "administrator navigation includes Manage accounts and Review & training");
const rita = await fetch(BASE + "/api/auth", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action: "register", username: "rita_ui", password: reviewerPassword }) });
check(rita.status === 200, "a contributor registers after setup");

await clickText("Manage accounts"); await wait("document.body.textContent.includes('rita_ui')");
check(await evaluate("document.querySelector('select[id^=role-]:disabled') !== null"), "the administrator cannot change their own role");
await evaluate(`(() => { const select = Array.from(document.querySelectorAll('select')).find(s => s.id && document.querySelector('label[for=' + s.id + ']').textContent.includes('rita_ui')); const setter = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set; setter.call(select, 'reviewer'); select.dispatchEvent(new Event('change', { bubbles: true })); })()`);
await wait(`Array.from(document.querySelectorAll('select')).some(s => document.querySelector('label[for=' + s.id + ']')?.textContent.includes('rita_ui') && s.value === 'reviewer')`);
check(true, "administrator promotes the contributor to reviewer from Manage accounts");
await evaluate(`Array.from(document.querySelectorAll('#workspace-content .surface-card > div')).find(row => row.textContent.includes('rita_ui')).querySelector('button:last-of-type').click()`);
await wait("/[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}/.test(document.body.textContent)");
const code = await evaluate("document.body.textContent.match(/[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}/)[0]");
check(await evaluate("document.body.textContent.includes('shown only once')"), "issued reset code is shown once with its expiry");
await screenshot("accounts-admin-desktop");

await clickText("Sign out"); await wait("!!document.querySelector('input[type=password]')");
await command("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 2, mobile: true });
await clickText("Forgot your password?");
await wait("document.querySelector('h1')?.textContent === 'Reset your password' && !!document.querySelector('input[autocomplete=one-time-code]')");
check(await evaluate("document.documentElement.scrollWidth <= 390"), "reset screen fits a 390px mobile viewport");
await screenshot("accounts-reset-mobile");
await type("input[autocomplete=username]", "rita_ui"); await type("input[autocomplete=one-time-code]", code); await type("input[type=password]", newPassword);
await evaluate("document.querySelector('form').requestSubmit()");
await wait("!!document.querySelector('.flora-nav-item')");
check(await evaluate("document.querySelector('h1')?.textContent === 'Label review'"), "reset code signs the reviewer in to the label review page");
check(await evaluate("!document.body.textContent.includes('Automatic training')"), "reviewer page hides training controls");
await evaluate("document.querySelector('[aria-label=\"Open navigation\"]').click()"); await pause(300);
check(await hasButton("Review & training") && !await hasButton("Manage accounts") && await hasButton("Account settings"), "reviewer navigation has review and account settings but not Manage accounts");
check(await evaluate("document.body.textContent.includes('rita_ui · Reviewer')"), "sidebar shows the reviewer role");
await screenshot("accounts-reviewer-mobile-nav");
await clickText("Account settings"); await wait("document.querySelector('h1')?.textContent === 'Account settings'");
check(await evaluate("document.documentElement.scrollWidth <= 390 && !!document.querySelector('input[autocomplete=current-password]')"), "account settings offers password change and fits 390px");

await writeFile("docs/part-7-access-browser-smoke.json", JSON.stringify({ checkedAt: new Date().toISOString(), checks, screenshots: ["accounts-admin-desktop", "accounts-reset-mobile", "accounts-reviewer-mobile-nav"].map(name => `storage/logs/ui-preview/${name}.png`) }, null, 2));
socket.close();
