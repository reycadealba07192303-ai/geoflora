# GeoFlora image classifier (services/ml) as a Hugging Face Docker Space. Built from the folder that
# scripts/deploy_hf_space.py uploads: this file, requirements.txt, README.md and services/ml/src.
FROM python:3.11-slim

# Spaces run the container as user 1000.
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/home/user/app/services/ml/src \
    GEOFLORA_ML_HOST=0.0.0.0 \
    GEOFLORA_ML_PORT=7860 \
    GEOFLORA_MODEL_PATH=/home/user/models/mobilenetv2.keras \
    GEOFLORA_CLASS_MAPPING_PATH=/home/user/models/class_mapping.json \
    TF_CPP_MIN_LOG_LEVEL=2
# Same layout as the repository, so geoflora_ml finds its packaged files where it expects them.
WORKDIR /home/user/app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt
COPY --chown=user services/ml/src services/ml/src

EXPOSE 7860
# At startup the service downloads the model from GEOFLORA_MODEL_REPO (Space variable) with HF_TOKEN (Space secret).
CMD ["python", "-m", "geoflora_ml.inference"]
