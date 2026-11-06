# GeoFlora: handover to the thesis group (7 November 2026)

GeoFlora is a web app that identifies invasive alien plants in the Philippines from a photo and maps where people found them. You take or upload a photo, GeoFlora's AI says what plant it probably is, and you save it as a sighting report with the date, time and location. Reports appear on a map. An administrator can approve or correct reports, and those corrections are used to train the AI further.

---

## 1. Links and access

| What | Where |
|---|---|
| **The app (online)** | **https://geoflora-ph.vercel.app** (also https://geoflora-one.vercel.app) |
| Source code | https://github.com/reycadealba07192303-ai/geoflora (public) |
| Database | MongoDB Atlas, project "geoflora" (free tier, Singapore) |
| Hosting | Vercel, project "geoflora" (free Hobby plan) |

**Accounts**
- **Administrator:** username `rycdlb_`. The password is given to you separately, not in this document. Change it after the handover: sign in, then open **Manage accounts**.
- **Contributors (users):** anyone can create an account on the sign-in page (**Create an account**). Email verification uses a 6-digit code.

---

## 2. Using GeoFlora (users)

1. **Identify a plant:** upload a photo or take one with the camera, then press **Identify plant**.
2. **Read the result.** It is one of three:
   - 🔴 **Target invasive species:** one of the 13 invasive plants GeoFlora monitors.
   - 🔵 **Not a target species:** a plant GeoFlora knows, but not a target.
   - 🟡 **Not sure:** the AI could not decide, often because the plant is not one of the 21 it knows. It shows the closest match ("Possibly …") and a second opinion from a general AI vision model.
3. **Save the report.** On the same screen:
   - **Date and time** are filled from the photo when the camera saved them, otherwise from now.
   - **Location** comes from the photo's GPS, your phone's location, or a pin you drop on the map.
   - Optional: place name, notes, your own description, and "This doesn't match my plant".
4. **My reports / Occurrence map:** every report, coloured by result (red / blue / amber). Open a report to see the species information or **Download PDF**.
5. **Feedback survey:** a short usability questionnaire, 10 standard SUS statements plus 5 GeoFlora statements. Please ask your respondents to answer it.

## 3. Using GeoFlora (administrator)

- **Review & training → To check:** for each report, press **Approve** (the AI is right) or **Correct** (choose the right species). **Reject** is for photos that are not plants.
- **Automatic training:**
  - Photos the AI **did not** get right (not sure, disputed or corrected) and that you approved or corrected are added to the training data, if the contributor allowed it. Allowing it is on by default.
  - After **20** such photos, the system retrains the model on the developer's computer.
  - If the new model is better, it appears under **Review & training** as **Approve new model**. It goes live only after you approve it.
- **Feedback survey (results):**
  - Administrators see the survey results above the form: mean SUS overall and per group, the 5 GeoFlora statements and the comments. Names are never shown.
  - **Download answers (CSV)** for your results chapter.
- **Manage accounts:** create accounts, change roles, reset passwords.

---

## 4. What the AI knows

**21 species.** The 13 target invasive species are verified against the DENR-BMB National Invasive Species Strategy and Action Plan (NISSAP) 2020-2030:

| Target invasive (13) | Not targets, used to tell look-alikes apart (8) |
|---|---|
| Hagonoy *Chromolaena odorata* | Billygoat weed *Ageratum conyzoides* |
| Lantana *Lantana camara* | Trailing lantana *Lantana montevidensis* |
| Water hyacinth *Pontederia crassipes* | Golden dewdrop *Duranta erecta* |
| Mile-a-minute *Mikania micrantha* | Water lettuce *Pistia stratiotes* |
| Cogon *Imperata cylindrica* | Gabi-gabi *Pontederia vaginalis* |
| Ipil-ipil *Leucaena leucocephala* | Yellow velvetleaf *Limnocharis flava* |
| African tulip tree *Spathodea campanulata* | Bagras *Eucalyptus deglupta* |
| Buyo-buyo *Piper aduncum* | Auri *Acacia auriculiformis* |
| Giant salvinia *Salvinia molesta* | |
| Paper mulberry *Broussonetia papyrifera* | |
| Mangium *Acacia mangium* | |
| Large-leaf mahogany *Swietenia macrophylla* | |
| Gmelina *Gmelina arborea* | |

**How it decides**
- Two deep-learning models (MobileNetV2, trained on 21 classes) look at the photo, and their answers are averaged.
- The AI is "sure" when the average score is at least **0.69**.
- If it is not sure, but its best guess is Hagonoy, Lantana or water hyacinth, a third model trained only on those 3 plants may confirm the guess. It confirms only when it agrees with a score of at least 0.968 and the average score is at least 0.60.
- The models run inside the web app itself. No separate AI server is needed.

