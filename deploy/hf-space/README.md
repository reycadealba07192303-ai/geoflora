---
title: GeoFlora Classifier
emoji: 🌿
colorFrom: green
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
---

Image classifier for the GeoFlora invasive plant reporting app. It answers only the GeoFlora web app, which sends the
shared service key (`X-GeoFlora-Key`). The model is downloaded from the private model repository named in the
`GEOFLORA_MODEL_REPO` variable. Deployed by `scripts/deploy_hf_space.py`.
