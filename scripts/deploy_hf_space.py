"""Creates or updates the Hugging Face Space that runs the image classifier, and publishes the current model.

Needs in apps/web/.env.local: HF_TOKEN (a write token), GEOFLORA_HF_SPACE (e.g. your-name/geoflora-classifier),
GEOFLORA_MODEL_REPO (e.g. your-name/geoflora-model), GEOFLORA_ML_API_KEY and GEOFLORA_ML_RELOAD_TOKEN.

The Space is public so the web app on Vercel can reach it, but it answers only requests carrying GEOFLORA_ML_API_KEY.
The model repository is private; the Space reads it with the HF_TOKEN secret set here. Run again after changing
services/ml; the Space rebuilds on its own (a few minutes).
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/ml/src"))
from geoflora_ml.env import load_env  # noqa: E402

load_env()
from huggingface_hub import HfApi  # noqa: E402

from model_promotion import publish  # noqa: E402

REQUIRED = ("HF_TOKEN", "GEOFLORA_HF_SPACE", "GEOFLORA_MODEL_REPO", "GEOFLORA_ML_API_KEY", "GEOFLORA_ML_RELOAD_TOKEN")


def space_url(space: str) -> str:
    owner, name = space.lower().split("/")
    return "https://" + f"{owner}-{name}".replace("_", "-").replace(".", "-") + ".hf.space"


def main():
    if missing := [name for name in REQUIRED if not os.environ.get(name)]:
        sys.exit(f"Set these in apps/web/.env.local first: {', '.join(missing)}")
    space = os.environ["GEOFLORA_HF_SPACE"]
    api = HfApi(token=os.environ["HF_TOKEN"])
    print(f"Signed in to Hugging Face as {api.whoami()['name']}")

    print("Publishing the installed model to", os.environ["GEOFLORA_MODEL_REPO"])
    publish("Publish installed model")

    api.create_repo(space, repo_type="space", space_sdk="docker", private=False, exist_ok=True)
    for key in ("HF_TOKEN", "GEOFLORA_ML_API_KEY", "GEOFLORA_ML_RELOAD_TOKEN"):
        api.add_space_secret(space, key, os.environ[key])
    api.add_space_variable(space, "GEOFLORA_MODEL_REPO", os.environ["GEOFLORA_MODEL_REPO"])
    api.upload_folder(repo_id=space, repo_type="space", folder_path=ROOT / "deploy/hf-space", commit_message="Space files")
    api.upload_folder(repo_id=space, repo_type="space", folder_path=ROOT / "services/ml/src", path_in_repo="services/ml/src",
                      ignore_patterns=["**/__pycache__/**", "*.pyc"], delete_patterns=["*.py", "*.yaml"], commit_message="Classifier source")
    url = space_url(space)
    print(f"Space uploaded: https://huggingface.co/spaces/{space}")
    print(f"It builds for a few minutes. Then set GEOFLORA_ML_API_URL={url} on Vercel (and here, so promotions reload it).")


if __name__ == "__main__":
    main()
