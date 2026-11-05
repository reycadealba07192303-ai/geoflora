// Shared usability-study protocol (docs/part-11-usability-kit.md). The server validates sessions against it.
export const CONSENT_VERSION = "geoflora-usability-consent-v1-2026-10-27";
export const GROUPS = { environmental_officer: "Environmental officer", researcher: "Researcher", public: "Public user" } as const;
export type Group = keyof typeof GROUPS;

export const TASKS: { id: string; title: string; prompt: string; success: string; core: boolean; groups: Group[] }[] = [
  { id: "T1", title: "Sign in", prompt: "Create an account (or sign in with the one provided) and reach the home screen.", success: "Home or Identify screen shown while signed in.", core: true, groups: ["environmental_officer", "researcher", "public"] },
  { id: "T2", title: "Identify a plant photo", prompt: "Use the provided photo to find out what plant it may be.", success: "A result or an uncertain message is shown for the photo.", core: true, groups: ["environmental_officer", "researcher", "public"] },
  { id: "T3", title: "Submit a sighting", prompt: "Report that you saw this plant at the test location, including when you saw it.", success: "Report saved and its reference shown.", core: true, groups: ["environmental_officer", "researcher", "public"] },
  { id: "T4", title: "Find it on the map", prompt: "Find the report you just made on the map and open its details.", success: "Report details or the report page for the new report are open.", core: true, groups: ["environmental_officer", "researcher", "public"] },
  { id: "T5", title: "Correct a pending report", prompt: "You entered the wrong place name. Fix it on your report.", success: "Corrected place name saved on the report.", core: false, groups: ["public", "researcher"] },
  { id: "T6", title: "Review a sighting", prompt: "As a reviewer, decide on one waiting sighting: verify it or ask for a correction, with a reason.", success: "Decision saved with a reason; the report leaves the awaiting list or shows correction requested.", core: false, groups: ["environmental_officer", "researcher"] },
  { id: "T7", title: "Check the catalog", prompt: "Find Lantana camara in the species catalog and say whether the AI can identify it.", success: "Participant opens the entry and correctly states it is supported by the live model.", core: false, groups: ["environmental_officer", "researcher", "public"] },
  { id: "T8", title: "Read the analytics", prompt: "Show only one species on the map and say how many verified reports were observed in the latest month shown.", success: "Species filter applied and the correct monthly count stated.", core: false, groups: ["environmental_officer", "researcher"] },
];

// System Usability Scale (Brooke, 1996): odd items positive, even items negative; 1 = strongly disagree, 5 = strongly agree.
export const SUS_ITEMS = [
  "I think that I would like to use this system frequently.",
  "I found the system unnecessarily complex.",
  "I thought the system was easy to use.",
  "I think that I would need the support of a technical person to be able to use this system.",
  "I found the various functions in this system were well integrated.",
  "I thought there was too much inconsistency in this system.",
  "I would imagine that most people would learn to use this system very quickly.",
  "I found the system very cumbersome to use.",
  "I felt very confident using the system.",
  "I needed to learn a lot of things before I could get going with this system.",
];
export const susScore = (answers: number[]) => answers.reduce((sum, value, index) => sum + (index % 2 === 0 ? value - 1 : 5 - value), 0) * 2.5;
export const TARGETS = { participants: 10, coreCompletion: 0.9, sus: 70 };
