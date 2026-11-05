# Experimental MobileNetV2 baseline

The owner authorized training on October 23, 2026. Labels are approved from owner attestation; per-record Philippine provenance and independent botanical review remain unverified. This run is an experimental classifier baseline, not a verified Philippine benchmark or a production deployment.

Dataset: storage/datasets/curated/v3/manifest.csv. Seed: 42. Counts: 166 train, 38 validation, 39 test. No cross-partition observation, checksum, or recomputed perceptual duplicate groups were detected. Historical v1/v2 were preserved. Dataset metadata and review snapshot are saved beside the v3 manifest.

Run from the project root after installing the training extra in services/ml:

```powershell
.\services\ml\.venv\Scripts\python.exe scripts/train_baseline.py
```

The script refuses to overwrite an existing candidate. It validates current reviews, image checksums, class coverage, and grouping before downloading ImageNet weights and training. Model preprocessing matches the current inference decoder (Pillow RGB resize to 224x224, external MobileNetV2 preprocessing).

Method: frozen ImageNet MobileNetV2 features, trainable softmax head with dropout, inverse-frequency training weights, Adam at 0.001, batch size 16, up to 30 epochs, validation-loss selection with patience 5. This initial baseline does not use augmentation or fine-tuning. Test labels are used only for final evaluation, not checkpoint selection. No confidence threshold is tuned in this run.

Candidate outputs: storage/models/candidates/mobilenetv2_v3_seed42/mobilenetv2.keras, class_mapping.json, and evaluation.json. The script verifies the saved model reloads with equivalent outputs. It does not activate the model in the running service or overwrite default model paths. Run results and completion status must be confirmed from actual artifacts, not from this procedure.

Required follow-up: inspect actual held-out results and per-class sample sizes; test unsupported inputs and latency; assess confidence/uncertainty; resolve geographic evidence; review a candidate before activation. Do not repeatedly tune against this test set.
