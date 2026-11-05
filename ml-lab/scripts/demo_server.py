"""Local demo of the lab's work: the pipeline flow with numbers read from this project's own files, photo
identification with an exported bundle (result + species description), and sighting reports with date, time and
location shown on a map.

Location and time come only from the photo's own EXIF data, the device's location, or the user (map pin or typed
coordinates). The model never produces them. Reports are AI suggestions, not verified records. They are stored
locally in demo_data/ (SQLite + photos). Binds to 127.0.0.1.

  python scripts/demo_server.py          # newest export per class count, http://127.0.0.1:8090
  python scripts/demo_server.py --model models/exported/geoflora-mnv2-3cls-v1.1 models/exported/<other> --no-browser

With several models the page offers a model selector; the first one listed (fewest classes by default) is the default.
"""

import base64
import csv
import io
import json
import os
import sqlite3
import tempfile
import threading
import uuid
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from _common import parser, setup

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "demo" / "index.html"
DATA_DIR = ROOT / "demo_data"
LOCATION_SOURCES = {"photo_exif", "device_gps", "map_pin", "manual"}
REPORT_FIELDS = ["id", "created_at", "observed_at", "latitude", "longitude", "location_source", "place", "reporter",
                 "notes", "photo_file", "species_id", "scientific_name", "common_name", "is_target_invasive",
                 "ecological_status", "decision", "score", "model_version"]


def photo_metadata(path) -> dict:
    """Date/time and GPS position recorded by the camera in the photo's EXIF data, when present."""
    from PIL import Image

    out = {"taken_at": None, "latitude": None, "longitude": None}
    try:
        with Image.open(path) as im:
            exif = im.getexif()
            dt = exif.get_ifd(0x8769).get(36867) or exif.get(306)  # DateTimeOriginal, else DateTime
            if dt:
                out["taken_at"] = datetime.strptime(str(dt).strip()[:19], "%Y:%m:%d %H:%M:%S").isoformat(timespec="minutes")
            gps = exif.get_ifd(0x8825)
            if gps.get(2) and gps.get(4):
                def degrees(v, ref):
                    d = float(v[0]) + float(v[1]) / 60 + float(v[2]) / 3600
                    return -d if str(ref).upper() in ("S", "W") else d
                lat, lon = degrees(gps[2], gps.get(1, "N")), degrees(gps[4], gps.get(3, "E"))
                if -90 <= lat <= 90 and -180 <= lon <= 180 and (lat, lon) != (0.0, 0.0):
                    out["latitude"], out["longitude"] = round(lat, 6), round(lon, 6)
    except Exception:  # noqa: BLE001 - missing or malformed EXIF just means no metadata
        pass
    return out


