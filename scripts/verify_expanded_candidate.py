"""Check a frozen expanded candidate, saved artifacts, and real FastAPI predictions in isolation."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
os.environ.setdefault("TF_NUM_INTRAOP_THREADS", "2")
os.environ.setdefault("TF_NUM_INTEROP_THREADS", "2")

from fastapi.testclient import TestClient
from geoflora_ml.inference.api import create_app
from geoflora_ml.inference.predictor import PlantPredictor
from geoflora_ml.datasets.duplicates import group_near_duplicates

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "storage/datasets/curated/v5_part2_final_five_classes"
OUT = ROOT / "storage/models/candidates/mobilenetv2_v5_five_seed42"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--frozen-dataset", type=Path, default=DATA)
    parser.add_argument("--candidate", type=Path, default=OUT)
    args = parser.parse_args()
    data = args.frozen_dataset.resolve()
    out = args.candidate.resolve()
    checksums = json.loads((out / "checksums.json").read_text())
    for name, expected in checksums.items():
        assert sha(out / name) == expected, name
    metadata = json.loads((data / "dataset_metadata.json").read_text())
    assert sha(data / "manifest.csv") == metadata["manifest_sha256"]
    assert sha(data / "reviews_snapshot.json") == metadata["reviews_snapshot_sha256"]
    active = ROOT / "storage/models/mobilenetv2.keras"
    active_before = sha(active)
    with (data / "manifest.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    for row in rows:
        assert sha(ROOT / row["local_path"]) == row["sha256"]
        row.pop("near_duplicate_group_id", None)
    grouped, _ = group_near_duplicates(rows, ROOT)
    for field in ("sha256", "group_id", "near_duplicate_group_id"):
        splits = {}
        for row in grouped:
            splits.setdefault(row[field], set()).add(row["split"])
        assert all(len(value) == 1 for value in splits.values()), field
    predictor = PlantPredictor(model_path=out / "mobilenetv2.keras", class_mapping_path=out / "class_mapping.json", species_path=data / "species.yaml")
    assert predictor.ready, predictor.unavailable_reason
    classes = json.loads((out / "class_mapping.json").read_text())["classes"]
    smoke = []
    with TestClient(create_app(predictor)) as client:
        health = client.get("/health").json()
        assert health["ready"] and health["supported_species_count"] == len(classes)
        for entry in classes:
            row = next(r for r in rows if r["split"] == "test" and r["species_id"] == entry["id"])
            response = client.post("/predict", files={"image": ("photo.jpg", (ROOT / row["local_path"]).read_bytes(), "image/jpeg")})
            assert response.status_code == 200, response.text
            prediction = response.json()
            assert prediction["status"] in {"identified", "uncertain"}
            assert 0 <= prediction["confidence"] <= 1
            assert len(prediction["candidates"]) == min(3, len(classes))
            if prediction["status"] == "uncertain":
                assert prediction["species"] is None
            smoke.append({"expected": entry["id"], "source_id": row["source_id"], "response": prediction})
    assert sha(active) == active_before
    evidence = {"health": health, "checks": ["artifact checksums", "all frozen image checksums", "recomputed split isolation", f"{len(classes)} real FastAPI photo requests", "active model unchanged"], "predictions": smoke}
    (out / "inference_smoke.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    checksums["inference_smoke.json"] = sha(out / "inference_smoke.json")
    (out / "checksums.json").write_text(json.dumps(checksums, indent=2), encoding="utf-8")
    print(json.dumps({"passed": True, "checks": evidence["checks"], "supported_species_count": len(classes)}, indent=2))


if __name__ == "__main__":
    main()
