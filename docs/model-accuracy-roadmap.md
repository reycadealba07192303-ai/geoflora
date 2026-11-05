# GeoFlora image-classifier accuracy roadmap

Updated: October 31, 2026

## Layunin at inaasahan

Target ang **95% top-1 accuracy sa isang bago at independent na test set ng mga Philippine field photo para sa tatlong kasalukuyang target species**: *Chromolaena odorata*, *Lantana camara*, at *Pontederia crassipes*. Hiwalay na target ang ligtas na pag-reject ng ibang species, hindi halaman, at malabong larawan. Hindi garantiya ang 95% at hindi ito makakamit sa pagpili lang ng architecture o pagdagdag ng epochs; nakadepende ito lalo na sa dami, kalidad at representativeness ng labels at test data.

Iulat palagi ang top-1 accuracy kasabay ng macro F1, precision at recall kada species, confusion matrix, coverage at selective accuracy sa napiling confidence threshold, false-accept rate sa unsupported photos, at 95% confidence intervals. Huwag tawaging 95% accurate ang system dahil lang mataas ang training/validation score o dahil sa iilang test images.

## Kasalukuyang baseline

- Active model: MobileNetV2 v3, tatlong klase; naiulat ang 87.18% top-1 accuracy at 82.74% macro F1 sa 39 held-out photos. Water-hyacinth recall ay 50%.
- Ang v5 five-class candidate ay hindi aktibo at hindi aprubado: 211 total photos (141 train / 34 validation / 36 test), 75.00% top-1 accuracy at 49.47% macro F1. May 5/1/1 photos lang ang Mikania at 3/2/2 ang Pistia sa train/validation/test.
- Sa v5, 35.37% ng 147 unsupported-species photos ay maling natanggap sa threshold na 0.90. Samakatuwid, hindi sapat ang saradong three-class accuracy para sa live system.
- Limitasyon sa labels: may owner attestation at visual screen ang ilang larawan, ngunit hindi pa independent botanical at per-image geographic verification.

Ebidensya: [active model](active-local-model.md), [v3 evaluation](part-6-v3-evaluation.json), [v5 model card](model-card-v5.md), [v5 results](training-v5-five-results.md).

## Diagnosis at susunod na recovery run (October 31, 2026)

Ang pinakabagong five-class candidate ay 39.13% accuracy / 35.24% macro F1 sa 23 test photos. Maliit ito para maging matatag na estimate, pero malinaw ang error pattern: 6/9 Hagonoy at 2/4 Lantana photos ang napredik bilang Mikania; 15/23 lahat ng test photos ay napredik bilang Mikania. Isang Pistia test photo lang ang nasa split at mali rin ang prediction nito.

Napakaliit ng active-class training subset sa snapshot na ito: 19 Hagonoy, 20 Lantana, at 6 Water Hyacinth photos; 28 Mikania at 4 Pistia lang ang training photos ng mga bagong klase. Hindi nito isinama ang dating v3 train/validation images. Sa v3 visual-triage list, may **84 preliminary field-like development photos** (Hagonoy 37, Lantana 36, Water Hyacinth 11) sa train/validation partitions. Hindi ito expert-verified, pero mas mabuting panimulang development corpus kaysa itapon ang dating active-class data at magsanay sa staging lang. Huwag isama ang v3 test photos.

### Recovery run at susunod na hakbang

Sinubukan na ang 3-class recovery gamit ang owner-approved staging at 84 preliminary field-like v3 train/validation photos; hindi isinama ang v3 test at v5 benchmark groups. Pagkatapos ng checksum, observation-group, near-duplicate at benchmark-overlap filtering, 75 photos lang ang natira (Hagonoy 21/9/5, Lantana 21/5/4, Water Hyacinth 5/3/2 train/validation/test). Candidate result: 63.64% accuracy / 46.67% macro F1 sa 11 test photos. Sa fixed benchmark: 78.79% accuracy / 83.33% macro recall kumpara sa live model na 90.91% / 92.86%. Hindi ito ia-activate. Ipinakita ng filtering na maraming lumang/staged photos ay parehong larawan o hindi puwedeng gamitin bilang bagong benchmark-independent sample.

