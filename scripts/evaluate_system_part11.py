"""Part 11 system evaluation: performance, concurrency, reliability, failure modes and recovery.

Everything runs against isolated resources: database geoflora_part11_validation (a read-only copy of the live
catalog plus 2,000 synthetic reports), temporary web instances on 5174-5176, a second inference process on 8001
and a throwaway mongod on 27999 (scratch data directory). The live web, inference service and database are only
read (catalog copy, active model hash). Build apps/web first. Results: docs/part-11-system-evaluation.json.
"""
import argparse
import csv
import hashlib
import http.client
import io
import json
import os
import platform
import random
import secrets
import shutil
import socket
import subprocess
import tempfile
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import requests
from bson import ObjectId
from PIL import Image
from pymongo import MongoClient

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "apps/web"
PYTHON = ROOT / "services/ml/.venv/Scripts/python.exe"
MONGOD = Path(r"C:\Program Files\MongoDB\Server\8.0\bin\mongod.exe")
LIVE = "mongodb://127.0.0.1:27017"
URI = "mongodb://127.0.0.1:27017/geoflora_part11_validation"
OUTAGE_URI = "mongodb://127.0.0.1:27999/geoflora_outage_validation"
OUTPUT = ROOT / "docs/part-11-system-evaluation.json"
SPECIES = ["Chromolaena odorata", "Lantana camara", "Pontederia crassipes", "Mikania micrantha", "Pistia stratiotes"]
processes = []


def percentile(values, q):
    return round(float(np.percentile(np.asarray(values), q)), 1)


def timing(values):
    return {"n": len(values), "p50_ms": percentile(values, 50), "p95_ms": percentile(values, 95), "max_ms": round(max(values), 1)}


def wait_http(url, seconds=90):
    for _ in range(seconds * 2):
        try:
            if requests.get(url, timeout=3).status_code < 500:
                return
        except requests.RequestException:
            pass
        time.sleep(0.5)
    raise RuntimeError(f"{url} did not become ready")


def start(command, cwd, env=None, log="part11.log"):
    handle = (ROOT / "storage/logs" / log).open("w", encoding="utf-8")
    process = subprocess.Popen(command, cwd=cwd, env={**os.environ, **(env or {})}, stdout=handle, stderr=subprocess.STDOUT)
    processes.append(process)
    return process


def start_web(port, uri, ml):
    process = start(["node", "node_modules/next/dist/bin/next", "start", "--hostname", "127.0.0.1", "--port", str(port)], WEB, {"GEOFLORA_MONGODB_URI": uri, "GEOFLORA_ML_API_URL": ml}, f"part11-web-{port}.log")
    wait_http(f"http://127.0.0.1:{port}/api/identify")
    return process


def stop(process):
    process.kill(); process.wait(timeout=30)


def account(base, action, username, password=None):
    session = requests.Session()
    response = session.post(base + "/api/auth", json={"action": action, "username": username, "password": password or secrets.token_urlsafe(18)}, timeout=15)
    assert response.status_code == 200, response.text
    return session, response.json()["user"]["id"]


def noise_png(size=160):
    buffer = io.BytesIO()
    Image.fromarray(np.random.default_rng().integers(0, 256, (size, size, 3), dtype=np.uint8)).save(buffer, format="PNG")
    return buffer.getvalue()


def sighting_fields(**changes):
    return {"requestId": str(uuid.uuid4()), "species": "unknown", "plantDescription": "Evaluation fixture: shrub with small flowers.", "latitude": "14.6", "longitude": "121.0",
            "locationMethod": "manual", "observedAt": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(), "consent": "yes", **changes}


def seed(db, owners):
    live = MongoClient(LIVE).geoflora
    db.species_catalog.insert_many(list(live.species_catalog.find()))
    db.species_catalog_staging.insert_many(list(live.species_catalog_staging.find()))
    rng = random.Random(42)
    centres = [(rng.uniform(6.0, 18.5), rng.uniform(117.5, 126.5)) for _ in range(40)]
    start_time = datetime(2025, 11, 1, tzinfo=timezone.utc)
    docs = []
    for index in range(2000):
        lat, lng = centres[index % 40]
        status = rng.choices(["verified", "pending", "correction_requested", "rejected"], [70, 20, 5, 5])[0]
        species = rng.choice(SPECIES)
        observed = start_time + timedelta(minutes=rng.randrange(0, 360 * 24 * 60))
        doc = {"_id": ObjectId(), "ownerId": owners[index % len(owners)], "requestId": str(uuid.uuid4()), "payloadHash": uuid.uuid4().hex, "status": status,
               "reportedSpecies": species if status != "verified" else "unknown", "observedAt": observed, "submittedAt": observed + timedelta(hours=2),
               "location": {"type": "Point", "coordinates": [round(lng + rng.gauss(0, 0.08), 6), round(lat + rng.gauss(0, 0.08), 6)]}, "locationMethod": "gps",
               "placeName": "evaluation fixture", "reviewHistory": [], "editHistory": [], "trainingConsent": False, "trainingCandidateStatus": "not_requested", "labelReviewStatus": "not_required"}
        if status == "verified":
            doc.update(verifiedScientificName=species, verifiedSpeciesId=species.lower().replace(" ", "_"))
        docs.append(doc)
    db.sightings.insert_many(docs)
    return len(docs)


