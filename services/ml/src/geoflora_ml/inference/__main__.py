from __future__ import annotations

import os

import uvicorn

from geoflora_ml.env import load_env

if __name__ == "__main__":
    load_env()
    # Hugging Face Spaces sets GEOFLORA_ML_HOST=0.0.0.0 and GEOFLORA_ML_PORT=7860 (deploy/hf-space/Dockerfile).
    uvicorn.run(
        "geoflora_ml.inference.api:app",
        host=os.environ.get("GEOFLORA_ML_HOST", "127.0.0.1"),
        port=int(os.environ.get("GEOFLORA_ML_PORT", "8000")),
        reload=False,
    )
