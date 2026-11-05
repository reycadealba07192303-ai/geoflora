# GeoFlora usability study kit (Part 11)

For facilitators running moderated sessions with environmental officers, researchers and public users. Record every session in **Usability study** (administrator sidebar). The protocol below matches the app's task list and consent version `geoflora-usability-consent-v1-2026-10-27`. If you change any wording, change the version in `apps/web/src/features/study/protocol.ts` too.

## Before sessions

- **Participants.** At least 10 in total, with a spread across the three groups. Aim for 3–4 per group and report the actual mix. Recruit adults only.
- **Study workspace.** Use a separate study database, so test reports never mix with real ones. Start the web app with `GEOFLORA_MONGODB_URI=mongodb://127.0.0.1:27017/geoflora_study`.
  - Create one administrator account for the facilitator.
  - For T6, add a reviewer account plus 2–3 waiting sightings from a practice run.
  - Have the inference service running.
- **Materials.** Prepare the same plant photo for everyone: a Lantana or Hagonoy test photo saved on the device. Also have a written test location, for example "Barangay Malanday, Marikina, near the creek". If GPS is unavailable, the participant can tap the map or type coordinates.
- **Device.** Record the device and browser (phone or laptop) for each participant.
- **Assign codes.** Give each participant a code (P01, P02, …). Never write names in the app; keep any sign-up list separately and on paper.

## Run-day checklist (study workspace prepared 2026-10-27)

The study workspace is ready. Database `geoflora_study` contains a copy of the catalog, 3 practice sightings awaiting review (for T6) and 12 verified practice sightings from September–October 2026 (for T8). Every practice record is labeled "Practice data for the usability study — not a real sighting". It contains no participant data. A facilitator dry run of T1–T8 on an identical pilot copy passed: `storage/study/materials/pilot-dry-run.json`.

