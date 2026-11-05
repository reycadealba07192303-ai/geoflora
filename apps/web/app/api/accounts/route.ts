import mongoose from "mongoose";
import { authModels, currentAccount, EMAIL_CODE_MINUTES, isAdmin, issueEmailCode, issueResetCode, passwordFields, RESET_CODE_MINUTES, revokeSessions, ROLES, type Role } from "../../../src/lib/auth";
import { mailConfigured, sendVerificationCode } from "../../../src/lib/mailer";
import { sameOriginRequest } from "../../../src/lib/sightings";

export const runtime = "nodejs";
const USERNAME = /^[a-z0-9_.-]{3,40}$/;
const EMAIL = /^[^\s@]{1,64}@[^\s@]+\.[^\s@]{2,}$/;

async function administrator(request: Request) {
  if (!sameOriginRequest(request)) return { error: Response.json({ detail: "This request is not allowed." }, { status: 403 }) };
  const account = await currentAccount(request);
  if (!account) return { error: Response.json({ detail: "Sign in first." }, { status: 401 }) };
  if (!isAdmin(account)) return { error: Response.json({ detail: "Administrator access required." }, { status: 403 }) };
  return { account };
}

export async function GET(request: Request) {
  try {
    const { error } = await administrator(request);
    if (error) return error;
    const { User } = await authModels();
    const users = await User.find().sort({ createdAt: 1 }).select("username email emailVerified role disabled createdAt").lean();
    return Response.json({ accounts: users.map(user => ({ id: String(user._id), username: user.username, email: user.email ?? "", role: user.role, disabled: !!user.disabled, emailVerified: user.emailVerified !== false, createdAt: user.createdAt })) }, { headers: { "Cache-Control": "no-store" } });
  } catch { return Response.json({ detail: "Accounts are unavailable. Check the account database." }, { status: 503 }); }
}

export async function POST(request: Request) {
  try {
    const { error } = await administrator(request);
    if (error) return error;
    const body = await request.json().catch(() => ({}));
    const username = typeof body.username === "string" ? body.username.trim().toLowerCase() : "";
    const email = typeof body.email === "string" ? body.email.trim().toLowerCase() : "";
    const password = typeof body.password === "string" ? body.password : "";
    const role = body.role as Role;
    if (!USERNAME.test(username) || email.length > 254 || !EMAIL.test(email) || password.length < 10 || password.length > 128 || !ROLES.includes(role))
      return Response.json({ detail: "Enter a valid email, username, password and role." }, { status: 400 });
    if (!mailConfigured()) return Response.json({ detail: "Email verification is not configured on this server." }, { status: 503 });
    const { User, PasswordReset } = await authModels();
    const created = await User.create({ username, email, emailVerified: false, ...await passwordFields(password), role });
    try {
      const code = await issueEmailCode(created._id, "verify-email");
      await sendVerificationCode(email, code, EMAIL_CODE_MINUTES);
    } catch (mailError) {
      await PasswordReset.deleteMany({ userId: created._id });
      await User.deleteOne({ _id: created._id });
      const diagnostic = mailError as { code?: string; responseCode?: number; command?: string };
      console.error("Admin-created account verification email failed:", { code: diagnostic.code, responseCode: diagnostic.responseCode, command: diagnostic.command });
      return Response.json({ detail: "The verification email could not be sent. The account was not created." }, { status: 503 });
    }
    return Response.json({ created: true, username, email, verificationRequired: true }, { status: 201 });
  } catch (error) {
    if ((error as { code?: number }).code === 11000) return Response.json({ detail: "That username or email is already in use." }, { status: 409 });
    return Response.json({ detail: "The account could not be created. Check the account database and retry." }, { status: 503 });
  }
}

export async function PATCH(request: Request) {
  try {
    const { account, error } = await administrator(request);
    if (error) return error;
    const body = await request.json().catch(() => ({}));
    if (typeof body.id !== "string" || !/^[a-f0-9]{24}$/i.test(body.id) || !["set-role", "disable", "enable", "reset-code", "mark-verified"].includes(body.action)) return Response.json({ detail: "Supply an account and a valid action." }, { status: 400 });
    // Administrators cannot lock themselves out; another administrator must change their access.
    if (body.id === account.id && body.action !== "reset-code") return Response.json({ detail: "You cannot change or delete your own account here." }, { status: 409 });
    const { User } = await authModels();
    const user = await User.findById(body.id);
    if (!user) return Response.json({ detail: "Account not found." }, { status: 404 });
    // An administrator can confirm an address by other means, for example when email delivery is down.
    if (body.action === "mark-verified") { user.emailVerified = true; await user.save(); return Response.json({ id: String(user._id), username: user.username, emailVerified: true }); }
    if (body.action === "set-role") {
      if (!ROLES.includes(body.role)) return Response.json({ detail: "Choose administrator, reviewer or contributor." }, { status: 400 });
      if (user.role === "admin" && !user.disabled && body.role !== "admin" && await User.countDocuments({ role: "admin", disabled: { $ne: true } }) <= 1) return Response.json({ detail: "Keep at least one enabled administrator." }, { status: 409 });
      user.role = body.role as Role;
      await user.save();
    } else if (body.action === "disable" || body.action === "enable") {
      if (body.action === "disable" && user.role === "admin" && !user.disabled && await User.countDocuments({ role: "admin", disabled: { $ne: true } }) <= 1) return Response.json({ detail: "Enable another administrator before disabling this account." }, { status: 409 });
      user.disabled = body.action === "disable";
      await user.save();
      if (user.disabled) await revokeSessions(user._id);
    } else {
      if (user.disabled) return Response.json({ detail: "Enable the account before issuing a reset code." }, { status: 409 });
      const code = await issueResetCode(user._id, account.username);
      return Response.json({ id: String(user._id), username: user.username, code, expiresInMinutes: RESET_CODE_MINUTES }, { headers: { "Cache-Control": "no-store" } });
    }
    return Response.json({ id: String(user._id), username: user.username, role: user.role, disabled: !!user.disabled });
  } catch { return Response.json({ detail: "The account change could not be saved." }, { status: 503 }); }
}

export async function DELETE(request: Request) {
  try {
    const { error } = await administrator(request);
    if (error) return error;
    const body = await request.json().catch(() => ({}));
    if (typeof body.id !== "string" || !/^[a-f0-9]{24}$/i.test(body.id)) return Response.json({ detail: "Supply a valid account." }, { status: 400 });
    const { User, Session, PasswordReset } = await authModels();
    if (body.id === (await currentAccount(request))?.id) return Response.json({ detail: "You cannot delete your own account." }, { status: 409 });
    const user = await User.findById(body.id);
    if (!user) return Response.json({ detail: "Account not found." }, { status: 404 });
    if (user.role === "admin" && !user.disabled && await User.countDocuments({ role: "admin", disabled: { $ne: true } }) <= 1) return Response.json({ detail: "Keep at least one enabled administrator." }, { status: 409 });
    await mongoose.connection.db!.collection("sightings").updateMany({ ownerId: String(user._id) }, { $set: { ownerId: null } });
    await Promise.all([Session.deleteMany({ userId: user._id }), PasswordReset.deleteMany({ userId: user._id })]);
    await User.deleteOne({ _id: user._id });
    return Response.json({ deleted: true, username: user.username, reportsAnonymized: true });
  } catch { return Response.json({ detail: "The account could not be deleted. Check the account database and retry." }, { status: 503 }); }
}
