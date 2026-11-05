import { z } from "zod";
import { askVision, visionImage } from "./ai-vision";
import { binomial, catalogIndex } from "./catalog";

// Broad plant identification for photos the image classifier cannot place among its few supported species.
// The vision model only names the plant; GeoFlora's own catalog says whether it is recorded in the Philippines,
// listed as introduced or naturalized by a source, or one of the species the classifier tracks.

const Suggestion = z.object({
  is_plant: z.boolean().describe("The photo shows a plant as its main subject."),
  scientific_name: z.string().nullable().describe("Most likely species, or the genus alone when the species is unclear (e.g. 'Nymphaea'); null when not a plant or not identifiable."),
  rank: z.enum(["species", "genus", "family", "unknown"]),
  common_names: z.array(z.string()).describe("English common name first (for a genus, the group name, e.g. 'Water lily'), then Filipino names when known."),
  confidence: z.number().describe("Confidence in the name, from 0 to 1."),
  identifying_features: z.string().describe("One or two sentences on what in the photo supports the identification."),
  description: z.string().describe("Two or three plain sentences describing the plant as seen in this photo, for a field report: leaf shape and arrangement, flower colour and form, growth habit and where it grows. Describe only what is visible; do not name the plant."),
  look_alikes: z.array(z.string()).describe("Up to three plants it could be confused with; empty when none."),
});
export type PlantSuggestion = z.infer<typeof Suggestion>;

const SYSTEM = `You help people in the Philippines find out what plant is in a photo. Name the most likely plant from what is visible. When leaves, flowers or growth form do not settle the species, give the genus (or family) and set rank accordingly; do not guess a species. Give a low confidence when unsure. Always give the usual English common name first, also for a genus or family (for example 'Water lily' for Nymphaea); add Filipino names only when you know them. Keep identifying_features short and specific to this photo. Write description the way a careful field observer would note what they see, without naming the plant or hedging about its identity; for example: "Floating plant with round, flat leaves split at the base. Pink, star-shaped flowers with yellow centres stand above the water on long stalks; closed buds point upward."`;

export async function suggestPlant(photo: Buffer, description = "") {
  const text = `What plant is this?${description.trim() ? `\n\nThe person describes it as: ${description.trim().slice(0, 500)}` : ""}`;
  const answer = await askVision(Suggestion, "plant_identification", SYSTEM, text, await visionImage(photo));
  const suggestion = answer.data;
  if (!suggestion?.is_plant || !suggestion.scientific_name) return { suggestion, model: answer.model, note: answer.note, catalog: null };
  const { entries } = await catalogIndex();
  const name = suggestion.scientific_name.trim();
  const genusOnly = suggestion.rank !== "species" || name.split(/\s+/).length < 2;
  const matches = genusOnly ? entries.filter(entry => entry.genus.toLowerCase() === name.split(/\s+/)[0].toLowerCase()) : entries.filter(entry => entry.binomial === binomial(name));
  const listed = matches.filter(entry => entry.sourceListings.length > 0);
  return {
    suggestion: { ...suggestion, confidence: Math.min(1, Math.max(0, Number(suggestion.confidence) || 0)) },
    model: answer.model,
    note: answer.note,
    catalog: {
      recordedInPhilippines: matches.length > 0,
      speciesInCatalog: matches.slice(0, 6).map(entry => entry.scientificName),
      tracked: matches.some(entry => entry.activeModel),
      introducedListings: listed.map(entry => ({ name: entry.scientificName, sources: entry.sourceListings.map(listing => listing.title) })).slice(0, 4),
    },
  };
}
