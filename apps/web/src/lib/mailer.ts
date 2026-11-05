import { createTransport, type Transporter } from "nodemailer";

// Gmail SMTP with an app password, configured in .env.local (GEOFLORA_SMTP_USER / GEOFLORA_SMTP_PASSWORD).
// GEOFLORA_SMTP_HOST / GEOFLORA_SMTP_PORT point it at another server (port 465 uses TLS from the start).
let transport: Transporter | null = null;
let transportConfig = "";
export const mailConfigured = () => !!process.env.GEOFLORA_SMTP_USER && !!process.env.GEOFLORA_SMTP_PASSWORD;
function mailer() {
  const port = Number(process.env.GEOFLORA_SMTP_PORT) || 465;
  const host = process.env.GEOFLORA_SMTP_HOST || "smtp.gmail.com";
  const config = `${host}\0${port}\0${process.env.GEOFLORA_SMTP_USER}\0${process.env.GEOFLORA_SMTP_PASSWORD}`;
  // Build the transport at send time so a dev server restarted with updated
  // .env.local values cannot accidentally reuse an older SMTP configuration.
  if (!transport || transportConfig !== config) {
    transport?.close();
    transport = createTransport({ host, port, secure: port === 465, auth: { user: process.env.GEOFLORA_SMTP_USER, pass: process.env.GEOFLORA_SMTP_PASSWORD }, connectionTimeout: 15_000, greetingTimeout: 15_000, socketTimeout: 20_000 });
    transportConfig = config;
  }
  return transport;
}

async function sendCode(to: string, code: string, minutes: number, subject: string, intro: string, ignore: string) {
  await mailer().sendMail({
    from: `${process.env.GEOFLORA_SMTP_FROM_NAME || "geoflora"} <${process.env.GEOFLORA_SMTP_USER}>`,
    to,
    subject: `${code} ${subject}`,
    replyTo: process.env.GEOFLORA_SMTP_USER,
    text: `${intro} ${code}.\n\nIt expires in ${minutes} minutes. ${ignore}`,
    html: `<div style="font-family:Arial,sans-serif;max-width:440px;margin:auto;padding:32px;color:#0d2618">
  <p style="font-size:22px;font-weight:800;margin:0 0 24px">geoflora<span style="color:#7fa96f">.</span></p>
  <p style="font-size:15px;margin:0 0 16px">${intro}</p>
  <p style="font-size:34px;font-weight:800;letter-spacing:8px;margin:0 0 16px;padding:16px;text-align:center;background:#eef1ea;border-radius:16px">${code}</p>
  <p style="font-size:13px;color:#5f6b62;margin:0">It expires in ${minutes} minutes. ${ignore}</p>
</div>`,
  });
}

export const sendResetCode = (to: string, code: string, minutes: number) =>
  sendCode(to, code, minutes, "is your GeoFlora password reset code", "Use this code to reset your password:", "If you did not ask to reset your password, you can ignore this email.");

export const sendVerificationCode = (to: string, code: string, minutes: number) =>
  sendCode(to, code, minutes, "is your GeoFlora verification code", "Use this code to verify your email and finish creating your GeoFlora account:", "If you did not create a GeoFlora account, you can ignore this email.");

export function resetMailer() {
  transport?.close();
  transport = null;
  transportConfig = "";
}