class ReportStore:
    """Sighting reports in demo_data/reports.sqlite; photos in demo_data/photos/."""

    def __init__(self, data_dir: Path):
        self.db = data_dir / "reports.sqlite"
        self.photos = data_dir / "photos"
        self.photos.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS reports (
                id TEXT PRIMARY KEY, created_at TEXT, observed_at TEXT, latitude REAL, longitude REAL,
                location_source TEXT, place TEXT, reporter TEXT, notes TEXT, photo_file TEXT, species_id TEXT,
                scientific_name TEXT, common_name TEXT, is_target_invasive INTEGER, ecological_status TEXT,
                decision TEXT, score REAL, model_version TEXT, prediction_json TEXT)""")

    def _conn(self):
        c = sqlite3.connect(self.db)
        c.row_factory = sqlite3.Row
        return c

    def add(self, fields: dict, photo_name: str, prediction: dict) -> dict:
        p = prediction["prediction"]
        row = {"id": fields["id"], "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "observed_at": fields["observed_at"], "latitude": fields["latitude"], "longitude": fields["longitude"],
               "location_source": fields["location_source"], "place": fields["place"], "reporter": fields["reporter"],
               "notes": fields["notes"], "photo_file": photo_name, "species_id": p["species_id"],
               "scientific_name": p["scientific_name"], "common_name": p.get("common_name", ""),
               "is_target_invasive": int(bool(p.get("is_target_invasive"))), "ecological_status": p.get("ecological_status"),
               "decision": prediction["unknown_handling"]["decision"], "score": p["softmax_score"],
               "model_version": prediction["model_version"]}
        with self._conn() as c:
            c.execute(f"INSERT INTO reports ({', '.join(REPORT_FIELDS)}, prediction_json) VALUES "
                      f"({', '.join('?' * (len(REPORT_FIELDS) + 1))})",
                      [row[k] for k in REPORT_FIELDS] + [json.dumps(prediction, ensure_ascii=False)])
        return row

    def all(self) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(f"SELECT {', '.join(REPORT_FIELDS)} FROM reports ORDER BY observed_at DESC").fetchall()
        return [{**dict(r), "is_target_invasive": bool(r["is_target_invasive"])} for r in rows]

    def get(self, rid: str) -> dict | None:
        with self._conn() as c:
            r = c.execute("SELECT * FROM reports WHERE id = ?", (rid,)).fetchone()
        return dict(r) if r else None

    def delete(self, rid: str) -> bool:
        r = self.get(rid)
        if not r:
            return False
        with self._conn() as c:
            c.execute("DELETE FROM reports WHERE id = ?", (rid,))
        (self.photos / r["photo_file"]).unlink(missing_ok=True)
        return True


def parse_report_fields(body: dict) -> dict:
    """Validate the user-supplied report fields; raise ValueError with a readable message."""
    try:
        lat, lon = float(body.get("latitude")), float(body.get("longitude"))
    except (TypeError, ValueError):
        raise ValueError("A location is required: use the photo's GPS, your current location, or click the map.")
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("Latitude must be between -90 and 90 and longitude between -180 and 180.")
    if body.get("location_source") not in LOCATION_SOURCES:
        raise ValueError("Unknown location source.")
    try:
        observed = datetime.fromisoformat(str(body.get("observed_at"))).isoformat(timespec="minutes")
    except ValueError:
        raise ValueError("Enter the date and time the plant was seen.")
    clip = lambda k, n: str(body.get(k) or "").strip()[:n]
    return {"id": uuid.uuid4().hex[:12], "observed_at": observed, "latitude": round(lat, 6), "longitude": round(lon, 6),
            "location_source": body["location_source"], "place": clip("place", 200), "reporter": clip("reporter", 100),
            "notes": clip("notes", 1000)}


def flow_stats(cfg: dict, bundle: Path, store: "ReportStore") -> dict:
    """Every number shown on the Flow tab, read from the project's manifest, reports and the exported bundle."""
    from geoflora_ml.config import project_path
    from geoflora_ml.manifest import load_manifest
    from geoflora_ml.utils import read_json

    reports = project_path(cfg, "reports")
    m = load_manifest(project_path(cfg, "image_manifest"))
    val = read_json(reports / "validation_summary.json")
    meta = read_json(bundle / "model_metadata.json")
    split = next((r for f in sorted(reports.rglob("split_report.json"))
                  if (r := read_json(f)).get("dataset_version") == meta["dataset_version"]),
                 read_json(reports / "split_report.json"))
    metrics = read_json(bundle / "evaluation_metrics.json")
    unk = metrics["unsupported_species"]["test"]
    ev = meta["evaluation_summary"]
    review = m["review_status"].value_counts().to_dict()
    reviewers = m.loc[m["review_status"] != "pending", "reviewer"].value_counts().to_dict()
    counts = {k: sum(v.values()) for k, v in split["image_counts"].items()}
    pct = lambda x: f"{100 * x:.1f}%"
    steps = [
        {"title": "Collect photos", "what": "Download licensed plant photos and their records from GBIF (mostly iNaturalist).",
         "numbers": [["Photos", len(m)], ["Species", m["species_id"].nunique()],
                     ["From the Philippines", pct((m["country_code"] == "PH").mean())],
                     ["Licenses", ", ".join(f"{k} ({v})" for k, v in m["license"].value_counts().items())]]},
        {"title": "Check quality", "what": "Reject unreadable, blurry, dark or tiny photos; link duplicates and photos from the same observation.",
         "numbers": [["Readable", val["readable"]], ["Passed quality checks", val["quality_pass"]],
                     ["Independent observation groups", val["total_observation_groups"]]]},
        {"title": "Review labels", "what": "A named reviewer approves, rejects or marks each photo unsure. Only approved photos are used.",
         "numbers": [["Approved", review.get("approved", 0)], ["Rejected", review.get("rejected", 0)],
                     ["Unsure", review.get("uncertain", 0)], ["Pending", review.get("pending", 0)],
                     ["Reviewer", ", ".join(reviewers) or "none yet"]],
         "note": cfg.get("review", {}).get("label_basis", "")},
        {"title": "Split the data", "what": "Divide by observation group so no plant appears in both training and testing.",
         "numbers": [["Train", counts.get("train", 0)], ["Validation", counts.get("val", 0)], ["Test", counts.get("test", 0)],
                     ["Other plants (threshold tuning)", counts.get("unknown_val", 0)],
                     ["Other plants (final test)", counts.get("unknown_test", 0)],
                     ["Leakage violations", split["leakage_check"]["violations"]]]},
        {"title": "Train the model", "what": meta["architecture"] + ", ImageNet transfer learning then fine-tuning.",
         "numbers": [["Classes", meta["num_classes"]], ["Training photos", meta["training"]["images"]["train"]],
                     ["Epochs", meta["training"]["epochs_run"]], ["Selected phase", meta["training"]["selected_phase"]]]},
        {"title": "Evaluate", "what": "Measure on test photos the model never saw, and on plants it was not trained on.",
         "numbers": [["Test accuracy", f"{pct(ev['test_accuracy'])} (95% CI {pct(ev['test_accuracy_ci'][0])}-{pct(ev['test_accuracy_ci'][1])})"],
                     ["Macro F1", f"{ev['test_macro_f1']:.3f}"],
                     ["Other plants wrongly accepted", f"{pct(ev['unknown_false_acceptance_with_threshold'])} of {ev['unknown_test_images']}"],
                     ["Target photos accepted at that threshold", pct(unk["known_acceptance_rate"])],
                     ["Time per photo (CPU)", f"{ev['batch1_latency_ms_median']:.0f} ms"]],
         "figures": [p.name for p in sorted(bundle.glob("*.png"))]},
        {"title": "Export for GeoFlora", "what": "Package the model, class mapping, preprocessing, descriptions and report. Not activated.",
         "numbers": [["Model version", meta["model_version"]], ["Status", meta["status"]],
                     ["Model SHA-256", meta["model_sha256"][:16] + "..."]]},
    ]
    reports = store.all()
    steps.append({"title": "Report and map sightings",
                  "what": "Save an identified photo with the date, time and place it was seen, and show all sightings on a map. "
                          "Location comes from the photo's GPS, the device, or a map pin, never from the model.",
                  "numbers": [["Reports", len(reports)],
                              ["Target invasive (model sure)", sum(r["is_target_invasive"] and r["decision"] == "supported_species" for r in reports)],
                              ["Uncertain", sum(r["decision"] != "supported_species" for r in reports)]]})
    descriptions = read_json(bundle / "species_descriptions.json") if (bundle / "species_descriptions.json").exists() else {}
    species = [{**s, "description": descriptions.get(s["species_id"])} for s in meta["supported_species"]]
    return {"model_version": meta["model_version"], "steps": steps, "species": species}


