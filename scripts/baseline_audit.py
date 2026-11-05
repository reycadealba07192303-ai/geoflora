"""Read-only dataset checks and temporary local service smoke checks.

Run with services/ml/.venv/Scripts/python.exe scripts/baseline_audit.py.
    Writes docs/baseline-evidence.json; preserves datasets and review decisions.
Requires the web production build (npm run build in apps/web).
"""
from __future__ import annotations

import csv
import hashlib
import json
import socket
import subprocess
import sys
import tempfile
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import requests
from pymongo import MongoClient
from geoflora_ml.datasets.audit import load_current_reviews
from geoflora_ml.datasets.duplicates import group_near_duplicates
from geoflora_ml.datasets.manifest import read_jsonl
from geoflora_ml.datasets.prepare import prepare_dataset

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "storage/datasets"


def main():
    evidence = {"generated_at": datetime.now(timezone.utc).isoformat()}
    raw = read_jsonl(DATA / "raw/manifest.jsonl")
    reviews = load_current_reviews(DATA)
    evidence["raw_species"] = dict(Counter(r["species_id"] for r in raw))
    evidence["review_events"] = len(read_jsonl(DATA / "raw/reviews.jsonl")) if (DATA / "raw/reviews.jsonl").exists() else 0
    evidence["approved_export_exists"] = (DATA / "curated/approved_manifest.csv").exists()
    evidence["manifests"] = {}
    for manifest in sorted((DATA / "curated").glob("**/*.csv")):
        with manifest.open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        groups = defaultdict(set)
        errors = Counter()
        for r in rows:
            path = (DATA / r["local_path"]).resolve()
            if not path.is_relative_to(DATA.resolve()) or not path.is_file():
                errors["missing_or_unsafe_path"] += 1
            elif hashlib.sha256(path.read_bytes()).hexdigest() != r["sha256"]:
                errors["checksum_mismatch"] += 1
            if reviews.get((r["source"], r["source_id"]), {}).get("decision") not in {"approved", "relabelled"}:
                errors["not_currently_approved"] += 1
            for field in ("sha256", "group_id"):
                groups[(field, r[field])].add(r.get("split", "export"))
        near_cross = None
        if rows and not errors["missing_or_unsafe_path"]:
            grouped, _ = group_near_duplicates(rows, DATA)
            near = defaultdict(set)
            for r in grouped:
                near[r["near_duplicate_group_id"]].add(r.get("split", "export"))
            near_cross = sum(len(v) > 1 for v in near.values())
        raw_keys = {(r["source"], r["source_id"]) for r in raw}
        evidence["manifests"][str(manifest.relative_to(ROOT))] = {
            "rows": len(rows), "sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
            "splits": dict(Counter(r.get("split", "export") for r in rows)),
            "species": dict(Counter(r["species_id"] for r in rows)),
            "errors": dict(errors),
            "absent_from_raw": sum((r["source"], r["source_id"]) not in raw_keys for r in rows),
            "cross_partition_checksum_or_observation_groups": sum(len(v) > 1 for v in groups.values()),
            "cross_partition_near_duplicate_groups": near_cross,
            "training_ready": False,
        }
    with tempfile.TemporaryDirectory() as temporary:
        try:
            prepare_dataset(DATA / "raw/manifest.jsonl", DATA, Path(temporary) / "prepared", 42)
            evidence["prepare_guard"] = "Preparation succeeded"
        except ValueError as exc:
            evidence["prepare_guard"] = str(exc)
    try:
        with MongoClient("mongodb://127.0.0.1:27017", serverSelectionTimeoutMS=2000) as client:
            evidence["mongodb"] = {"ping": client.admin.command("ping")["ok"]}
    except Exception as exc:
        evidence["mongodb"] = {"available": False, "error_type": type(exc).__name__}

    processes = []
    evidence["http"] = {}
    try:
        for port, cwd, command, endpoint in [
            (8000, ROOT / "services/ml", [sys.executable, "-m", "geoflora_ml.inference"], "/health"),
            (5173, ROOT / "apps/web", ["node", "node_modules/next/dist/bin/next", "start", "--hostname", "127.0.0.1", "--port", "5173"], "/"),
            (8765, ROOT, [str(ROOT / "services/ml/.venv/Scripts/geoflora-ml.exe"), "review-ui"], "/"),
        ]:
            with socket.socket() as probe:
                occupied = probe.connect_ex(("127.0.0.1", port)) == 0
            if not occupied:
                processes.append(subprocess.Popen(command, cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
            url = f"http://127.0.0.1:{port}{endpoint}"
            deadline = time.monotonic() + 30
            while True:
                try:
                    response = requests.get(url, timeout=2)
                    response.raise_for_status()
                    break
                except requests.RequestException:
                    if time.monotonic() >= deadline:
                        raise RuntimeError(f"Service did not start: {url}")
                    time.sleep(0.25)
            evidence["http"][url] = {"status": response.status_code, "already_running": occupied}
            if port == 8000:
                evidence["http"][url]["body"] = response.json()
        started = time.monotonic()
        response = requests.get("http://127.0.0.1:8765/api/stats", timeout=45)
        response.raise_for_status()
        evidence["http"]["review_stats"] = {"status": response.status_code, "seconds": round(time.monotonic() - started, 2), "records": response.json()["totals"]["manifest_records"]}
        response = requests.get("http://127.0.0.1:5173/api/identify", timeout=5)
        evidence["http"]["proxy_health"] = {"status": response.status_code, "body": response.json()}
        sample = DATA / raw[0]["local_path"]
        with sample.open("rb") as image:
            response = requests.post("http://127.0.0.1:5173/api/identify", files={"image": ("plant.jpg", image, "image/jpeg")}, timeout=10)
        evidence["http"]["prediction_without_model"] = {"status": response.status_code, "body": response.json()}
        assert response.status_code == 503, "Expected unavailable-model response"
        response = requests.post("http://127.0.0.1:5173/api/identify", files={"image": ("bad.txt", b"invalid", "text/plain")}, timeout=5)
        evidence["http"]["invalid_upload"] = {"status": response.status_code, "body": response.json()}
        assert response.status_code == 415
    finally:
        for process in reversed(processes):
            process.terminate()
            process.wait(timeout=10)
        output = ROOT / "docs/baseline-evidence.json"
        output.parent.mkdir(exist_ok=True)
        output.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        print(output)


if __name__ == "__main__":
    main()
