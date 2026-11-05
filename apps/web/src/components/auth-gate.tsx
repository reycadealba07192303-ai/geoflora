"use client";
import { createContext, useContext, useEffect, useState, type ReactNode, type FormEvent } from "react";
import { ArrowLeft, ArrowRight, Eye, EyeOff, KeyRound, MailCheck, ShieldCheck } from "lucide-react";
import LandingPage from "./landing-page";

export type Role = "admin" | "reviewer" | "user";
interface Account { id: string; username: string; role: Role }
export const roleLabel = (role: Role) => role === "admin" ? "Administrator" : role === "reviewer" ? "Reviewer" : "Contributor";
export const canModerate = (role: Role) => role === "admin" || role === "reviewer";
const Context = createContext<{ user: Account; signOut: () => Promise<void> } | null>(null);
export function useAccount() { const value = useContext(Context); if (!value) throw Error("Account context is unavailable"); return value; }

export default function AuthGate({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Account | null>(null), [loading, setLoading] = useState(true), [setup, setSetup] = useState(false);
  const [register, setRegister] = useState(false), [username, setUsername] = useState(""), [password, setPassword] = useState(""), [busy, setBusy] = useState(false), [message, setMessage] = useState("");
  const [resetting, setResetting] = useState(false), [code, setCode] = useState(""), [landing, setLanding] = useState(true), [showPassword, setShowPassword] = useState(false), [email, setEmail] = useState("");
  const [codeSent, setCodeSent] = useState(false), [cooldown, setCooldown] = useState(0);
  // Set while a new account waits for its emailed verification code.
  const [verifying, setVerifying] = useState<string | null>(null);
  const creating = setup || (register && !resetting);
  useEffect(() => { fetch("/api/auth", { cache: "no-store" }).then(async response => { const data = await response.json(); if (!response.ok) throw Error(data.detail); setUser(data.user); setSetup(data.setupRequired); }).catch(error => setMessage(error.message)).finally(() => setLoading(false)); }, []);
  useEffect(() => { if (cooldown <= 0) return; const timer = setTimeout(() => setCooldown(cooldown - 1), 1000); return () => clearTimeout(timer); }, [cooldown]);
  async function post(body: Record<string, string>) {
    const response = await fetch("/api/auth", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const data = await response.json();
    if (!response.ok) { if (data.verificationRequired) { setVerifying(data.email); setCode(""); } throw Error(data.detail); }
    return data;
  }
  async function run(task: () => Promise<void>) {
    setBusy(true); setMessage("");
    try { await task(); } catch (error) { setMessage(error instanceof Error ? error.message : "Something went wrong. Try again."); } finally { setBusy(false); }
  }
  // Password reset: first email a six-digit code, then exchange it for a new password.
  const requestCode = () => run(async () => { await post({ action: "reset-request", email }); setCodeSent(true); setCode(""); setCooldown(60); });
  const resendVerification = () => run(async () => { await post({ action: "resend-verification", username: verifying!, password }); setCode(""); setCooldown(60); });
  function submit(event: FormEvent) {
    event.preventDefault();
    if (resetting && !codeSent) { void requestCode(); return; }
    void run(async () => {
      const data = await post(verifying ? { action: "verify-email", username: verifying, code } : resetting ? { action: "reset", username: email, code, password } : { action: setup ? "setup" : register ? "register" : "login", username, password, ...(creating ? { email } : {}) });
      if (data.verificationRequired) { setVerifying(data.email); setCode(""); setCooldown(60); return; }
      setUser(data.user); setSetup(false); setPassword(""); setCode(""); setResetting(false); setCodeSent(false); setVerifying(null);
    });
  }
  async function signOut() { const response = await fetch("/api/auth", { method: "DELETE" }); if (response.ok) { setUser(null); setLanding(true); setRegister(false); setResetting(false); setCodeSent(false); setVerifying(null); setUsername(""); setEmail(""); setPassword(""); setCode(""); } }
  if (loading) return <div className="flora-shell grid min-h-screen place-items-center text-sm text-[#52745a]" role="status">Opening your workspace...</div>;
  if (user) return <Context.Provider value={{ user, signOut }}>{children}</Context.Provider>;
  if (landing) return <LandingPage setupRequired={setup} onGetStarted={() => { setLanding(false); setRegister(!setup); setResetting(false); setCodeSent(false); setMessage(""); }} />;
  const switchTo = (next: "register" | "login" | "reset") => { setVerifying(null); setRegister(next === "register"); setResetting(next === "reset"); setCodeSent(false); setCode(""); setMessage(""); setPassword(""); setShowPassword(false); };
  const heading = verifying ? ["Verify your", "email."] : setup ? ["Set up your", "workspace."] : resetting ? codeSent ? ["Check your", "email."] : ["Forgot your", "password?"] : register ? ["Join the", "map."] : ["Welcome", "back."];
  const subtitle = verifying ? "Enter the 6-digit code we sent to finish creating your account. It expires in 10 minutes." : setup ? "Create the first administrator account. New registrations after this are contributor accounts." : resetting ? codeSent ? "Enter the 6-digit code we sent. It expires in 10 minutes." : "Enter your account email and we'll send you a 6-digit code." : register ? "Create a contributor account to start mapping invasive plants." : "Sign in to identify plants, report sightings and explore the map.";
  const newPassword = setup || register || resetting;
  return <main className="auth-page">
    <aside className="auth-photo">
      <img src="/landing/auth.jpg" alt="" />
      <span className="lp-wordmark text-[24px]">geoflora<span className="text-[#c6dcae]">.</span></span>
      <div>
        <h2 className="lp-display">Every record<br />starts in the <span className="text-[#c6dcae]">field.</span></h2>
        <p>From one photo to a verified record, helping protect Philippine landscapes.</p>
      </div>
    </aside>
    <div className="auth-panel">
      <div className="auth-top">
        <span className="lp-wordmark text-[22px] lg:invisible">geoflora<span className="text-[#7fa96f]">.</span></span>
        <button className="auth-back" onClick={() => setLanding(true)}><ArrowLeft size={15} />Back to home</button>
      </div>
      <section className="auth-card">
        <span className="lp-tag">{verifying ? "Email verification" : setup ? "Administrator setup" : resetting ? "Password reset" : register ? "Create account" : "Sign in"}</span>
        <h1 className="lp-display auth-title">{heading[0]}<br /><span className="lp-photo-text">{heading[1]}</span></h1>
        <p className="auth-subtitle">{subtitle}</p>
        {verifying ? <form onSubmit={submit} className="auth-form"><fieldset disabled={busy}>
          <p className="auth-sent" role="status"><MailCheck size={18} /><span>Code sent to <strong>{verifying}</strong></span></p>
          <label>6-digit code<input className="auth-code" inputMode="numeric" autoComplete="one-time-code" required pattern="\d{6}" maxLength={6} title="The 6-digit code from your email" placeholder="000000" value={code} onChange={event => setCode(event.target.value.replace(/\D/g, ""))} /></label>
          {message && <p role="alert" className="content-notice is-error">{message}</p>}
          <button className="auth-submit" disabled={busy}><ShieldCheck size={17} />{busy ? "Please wait..." : "Verify and continue"}</button>
        </fieldset></form> : <form onSubmit={submit} className="auth-form"><fieldset disabled={busy}>
          {resetting && codeSent && <p className="auth-sent" role="status"><MailCheck size={18} /><span>Code sent to <strong>{email}</strong></span><button type="button" className="auth-link" onClick={() => { setCodeSent(false); setMessage(""); }}>Change</button></p>}
          {(creating || (resetting && !codeSent)) && <label>Email<input type="email" autoComplete="email" required maxLength={254} placeholder="you@example.com" value={email} onChange={event => setEmail(event.target.value)} /></label>}
          {creating && <label>Username<input autoComplete="username" required minLength={3} maxLength={40} pattern="[A-Za-z0-9_.\-]+" title="3–40 letters, numbers, dots, dashes or underscores" placeholder="Choose a username" value={username} onChange={event => setUsername(event.target.value)} /></label>}
          {!creating && !resetting && <label>Email or username<input autoComplete="username" required minLength={3} maxLength={254} placeholder="Enter your email or username" value={username} onChange={event => setUsername(event.target.value)} /></label>}
          {resetting && codeSent && <label>6-digit code<input className="auth-code" inputMode="numeric" autoComplete="one-time-code" required pattern="\d{6}" maxLength={6} title="The 6-digit code from your email" placeholder="000000" value={code} onChange={event => setCode(event.target.value.replace(/\D/g, ""))} /></label>}
          {(!resetting || codeSent) && <label><span className="flex items-center justify-between">{resetting ? "New password" : "Password"}{!newPassword && <button type="button" className="auth-link" onClick={() => switchTo("reset")}>Forgot password?</button>}</span><span className="auth-password">
            <input type={showPassword ? "text" : "password"} autoComplete={newPassword ? "new-password" : "current-password"} required minLength={10} maxLength={128} placeholder={newPassword ? "At least 10 characters" : "Enter your password"} value={password} onChange={event => setPassword(event.target.value)} />
            <button type="button" aria-label={showPassword ? "Hide password" : "Show password"} aria-pressed={showPassword} onClick={() => setShowPassword(!showPassword)}>{showPassword ? <EyeOff size={17} /> : <Eye size={17} />}</button>
          </span></label>}
          {message && <p role="alert" className="content-notice is-error">{message}</p>}
          <button className="auth-submit" disabled={busy}>{setup ? <ShieldCheck size={17} /> : resetting && codeSent ? <KeyRound size={17} /> : null}{busy ? "Please wait..." : setup ? "Create administrator" : resetting ? codeSent ? "Set new password" : "Send code" : register ? "Create account" : "Sign in"}{!setup && !(resetting && codeSent) && <ArrowRight size={17} />}</button>
        </fieldset></form>}
        {verifying ? <p className="auth-switch"><button className="auth-link" onClick={() => switchTo("login")}><ArrowLeft size={14} />Back to sign in</button><span aria-hidden="true">·</span><button className="auth-link" disabled={busy || cooldown > 0 || !password} title={password ? undefined : "Sign in again to request a new code"} onClick={() => void resendVerification()}>{cooldown > 0 ? `Resend code in ${cooldown}s` : "Resend code"}</button></p>
        : !setup && <p className="auth-switch">{resetting
          ? <><button className="auth-link" onClick={() => switchTo("login")}><ArrowLeft size={14} />Back to sign in</button>{codeSent && <><span aria-hidden="true">·</span><button className="auth-link" disabled={busy || cooldown > 0} onClick={() => void requestCode()}>{cooldown > 0 ? `Resend code in ${cooldown}s` : "Resend code"}</button></>}</>
          : register ? <>Already have an account? <button className="auth-link" onClick={() => switchTo("login")}>Sign in<ArrowRight size={14} /></button></> : <>New to GeoFlora? <button className="auth-link" onClick={() => switchTo("register")}>Create an account<ArrowRight size={14} /></button></>}</p>}
      </section>
    </div>
  </main>;
}
