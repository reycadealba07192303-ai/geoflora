import sharp from "sharp";
import { ACTIVE, sameOriginRequest, sightingModel } from "../../../../../src/lib/sightings";
import { canModerate, currentAccount } from "../../../../../src/lib/auth";

export const runtime = "nodejs";

export async function GET(request: Request, context: { params: Promise<{ id: string }> }) {
  if (!sameOriginRequest(request)) return Response.json({ detail: "This request is not allowed." }, { status: 403 });
  const { id } = await context.params;
  if (!/^[a-f0-9]{24}$/i.test(id)) return Response.json({ detail: "Invalid report ID" }, { status: 400 });
  try {
    const account = await currentAccount(request);
    if (!account) return Response.json({ detail: "Sign in to view report photos." }, { status: 401 });
    const model = await sightingModel();
    const report = await model.findOne({ _id: id, ...ACTIVE, ...(canModerate(account) ? {} : { ownerId: account.id }) }).select("photo");
    if (!report?.photo) return Response.json({ detail: "Report photo not found" }, { status: 404 });
    const thumbnail = new URL(request.url).searchParams.get("thumbnail") === "1";
    const photo = thumbnail
      ? await sharp(report.photo).resize(120, 120, { fit: "cover" }).jpeg({ quality: 80 }).toBuffer()
      : report.photo;
    return new Response(new Uint8Array(photo), { headers: {
      "Content-Type": "image/jpeg", "Cache-Control": "private, no-store",
      "X-Content-Type-Options": "nosniff", "Cross-Origin-Resource-Policy": "same-origin",
    } });
  } catch { return Response.json({ detail: "Could not load report photo" }, { status: 503 }); }
}
