"use client";
import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { Ban, Check, Copy, Ellipsis, KeyRound, MailCheck, Plus, Search, ShieldCheck, Trash2, UserCheck, UserCog, Users, X } from "lucide-react";
import { roleLabel, useAccount, type Role } from "../../components/auth-gate";

interface Row { id: string; username: string; email: string; role: Role; disabled: boolean; emailVerified: boolean; createdAt: string }
const ROLES: Role[] = ["user", "reviewer", "admin"];
const roleTone: Record<Role, string> = { admin: "tone-violet", reviewer: "tone-blue", user: "tone-green" };
const roleInfo: Record<Role, string> = { user: "Submit sightings and see their own reports.", reviewer: "Also verify labels and see every workspace report.", admin: "Also manage accounts, training and the usability study." };
const FILTERS = [{ id: "all", label: "All" }, { id: "admin", label: "Administrators" }, { id: "reviewer", label: "Reviewers" }, { id: "user", label: "Contributors" }, { id: "disabled", label: "Disabled" }];

export default function ManageAccounts() {
  const { user } = useAccount();
  const [accounts, setAccounts] = useState<Row[] | null>(null), [error, setError] = useState(""), [success, setSuccess] = useState(""), [busy, setBusy] = useState("");
  const [menuId, setMenuId] = useState<string | null>(null);
  const [issued, setIssued] = useState<{ username: string; code: string; expiresInMinutes: number } | null>(null), [copied, setCopied] = useState(false);
  const [query, setQuery] = useState(""), [filter, setFilter] = useState("all"), [creating, setCreating] = useState(false);
  const [newUsername, setNewUsername] = useState(""), [newEmail, setNewEmail] = useState(""), [newPassword, setNewPassword] = useState(""), [newRole, setNewRole] = useState<Role>("user");
  const load = useCallback(async () => {
    try { const response = await fetch("/api/accounts", { cache: "no-store" }); const data = await response.json(); if (!response.ok) throw Error(data.detail); setAccounts(data.accounts); setError(""); }
    catch (e) { setError(e instanceof Error ? e.message : "Accounts are unavailable."); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    const closeOnOutside = (event: PointerEvent) => { if (!(event.target as HTMLElement).closest?.(".account-actions")) setMenuId(null); };
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === "Escape") setMenuId(null); };
    document.addEventListener("pointerdown", closeOnOutside);
    document.addEventListener("keydown", closeOnEscape);
    return () => { document.removeEventListener("pointerdown", closeOnOutside); document.removeEventListener("keydown", closeOnEscape); };
  }, []);
  async function change(id: string, body: Record<string, string>) {
    setBusy(id); setError(""); setMenuId(null);
    try {
      const response = await fetch("/api/accounts", { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id, ...body }) });
      const data = await response.json();
      if (!response.ok) throw Error(data.detail);
      if (data.code) { setIssued(data); setCopied(false); }
      await load();
    } catch (e) { setError(e instanceof Error ? e.message : "The change could not be saved."); } finally { setBusy(""); }
  }
  async function create(event: FormEvent) {
    event.preventDefault(); setBusy("create"); setError(""); setSuccess("");
    try {
      const response = await fetch("/api/accounts", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: newUsername, email: newEmail, password: newPassword, role: newRole }) });
      const data = await response.json(); if (!response.ok) throw Error(data.detail);
      setCreating(false); setNewUsername(""); setNewEmail(""); setNewPassword(""); setNewRole("user"); await load();
      setIssued(null); setSuccess(`Account created for ${data.username}. A verification code was sent to ${data.email}.`);
    } catch (e) { setError(e instanceof Error ? e.message : "The account could not be created."); } finally { setBusy(""); }
  }
  async function remove(row: Row) {
    if (!window.confirm(`Delete ${row.username}? Their reports will be anonymized and their sessions and reset codes removed.`)) return;
    setBusy(row.id); setError(""); setSuccess(""); setMenuId(null);
    try {
      const response = await fetch("/api/accounts", { method: "DELETE", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: row.id }) });
      const data = await response.json(); if (!response.ok) throw Error(data.detail); await load();
    } catch (e) { setError(e instanceof Error ? e.message : "The account could not be deleted."); } finally { setBusy(""); }
  }
  function toggle(row: Row) {
    if (!row.disabled && !window.confirm(`Disable ${row.username}? They are signed out everywhere until an administrator enables the account again.`)) return;
    void change(row.id, { action: row.disabled ? "enable" : "disable" });
  }
  async function copy() {
    if (!issued) return;
    try { await navigator.clipboard.writeText(issued.code); setCopied(true); } catch { setCopied(false); }
  }
  const count = useMemo(() => {
    const rows = accounts ?? [];
    return { all: rows.length, admin: rows.filter(row => row.role === "admin").length, reviewer: rows.filter(row => row.role === "reviewer").length, user: rows.filter(row => row.role === "user").length, disabled: rows.filter(row => row.disabled).length } as Record<string, number>;
  }, [accounts]);
  const shown = (accounts ?? []).filter(row => (filter === "all" || (filter === "disabled" ? row.disabled : row.role === filter)) && `${row.username} ${row.email}`.toLowerCase().includes(query.trim().toLowerCase()));
  const stats = [
    { label: "Accounts", value: count.all, icon: Users, tone: "tone-green" },
    { label: "Administrators", value: count.admin, icon: ShieldCheck, tone: "tone-violet" },
    { label: "Reviewers", value: count.reviewer, icon: UserCheck, tone: "tone-blue" },
    { label: "Disabled", value: count.disabled, icon: Ban, tone: "tone-rose" },
  ];

  return <section className="admin-page accounts-page">
    <header className="admin-header"><div><span className="content-eyebrow">ADMINISTRATION</span><h1>Manage accounts</h1>
      <p>Create accounts, manage access and recover sign-in. Deleting an account anonymizes its reports and removes its sessions.</p></div>
      <div className="admin-header-actions"><button className="admin-btn is-primary" onClick={() => { setCreating(!creating); setError(""); }} aria-expanded={creating}>{creating ? <X size={16} /> : <Plus size={16} />}{creating ? "Close" : "Create account"}</button></div>
    </header>

    <div className="admin-stats" aria-label="Account totals">{stats.map(stat => <div key={stat.label} className="surface-card admin-stat">
      <span className={`admin-icon ${stat.tone}`}><stat.icon size={18} strokeWidth={1.7} /></span>
      <div className="min-w-0"><strong>{accounts ? stat.value : "…"}</strong><p>{stat.label}</p></div>
    </div>)}</div>

    {creating && <form onSubmit={create} className="surface-card account-create">
      <div className="account-create-head"><div><span className="content-eyebrow">NEW USER</span><h2>Create an account</h2><p>We’ll email a verification code to the account owner.</p></div><span className="admin-icon tone-green"><UserCheck size={18} /></span></div>
      <fieldset disabled={busy === "create"} className="account-create-grid">
        <label className="admin-field">Username<input className="admin-input" required minLength={3} maxLength={40} pattern="[A-Za-z0-9_.-]+" autoComplete="off" value={newUsername} onChange={event => setNewUsername(event.target.value)} placeholder="e.g. maria_santos" /></label>
        <label className="admin-field">Email address<input className="admin-input" type="email" required maxLength={254} autoComplete="off" value={newEmail} onChange={event => setNewEmail(event.target.value)} placeholder="name@example.com" /></label>
        <label className="admin-field">Temporary password<small>At least 10 characters. The user can change it after signing in.</small><input className="admin-input" type="password" required minLength={10} maxLength={128} autoComplete="new-password" value={newPassword} onChange={event => setNewPassword(event.target.value)} /></label>
        <label className="admin-field">Access role<select className="admin-input" value={newRole} onChange={event => setNewRole(event.target.value as Role)}>{ROLES.map(role => <option key={role} value={role}>{roleLabel(role)}</option>)}</select></label>
      </fieldset>
      <div className="account-create-actions"><button type="button" className="admin-btn" onClick={() => setCreating(false)}>Cancel</button><button className="admin-btn is-primary" disabled={busy === "create"}>{busy === "create" ? "Creating…" : "Create and send code"}</button></div>
    </form>}

    <div className="grid gap-3 md:grid-cols-3" aria-label="What each role can do">{ROLES.map(role => <div key={role} className="account-role-card">
      <span className={`admin-badge ${roleTone[role]}`}>{roleLabel(role)}</span><p>{roleInfo[role]}</p>
    </div>)}</div>

    {issued && <div role="status" className="surface-card admin-panel border-l-4 !border-l-[#477c55]">
      <h2 className="admin-panel-title"><span className="admin-icon is-small tone-green"><KeyRound size={16} /></span>Reset code for {issued.username}</h2>
      <p className="mt-3 text-[13px] leading-[1.7]">Give it to them directly; it is shown only once and expires in {issued.expiresInMinutes} minutes.</p>
      <div className="account-code"><output aria-label="One-time reset code">{issued.code}</output>
        <button className="admin-btn is-small" onClick={() => void copy()}>{copied ? <Check size={14} /> : <Copy size={14} />}{copied ? "Copied" : "Copy code"}</button>
        <button className="admin-btn is-small is-primary" onClick={() => setIssued(null)}>Done</button></div>
    </div>}
    {error && <p role="alert" className="content-notice is-error account-feedback">{error}</p>}
    {success && <p role="status" className="content-notice is-success account-feedback">{success}</p>}

    <div className="admin-toolbar accounts-toolbar">
      <div className="admin-tabs" role="group" aria-label="Filter accounts">{FILTERS.map(item => <button key={item.id} aria-pressed={filter === item.id} onClick={() => setFilter(item.id)} className="admin-tab">{item.label}<span className="admin-count">{accounts ? count[item.id] : "…"}</span></button>)}</div>
      <label className="admin-search"><Search size={14} aria-hidden="true" /><span className="sr-only">Search accounts</span><input placeholder="Search username or email" value={query} onChange={event => setQuery(event.target.value)} /></label>
    </div>

    {!accounts && !error && <div className="surface-card admin-empty" role="status"><span className="admin-icon tone-green"><Users size={18} /></span><h3>Loading accounts…</h3></div>}
    {accounts && <div className="surface-card account-list">
      {shown.length === 0 && <div className="admin-empty"><span className="admin-icon tone-slate"><Search size={18} /></span><h3>No accounts match</h3><p>Try another name, email or filter.</p></div>}
      {shown.map(row => {
        const self = row.id === user.id;
        return <article key={row.id} className={`account-row ${row.disabled ? "is-disabled" : ""}`}>
          <span className={`account-avatar ${row.disabled ? "tone-slate" : roleTone[row.role]}`} aria-hidden="true">{row.username.slice(0, 2)}</span>
          <div className="account-identity">
            <p className="account-name"><span>{row.username}</span>{self && <span className="admin-badge tone-green">You</span>}{row.disabled && <span className="admin-badge tone-rose">Disabled</span>}{!row.emailVerified && <span className="admin-badge tone-amber">Email not verified</span>}</p>
            <p className="account-email">{row.email || "No email on file"}</p>
            <p className="account-created">Created {new Date(row.createdAt).toLocaleDateString("en-PH", { timeZone: "Asia/Manila", dateStyle: "medium" })}</p>
          </div>
          <div className={`account-actions ${menuId === row.id ? "is-open" : ""}`}>
            <button className="admin-btn is-small account-menu-trigger" aria-label={`More options for ${row.username}`} title="More options" aria-haspopup="true" aria-expanded={menuId === row.id} onClick={() => setMenuId(menuId === row.id ? null : row.id)}><Ellipsis size={18} /></button>
            {menuId === row.id && <div className="account-action-menu" role="group" aria-label={`Account actions for ${row.username}`}>
              <label className="account-menu-label" htmlFor={`role-${row.id}`}>Access role</label>
              <span className="account-role-control"><UserCog size={14} aria-hidden="true" /><select id={`role-${row.id}`} className="admin-input" value={row.role} disabled={self || busy === row.id} onChange={event => void change(row.id, { action: "set-role", role: event.target.value })}>{ROLES.map(role => <option key={role} value={role}>{roleLabel(role)}</option>)}</select></span>
              {!row.emailVerified && <button className="account-menu-item" disabled={busy === row.id} onClick={() => void change(row.id, { action: "mark-verified" })}><MailCheck size={15} />Mark verified</button>}
              <button className={`account-menu-item ${row.disabled ? "" : "is-danger"}`} disabled={self || busy === row.id} onClick={() => toggle(row)}>{row.disabled ? <UserCheck size={15} /> : <Ban size={15} />}{row.disabled ? "Enable account" : "Disable account"}</button>
              <button className="account-menu-item" disabled={row.disabled || busy === row.id} onClick={() => void change(row.id, { action: "reset-code" })}><KeyRound size={15} />Issue reset code</button>
              <button className="account-menu-item is-danger" disabled={self || busy === row.id} onClick={() => void remove(row)}><Trash2 size={15} />Delete account</button>
            </div>}
          </div>
        </article>;
      })}
    </div>}
  </section>;
}