## 5. Results you can use in the thesis

**Overall** (independent test photos never used in training; thresholds chosen on separate validation photos):

| Measure | Result |
|---|---|
| Overall accuracy (top-1) | **84.2%** (931 test photos) · 82.8% (1,013 photos, larger test set) |
| Accuracy when the AI says "sure" | **98.4%** · 97.3% (larger test set) |
| Precision / recall / F1 (macro, single model v3) | 0.84 / 0.84 / 0.83 |
| Response time | About 0.2 s per photo on a laptop. Online, about 1-3 s, and about 8 s for the first photo after the server has been idle. |

**Independent photos from Kaggle** (`Downloads\GeoFlora-Kaggle-Test`, not used in training):

| Folder | Result |
|---|---|
| Lantana | 16/25 sure and correct |
| Water hyacinth | 16/25 sure and correct (7/13 of the photos with **no licence**) |
| Pistia | 21/25 sure and correct |
| Plants not in the model | 49/50 correctly "Not sure" |

**Per-species precision (P) and recall (R), model v3** (full table and confusion matrix in `ml-lab/models/exported/geoflora-mnv2-21cls-v3/`):
- Lantana: P 1.00, R 0.94
- Water hyacinth: P 0.77, R 0.93
- Hagonoy: P 0.78, R 0.63
- Ageratum: P 0.92, R 0.73
- Mikania: P 0.64, R 0.55

The weakest classes are Hagonoy and Mikania. They look alike, and each is often confused with Ageratum.

**Known limitations** (say these in the thesis):
- **Labels:**
  - Training photos are iNaturalist "research-grade" observations from GBIF.
  - Each photo was screened by the developer (Reyca de Alba), with an AI pre-screen flagging doubtful photos.
  - This is **not** verification by a botanist.
  - The NISSAP status of the 13 targets was checked by the developer from the NISSAP document.
- **Unknown plants:** a plant that is not one of the 21 can still be called "sure", for example a red hibiscus called African tulip tree. On the lab's unknown-plant test, about a quarter of such photos were. This is why administrators can correct reports.
- **Field photos:** most training photos come from other countries. Photos taken in the Philippines and corrected through the app will improve the model.

## 6. Where things run and what they cost

| Part | Service | Free-tier limit |
|---|---|---|
| Web app + AI | Vercel Hobby | Non-commercial use; up to 12 server functions per deployment. The app currently fits. |
| Data and report photos | MongoDB Atlas M0 | 512 MB storage; about 50 MB is used now. Report photos are stored in the database, so watch it as reports grow. |
| Code | GitHub | Every push to `main` redeploys the app automatically. |
| Training | Developer's computer (`ml-lab/`) | Needs Python and TensorFlow, and takes 1-2 hours per training run on CPU. |

## 7. Protection and automatic checks

- **Rate limiting** prevents abuse and keeps the free AI services within their limits. Each account and each internet address has a budget:

| Action | Limit |
|---|---|
| Identify | 40 photos per 10 minutes |
| AI second opinion | 15 per 10 minutes |
| Save report | 30 per hour |
| Download PDF | 30 per 10 minutes |
| Feedback survey | 10 per hour |
| Sign-in, sign-up or reset requests | 40 per 15 minutes from one address |
| **Any API request** (server protection) | **120 per minute** per address, of which at most **40 per minute** may save or change data |

- On top of these, sign-in allows 10 failed attempts per account, and reset codes are limited to 3 per 15 minutes.
- Administrators and reviewers are not limited.
- Over the limit, the app says "Too many requests. Please wait a few minutes and try again."
- **CI/CD:**
  - **CI:** every push and pull request on GitHub runs automatic checks (GitHub Actions): the web app's typecheck and production build, a check that the AI models are present, and the ML lab tests. Results are under the repository's **Actions** tab and on the README badge.
  - **CD:** Vercel deploys automatically. A push to `main` updates https://geoflora-ph.vercel.app, and a pull request gets its own preview link.

## 8. Maintenance

- **Back up the data:** Atlas → Cluster → **Backup** is not included in the free tier. Instead, ask the developer to export the database, as was done when moving from the local database.
- **Undo a model change:**
  - Each approved model saves the previous setup as `apps/web/models/ensemble.before-<version>.json`.
  - To go back, copy that file over `ensemble.json` and push.
- **Change the AI threshold or models:** edit `apps/web/models/ensemble.json`. Technical notes are in `docs/ml-in-nextjs.md`.
- **More details:**
  - `docs/simple-identify-flow-2026-11-05.md`: app flow
  - `docs/ml-in-nextjs.md`: AI inside the app
  - `ml-lab/README.md`: training pipeline
  - `CLAUDE.md`: project overview

**Contact for technical help:** Reyca de Alba (developer).