1. **Kumuha ng bagong eligible Philippine field photos.** Unahin ang Water Hyacinth at Water Lettuce dahil 5 at 4 lang ang training samples nila sa recovery/five-class snapshots. Dagdagan din ang Hagonoy at Lantana gamit ang bagong observation groups, hindi dagdag na kuha ng parehong halaman. CC0/CC BY/CC BY-SA lamang ang gamitin sa invasive training.
2. **Ayusin ang mahihirap na pares sa development set.** Tingnan ang Hagonoy↔Mikania at Lantana↔Mikania na larawan sa train/validation, at ipa-verify ang hindi malinaw na labels sa botanist o qualified reviewer. Huwag mag-tune sa nakitang 23-photo five-class o 11-photo three-class test split; hindi na blind ang mga iyon.
3. **Mag-freeze ng bagong, independent blind test cohort.** Ihiwalay ito sa training, tuning, owner gallery review at public benchmark photos. Iulat ang per-class recall/precision, macro F1, unknown rejection, support at confidence intervals.

Hindi architecture o dagdag na epochs ang agarang lunas. Kailangan muna ng mas maraming tunay na independent, rights-eligible field observations. Kapag sapat na ang data, saka ulitin ang group-aware training at benchmark comparison; 95% claim o production activation lamang kapag pumasa sa release gates.

## Ano ang susunod na gagawin natin

Hindi tayo magsisimula sa panibagong training run o magpapalit ng active model. Ang unang trabaho ay **dataset audit at malinis na experimental snapshot**. Kaya natin itong simulan sa repository gamit ang kasalukuyang files at scripts.

Paunang read-only check sa `storage/datasets/curated/v3/manifest.csv`: 243 rows (166 train / 38 validation / 39 test), mula sa GBIF (140) at iNaturalist (103). May 93 *Chromolaena*, 114 *Lantana*, at 36 *Pontederia*. May 23 rows na ang attribution o URL ay may collection/herbarium/specimen/botanic keywords; hindi pa ito visual verdict, pero dapat i-review bago ituring ang corpus bilang field-photo data. Ang 39-image test ay nagamit na sa naunang evaluation, kaya hindi ito bagong blind test.

**Unang audit at ikalawang visual-screen pass: kumpleto.** Ang [reproducible audit script](../scripts/audit_v3_corpus.py) ay nagbukas at nag-checksum ng 243/243 images, nakakita ng 243/243 kasalukuyang approved records, 0 exact duplicates, 0 cross-split duplicate/group leakage, at 93 recomputed near-duplicate pairs. Sa contact sheets, 46 records ang malinaw na specimen-sheet holds, 1 ang held dahil harvested sa labas ng field setting, 93 near-duplicate copies ang held, at 103 ang mukhang live field photos. Ang mga 103 ay bumubuo lang ng 69 source observation groups (train: 41; validation: 13; old test: 15), at **hindi training-ready**: species labels at row-level Philippine provenance ay hindi independent na napatunayan. Tingnan ang [candidate summary](v3-corpus-audit/candidate-summary.json), [candidate review manifest](v3-corpus-audit/candidate-review-manifest.csv), [preliminary field-photo list](v3-corpus-audit/preliminary-field-photos.csv), at [visual notes](v3-corpus-audit/preliminary-visual-review.md). Hindi binago ang source data, approved review history, o active model. Susunod: qualified label/provenance review at bagong independent blind-test cohort; saka gumawa ng experimental training snapshot.

**Bounded data collection, owner gallery review, at automated staging audit: kumpleto para sa unang batch.** Nakakuha ng tig-150 bagong Philippines-filtered, iNaturalist research-grade candidates para sa *Chromolaena* at *Lantana*; walang nakuha para sa *Pontederia*. Sinubukan ang pagpapatuloy lampas sa huling iNaturalist observation ID at maliit na GBIF sample; walang bagong Water Hyacinth images. Valid staging totals: 302 / 300 / 129 images at 217 / 209 / 87 observation groups ayon sa pagkakasunod. Kinumpirma ng owner na tama ang class labels sa tatlong gallery. Lahat ng 731 files ay pumasa sa checksum, decode, license/attribution, PH-source-filter, at provenance-field checks. May 6 exact-duplicate groups at 7 karagdagang near-duplicate groups; nagdagdag ng exact-checksum dedupe sa automatic training freeze. Apat na Hagonoy images ay 223×500 px. Ang AI visual screen ay hindi nakatakbo dahil ubos ang shared free quota; field suitability at exact locality ay hindi pa independently na-verify. Tingnan ang [collection update](model-accuracy-collection-2026-10-31.md), [reproducible staging audit](../scripts/audit_staging_species.py), at [audit report](staging-quality-audit-2026-10-31.json). Susunod: kumuha ng bagong *Pontederia* field data at saka gumawa ng leakage-safe experimental snapshot. Walang training run o model promotion.