def load(session, url, total, workers):
    def one(_):
        tick = time.perf_counter()
        try:
            ok = session.get(url, timeout=60).status_code == 200
        except requests.RequestException:
            ok = False
        return (time.perf_counter() - tick) * 1000, ok
    with ThreadPoolExecutor(workers) as pool:
        results = list(pool.map(one, range(total)))
    return {**timing([ms for ms, _ in results]), "workers": workers, "errors": sum(1 for _, ok in results if not ok)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-outages", action="store_true")
    args = parser.parse_args()
    report = {"generated_at_utc": datetime.now(timezone.utc).isoformat(), "environment": {
        "os": platform.platform(), "cpu": "13th Gen Intel Core i7-13620H (10 cores / 16 threads)", "logical_cpus": os.cpu_count(), "ram_gb": 16,
        "network": "Loopback (127.0.0.1); client, Next.js, FastAPI and MongoDB on one machine", "mongodb": "8.0 local", "python": platform.python_version()}}
    active = ROOT / "storage/models/mobilenetv2.keras"
    active_sha = hashlib.sha256(active.read_bytes()).hexdigest()
    MongoClient(URI).drop_database("geoflora_part11_validation")
    db = MongoClient(URI).get_default_database()
    try:
        web = start_web(5174, URI, "http://127.0.0.1:8000")
        base = "http://127.0.0.1:5174"
        admin, _ = account(base, "setup", "eval_admin")
        user, user_id = account(base, "register", "eval_contributor")
        report["dataset"] = {"synthetic_reports": seed(db, [user_id, "eval_other_a", "eval_other_b"]), "catalog_records": db.species_catalog.estimated_document_count(), "staging_records": db.species_catalog_staging.estimated_document_count()}

        # 1. Identification upload-to-result, sequential, real held-out photos up to 5 MB.
        rows = [r for r in csv.DictReader((ROOT / "storage/datasets/curated/v3/manifest.csv").open(encoding="utf-8")) if r["split"] == "test"]
        photos = [(ROOT / "storage/datasets" / r["local_path"]).read_bytes() for r in rows]
        photos = [p for p in photos if len(p) <= 5 * 1024 * 1024]
        identify = lambda session, photo: session.post(base + "/api/identify", files={"image": ("plant.jpg", photo, "image/jpeg")}, timeout=90)
        for photo in photos[:3]:
            identify(user, photo)
        sequential, codes = [], []
        for photo in (photos * 2)[:40]:
            tick = time.perf_counter(); response = identify(user, photo); sequential.append((time.perf_counter() - tick) * 1000); codes.append(response.status_code)
        report["identification_sequential"] = {**timing(sequential), "status_200": codes.count(200), "payload_bytes_max": max(len(p) for p in photos),
                                               "target": "p95 <= 5000 ms for <= 5 MB photos, one user, >= 30 timed requests", "met": percentile(sequential, 95) <= 5000 and codes.count(200) == len(codes) and len(codes) >= 30}
        sessions = [account(base, "register", f"eval_conc_{i}")[0] for i in range(5)]
        def burst(index):
            out = []
            for photo in photos[index * 7:(index * 7) + 8]:
                tick = time.perf_counter(); response = identify(sessions[index], photo); out.append(((time.perf_counter() - tick) * 1000, response.status_code == 200))
            return out
        with ThreadPoolExecutor(5) as pool:
            concurrent = [item for part in pool.map(burst, range(5)) for item in part]
        report["identification_concurrent_5_users"] = {**timing([ms for ms, _ in concurrent]), "errors": sum(1 for _, ok in concurrent if not ok)}

        # 2. Dashboard/map APIs on the representative dataset, 1 and 10 concurrent users.
        moderator = admin
        endpoints = {"occurrences_default": "/api/occurrences", "occurrences_filtered": "/api/occurrences?layer=all&species=lantana%20camara&from=2026-01-01&to=2026-06-30",
                     "analytics_workspace": "/api/analytics", "analytics_filtered": "/api/analytics?layer=all&species=chromolaena%20odorata&bbox=118,8,124,15",
                     "overview": "/api/overview", "catalog_search": "/api/catalog?q=asteraceae", "catalog_listed": "/api/catalog?filter=listed&page=3", "review_queue": "/api/admin/review"}
        moderator.get(base + "/api/catalog", timeout=60)
        dashboard = {}
        for name, path in endpoints.items():
            dashboard[name] = {"single_user": load(moderator, base + path, 30, 1), "ten_users": load(moderator, base + path, 100, 10)}
        worst = max(entry["ten_users"]["p95_ms"] for entry in dashboard.values())
        report["dashboard_apis"] = {"results": dashboard, "worst_p95_ms_10_users": worst, "target": "p95 filtered map/API response <= 3000 ms", "met": worst <= 3000 and all(e["single_user"]["errors"] == e["ten_users"]["errors"] == 0 for e in dashboard.values())}
        occurrences = moderator.get(base + "/api/occurrences?layer=all", timeout=60).json()
        report["dashboard_apis"]["points_returned_layer_all"] = len(occurrences["points"])

        # 3. Controlled 100-request reliability run of valid requests.
        outcomes = []
        for index in range(100):
            kind = index % 10
            try:
                if kind < 3:
                    response = identify(user, photos[index % len(photos)])
                elif kind < 6:
                    response = user.post(base + "/api/sightings", data=sighting_fields(), files={"image": ("plant.png", noise_png(), "image/png")}, timeout=30)
                else:
                    response = user.get(base + ["/api/sightings", "/api/occurrences", "/api/analytics", "/api/catalog?q=lantana"][kind - 6], timeout=30)
                outcomes.append(response.status_code in (200, 201))
            except requests.RequestException:
                outcomes.append(False)
        report["reliability_100"] = {"requests": 100, "succeeded": sum(outcomes), "success_rate": sum(outcomes) / 100, "mix": "30 identifications, 30 report submissions, 40 list/map/analytics/catalog reads", "target": ">= 99% successful valid requests", "met": sum(outcomes) >= 99}

        # 4. Retry behaviour and failed uploads.
        fields, photo = sighting_fields(), noise_png()
        with ThreadPoolExecutor(5) as pool:
            statuses = list(pool.map(lambda _: user.post(base + "/api/sightings", data=fields, files={"image": ("plant.png", photo, "image/png")}, timeout=30).status_code, range(5)))
        concurrent_saved = db.sightings.count_documents({"requestId": fields["requestId"]})
        aborted = sighting_fields()
        boundary = "----geoflora" + uuid.uuid4().hex
        body = "".join(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n" for k, v in aborted.items()).encode()
        body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"plant.png\"\r\nContent-Type: image/png\r\n\r\n".encode() + photo[: len(photo) // 3]
        connection = http.client.HTTPConnection("127.0.0.1", 5174, timeout=10)
        connection.putrequest("POST", "/api/sightings"); connection.putheader("Content-Type", f"multipart/form-data; boundary={boundary}")
        connection.putheader("Content-Length", str(len(body) + len(photo))); connection.putheader("Cookie", "; ".join(f"{c.name}={c.value}" for c in user.cookies))
        connection.endheaders(); connection.send(body); connection.sock.shutdown(socket.SHUT_RDWR); connection.close()
        time.sleep(2)
        partial_saved = db.sightings.count_documents({"requestId": aborted["requestId"]})
        retry = user.post(base + "/api/sightings", data=aborted, files={"image": ("plant.png", photo, "image/png")}, timeout=30)
        again = user.post(base + "/api/sightings", data=aborted, files={"image": ("plant.png", photo, "image/png")}, timeout=30)
        report["retry_and_failed_upload"] = {"concurrent_identical_submissions": {"statuses": statuses, "records_saved": concurrent_saved},
                                             "interrupted_upload": {"records_after_disconnect": partial_saved, "retry_status": retry.status_code, "second_retry_replayed": again.json().get("replayed") is True, "records_after_retries": db.sightings.count_documents({"requestId": aborted["requestId"]})},
                                             "met": concurrent_saved == 1 and partial_saved == 0 and retry.status_code == 201 and again.json().get("replayed") is True}
        invalid = {"gif": user.post(base + "/api/identify", files={"image": ("x.gif", b"GIF89a", "image/gif")}, timeout=30).status_code, "not_image": user.post(base + "/api/identify", files={"image": ("x.jpg", b"not an image", "image/jpeg")}, timeout=30).status_code,
                   "tiny": user.post(base + "/api/identify", files={"image": ("x.png", noise_png(32), "image/png")}, timeout=30).status_code,
                   "oversized": user.post(base + "/api/identify", files={"image": ("x.jpg", b"\xff" * (20 * 1024 * 1024 + 1), "image/jpeg")}, timeout=60).status_code}
        report["invalid_images"] = {**invalid, "met": invalid == {"gif": 415, "not_image": 422, "tiny": 422, "oversized": 413}}

        if not args.skip_outages:
            # 5. Inference outage and recovery without restarting the web app.
            inference = start([str(PYTHON), "-m", "uvicorn", "geoflora_ml.inference.api:app", "--host", "127.0.0.1", "--port", "8001"], ROOT, log="part11-inference-8001.log")
            wait_http("http://127.0.0.1:8001/health", 120)
            web_b = start_web(5175, URI, "http://127.0.0.1:8001")
            base_b = "http://127.0.0.1:5175"
            user_b, _ = account(base_b, "register", "eval_contributor_b")
            before = user_b.post(base_b + "/api/identify", files={"image": ("p.jpg", photos[0], "image/jpeg")}, timeout=90)
            stop(inference)
            during = user_b.post(base_b + "/api/identify", files={"image": ("p.jpg", photos[0], "image/jpeg")}, timeout=90)
            health = requests.get(base_b + "/api/identify", timeout=10)
            inference = start([str(PYTHON), "-m", "uvicorn", "geoflora_ml.inference.api:app", "--host", "127.0.0.1", "--port", "8001"], ROOT, log="part11-inference-8001b.log")
            wait_http("http://127.0.0.1:8001/health", 120)
            after = user_b.post(base_b + "/api/identify", files={"image": ("p.jpg", photos[0], "image/jpeg")}, timeout=90)
            report["inference_outage"] = {"before": before.status_code, "during": during.status_code, "during_message": during.json().get("detail"), "health_during": health.status_code,
                                          "after_restart": after.status_code, "met": before.status_code == 200 and during.status_code == 503 and health.status_code == 503 and after.status_code == 200}
            stop(inference); stop(web_b)

            # 6. Database outage and recovery with a throwaway mongod; the same submission ID is retried.
            data_dir = Path(tempfile.mkdtemp(prefix="geoflora-mongod-"))
            mongod = lambda: start([str(MONGOD), "--port", "27999", "--bind_ip", "127.0.0.1", "--dbpath", str(data_dir)], ROOT, log="part11-mongod.log")
            database = mongod(); time.sleep(4)
            web_c = start_web(5176, OUTAGE_URI, "http://127.0.0.1:8000")
            base_c = "http://127.0.0.1:5176"
            owner, _ = account(base_c, "setup", "outage_admin")
            first = owner.post(base_c + "/api/sightings", data=sighting_fields(), files={"image": ("p.png", noise_png(), "image/png")}, timeout=30)
            stop(database)
            pending = sighting_fields()
            down = owner.post(base_c + "/api/sightings", data=pending, files={"image": ("p.png", photo, "image/png")}, timeout=60)
            auth_down = requests.get(base_c + "/api/auth", timeout=30)
            database = mongod(); time.sleep(5)
            recovered = None
            for _ in range(10):
                recovered = owner.post(base_c + "/api/sightings", data=pending, files={"image": ("p.png", photo, "image/png")}, timeout=30)
                if recovered.status_code in (200, 201):
                    break
                time.sleep(2)
            saved = MongoClient(OUTAGE_URI, serverSelectionTimeoutMS=3000).get_default_database().sightings.count_documents({"requestId": pending["requestId"]})
            report["database_outage"] = {"before": first.status_code, "submit_during": down.status_code, "submit_during_message": down.json().get("detail"), "auth_during": auth_down.status_code, "auth_during_message": auth_down.json().get("detail"),
                                         "retry_after_restart": recovered.status_code, "records_for_retried_id": saved,
                                         "met": first.status_code == 201 and down.status_code == 503 and auth_down.status_code == 503 and recovered.status_code == 201 and saved == 1}
            stop(web_c); stop(database)
            shutil.rmtree(data_dir, ignore_errors=True)
        report["active_model_unchanged"] = hashlib.sha256(active.read_bytes()).hexdigest() == active_sha
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
    OUTPUT.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps({key: value.get("met") for key, value in report.items() if isinstance(value, dict) and "met" in value}, indent=2))


if __name__ == "__main__":
    main()
