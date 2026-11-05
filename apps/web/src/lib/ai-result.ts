// The result of a report as shown everywhere in the app, the same three outcomes as the ML lab demo.
// Owner decision (2026-11-05): there is no botanist, so new reports are recorded straight away with the AI
// model's result ("recorded" status) instead of waiting in a review queue. An administrator may still approve or
// correct a report afterwards. Older reports keep their reviewed status.

import { speciesInformation } from "../features/identification/species-information";

export type AiResult = "target" | "other" | "uncertain";

// Scientific names of the live model's target invasive species (verified status in the catalog export).
export const TARGET_SPECIES: string[] = Object.entries(speciesInformation)
  .filter(([, info]) => info.ecologicalStatus === "target_invasive")
  .map(([id]) => id.replace(/_/g, " ").replace(/^./, first => first.toUpperCase()));
export type ReportResult = AiResult | "rejected";

interface PredictionLike {
  status?: string;
  method?: string;
  species?: { id?: string; scientific_name?: string; role?: string } | null;
  candidates?: { species?: { id?: string; scientific_name?: string } }[];
  referenceSource?: { ecologicalStatus?: string };
}

// From the identification attached to a new report.
export function aiResultOf(prediction: PredictionLike | null | undefined, disagrees = false): AiResult {
  if (!prediction || disagrees || prediction.status !== "identified" || !prediction.species) return "uncertain";
  if (prediction.method === "verified_reference") return prediction.referenceSource?.ecologicalStatus === "target_invasive" ? "target" : "other";
  return prediction.species.role === "lookalike" ? "other" : "target";
}

// For any saved report, old (reviewed) or new (recorded).
// Older reviewed reports carry no AI result; they count as target when the reviewed species is a target species.
export function reportResult(row: { status?: string | null; aiResult?: string | null; verifiedEcologicalStatus?: string | null; verifiedScientificName?: string | null; reportedSpecies?: string | null }): ReportResult {
  if (row.status === "rejected") return "rejected";
  if (row.status === "verified") return row.verifiedEcologicalStatus === "target_invasive" || TARGET_SPECIES.includes(row.verifiedScientificName || row.reportedSpecies || "") ? "target" : "other";
  if (row.aiResult === "target" || row.aiResult === "other") return row.aiResult;
  return "uncertain";
}

// The closest species for an uncertain result ("Possibly ..."), from the model's top candidate.
export function possibleSpecies(prediction: PredictionLike | null | undefined): { id?: string; scientific_name?: string } | null {
  return prediction?.candidates?.[0]?.species ?? prediction?.species ?? null;
}

export const RESULT_LABEL: Record<ReportResult, string> = { target: "Target invasive", other: "Not a target", uncertain: "Not sure", rejected: "Rejected" };
export const RESULT_COLOR: Record<ReportResult, string> = { target: "#c62828", other: "#1565c0", uncertain: "#e7a641", rejected: "#9a9a9a" };
export const RESULT_TONE: Record<ReportResult, string> = { target: "tone-rose", other: "tone-blue", uncertain: "tone-amber", rejected: "tone-slate" };
