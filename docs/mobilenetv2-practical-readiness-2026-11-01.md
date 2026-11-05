# GeoFlora practical dataset readiness — 2026-11-01

## Outcome

No CNN training was run. The active `mobilenetv2_v3_seed42`, its 3-class mapping, and 0.80 confidence threshold remain unchanged. SHA-256 checks for the active model's `mobilenetv2.keras` and `class_mapping.json` match its recorded candidate checksums.

The current frozen v3 partitions cannot support safe retraining or a new accuracy claim after applying the all-history holdout boundary. The 50-slot roster remains research-only: none of its 47 proposed additions has project ecological approval; no staging candidate has a qualifying human label approval with both reviewer and rationale.

## Three-class group shortfall

To make the shortage concrete, this table targets the number of independent groups present in each original v3 partition. For train and validation, it compares with the groups remaining after exact-hash, observation-group, and perceptual holdout exclusions. For test, it requires **fresh** observations at least matching the historical v3 test partition's group count. This is a volume-comparison target only; it does not establish that the test set is statistically adequate.

| Class | Train target / safe groups / additional groups | Validation target / safe groups / additional groups | Fresh blind test groups required |
|---|---:|---:|---:|
| Chromolaena odorata | 42 / 9 / **33** | 11 / 4 / **7** | **14** |
| Lantana camara | 55 / 26 / **29** | 14 / 6 / **8** | **13** |
| Pontederia crassipes | 19 / 9 / **10** | 5 / 0 / **5** | **4** |
| **Total** | **116 / 44 / 72** | **30 / 10 / 20** | **31** |

These are observation-group counts, not photo counts. They must be assigned by group so an observation or near-duplicate cluster cannot cross partitions. Candidate groups below are not subtracted from these shortages: they are pending review and have not all been reconciled against development groups for partition assignment. The 31 fresh test groups are a minimum to match the old test's independent-group volume, not a guarantee of a precise accuracy estimate; larger independently collected coverage would be preferable.

The prior safe folder export contains 9/4/0 Hagonoy, 28/6/0 Lantana, and 11/0/0 Water Hyacinth train/validation/test images. It used 413 unique historical test hashes and 1,043 normalized historical test-group keys as exclusions. Historical test records remain held out and were not copied into a new test folder.

## Bounded licensed-photo acquisition

Used the existing incremental iNaturalist collector with CC0, CC BY, and CC BY-SA only, Philippines filter, three-page limit, and no registry sync. It continued after each species' highest saved observation ID; no non-commercial license was admitted.

| Class | New image records | Existing locally valid records / observation groups | License and holdout-screened staged images / groups | Distinct from v3 development groups |
|---|---:|---:|---:|---:|
| Pontederia crassipes | **0** | 14 / 11 | 3 / 2 | **0** |
| Chromolaena odorata | **0** | 48 / 33 | 6 / 5 | **2** |
| Lantana camara | **2** | 45 / 28 | 4 / 4 | **0** |

The two new Lantana images belong to the same observation group (`inaturalist:observation:353028701`) and hit the historical-test exact/group/perceptual boundary, so neither is eligible for development. The two potentially new Hagonoy groups are only candidates: their labels are unreviewed, so they cannot yet enter training or validation. Water Hyacinth remains the immediate collection bottleneck: no newly eligible observation was found.

The distinction between “valid” and “usable” matters: collector-valid means decodable file, Philippine provenance fields, attribution, and an allowlisted license. It does not mean the pictured taxon was independently botanically verified, ecologically approved, or approved for training.

## Review queues and evidence

- [Read-only image review gallery](mobilenetv2-expansion-image-review-2026-11-01.html): 1,760 candidate images with source links, attribution, license, observation group, review status, and historical-test/duplicate warnings. The gallery records no decisions.
- [Image review CSV](mobilenetv2-expansion-image-review-queue-2026-11-01.csv): 1,760 staged records. It labels source/research-grade identifications as unverified and asks a reviewer to record visible diagnostic evidence. It does not convert AI screening or iNaturalist research-grade status into independent verification.
- [Ecological review CSV](mobilenetv2-expansion-ecological-review-queue-2026-11-01.csv): all 47 proposed additions, sorted with source-flagged candidates first; includes GRIIS dataset/DOI citation when applicable, CDFP family-page citation/annotation, conflicts, and the required human decision. The six GRIIS-flagged candidates are source flags only; all project ecological approvals remain ungranted. Introduced-only candidates are not labeled invasive by default.
- [Mechanical review-queue summary](mobilenetv2-expansion-review-queue-summary-2026-11-01.json): per-taxon exact-unique image, group, license-screen, holdout, and recorded-approval counts.
- [Refreshed full staging inventory](../storage/species_catalog/exports/image_dataset_readiness.json): 2,544 source records, 86 scientific-name buckets, and the frozen 11-class development dataset inventory. This is a source inventory, not a reviewed or approved training set.
- [Pontederia incremental collection log](staging-pontederia_crassipes-evidence.json), [Chromolaena log](staging-chromolaena_odorata-evidence.json), [Lantana log](staging-lantana_camara-evidence.json).

Automated screening compared all candidate images to all curated historical test images using SHA-256, normalized observation identities, and the existing perceptual-hash cutoff (Hamming distance ≤6). Historical-test overlaps are flagged for exclusion. Stored near-duplicate-group identifiers are included for reviewers. These checks flag candidates; they do not approve a label.

## Ecological separation and incremental path

1. **Recover a safe three-class corpus first.** Resolve the 72 train and 20 validation group deficits, collect 31 fresh blind-test groups to match the historic held-out group volume, review each label and license, then assign whole observations/duplicate clusters to splits. Keep the fresh test sealed from model selection.
2. **Only then prepare five classes.** Consider Mikania micrantha and Pistia stratiotes as evidence-prioritized candidates because the saved sources flag them and prior project sources contain Philippine records. Their status still needs contextual ecological approval, and their images still need independent label review, licensing and group-split readiness. They are not active model classes now.
3. **Expand gradually toward 50.** Admit one class at a time only after accepted-name reconciliation, evidence for its intended role (invasive target or clearly separate non-target look-alike), sufficient independent PH observations, rights/attribution, human label review, holdout clearance, and its own group-aware partitions. Never make 50 output classes just because 50 is the ceiling.

## Readiness and remaining human actions

- Current approved training additions: **0**. Candidate labels reviewed with documented human reviewer+rationale: **0**. Project ecological approvals for the 47 additions: **0**.
- Fresh blind test: **0 groups available**. The historical test remains protected.
- Human reviewers must inspect the image gallery, provide a visible-feature rationale per approved record (or reject/mark uncertain), and separately decide each taxon's ecological role from cited evidence. A source flag, owner visual approval, community ID, or AI screen cannot substitute for those decisions.
- New collections must continue to use a permitted license with attribution and a documented Philippine observation. Contributors must separately consent if their uploads are used for training.

Dataset is **not ready for training**. No training, model promotion, class-map change, or alteration to the active model occurred.