1. **Start the services.** Make sure inference is running (http://127.0.0.1:8000/health shows `ready: true`). Then run `powershell -ExecutionPolicy Bypass -File scripts\start_study_web.ps1` and open **http://127.0.0.1:5180**. This is the study app; the live app stays on 5173.
2. **Create the facilitator account.** On first open, create the facilitator **administrator** account with your own password.
3. **Set up the T6 reviewer.** Create a contributor account named `study_reviewer` (sign out, then "New here?"). Sign back in as the facilitator and set it to **Reviewer** in Manage accounts.
4. **Prepare the photo.** Copy `storage/study/materials/T2-T3-plant-photo.jpg` to the session device. It is a licensed Lantana photo that the live model identifies at 0.993; see the attribution file beside it. Give participants the test location "Marikina River Park, Marikina".
5. **Answer key.** Use `storage/study/materials/study-setup.json`.
   - T7: *Lantana camara* is supported by the live model.
   - T8 latest month (October 2026): 4 verified *Lantana camara* and 3 verified *Chromolaena odorata*.
   - Reports verified during sessions change these counts, so keep the T6 decision to "request correction", or recheck the answer key.
6. **For each participant:** read the consent script, record consent and the code in **Usability study**, run the tasks with the timers, collect the SUS, add comments, then save.
7. **Device limits.** The app accepts only loopback connections, so participants use the facilitator's computer. For a phone-sized layout, use the browser's device mode. Phones on a network need the Part 12 deployment.
8. **Between participants.** Sign out. Each participant creates their own account in T1.
9. **To start over:** `services/ml/.venv/Scripts/python.exe scripts/prepare_usability_study.py --reset`. This deletes recorded sessions, so export the CSV first.

## Consent script (read aloud; record consent in the app before starting)

**English.** "Thank you for helping us test GeoFlora, a research prototype for identifying invasive plants and recording where they are found.

- I will ask you to do a few short tasks and then answer ten questions about the system. It takes about 20–30 minutes.
- We are testing the system, not you. There are no wrong answers.
- Taking part is voluntary. You can skip any task or stop at any time without giving a reason.
- I will record whether each task was completed, how long it took, any errors, your questionnaire answers and your comments, under a code, not your name.
- The photos and reports you make here are test data in a separate study workspace.
- Results will be reported only as group summaries.
- You can ask us to delete your data later by giving your code.

Do you agree to take part?"

**Tagalog.** "Salamat sa pagtulong sa pagsubok ng GeoFlora, isang research prototype para makilala ang mga invasive na halaman at maitala kung saan ito nakita.

- Hihilingin kong gawin mo ang ilang maiikling gawain, at pagkatapos ay sagutin ang sampung tanong tungkol sa sistema. Mga 20–30 minuto ito.
- Ang sistema ang sinusubok namin, hindi ikaw. Walang maling sagot.
- Boluntaryo ang paglahok. Maaari kang lumaktaw ng gawain o tumigil anumang oras nang walang paliwanag.
- Itatala ko kung natapos ang bawat gawain, gaano katagal, anumang pagkakamali, ang iyong mga sagot at komento, gamit ang isang code at hindi ang iyong pangalan.
- Test data lamang sa hiwalay na study workspace ang mga larawan at ulat na gagawin mo rito.
- Iuulat lamang ang resulta bilang buod ng grupo.
- Maaari mong ipabura ang iyong data sa pagbigay ng iyong code.

Pumapayag ka bang lumahok?"

If the answer is no, thank them and stop; record nothing. If yes, tick the consent box in the app.

## Tasks

Read each prompt as written. Do not show where to click. Start the timer when you finish reading and stop it when the success condition is reached or the participant gives up.

- **Outcomes:**
  - **Completed without help.**
  - **Completed with help:** you gave any hint.
  - **Not completed.**
  - **Skipped:** the task was not attempted.
- **Errors:** count wrong paths that needed backing out, invalid submissions and misread results.

| Task | Prompt | Success | Groups |
|---|---|---|---|
| T1 (core) | Create an account (or sign in with the one provided) and reach the home screen. | Signed in; home or Identify shown | All |
| T2 (core) | Use the provided photo to find out what plant it may be. | Result or uncertain message shown | All |
| T3 (core) | Report that you saw this plant at the test location, including when you saw it. | Report saved, reference shown | All |
| T4 (core) | Find the report you just made on the map and open its details. | Details/report page for it open | All |
| T5 | You entered the wrong place name. Fix it on your report. | Corrected place saved | Public, researchers |
| T6 | As a reviewer, decide on one waiting sighting: verify it or ask for a correction, with a reason. | Decision saved with reason | Officers, researchers |
| T7 | Find *Lantana camara* in the species catalog and say whether the AI can identify it. | Opens entry; says it is supported by the live model | All |
| T8 | Show only one species on the map and say how many verified reports were observed in the latest month shown. | Filter applied; correct count stated | Officers, researchers |

For T6, sign in to the prepared reviewer account first. After the tasks, ask: "What was confusing? What would you change? Would you use this in your work or community?" Type the answers into Participant comments.

## System Usability Scale (SUS)

Have the participant answer from 1 (strongly disagree) to 5 (strongly agree) without discussion. The app computes the score: odd items score − 1, even items 5 − score, sum × 2.5.

| # | English | Tagalog |
|---|---|---|
| 1 | I think that I would like to use this system frequently. | Sa tingin ko, gugustuhin kong gamitin nang madalas ang sistemang ito. |
| 2 | I found the system unnecessarily complex. | Masyadong kumplikado ang sistema nang hindi kailangan. |
| 3 | I thought the system was easy to use. | Madaling gamitin ang sistema. |
| 4 | I think that I would need the support of a technical person to be able to use this system. | Kakailanganin ko ang tulong ng isang teknikal na tao para magamit ang sistemang ito. |
| 5 | I found the various functions in this system were well integrated. | Maayos na magkakaugnay ang iba't ibang bahagi ng sistema. |
| 6 | I thought there was too much inconsistency in this system. | Masyadong maraming hindi pagkakatugma sa sistema. |
| 7 | I would imagine that most people would learn to use this system very quickly. | Sa palagay ko, mabilis matututunan ng karamihan ang paggamit ng sistemang ito. |
| 8 | I found the system very cumbersome to use. | Napakahirap at nakakapagod gamitin ang sistema. |
| 9 | I felt very confident using the system. | Kumpiyansa ako habang ginagamit ang sistema. |
| 10 | I needed to learn a lot of things before I could get going with this system. | Marami akong kinailangang matutunan bago ko nagamit ang sistema. |

The Tagalog wording is a working translation. Use the same language version for everyone in a group, and note it in the device field (for example "Android, Chrome, TL").

## Analysis against the Part 1 targets

The app's summary updates as sessions are saved. Download the CSV for the final report.

| Target | Measure in the app |
|---|---|
| ≥ 90% completion of core tasks (T1–T4) **without assistance** | "Core tasks done without help". *Completed with help* counts as not met |
| Mean SUS ≥ 70 | "Mean SUS" |
| ≥ 10 participants across groups | "Participants" with the per-group counts |

- **Report the facts.** Include the real sample size and group mix, the per-task completion, the median times and the errors, alongside the targets. Report unmet targets plainly.
- **Small samples.** With fewer than about 5 per group, do not claim group differences.
- **Withdrawals.** If a participant withdraws, use **Withdraw data** next to their code. This deletes the session, and summaries recompute.
