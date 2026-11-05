import { createHash, randomBytes, randomInt, scrypt, timingSafeEqual } from "node:crypto";
import { promisify } from "node:util";
import mongoose from "mongoose";
import { connectDatabase } from "./sightings";

const derive = promisify(scrypt);
const userSchema = new mongoose.Schema({
  username: { type: String, required: true, unique: true },
  // Required for new accounts; sparse so accounts created before emails were collected stay valid.
  email: { type: String, unique: true, sparse: true },
  passwordHash: { type: String, required: true, select: false },
  salt: { type: String, required: true, select: false },
  // "user" is the stored value for contributors; kept for existing accounts.
  role: { type: String, enum: ["admin", "reviewer", "user"], required: true },
  disabled: { type: Boolean, default: false },
  // false until the emailed code is entered; absent on accounts created before verification existed (treated as verified).
  emailVerified: { type: Boolean },
  bootstrapKey: { type: String, unique: true, sparse: true },
}, { timestamps: true });
const sessionSchema = new mongoose.Schema({
  tokenHash: { type: String, required: true, unique: true },
  userId: { type: mongoose.Schema.Types.ObjectId, required: true },
  expiresAt: { type: Date, required: true, expires: 0 },
});
// Admin-issued one-time password reset codes; only the hash is stored.
const resetSchema = new mongoose.Schema({
  userId: { type: mongoose.Schema.Types.ObjectId, required: true, index: true },
  codeHash: { type: String, required: true, unique: true },
  issuedBy: { type: String, required: true },
  expiresAt: { type: Date, required: true, expires: 0 },
});
export type Role = "admin" | "reviewer" | "user";
export type Account = { id: string; username: string; role: Role };
export const ROLES: Role[] = ["admin", "reviewer", "user"];
export const RESET_CODE_MINUTES = 30;
// Reviewers and administrators moderate reports; only administrators manage accounts and training.
export const canModerate = (account: Account) => account.role === "admin" || account.role === "reviewer";
export const isAdmin = (account: Account) => account.role === "admin";
export const SESSION_COOKIE = "geoflora_session";
export const tokenHash = (token: string) => createHash("sha256").update(token).digest("hex");
export async function authModels() {
  await connectDatabase();
  type User = mongoose.InferSchemaType<typeof userSchema>;
  type Session = mongoose.InferSchemaType<typeof sessionSchema>;
  type Reset = mongoose.InferSchemaType<typeof resetSchema>;
  const UserModel: mongoose.Model<User> = (mongoose.models.Account as mongoose.Model<User> | undefined) ?? mongoose.model<User>("Account", userSchema);
  const SessionModel: mongoose.Model<Session> = (mongoose.models.Session as mongoose.Model<Session> | undefined) ?? mongoose.model<Session>("Session", sessionSchema);
  const ResetModel: mongoose.Model<Reset> = (mongoose.models.PasswordReset as mongoose.Model<Reset> | undefined) ?? mongoose.model<Reset>("PasswordReset", resetSchema);
  await Promise.all([UserModel.init(), SessionModel.init(), ResetModel.init()]);
  return { User: UserModel, Session: SessionModel, PasswordReset: ResetModel };
}
export function sessionToken(request: Request) {
  return request.headers.get("cookie")?.split(";").map(value => value.trim()).find(value => value.startsWith(`${SESSION_COOKIE}=`))?.slice(SESSION_COOKIE.length + 1) ?? "";
}
export async function currentAccount(request: Request): Promise<Account | null> {
  const token = sessionToken(request);
  if (!/^[a-f0-9]{64}$/.test(token)) return null;
  const { User, Session } = await authModels();
  const session = await Session.findOne({ tokenHash: tokenHash(token), expiresAt: { $gt: new Date() } }).lean();
  if (!session) return null;
  const user = await User.findById(session.userId).lean();
  return user && !user.disabled ? { id: String(user._id), username: user.username, role: user.role } : null;
}
export async function passwordFields(password: string) {
  const salt = randomBytes(16).toString("hex");
  const result = await derive(password, salt, 64) as Buffer;
  return { salt, passwordHash: result.toString("hex") };
}
export async function passwordMatches(password: string, salt: string, hash: string) {
  const result = await derive(password, salt, 64) as Buffer;
  const expected = Buffer.from(hash, "hex");
  return expected.length === result.length && timingSafeEqual(result, expected);
}
export async function newSession(userId: mongoose.Types.ObjectId) {
  const { Session } = await authModels();
  const token = randomBytes(32).toString("hex");
  await Session.create({ tokenHash: tokenHash(token), userId, expiresAt: new Date(Date.now() + 8 * 60 * 60 * 1000) });
  return token;
}
export async function issueResetCode(userId: mongoose.Types.ObjectId | string, issuedBy: string) {
  const { PasswordReset } = await authModels();
  // Grouped for reading aloud or copying; normalized before hashing.
  const code = randomBytes(6).toString("hex").toUpperCase().match(/.{4}/g)!.join("-");
  await PasswordReset.deleteMany({ userId });
  await PasswordReset.create({ userId, codeHash: tokenHash(normalizeResetCode(code)), issuedBy, expiresAt: new Date(Date.now() + RESET_CODE_MINUTES * 60_000) });
  return code;
}
// Six-digit codes emailed to the account owner. Hashed with the user id so equal codes for different users never collide.
export const EMAIL_CODE_MINUTES = 10;
export const emailCodeHash = (userId: mongoose.Types.ObjectId | string, code: string) => tokenHash(`${userId}:${code}`);
// "email" codes reset a password; "verify-email" codes confirm a new account's address. Neither works for the other.
export async function issueEmailCode(userId: mongoose.Types.ObjectId, purpose: "email" | "verify-email" = "email") {
  const { PasswordReset } = await authModels();
  const code = String(randomInt(0, 1_000_000)).padStart(6, "0");
  await PasswordReset.deleteMany({ userId, issuedBy: purpose });
  await PasswordReset.create({ userId, codeHash: emailCodeHash(userId, code), issuedBy: purpose, expiresAt: new Date(Date.now() + EMAIL_CODE_MINUTES * 60_000) });
  return code;
}
export const normalizeResetCode =(code: string) => code.replace(/[^a-z0-9]/gi, "").toUpperCase();
export async function revokeSessions(userId: mongoose.Types.ObjectId | string, keepTokenHash?: string) {
  const { Session } = await authModels();
  await Session.deleteMany({ userId, ...(keepTokenHash ? { tokenHash: { $ne: keepTokenHash } } : {}) });
}
