"""Where the served model comes from when the service runs away from the training computer.

With GEOFLORA_MODEL_REPO set (a Hugging Face model repository such as "user/geoflora-model"), the service downloads the
repository's files (model, class_mapping.json, species.yaml, active_model.json) into the installed-model folder at
startup and on /reload. The training computer uploads them there when it promotes a model (scripts/model_promotion.py).
Without it, the model already on disk is used, as in local development.
"""
from __future__ import annotations

import os

from geoflora_ml.inference.predictor import default_model_path


def refresh_model() -> bool:
    repo = os.environ.get("GEOFLORA_MODEL_REPO")
    if not repo:
        return False
    from huggingface_hub import snapshot_download

    target = default_model_path().parent
    target.mkdir(parents=True, exist_ok=True)
    snapshot_download(repo_id=repo, repo_type="model", local_dir=target, token=os.environ.get("HF_TOKEN") or None)
    return True
