"""Part 6 identification checks through Next.js: real predictions, latency, validation and failure modes.

Starts two temporary `next start` instances on an isolated MongoDB database (build apps/web first):
- 5174 proxies to the running inference service on 8000 (real model predictions and timing);
- 5175 proxies to a scripted fake ML server for timeout, outage and malformed-response cases.
Live reports, accounts and models are not touched.
"""
import csv
import hashlib
import io
import json
import os
import platform
import subprocess
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np
import requests
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "apps/web"
URI = "mongodb://127.0.0.1:27017/geoflora_identification_validation"
REAL, FAKE, FAKE_ML = 5174, 5175, 8999
OUTPUT = ROOT / "docs/part-6-identification-smoke.json"
MODE = {"value": "ok"}


class FakeInference(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, status, body, content_type="application/json"):
        payload = body.encode() if isinstance(body, str) else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        self._send(200, {"service": "geoflora-ml-inference", "ready": MODE["value"] != "unavailable", "model_version": "fake"})

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        mode = MODE["value"]
        if mode == "slow":
            time.sleep(6)
            return self._send(200, {"status": "uncertain"})
        if mode == "unavailable":
            return self._send(503, {"detail": "No trained MobileNetV2 model is installed yet."})
        if mode == "garbage":
            return self._send(200, "<html>proxy error</html>", "text/html")
        if mode == "crash":
            return self._send(500, {"detail": [{"msg": "internal structure"}]})
        self.connection.close()


def start_web(port, ml_url, extra=None):
    env = {**os.environ, "GEOFLORA_MONGODB_URI": URI, "GEOFLORA_ML_API_URL": ml_url, **(extra or {})}
    log = (ROOT / f"storage/logs/identification-smoke-{port}.log").open("w", encoding="utf-8")
    process = subprocess.Popen(["node", "node_modules/next/dist/bin/next", "start", "--hostname", "127.0.0.1", "--port", str(port)],
                               cwd=WEB, env=env, stdout=log, stderr=subprocess.STDOUT)
    for _ in range(60):
        try:
            if requests.get(f"http://127.0.0.1:{port}/api/auth", timeout=3).status_code in (200, 503):
                return process
        except requests.ConnectionError:
            time.sleep(0.5)
    process.kill()
    raise RuntimeError(f"Web instance on {port} did not start")


def session_for(base):
    # Use the isolated validation database's administrator for authenticated API checks.
    # Registration now requires an email/verification flow, which this inference smoke does not test.
    admin = requests.Session()
    setup = admin.get(base + "/api/auth", timeout=15).json()["setupRequired"]
    response = admin.post(base + "/api/auth", json={"action": "setup" if setup else "login", "username": "fixture_admin", "password": "GeoFlora-Smoke-Only-2026"}, timeout=15)
    assert response.status_code == 200, response.text
    return admin


def png(size, color=(30, 120, 40)):
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def post(session, base, payload, name="plant.jpg", content_type="image/jpeg"):
    return session.post(base + "/api/identify", files={"image": (name, payload, content_type)}, timeout=90)


