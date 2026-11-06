import { after } from "next/server";
import { NextResponse } from "next/server";
import { clearLimit, overLimit, rateLimit } from "../../../src/lib/rate-limit";
import { authModels, currentAccount, EMAIL_CODE_MINUTES, emailCodeHash, issueEmailCode, newSession, normalizeResetCode, passwordFields, passwordMatches, revokeSessions, SESSION_COOKIE, sessionToken, tokenHash } from "../../../src/lib/auth";
import { mailConfigured, sendResetCode, sendVerificationCode } from "../../../src/lib/mailer";
import { sameOriginRequest } from "../../../src/lib/sightings";

export const runtime = "nodejs";
const USERNAME = /^[a-z0-9_.-]{3,40}$/;
const EMAIL = /^[^\s@]{1,64}@[^\s@]+\.[^\s@]{2,}$/;

export async function GET(request: Request) {
  if (!sameOriginRequest(request)) return NextResponse.json({ detail: "This request is not allowed." }, { status: 403 });
  try {
    const { User } = await authModels();
    return NextResponse.json({ user: await currentAccount(request), setupRequired: !await User.exists({ role: "admin" }) }, { headers: { "Cache-Control": "no-store" } });
  } catch { return NextResponse.json({ detail: "The account database is unavailable." }, { status: 503 }); }
}

