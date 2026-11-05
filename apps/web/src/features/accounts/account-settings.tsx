"use client";
import { useState, type FormEvent } from "react";
import { KeyRound } from "lucide-react";
import { roleLabel, useAccount } from "../../components/auth-gate";

export default function AccountSettings() {
  const { user } = useAccount();
  const [current, setCurrent] = useState(""), [next, setNext] = useState(""), [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false), [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  async function submit(event: FormEvent) {
    event.preventDefault(); setMessage(null);
    if (next !== confirm) { setMessage({ ok: false, text: "The new passwords do not match." }); return; }
    setBusy(true);
    try {
      const response = await fetch("/api/auth", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action: "change-password", currentPassword: current, password: next }) });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw Error(data.detail || "Password could not be changed.");
      setCurrent(""); setNext(""); setConfirm("");
      setMessage({ ok: true, text: "Password changed. Your other signed-in sessions were signed out." });
    } catch (error) { setMessage({ ok: false, text: error instanceof Error ? error.message : "Password could not be changed." }); } finally { setBusy(false); }
  }
  return <section className="pg">
    <header className="pg-head"><div><span className="content-eyebrow">Your account</span><h1>Account settings</h1><p>Manage your password and sessions.</p></div></header>
    <div className="grid items-start gap-3 lg:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)]">
      <div className="pg-ink">
        <span className="grid h-16 w-16 place-items-center rounded-full bg-[#c6dcae] text-[22px] font-bold uppercase text-[#0d2618]" aria-hidden="true">{user.username.slice(0, 2)}</span>
        <p className="mt-5 text-[22px] font-semibold">{user.username}</p>
        <span className="mt-2 inline-flex rounded-full bg-white/10 px-3 py-1 text-[12px] font-semibold text-[#c6dcae]">{roleLabel(user.role)}</span>
        <p className="mt-5 text-[13px] leading-6 text-white/70">Role: {roleLabel(user.role)}. Sessions expire after eight hours. Only an administrator can change roles.</p>
      </div>
      <form onSubmit={submit} className="pg-card"><fieldset disabled={busy} className="grid gap-4">
        <h2 className="pg-card-title"><span className="pg-num"><KeyRound size={14} /></span>Change password</h2>
        <label className="admin-field">Current password<input className="admin-input" type="password" autoComplete="current-password" required maxLength={128} value={current} onChange={event => setCurrent(event.target.value)} /></label>
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="admin-field">New password<input className="admin-input" type="password" autoComplete="new-password" required minLength={10} maxLength={128} value={next} onChange={event => setNext(event.target.value)} /><small>At least 10 characters.</small></label>
          <label className="admin-field">Confirm new password<input className="admin-input" type="password" autoComplete="new-password" required minLength={10} maxLength={128} value={confirm} onChange={event => setConfirm(event.target.value)} /></label>
        </div>
        {message && <p role={message.ok ? "status" : "alert"} className={`content-notice !mt-0 ${message.ok ? "" : "is-error"}`}>{message.text}</p>}
        <button className="content-primary-button justify-center">{busy ? "Please wait..." : "Change password"}</button>
      </fieldset></form>
    </div>
  </section>;
}