def main():
    active = json.loads((ROOT / "storage/models/active_model.json").read_text())
    active_sha = hashlib.sha256((ROOT / "storage/models/mobilenetv2.keras").read_bytes()).hexdigest()
    rows = [r for r in csv.DictReader((ROOT / "storage/datasets/curated/v3/manifest.csv").open(encoding="utf-8")) if r["split"] == "test"]
    fake = ThreadingHTTPServer(("127.0.0.1", FAKE_ML), FakeInference)
    threading.Thread(target=fake.serve_forever, daemon=True).start()
    processes = []
    evidence = {"generated_at_utc": datetime.now(timezone.utc).isoformat(), "database": URI, "active_model": active,
                "environment": {"platform": platform.platform(), "processor": platform.processor(), "cpu_count": os.cpu_count()}}
    try:
        processes.append(start_web(REAL, "http://127.0.0.1:8000"))
        processes.append(start_web(FAKE, f"http://127.0.0.1:{FAKE_ML}", {"GEOFLORA_INFERENCE_TIMEOUT_MS": "2000"}))
        base, fake_base = f"http://127.0.0.1:{REAL}", f"http://127.0.0.1:{FAKE}"
        user = session_for(base)

        health = requests.get(base + "/api/identify", timeout=10).json()
        assert health["ready"] and health["model_version"] == active["candidate"], health

        # Real predictions: one held-out photo per supported class.
        predictions = []
        for species in sorted({r["species_id"] for r in rows}):
            row = next(r for r in rows if r["species_id"] == species)
            response = post(user, base, (ROOT / "storage/datasets" / row["local_path"]).read_bytes())
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["method"] == "model" and body["model_version"] == active["candidate"]
            assert body["confidence_threshold"] == active["confidence_threshold"] and len(body["candidates"]) == 3
            assert body["identification_id"] and 0 <= body["confidence"] <= 1
            assert (body["status"] == "identified") == (body["confidence"] >= body["confidence_threshold"])
            assert body["species"] is None if body["status"] == "uncertain" else body["information"]["source"]["url"].startswith("https://")
            predictions.append({"expected": species, "status": body["status"], "predicted": (body["species"] or {}).get("id"), "confidence": body["confidence"]})
        evidence["predictions"] = predictions

        # Upload-to-result latency through the web API (multipart upload, auth, normalization, inference, storage).
        timings, sizes = [], []
        photos = [(ROOT / "storage/datasets" / r["local_path"]).read_bytes() for r in rows]
        for photo in photos:
            tick = time.perf_counter()
            response = post(user, base, photo)
            timings.append((time.perf_counter() - tick) * 1000)
            assert response.status_code == 200, response.text
            sizes.append(len(photo))
        evidence["latency"] = {"requests": len(timings), "concurrency": 1, "payload_bytes": {"min": min(sizes), "max": max(sizes), "median": float(np.median(sizes))},
                               "upload_to_result_ms": {"p50": float(np.percentile(timings, 50)), "p95": float(np.percentile(timings, 95)), "max": max(timings)},
                               "target": "p95 <= 5000 ms for <= 5 MB photos, one user", "met": float(np.percentile(timings, 95)) <= 5000 and max(sizes) <= 5 * 1024 * 1024,
                               "scope": "Loopback HTTP on the development machine; excludes mobile network and browser rendering."}

        # Validation failures return clear messages and no prediction.
        cases = {
            "unsupported_type": (post(user, base, b"GIF89a", "plant.gif", "image/gif"), 415),
            "not_an_image": (post(user, base, b"definitely not a photo"), 422),
            "too_small": (post(user, base, png((32, 32)), "small.png", "image/png"), 422),
            "oversized": (post(user, base, b"\xff" * (20 * 1024 * 1024 + 1)), 413),
            "missing_file": (user.post(base + "/api/identify", data={"note": "x"}, timeout=30), 400),
            "signed_out": (post(requests.Session(), base, photos[0]), 401),
        }
        # Failure modes from the inference side, through the second web instance.
        fake_user = session_for(fake_base)
        for mode, expected in (("slow", 504), ("unavailable", 503), ("garbage", 502), ("crash", 500), ("reset", 503)):
            MODE["value"] = mode
            cases[f"inference_{mode}"] = (post(fake_user, fake_base, photos[0]), expected)
        fake.shutdown(); fake.server_close()
        cases["inference_unreachable"] = (post(fake_user, fake_base, photos[0]), 503)
        cases["health_unreachable"] = (requests.get(fake_base + "/api/identify", timeout=10), 503)
        results = {}
        for name, (response, expected) in cases.items():
            detail = response.json().get("detail") if name != "health_unreachable" else response.json().get("reason")
            assert response.status_code == expected, (name, response.status_code, response.text)
            assert isinstance(detail, str) and detail, (name, response.text)
            results[name] = {"status": response.status_code, "message": detail}
        evidence["failure_cases"] = results

        assert hashlib.sha256((ROOT / "storage/models/mobilenetv2.keras").read_bytes()).hexdigest() == active_sha
        evidence["active_model_unchanged"] = True
    finally:
        for process in processes:
            process.kill()
    OUTPUT.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps({"passed": True, "predictions": evidence["predictions"], "latency": evidence["latency"]["upload_to_result_ms"],
                      "failure_cases": {k: v["status"] for k, v in evidence["failure_cases"].items()}}, indent=2))


if __name__ == "__main__":
    main()
