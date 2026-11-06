# Adding new species to GeoFlora (runbook, prepared 2026-11-07 for Monday)

The live model knows 21 species. This runbook lists the decisions to make before you start, the candidate species, the exact steps with commands and times, and the traps to avoid.

---

## 1. Decide before Monday (Reyca / thesis group)

Decide these for each new species. Nothing can be trained until they are settled.

| Decision | Why it matters |
|---|---|
| **Which species** (scientific name) | One class each. Aim for 3-6 species per round. |
| **Target invasive or not?** | A **target** needs a Philippine source (for example the NISSAP 2020-2030 page or table), a **named verifier** and a date, as was done for the 13 current targets. Without these the species is added as **"not a target"** (status unresolved). |
| **Common name(s)** in the Philippines | Shown in the app and the PDF. |
| **Who screens the photos** | Reyca, with the AI pre-screen: Claude flags doubtful photos and Reyca OKs the list, the same as for Hagonoy and Ageratum. |

## 2. Candidates and photo availability

Counts are iNaturalist research-grade photos on GBIF, checked 2026-11-07. A class needs at least 60 approved photos from 30 independent observations; about 300-400 is better.

| Species | Common name | PH photos | World photos | Notes |
|---|---|---|---|---|
| *Sphagneticola trilobata* | Wedelia | 196 | 26,466 | Already in the catalog as an expansion candidate (IUCN 100 worst, global evidence only). |
| *Antigonon leptopus* | Coral vine / cadena de amor | 86 | 11,803 | Already in the catalog and in the app's species registry. |
| *Tithonia diversifolia* | Mexican sunflower | 75 | 5,688 | Already in the catalog. |
| *Mimosa diplotricha* | Giant false sensitive plant | 14 | 1,309 | Already in the catalog. |
| *Miconia crenata* | Koster's curse | 0* | 5,870 | Already in the catalog. *Check PH records under its old name *Clidemia hirta*. |
| *Mimosa pigra* | Giant sensitive plant | 0 | 2,968 | Already in the catalog (IUCN 100 worst). Few PH photos. |
| *Euphorbia hirta* | Tawa-tawa | 491 | 18,435 | **5 app reports were already corrected to it by the admin.** They are waiting and are imported automatically once the species is in the model. |
| *Coccinia grandis* | Ivy gourd / tamilok | 271 | 6,448 | In the app's species registry. |
| *Caladium bicolor* | Caladium | 217 | 4,081 | 1 app report was corrected to it. |
| *Mimosa pudica* | Makahiya | 406 | 16,258 | ⚠️ Currently one of the **"unknown plants"** used to test that the AI says "not sure". If you add it, choose another unknown plant to replace it. The same applies to *Hibiscus*, *Ixora*, *Bidens* and *Ipomoea aquatica*. |

## 3. Steps (Claude can run all of these; times are approximate)

| # | Step | Command / where | Time |
|---|---|---|---|
| 1 | Add each species to the catalog (scientific name, GBIF key, role, status, evidence, verifier) | `ml-lab/metadata/species_catalog.csv` | 15 min |
| 2 | Download photos (PH first, then worldwide) | `python scripts/download_dataset.py --species <IDs> --max-per-species 400` | 15-30 min per species |
| 3 | Check quality and duplicates | `python scripts/validate_images.py --no-recheck` | 5 min |
| 4 | AI pre-screen: contact sheets, flags, summary page | `scripts/contact_sheets.py`, then `scripts/prescreen_summary.py` | 30-60 min |
| 5 | **Reyca OKs the list**, then the decisions are imported under Reyca's name | `python scripts/review_images.py import <proposals.csv> --reviewer "Reyca de Alba"` | your time + 2 min |
| 6 | New config with the new classes. Write to **new folders**, so the current model and its test set stay intact. | copy `configs/expansion_nissap_v2.yaml` → `configs/expansion_v4.yaml` (add the IDs to `extra_class_species`; set `paths` to `dataset/v4`, `metadata/v4`, `models/checkpoints/v4`, `reports/v4`) | 10 min |
| 7 | Split and train | `split_dataset.py --config configs/expansion_v4.yaml`, then `train.py …` | about 2 h per model |
| 8 | Evaluate and export | `evaluate.py`, then `export_model.py --model-version geoflora-mnv2-<N>cls-v1` | 10 min |
| 9 | Species descriptions for the app: how to recognise it, look-alikes, why it matters, references | `ml-lab/metadata/species_descriptions.json`, then `scripts/export_species_information.py` (writes `apps/web/src/features/identification/species-information.ts`) | 30 min |
| 10 | Package and convert to ONNX, and check it against Keras | `package_for_geoflora.py`, then `export_onnx.py` (in `.venv-onnx`) | 10 min |
| 11 | Put it in the app (see trap A) and test it, including Kaggle or other new photos | `apps/web/models/ensemble.json` | 20 min |
| 12 | Push. CI checks it and Vercel deploys. | `git push` | 10 min |

## 4. Traps (read before step 11)

- **A. Every model in the ensemble must know the same species.**
  - The live ensemble averages v1 and v3, both 21-class.
  - A 25-class model cannot be averaged with them. The app refuses to start the classifier, so nothing breaks silently.
  - Either put the new model in alone (`"members": ["geoflora-mnv2-25cls-v1"]`), or train a second model with the other recipe and use both.
  - The 3-class confirm model (Hagonoy, Lantana, water hyacinth) can stay.
- **B. Cloud training follows the current class set.**
  - `ml-lab/scripts/cloud_training.py` uses `configs/expansion_nissap_v2.yaml` and the `dataset/nissap` photos stored in Atlas.
  - After a new class set goes live, point both at the new config and re-upload the photos with `cloud_data.py upload`. Otherwise cloud retraining keeps producing 21-class models.
- **C. Keep the test sets fixed.** New species get their own test photos; never move photos between splits by hand. Compare old and new models only on the classes they share.
- **D. Thresholds.** Re-choose the "sure" threshold on the **validation** set of the new model (Youden J, as before), never on the test set.
- **E. Atlas space.** About 20 KB per training photo plus report photos; the free tier has 512 MB. 2,000 more photos is about 40 MB.
- **F. Honesty for the thesis.**
  - Labels are research-grade iNaturalist photos screened by Reyca with an AI pre-screen. They are not verified by a botanist.
  - A species is "target invasive" only with a source and a named verifier.

## 5. What already helps now

- When the AI does not know a plant, admins can **Correct → Another species (type its name)** in Review & training. Those reports are kept, and their photos join training once the species is in the catalog. *Euphorbia hirta* already has 5.
- In the cloud workflow log, "species not in the model yet" lists which corrected species are waiting.