export async function POST(request: Request) {
  if (!sameOriginRequest(request)) return NextResponse.json({ detail: "This request is not allowed." }, { status: 403 });
  try {
    const body = await request.json();
    const password = typeof body.password === "string" ? body.password : "";
    const action = body.action;
    // Per-address budget on top of the per-account limits below (password changes are already signed in).
    if (action !== "change-password") { const blocked = await rateLimit(request, "auth"); if (blocked) return blocked; }
    if (action === "change-password") {
      const account = await currentAccount(request);
      if (!account) return NextResponse.json({ detail: "Sign in first." }, { status: 401 });
      const key = `change:${account.id}`;
      if (await overLimit(key, 10)) return NextResponse.json({ detail: "Too many attempts. Try again in 15 minutes." }, { status: 429 });
      const current = typeof body.currentPassword === "string" ? body.currentPassword : "";
      if (password.length < 10 || password.length > 128 || password === current) return NextResponse.json({ detail: "Choose a new password of 10–128 characters that differs from the current one." }, { status: 400 });
      const { User } = await authModels();
      const user = await User.findById(account.id).select("+passwordHash +salt");
      if (!user || !await passwordMatches(current, user.salt, user.passwordHash)) return NextResponse.json({ detail: "Current password is incorrect." }, { status: 401 });
      Object.assign(user, await passwordFields(password)); await user.save();
      // Other devices are signed out; this session continues.
      await revokeSessions(user._id, tokenHash(sessionToken(request)));
      await clearLimit(key);
      return NextResponse.json({ changed: true });
    }
    if (action === "reset-request") {
      const email = typeof body.email === "string" ? body.email.trim().toLowerCase() : "";
      if (email.length > 254 || !EMAIL.test(email)) return NextResponse.json({ detail: "Enter a valid email address." }, { status: 400 });
      if (!mailConfigured()) return NextResponse.json({ detail: "Password reset email is not set up on this server." }, { status: 503 });
      const key = `code:${email}`;
      if (await overLimit(key, 3)) return NextResponse.json({ detail: "Too many codes requested. Try again in 15 minutes." }, { status: 429 });
      const { User } = await authModels();
      const user = await User.findOne({ email });
      // Sent in the background and answered the same way either way, so the response does not reveal which emails have accounts.
      // after(): on Vercel the function stays alive until the email is sent (a bare promise was cut off when the response returned).
      if (user && !user.disabled) { const code = await issueEmailCode(user._id); after(() => sendResetCode(email, code, EMAIL_CODE_MINUTES).catch(error => console.error("Password reset email failed:", error))); }
      return NextResponse.json({ sent: true, minutes: EMAIL_CODE_MINUTES });
    }
    // Step 2 of password reset: check the emailed code before asking for the new password. The code is not used up here;
    // the final "reset" step checks it again and consumes it.
    if (action === "reset-verify") {
      const email = typeof body.email === "string" ? body.email.trim().toLowerCase() : "";
      const code = typeof body.code === "string" ? body.code.replace(/\D/g, "") : "";
      const key = `resetverify:${email}`;
      if (await overLimit(key, 10)) return NextResponse.json({ detail: "Too many attempts. Request a new code in 15 minutes." }, { status: 429 });
      const invalid = NextResponse.json({ detail: "The code is invalid or has expired. Request a new one." }, { status: 400 });
      if (!EMAIL.test(email) || !/^\d{6}$/.test(code)) return invalid;
      const { User, PasswordReset } = await authModels();
      const user = await User.findOne({ email });
      if (!user || user.disabled) return invalid;
      if (!await PasswordReset.exists({ userId: user._id, issuedBy: "email", codeHash: emailCodeHash(user._id, code), expiresAt: { $gt: new Date() } })) return invalid;
      return NextResponse.json({ verified: true });
    }
    if (action === "verify-email" || action === "resend-verification") {
      const id = typeof body.username === "string" ? body.username.trim().toLowerCase() : "";
      const key = `${action}:${id}`;
      const limit = action === "verify-email" ? 10 : 3;
      if (await overLimit(key, limit)) return NextResponse.json({ detail: action === "verify-email" ? "Too many attempts. Request a new code in 15 minutes." : "Too many codes requested. Try again in 15 minutes." }, { status: 429 });
      const { User, PasswordReset } = await authModels();
      const user = await User.findOne(id.includes("@") ? { email: id } : { username: id }).select("+passwordHash +salt");
      if (action === "resend-verification") {
        // The password proves the request comes from the account owner, so codes cannot be sent to someone else's inbox at will.
        if (!user || user.disabled || user.emailVerified !== false || !user.email || !await passwordMatches(typeof body.password === "string" ? body.password : "", user.salt, user.passwordHash)) return NextResponse.json({ detail: "Sign in again to request a new code." }, { status: 400 });
        const code = await issueEmailCode(user._id, "verify-email");
        try { await sendVerificationCode(user.email, code, EMAIL_CODE_MINUTES); } catch { return NextResponse.json({ detail: "The verification email could not be sent. Try again later." }, { status: 503 }); }
        return NextResponse.json({ sent: true, minutes: EMAIL_CODE_MINUTES });
      }
      const code = typeof body.code === "string" ? body.code.replace(/\D/g, "") : "";
      const invalid = NextResponse.json({ detail: "The code is invalid or has expired. Request a new one." }, { status: 400 });
      // Older accounts have no emailVerified field and are treated as verified
      // for sign-in. If one has a still-valid verification code (for example,
      // after a server restart during signup), let the code complete verification.
      if (!user || user.disabled || user.emailVerified === true || !/^\d{6}$/.test(code)) return invalid;
      if (!await PasswordReset.findOneAndDelete({ userId: user._id, issuedBy: "verify-email", codeHash: emailCodeHash(user._id, code), expiresAt: { $gt: new Date() } })) return invalid;
      user.emailVerified = true; await user.save();
      await clearLimit(key);
      const verified = NextResponse.json({ user: { id: String(user._id), username: user.username, role: user.role } });
      verified.cookies.set(SESSION_COOKIE, await newSession(user._id), { httpOnly: true, sameSite: "strict", secure: new URL(request.url).protocol === "https:", path: "/", maxAge: 8 * 60 * 60 });
      return verified;
    }
    // Sign-in and reset accept an email or a username; new accounts give both.
    const username = typeof body.username === "string" ? body.username.trim().toLowerCase() : "";
    const email = typeof body.email === "string" ? body.email.trim().toLowerCase() : "";
    const creating = action === "register" || action === "setup";
    const validUsername = USERNAME.test(username), validEmail = (value: string) => value.length <= 254 && EMAIL.test(value);
    if (!["login", "register", "setup", "reset"].includes(action) || password.length < 10 || password.length > 128 || (creating ? !validUsername || !validEmail(email) : !validUsername && !validEmail(username)))
      return NextResponse.json({ detail: creating ? "Use a valid email, a 3–40 character username and a password of 10–128 characters." : "Enter your email or username and a password of 10–128 characters." }, { status: 400 });
    const lookup = username.includes("@") ? { email: username } : { username };
    if (await overLimit(`signin:${username}`, 10)) return NextResponse.json({ detail: "Too many attempts. Try again in 15 minutes." }, { status: 429 });
    const { User, PasswordReset } = await authModels();
    let user;
    if (action === "login") {
      user = await User.findOne(lookup).select("+passwordHash +salt");
      if (!user || !await passwordMatches(password, user.salt, user.passwordHash)) return NextResponse.json({ detail: "Email, username or password is incorrect." }, { status: 401 });
      if (user.disabled) return NextResponse.json({ detail: "This account is disabled. Contact an administrator." }, { status: 403 });
      if (user.emailVerified === false) return NextResponse.json({ detail: "Verify your email to finish creating your account.", verificationRequired: true, email: user.email }, { status: 403 });
    } else if (action === "reset") {
      const code = typeof body.code === "string" ? normalizeResetCode(body.code) : "";
      user = await User.findOne(lookup);
      // One generic message so a reset attempt does not reveal which accounts exist.
      const invalid = NextResponse.json({ detail: "The code is invalid or has expired. Request a new one." }, { status: 400 });
      // Six digits: an emailed code. Twelve characters: an administrator-issued code.
      const emailed = /^\d{6}$/.test(code);
      if (!user || user.disabled || (!emailed && code.length !== 12)) return invalid;
      const reset = await PasswordReset.findOneAndDelete({ userId: user._id, issuedBy: emailed ? "email" : { $nin: ["email", "verify-email"] }, codeHash: emailed ? emailCodeHash(user._id, code) : tokenHash(code), expiresAt: { $gt: new Date() } });
      if (!reset) return invalid;
      Object.assign(user, await passwordFields(password)); await user.save();
      await revokeSessions(user._id);
    } else {
      const hasAdmin = !!await User.exists({ role: "admin" });
      if ((action === "setup" && hasAdmin) || (action === "register" && !hasAdmin)) return NextResponse.json({ detail: "Complete the available account setup flow." }, { status: 409 });
      if (!mailConfigured()) return NextResponse.json({ detail: "Email verification is not set up on this server. Ask the administrator to configure email." }, { status: 503 });
      // Unique bootstrapKey prevents two concurrent first-admin creations.
      const created = await User.create({ username, email, emailVerified: false, ...await passwordFields(password), role: action === "setup" ? "admin" : "user", ...(action === "setup" ? { bootstrapKey: "first-admin" } : {}) });
      // No session until the address is confirmed. If the email cannot be sent, the account is not kept, so the person can retry.
      try { await sendVerificationCode(email, await issueEmailCode(created._id, "verify-email"), EMAIL_CODE_MINUTES); }
      catch (error) {
        const mailError = error as { code?: string; responseCode?: number; command?: string; message?: string };
        console.error("Verification email failed:", { code: mailError.code, responseCode: mailError.responseCode, command: mailError.command, message: mailError.message });
        await PasswordReset.deleteMany({ userId: created._id }); await User.deleteOne({ _id: created._id });
        return NextResponse.json({ detail: "We could not send the verification email, so the account was not created. Try again later." }, { status: 503 });
      }
      await clearLimit(`signin:${username}`);
      return NextResponse.json({ verificationRequired: true, email, minutes: EMAIL_CODE_MINUTES }, { status: 201 });
    }
    await clearLimit(`signin:${username}`);
    const response = NextResponse.json({ user: { id: String(user._id), username: user.username, role: user.role } });
    response.cookies.set(SESSION_COOKIE, await newSession(user._id), { httpOnly: true, sameSite: "strict", secure: new URL(request.url).protocol === "https:", path: "/", maxAge: 8 * 60 * 60 });
    return response;
  } catch (error) {
    if ((error as { code?: number }).code === 11000) return NextResponse.json({ detail: "That username or email is already in use, or administrator setup was already completed." }, { status: 409 });
    return NextResponse.json({ detail: "Could not sign in. Check the account database and retry." }, { status: 503 });
  }
}

export async function DELETE(request: Request) {
  if (!sameOriginRequest(request)) return NextResponse.json({ detail: "This request is not allowed." }, { status: 403 });
  const { Session } = await authModels();
  await Session.deleteOne({ tokenHash: tokenHash(sessionToken(request)) });
  const response = NextResponse.json({ signedOut: true });
  response.cookies.set(SESSION_COOKIE, "", { httpOnly: true, sameSite: "strict", path: "/", maxAge: 0 });
  return response;
}
