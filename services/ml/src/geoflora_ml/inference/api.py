from __future__ import annotations

import hmac
import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from geoflora_ml.inference.model_store import refresh_model
from geoflora_ml.inference.predictor import (
    MAX_UPLOAD_BYTES,
    InvalidImageError,
    ModelUnavailableError,
    PlantPredictor,
)

LOGGER = logging.getLogger(__name__)
LOOPBACK = {"127.0.0.1", "::1", "localhost", "testclient"}
PUBLIC_MODEL_UNAVAILABLE = "The image identification model is unavailable. Please try again later."


def _matches(given: str | None, expected: str) -> bool:
    return given is not None and hmac.compare_digest(given.encode(), expected.encode())


def create_app(predictor: PlantPredictor | None = None) -> FastAPI:
    # Held in a mutable slot so /reload can swap in a newly activated model without restarting the service.
    if predictor is None:
        try:
            refresh_model()
        except Exception:  # noqa: BLE001 - serve whatever model is already on disk.
            LOGGER.exception("Model download failed; using the installed model if any")
    current = {"model": predictor or PlantPredictor()}

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        LOGGER.info(
            "MobileNetV2 inference service ready=%s model_version=%s",
            current["model"].ready,
            current["model"].model_version,
        )
        yield

    app = FastAPI(
        title="GeoFlora Plant Identification",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.predictor = current["model"]
    @app.middleware("http")
    async def require_key(request: Request, call_next):  # type: ignore[no-untyped-def]
        """With GEOFLORA_ML_API_KEY set (the public Hugging Face Space), only the GeoFlora web app may call the service."""
        key = os.environ.get("GEOFLORA_ML_API_KEY")
        if key and request.url.path != "/" and not _matches(request.headers.get("x-geoflora-key"), key):
            return JSONResponse({"detail": "Missing or wrong service key."}, status_code=401)
        return await call_next(request)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.get("/")
    def root() -> dict[str, str]:
        return {"service": "geoflora-ml-inference"}

    @app.get("/health")
    def health() -> dict[str, object]:
        model = current["model"]
        return {
            "service": "geoflora-ml-inference",
            "ready": model.ready,
            "model_version": model.model_version,
            "supported_species_count": model.supported_species_count,
            # Never return internal loader exceptions or filesystem paths from a public health endpoint.
            "reason": None if model.ready else PUBLIC_MODEL_UNAVAILABLE,
            "species": model.species,
        }

    @app.post("/predict")
    async def predict(image: UploadFile = File(...)) -> dict[str, object]:
        model = current["model"]
        if image.content_type not in {"image/jpeg", "image/png", "image/webp"}:
            raise HTTPException(
                status_code=415,
                detail="Upload a JPEG, PNG, or WebP plant photo.",
            )
        if not model.ready:
            raise HTTPException(
                status_code=503,
                detail=PUBLIC_MODEL_UNAVAILABLE,
            )
        image_bytes = await image.read(MAX_UPLOAD_BYTES + 1)
        if len(image_bytes) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="Image exceeds the 20 MB limit.")
        try:
            result = model.predict(image_bytes)
        except InvalidImageError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except ModelUnavailableError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except RuntimeError as exc:
            LOGGER.exception("Model inference failed")
            raise HTTPException(
                status_code=500,
                detail="The model could not process this image.",
            ) from exc

        return {
            "status": result.status,
            "species": result.species.__dict__ if result.species else None,
            "confidence": result.confidence,
            "confidence_threshold": result.confidence_threshold,
            "candidates": result.candidates,
            "model_version": result.model_version,
        }

    @app.post("/embed")
    async def embed(image: UploadFile = File(...)) -> dict[str, object]:
        """Image embedding for verified-reference search; scores are not botanical confidence."""
        model = current["model"]
        if image.content_type not in {"image/jpeg", "image/png", "image/webp"}:
            raise HTTPException(status_code=415, detail="Upload a JPEG, PNG, or WebP plant photo.")
        if not model.ready:
            raise HTTPException(status_code=503, detail=PUBLIC_MODEL_UNAVAILABLE)
        image_bytes = await image.read(MAX_UPLOAD_BYTES + 1)
        if len(image_bytes) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="Image exceeds the 20 MB limit.")
        try:
            embedding = model.embed(image_bytes)
        except InvalidImageError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except ModelUnavailableError as exc:
            raise HTTPException(status_code=503, detail=PUBLIC_MODEL_UNAVAILABLE) from exc
        except RuntimeError as exc:
            LOGGER.exception("Visual feature extraction failed")
            raise HTTPException(status_code=500, detail="The image could not be compared with verified references.") from exc
        return {"embedding": embedding, "embedding_version": model.embedding_version, "score_type": "uncalibrated_cosine_similarity"}

    @app.post("/reload")
    def reload(request: Request) -> dict[str, object]:
        """Load the installed model again (after an automatic activation).

        Allowed from this machine, or remotely with the X-GeoFlora-Reload header matching GEOFLORA_ML_RELOAD_TOKEN (the
        training computer reloading the Hugging Face Space). When GEOFLORA_MODEL_REPO is set, the newest model is
        downloaded first. The new predictor replaces the running one only if it loads; otherwise the previous model
        keeps serving.
        """
        token = os.environ.get("GEOFLORA_ML_RELOAD_TOKEN")
        local = request.client is not None and request.client.host in LOOPBACK
        if not local and not (token and _matches(request.headers.get("x-geoflora-reload"), token)):
            raise HTTPException(status_code=403, detail="Reload is limited to this machine or the reload token.")
        try:
            refresh_model()
        except Exception as exc:  # noqa: BLE001 - a failed download leaves the running model in place.
            LOGGER.exception("Model download failed")
            raise HTTPException(status_code=502, detail=f"The model could not be downloaded: {exc}") from exc
        candidate = PlantPredictor()
        if not candidate.ready:
            raise HTTPException(status_code=409, detail=candidate.unavailable_reason or "The installed model could not be loaded.")
        current["model"] = candidate
        app.state.predictor = candidate
        LOGGER.info("Reloaded model_version=%s", candidate.model_version)
        return {"ready": True, "model_version": candidate.model_version, "supported_species_count": candidate.supported_species_count}

    return app


app = create_app()