**Water Lettuce gallery review: kumpleto; model promotion: hindi pasado.** Tinanggap ng owner ang gallery bilang candidate Water Lettuce photos. Sa 168 PH records/148 observation groups, 161 photos ay CC BY-NC at hindi puwedeng gamitin sa invasive-class training policy; 7 CC BY/CC0 photos lang mula sa 6 groups ang eligible. Walang dagdag na eligible PH photos ang bounded rescan. Ang existing 11-class candidate ay 73.52% accuracy / 73.53% macro F1; Pistia recall 83.33% sa 24 test photos. Sa fixed benchmark para sa tatlong active class, 63.64% accuracy / 71.43% macro recall ito kumpara sa live model na 90.91% / 92.86% (33 photos). Hindi pasado ang candidate sa quality o benchmark gate, kaya hindi ito ia-activate. Tingnan ang [Water Lettuce status](model-expansion-status-2026-10-31.md), [candidate dossier](model-expansion-candidate-pistia-stratiotes.md), at [gallery](http://127.0.0.1:8767/invasive_pistia_stratiotes_ph/review_gallery.html).

**Mikania gallery review: kumpleto; model promotion: hindi pasado.** Inaprubahan ng owner ang 151-photo main gallery at 30-photo supplemental gallery. Ang 30 supplemental photos ay CC BY/CC0 at checksum-deduplicated laban sa main gallery. Pagkatapos ng benchmark-overlap at near-duplicate filtering, ang five-class candidate ay may 124 images, 47 dito ay Mikania. Nakuha nito ang 39.13% accuracy / 35.24% macro F1 sa 23 test photos at mas mababa ito sa live model sa fixed benchmark. Hindi ito ia-activate; nanatiling unchanged ang active model. Tingnan ang [main gallery](http://127.0.0.1:8767/invasive_mikania_micrantha_ph/review_gallery.html), [supplemental gallery](http://127.0.0.1:8767/invasive_mikania_micrantha_ph/supplemental_review_gallery.html), at [status report](model-expansion-status-2026-10-31.md).

### Gagawin ko rito

1. I-validate ang 243 larawan ng v3 manifest: file/readability, checksums, labels/review records, duplicate at group assignments, split leakage, dimensions at basic image quality.
2. Gumawa ng contact sheets at i-flag ang specimen/herbarium, hindi field-like, out-of-scope, malabo, o kahina-hinalang larawan para sa human review. Hindi ko babaguhin nang tahimik ang approved labels o ang kasalukuyang active dataset.
3. Iulat ang bilang kada species/split at ang pinagmulan; panatilihin ang lumang manifest at artifacts. Kung may malinaw na data-quality exclusions, gumawa ng bagong versioned candidate snapshot, hindi overwrite.
4. Patakbuhin ang baseline/candidate training at validation-only experiments sa hiwalay na artifacts. Iwanang untouched ang lumang test split para sa paghahambing; dahil nailathala na ang resulta nito, hindi na ito magiging bagong blind test.
5. Suriin ang kasalukuyang unsupported/lookalike staging data at ihanda ang evaluation scripts/report. Walang candidate na ia-activate hangga't hindi pumapasa sa promotion gate.

### Kailangan ng owner o external reviewer

- Bagong, tunay na Philippine field photos mula sa iba-ibang lugar, season at phone/camera, na may pahintulot at usable provenance. Kaya kong ihanda/patakbuhin ang supported public-source collection tools, pero hindi ako makakakuha ng field coverage na wala sa sources.
- Botanical confirmation ng mahirap o hindi siguradong labels at hiwalay na sign-off sa final test labels. Maaari kong i-flag at ayusin ang metadata; hindi ko dapat ipanggap na expert verification ang aking visual screen.
- Pagpili/pag-apruba ng operational scope at anumang claim na ilalagay sa users o stakeholders.

### Unang deliverable at gate

Ang unang output ay isang audit report at review contact sheets para sa kasalukuyang v3 corpus, kasama ang listahan ng mga dapat i-hold at ang usable sample count bawat species. Pagkatapos nito, magpapasya tayo kung sapat ang nalinis na data para sa experimental training iteration o kailangan munang magdagdag ng field data. Ang gate ay **walang model promotion at walang 95% claim** hangga't hindi may bagong independent test cohort at kinakailangang human verification.

## Mga phase

### Phase 0 — I-freeze ang scope at sukatan

1. Panatilihin muna ang tatlong active species; huwag idagdag ang research-queue candidates bilang model classes habang hindi pa dumadaan sa sariling review at acceptance gate.
2. Tukuyin kung saan gagamitin ang score: Philippine field photos mula sa cellphone, isang pangunahing plant/organ visible, hindi herbarium images.
3. Itakda ang reporting rules bago mangolekta: overall at per-class metrics, unsupported-input false acceptance, confidence intervals, at hiwalay na performance sa region, season, device, at image condition kapag sapat ang sample.
4. Magtakda ng release gate: top-1 accuracy ≥95% sa blind in-scope test, macro F1 ≥90%, walang species na recall <90%, at sa accepted predictions ay precision ≥95% na may ≥80% coverage. Sa hiwalay na unsupported set, false-accept rate ≤5%. Iulat din ang bawat metric at confidence interval; kung kulang ang sample para sa makabuluhang interval, dagdagan ang test set.

**Gate:** aprubado ang scope, label guide, data split rules, at evaluation report template bago mag-training.

### Phase 1 — Ayusin at i-verify ang data

1. I-audit ang v3 active dataset at bawat source record. Itala ang scientific/common name, license, source, collection locality/date kung alam, photographer/observation ID, at reviewer/rationale.
2. Ipa-review sa botanist o kwalipikadong reviewer ang bawat label. Ihiwalay ang uncertain, juvenile, damaged, partial, at lookalike examples; huwag piliting lagyan ng species label ang hindi sigurado.
3. Magkaroon ng hiwalay na label para sa `unknown / not one of the target classes`, na may non-target Philippine plants, malalapit na lookalikes, non-plant objects, at mahihirap na photos. Panatilihin ang source/license checks.
4. Sukatin ang bilang ng **independent observations at halaman**, hindi lang bilang ng files. Ang maraming kuha ng iisang halaman o observation ay isang group.

**Gate:** walang unresolved label issue sa training/validation/test candidates; may source provenance at review trail ang bawat image.

### Phase 2 — Mangolekta ng mas representatibong field photos

Gamitin itong panimulang target bawat species, at taasan kung hindi pa sakop ang variation:

| Partition | Panimulang target bawat species | Gamit |
|---|---:|---|
| Train | 500–1,000 independent observations | Matutunan ang natural na variation |
| Validation | 100–200 independent observations | Model selection, threshold at calibration |
| Blind test | ≥300 independent observations | Isang beses na final estimate |

Magdagdag din ng hindi bababa sa 500 reviewed unsupported photos para sa development ng rejection logic, at panatilihin ang hiwalay na blind unsupported test. Balansihin ang coverage sa rehiyon, season, cellphone/camera, distance, plant age, background, lighting, focus at framing. Iwasan ang pagkuha ng lahat sa iisang source o iisang lokasyon.

Mga bilang na ito ay **collection targets, hindi patunay ng 95%**. Kung hindi kayang abutin, sabihin ang limitasyon at huwag mag-claim ng malawak na nationwide performance. Ang test sample size at confidence interval ang magtatakda kung gaano kalakas ang claim.

**Gate:** sapat at sari-sari ang independent field groups bawat klase; may blind test data na hindi makikita ng training team habang nag-eeksperimento.

### Phase 3 — Gumawa ng leakage-safe dataset snapshot

1. I-normalize ang image decoding at preprocessing sa parehong code path para sa training at inference.
2. I-group bago mag-split ang exact duplicates, perceptual near-duplicates, parehong observation/plant, at kung posible parehong photographer/location burst. Isang group lang ang puwedeng mapunta sa isang partition.
3. Gumawa ng versioned, checksummed train/validation/test manifests. Panatilihing untouched ang blind test hanggang final evaluation.
4. Gumamit ng group-aware, stratified cross-validation sa training/validation para pumili ng hyperparameters; huwag i-tune sa blind test.

**Gate:** automated split audit ay pumapasa at nagpapatunay na walang group leakage.

### Phase 4 — Mag-train ng MobileNetV2 transfer-learning candidates

1. Magsimula sa ImageNet-pretrained MobileNetV2 na walang original classification head. I-freeze ang backbone at sanayin muna ang bagong classification head.
2. Pagkatapos maging stable ang head, mag-eksperimento sa pag-unfreeze ng iilang top layers gamit ang mas mababang learning rate. Panatilihing inference mode ang BatchNormalization habang fine-tuning.
3. Ihambing ang ilang seeds at makatwirang variants: class weighting/sampling, regularization, at conservative train-only augmentation (lighting, crop/scale, rotation). Huwag gumawa ng augmentation na nagbabago ng species-defining traits o maglagay ng augmented copy sa validation/test.
4. I-save ang learning curves, confusion matrix, seed, preprocessing, manifest hashes, class mapping, weights, dependency versions at checksums para sa bawat candidate.

**Gate:** piliin lang ang candidate gamit ang grouped validation; kailangan nitong umangat sa baseline nang walang malaking per-class regression o sobrang overfit.

### Phase 5 — Hiwalay na kilalanin ang target at unknown inputs

1. Sukatin ang in-scope classification at unknown detection nang hiwalay. Huwag ituring ang pinakamataas na softmax score bilang patunay na kabilang sa tatlong klase.
2. I-calibrate ang confidence gamit lamang ang validation data at piliin ang threshold ayon sa precision/coverage trade-off.
3. Subukan ang unknown/lookalike, non-plant, malabo, madilim, overexposed, cropped, at out-of-region photos. Ang mababang confidence ay dapat magresulta sa “hindi sigurado / hindi suportadong larawan,” hindi sapilitang species label.
4. Ipakita sa user na mungkahi lang ito; reviewer-confirmed sightings ang batayan ng verified map data.

**Gate:** naaabot ang target na false-accept rate sa validation unknown set nang hindi bumabagsak sa minimum coverage.

### Phase 6 — Blind final evaluation at approval

1. I-freeze ang model, threshold, class mapping at preprocessing bago buksan ang blind test.
2. Ipatakbo ang final evaluation nang isang beses. Iulat ang overall/per-class accuracy, macro F1, precision/recall, confusion matrix, confidence intervals, coverage/selective accuracy, unknown false acceptance, at subgroup results.
3. Kung pumalya sa kahit isang release gate, huwag i-activate. Bumalik sa data/model work gamit ang bagong development data; panatilihing blind ang test. Para sa panibagong final claim, mangolekta ng bagong test cohort.
4. Ipa-review at i-approve ang model card, limitations, artifact checksums at rollback plan bago i-promote.

**Gate:** pasado sa Phase 0 targets at independent reviewer sign-off; kung hindi, mananatiling candidate.

### Phase 7 — Shadow rollout at tuloy-tuloy na monitoring

1. I-deploy muna bilang candidate o shadow version; huwag palitan agad ang active model.
2. Bantayan ang confidence distribution, abstain rate, reviewer corrections, error type, regional/device drift at latency. Huwag gamitin ang unreviewed user predictions bilang ground-truth training labels.
3. Magdagdag ng bagong data pagkatapos ng consent/license at expert review; ulitin ang leakage-safe split, evaluation at promotion gates sa bawat release.

**Gate:** walang critical regression at may ligtas na rollback sa nakaraang active artifact.

## Papel ng tatlong konsepto

- **CNN:** architecture family na kumukuha ng spatial visual features mula sa image; natututo ito ng patterns pero maaari ring matuto ng background/source artifacts kung biased ang data.
- **MobileNetV2:** lightweight CNN backbone at makatwirang baseline para sa mobile/low-resource inference. Hindi awtomatikong nagdudulot ng 95% accuracy.
- **Transfer learning:** gamitin muna ang pretrained backbone bilang frozen feature extractor, sanayin ang bagong class head, at saka lang subukan ang maingat na fine-tuning. Ang performance ay kailangang mapatunayan sa independent test set.

## Mahahalagang limitasyon

- Ang 95% ay performance sa tinukoy na test distribution; hindi nito ginagarantiya ang 95% sa bawat isla, season, camera o lahat ng species sa Pilipinas.
- Mas malaking model o mas maraming epochs ay hindi lunas sa maling labels, duplicates, kakulangan ng independent observations, o source bias.
- Ang 95% threshold para sa accepted predictions ay maaaring magpababa ng coverage. Iulat ang dalawa para hindi maitago ang dami ng larawang tinatanggihan.
- Species additions ay hiwalay na release scope at nangangailangan ng sariling data, blind evaluation at rollback-safe model version.

## Technical references

- TensorFlow, [Transfer learning and fine-tuning](https://www.tensorflow.org/tutorials/images/transfer_learning): freeze the pretrained base first; fine-tune selected top layers with care around BatchNormalization.
- PlantNet-300K authors, [A plant image dataset with high label ambiguity and a long-tailed distribution](https://datasets-benchmarks-proceedings.neurips.cc/paper_files/paper/2021/hash/7e7757b1e12abcb736ab9a754ffb617a-Abstract-round2.html): plant labels can be ambiguous and class distributions imbalanced.
- Guo et al., [On Calibration of Modern Neural Networks](https://proceedings.mlr.press/v70/guo17a.html): confidence scores may need calibration before they are interpreted as probabilities.
- Cattelan & Silva, [How to Fix a Broken Confidence Estimator](https://proceedings.mlr.press/v244/cattelan24a.html): evaluate selective prediction and abstention behavior, not only top-1 accuracy.