def make_handler(cfg: dict, models: dict, lock: threading.Lock, store: ReportStore):
    """models: model_version -> {"bundle": Path, "predictor": Predictor}; the first entry is the default."""
    default = next(iter(models))
    from urllib.parse import parse_qs, urlsplit

    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, obj) -> None:
            self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def _model(self):
            q = parse_qs(urlsplit(self.path).query).get("model", [default])[0]
            return models.get(q) or models[default]

        def do_GET(self):  # noqa: N802
            route = urlsplit(self.path).path
            if route in ("/", "/index.html"):
                self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
            elif route == "/api/models":
                self._json(200, {"default": default, "models": [
                    {"model_version": v, "num_classes": m["meta"]["num_classes"],
                     "test_accuracy": m["meta"]["evaluation_summary"]["test_accuracy"]} for v, m in models.items()]})
            elif route == "/api/flow":
                self._json(200, flow_stats(cfg, self._model()["bundle"], store))
            elif route == "/api/reports":
                self._json(200, {"reports": store.all()})
            elif route == "/api/reports.csv":
                buf = io.StringIO()
                w = csv.DictWriter(buf, fieldnames=REPORT_FIELDS)
                w.writeheader()
                w.writerows(store.all())
                self._send(200, ("﻿" + buf.getvalue()).encode("utf-8"), "text/csv; charset=utf-8")
            elif route.startswith("/photos/"):
                r = store.get(route.rsplit("/", 1)[-1])
                f = store.photos / r["photo_file"] if r else None
                if f and f.is_file():
                    self._send(200, f.read_bytes(), {".png": "image/png", ".webp": "image/webp"}.get(f.suffix, "image/jpeg"))
                else:
                    self._json(404, {"error": "not found"})
            elif route.startswith("/figures/"):
                name = route.rsplit("/", 1)[-1]
                bundle = self._model()["bundle"]
                fig = bundle / name
                if name.endswith(".png") and fig.parent == bundle and fig.is_file():
                    self._send(200, fig.read_bytes(), "image/png")
                else:
                    self._json(404, {"error": "not found"})
            else:
                self._json(404, {"error": "not found"})

        def do_DELETE(self):  # noqa: N802
            if self.path.startswith("/api/reports/") and store.delete(self.path.rsplit("/", 1)[-1]):
                return self._json(200, {"deleted": True})
            self._json(404, {"error": "not found"})

        def do_POST(self):  # noqa: N802
            route = urlsplit(self.path).path
            if route == "/api/reports":
                return self._save_report()
            if route != "/api/predict":
                return self._json(404, {"error": "not found"})
            size = int(self.headers.get("Content-Length") or 0)
            if not 0 < size <= MAX_UPLOAD_BYTES:
                return self._json(400, {"error": "Send one photo of at most 20 MB."})
            data = self.rfile.read(size)
            fd, tmp = tempfile.mkstemp(suffix=".img")
            try:
                with os.fdopen(fd, "wb") as f:
                    f.write(data)
                with lock:
                    result = self._model()["predictor"].predict(tmp)
                result["image"]["filename"] = self.headers.get("X-Filename", "upload")
                result["photo_metadata"] = photo_metadata(tmp)  # from the camera's EXIF, not from the model
                self._json(200, result)
            except Exception as exc:  # noqa: BLE001 - unreadable uploads are the expected failure
                self._json(400, {"error": f"Could not read this image as a photo ({type(exc).__name__})."})
            finally:
                Path(tmp).unlink(missing_ok=True)

        def _save_report(self):
            size = int(self.headers.get("Content-Length") or 0)
            if not 0 < size <= MAX_UPLOAD_BYTES * 2:
                return self._json(400, {"error": "Report is empty or too large."})
            try:
                body = json.loads(self.rfile.read(size))
                fields = parse_report_fields(body)
                photo = base64.b64decode(body.get("photo_b64") or "", validate=True)
            except (ValueError, json.JSONDecodeError) as exc:
                return self._json(400, {"error": str(exc) or "Invalid report."})
            if not 0 < len(photo) <= MAX_UPLOAD_BYTES:
                return self._json(400, {"error": "Attach one photo of at most 20 MB."})
            from PIL import Image

            try:
                with Image.open(io.BytesIO(photo)) as im:
                    ext = {"PNG": ".png", "WEBP": ".webp"}.get(im.format, ".jpg")
            except Exception:  # noqa: BLE001
                return self._json(400, {"error": "The attached file is not a readable photo."})
            path = store.photos / f"{fields['id']}{ext}"
            path.write_bytes(photo)
            try:
                with lock:  # identify again on the server so the saved result always comes from the model
                    prediction = (models.get(body.get("model")) or models[default])["predictor"].predict(path)
                row = store.add(fields, path.name, prediction)
            except Exception as exc:  # noqa: BLE001
                path.unlink(missing_ok=True)
                return self._json(400, {"error": f"Could not save the report ({type(exc).__name__})."})
            self._json(200, {"report": row})

        def log_message(self, fmt, *args):  # keep the console quiet apart from errors
            if not str(args[1] if len(args) > 1 else "").startswith("2"):
                super().log_message(fmt, *args)

    return Handler


