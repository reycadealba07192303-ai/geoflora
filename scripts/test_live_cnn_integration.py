"""Exercise a real held-out plant image through the local Next.js -> FastAPI -> Keras path.

Uses a short-lived local MongoDB account/session and removes all test records in finally.
Refuses remote MongoDB URIs so it cannot create a test account in production.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import secrets
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from bson import ObjectId
from pymongo import MongoClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/ml/src"))
from geoflora_ml.inference.predictor import PlantPredictor, default_model_path  # noqa: E402

WEB_URL = os.environ.get("GEOFLORA_TEST_WEB_URL", "http://127.0.0.1:5173")
MODEL_VERSION = "mobilenetv2_v3_seed42"
TARGET = {"chromolaena_odorata", "lantana_camara", "pontederia_crassipes"}
MANIFEST = ROOT / "storage/datasets/curated/v3/manifest.csv"


def local_mongo_uri() -> str:
    if os.environ.get("GEOFLORA_MONGODB_URI"):
        uri = os.environ["GEOFLORA_MONGODB_URI"]
    else:
        env_file = ROOT / "apps/web/.env.local"
        uri = "mongodb://127.0.0.1:27017/geoflora"
        if env_file.is_file():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if line.startswith("GEOFLORA_MONGODB_URI="):
                    uri = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    parsed = urlparse(uri)
    if parsed.scheme != "mongodb" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("Integration test requires a local mongodb:// URI; remote database use is refused.")
    return uri


def main() -> None:
    if not default_model_path().is_file():
        raise RuntimeError("The installed Keras model file is missing.")
    local_predictor = PlantPredictor()
    if not local_predictor.ready or local_predictor.model_version != MODEL_VERSION:
        raise RuntimeError("The locally loaded Keras model is not the expected active version.")
    with MANIFEST.open(encoding="utf-8", newline="") as stream:
        candidates = [row for row in csv.DictReader(stream) if row["split"] == "test" and row["species_id"] in TARGET]
    if not candidates:
        raise RuntimeError("No held-out v3 plant image is available.")

    uri = local_mongo_uri()
    client = MongoClient(uri, serverSelectionTimeoutMS=3000)
    database = client.get_default_database()
    if database is None:
        database = client["geoflora"]
    client.admin.command("ping")
    username = f"cnn_audit_{secrets.token_hex(8)}"
    user_id = ObjectId()
    session_token = secrets.token_hex(32)
    identification_ids = []
    try:
        database.accounts.insert_one({
            "_id": user_id, "username": username, "passwordHash": "integration-test-only",
            "salt": "integration-test-only", "role": "user", "disabled": False,
            "emailVerified": True, "createdAt": datetime.now(timezone.utc), "updatedAt": datetime.now(timezone.utc),
        })
        database.sessions.insert_one({
            "tokenHash": hashlib.sha256(session_token.encode()).hexdigest(), "userId": user_id,
            "expiresAt": datetime.now(timezone.utc) + timedelta(minutes=10),
        })
        last_result = None
        for row in candidates:
            relative = Path(row["local_path"])
            data_root = ROOT / "storage/datasets"
            path = (ROOT / relative if relative.parts[:2] == ("storage", "datasets") else data_root / relative).resolve()
            if not path.is_relative_to(data_root.resolve()):
                raise RuntimeError("Unsafe image path in v3 manifest.")
            image_bytes = path.read_bytes()
            expected = local_predictor.predict(image_bytes)
            with path.open("rb") as image:
                response = requests.post(
                    f"{WEB_URL}/api/identify",
                    cookies={"geoflora_session": session_token},
                    files={"image": (path.name, image, "image/jpeg")},
                    timeout=75,
                )
            if response.status_code != 200:
                raise RuntimeError(f"Next.js identification endpoint returned HTTP {response.status_code}: {response.text[:300]}")
            result = response.json()
            last_result = result
            if result.get("identification_id"):
                identification_ids.append(result["identification_id"])
            # A verified-reference result proves only an exact photo lookup. Try another held-out image instead.
            if result.get("method") == "model":
                if result.get("model_version") != MODEL_VERSION:
                    raise RuntimeError(f"Unexpected model version in CNN response: {result.get('model_version')!r}")
                if not isinstance(result.get("confidence"), (float, int)):
                    raise RuntimeError("CNN response did not include the model's numeric softmax score.")
                if result.get("status") not in {"identified", "uncertain"}:
                    raise RuntimeError(f"Unexpected prediction status: {result.get('status')!r}")
                if abs(float(result["confidence"]) - expected.confidence) > 1e-5:
                    raise RuntimeError("HTTP result does not match a fresh prediction from the loaded active Keras artifact.")
                expected_species = expected.species.id if expected.species else None
                actual_species = (result.get("species") or {}).get("id")
                if actual_species != expected_species:
                    raise RuntimeError("HTTP species result does not match the locally loaded Keras artifact.")
                print(json.dumps({
                    "passed": True, "path": "Next.js /api/identify -> FastAPI /predict -> loaded Keras model.predict",
                    "method": result["method"], "model_version": result["model_version"],
                    "test_species": row["species_id"], "predicted_species": (result.get("species") or {}).get("id"),
                    "status": result["status"], "confidence": result["confidence"],
                    "verified_reference_match": False, "matches_fresh_local_keras_prediction": True,
                }, indent=2))
                return
        raise RuntimeError(f"Every attempted held-out image matched the reference lookup; last method={last_result.get('method') if last_result else None}")
    finally:
        for identification_id in identification_ids:
            try:
                database.identifications.delete_one({"_id": ObjectId(identification_id), "ownerId": str(user_id)})
            except Exception:
                pass
        database.sessions.delete_many({"userId": user_id})
        database.accounts.delete_one({"_id": user_id})
        client.close()


if __name__ == "__main__":
    main()
