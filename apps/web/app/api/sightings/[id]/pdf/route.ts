import { canModerate, currentAccount } from "../../../../../src/lib/auth";
import { ACTIVE, sameOriginRequest, reportSummary, sightingModel } from "../../../../../src/lib/sightings";
import { createReportPdf } from "../../../../../src/lib/report-pdf";

export const runtime = "nodejs";
export async function GET(request: Request, context: { params: Promise<{ id: string }> }) {
  if (!sameOriginRequest(request)) return Response.json({ detail: "This request is not allowed." }, { status: 403 });
  try {
    const account = await currentAccount(request);
    if (!account) return Response.json({ detail: "Sign in to download reports." }, { status: 401 });
    const { id } = await context.params;
    if (!/^[a-f0-9]{24}$/i.test(id)) return Response.json({ detail: "Invalid report reference." }, { status: 400 });
    const report = await (await sightingModel()).findOne({ _id: id, ...ACTIVE, ...(canModerate(account) ? {} : { ownerId: account.id }) }).select("+photo");
    if (!report?.photo) return Response.json({ detail: "Report not found." }, { status: 404 });
    const bytes = await createReportPdf(reportSummary(report), report.photo);
    return new Response(new Uint8Array(bytes), { headers: { "Content-Type": "application/pdf", "Content-Disposition": `attachment; filename="geoflora-report-${id}.pdf"`, "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff" } });
  } catch (error) { console.error("Report PDF generation failed", error instanceof Error ? error.message : "unknown error"); return Response.json({ detail: "The PDF could not be generated. Please retry." }, { status: 503 }); }
}
