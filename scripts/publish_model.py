"""Uploads the administrator-approved model now installed in storage/models to the Hugging Face model repository and reloads the service.

Run once after creating the Space, after an administrator-approved promotion, or whenever the model was changed by hand. Experimental candidates are not published.
Needs GEOFLORA_MODEL_REPO and HF_TOKEN in apps/web/.env.local; GEOFLORA_ML_API_URL should be the Space address.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/ml/src"))
from geoflora_ml.env import load_env  # noqa: E402

load_env()
from model_promotion import _reload, publish  # noqa: E402

if not publish("Publish installed model"):
    sys.exit("Set GEOFLORA_MODEL_REPO (and HF_TOKEN) in apps/web/.env.local first.")
print("Uploaded. Asking the service to load it...")
print(_reload())