def main():
    p = parser(__doc__)
    p.add_argument("--model", nargs="*", default=None,
                   help="exported bundle directories; first = default (default: newest export per class count)")
    p.add_argument("--port", type=int, default=8090)
    p.add_argument("--no-browser", action="store_true")
    args = p.parse_args()
    cfg = setup(args)
    from geoflora_ml.config import project_path
    from geoflora_ml.inference import Predictor

    from geoflora_ml.utils import read_json

    if args.model:
        bundles = [Path(m).resolve() for m in args.model]
    else:
        newest: dict[int, Path] = {}
        for d in project_path(cfg, "exported").iterdir():
            if (d / "model_metadata.json").exists():
                n = read_json(d / "model_metadata.json")["num_classes"]
                if n not in newest or (d / "model_metadata.json").stat().st_mtime > (newest[n] / "model_metadata.json").stat().st_mtime:
                    newest[n] = d
        if not newest:
            raise SystemExit("No exported model found; run scripts/export_model.py first.")
        bundles = [newest[n] for n in sorted(newest)]
    models = {}
    for b in bundles:
        print(f"Loading {b.name} ...")
        meta = read_json(b / "model_metadata.json")
        models[meta["model_version"]] = {"bundle": b, "predictor": Predictor(b), "meta": meta}
    store = ReportStore(DATA_DIR)

    class Server(ThreadingHTTPServer):
        allow_reuse_address = os.name != "nt"  # on Windows SO_REUSEADDR lets a second server silently share the port

    try:
        server = Server(("127.0.0.1", args.port), make_handler(cfg, models, threading.Lock(), store))
    except OSError:
        raise SystemExit(f"Port {args.port} is already in use - is the demo already running? "
                         f"Stop it with Ctrl+C in its terminal, or start this one with --port {args.port + 1}.")
    url = f"http://127.0.0.1:{args.port}/"
    print(f"GeoFlora-ML-Lab demo running at {url}  (Ctrl+C to stop)")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
