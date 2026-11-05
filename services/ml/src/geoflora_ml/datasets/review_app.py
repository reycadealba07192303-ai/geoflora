from __future__ import annotations

import json
import logging
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from geoflora_ml.datasets.audit import record_review
from geoflora_ml.datasets.review_service import (
    export_approved_manifest,
    get_review_items,
    get_review_stats,
)

LOGGER = logging.getLogger(__name__)
MAX_REQUEST_BYTES = 16_384
STATIC_PATH = Path(__file__).with_name("static") / "review.html"


def run_review_app(data_dir: Path, port: int = 8765) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    handler = _handler_for(data_dir)
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    LOGGER.info("GeoFlora dataset review tool: http://127.0.0.1:%s", port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        LOGGER.info("Stopping GeoFlora dataset review tool")
    finally:
        server.server_close()


def _handler_for(data_dir: Path) -> type[BaseHTTPRequestHandler]:
    class ReviewHandler(BaseHTTPRequestHandler):
        server_version = "GeoFloraReview/1.0"
        sys_version = ""

        def _is_local_request(self) -> bool:
            if self.client_address[0] not in {"127.0.0.1", "::1"}:
                return False
            allowed_hosts = {
                f"127.0.0.1:{self.server.server_port}",
                f"localhost:{self.server.server_port}",
            }
            if self.headers.get("Host") not in allowed_hosts:
                return False
            origin = self.headers.get("Origin")
            return origin is None or origin in {
                f"http://127.0.0.1:{self.server.server_port}",
                f"http://localhost:{self.server.server_port}",
            }

        def do_GET(self) -> None:
            if not self._is_local_request():
                self._json({"error": "Local access only"}, status=403)
                return
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self._send_file(STATIC_PATH, "text/html; charset=utf-8")
                return
            if parsed.path == "/api/items":
                self._items(parse_qs(parsed.query))
                return
            if parsed.path == "/api/stats":
                self._json(get_review_stats(data_dir))
                return
            if parsed.path == "/api/image":
                self._image(parse_qs(parsed.query))
                return
            self._json({"error": "Not found"}, status=404)

        def do_POST(self) -> None:
            if not self._is_local_request():
                self._json({"error": "Local access only"}, status=403)
                return
            parsed = urlparse(self.path)
            if parsed.path not in {"/api/review", "/api/export"}:
                self._json({"error": "Not found"}, status=404)
                return
            length = self.headers.get("Content-Length")
            if not length or not length.isdigit() or int(length) > MAX_REQUEST_BYTES:
                self._json({"error": "Invalid or oversized request body"}, status=413)
                return
            try:
                body = json.loads(self.rfile.read(int(length)))
                if not isinstance(body, dict):
                    raise ValueError("Request body must be a JSON object")
                if parsed.path == "/api/export":
                    output = export_approved_manifest(data_dir)
                    self._json({"path": str(output), "message": "Approved manifest exported"})
                    return
                relabel_to = body.get("relabel_to")
                if relabel_to is not None and not isinstance(relabel_to, str):
                    raise ValueError("relabel_to must be a species ID string")
                record_review(
                    data_dir=data_dir,
                    source=_required_string(body, "source"),
                    source_id=_required_string(body, "source_id"),
                    decision=_required_string(body, "decision"),
                    reviewer=_required_string(body, "reviewer"),
                    rationale=_required_string(body, "rationale"),
                    relabel_to=relabel_to,
                )
                self._json({"message": "Review saved"})
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                self._json({"error": str(exc)}, status=400)

        def _items(self, query: dict[str, list[str]]) -> None:
            try:
                limit = min(200, max(1, int(_first(query, "limit", "50"))))
                offset = max(0, int(_first(query, "offset", "0")))
            except ValueError:
                self._json({"error": "limit and offset must be integers"}, status=400)
                return
            status = _first(query, "status")
            if status and status not in {"pending", "approved", "rejected", "flagged", "relabelled"}:
                self._json({"error": "Unknown review status"}, status=400)
                return
            self._json(
                get_review_items(
                    data_dir,
                    species_id=_first(query, "species"),
                    status=status,
                    source=_first(query, "source"),
                    duplicate_group=_first(query, "duplicate_group"),
                    limit=limit,
                    offset=offset,
                )
            )

        def _image(self, query: dict[str, list[str]]) -> None:
            source = _first(query, "source")
            source_id = _first(query, "source_id")
            from geoflora_ml.datasets.manifest import read_jsonl

            manifest_path = data_dir / "raw" / "manifest.jsonl"
            if not manifest_path.exists():
                self._json({"error": "Image not found"}, status=404)
                return
            record = next(
                (
                    item
                    for item in read_jsonl(manifest_path)
                    if item.get("source") == source and item.get("source_id") == source_id
                ),
                None,
            )
            if record is None:
                self._json({"error": "Image not found"}, status=404)
                return
            from geoflora_ml.datasets.review_service import _safe_image_path

            image_path = _safe_image_path(record, data_dir.resolve())
            if image_path is None:
                self._json({"error": "Image failed integrity validation"}, status=404)
                return
            self._send_file(image_path, mimetypes.guess_type(image_path.name)[0] or "image/jpeg")

        def _send_file(self, path: Path, content_type: str) -> None:
            try:
                payload = path.read_bytes()
            except OSError as exc:
                self._json({"error": str(exc)}, status=404)
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(payload)

        def _json(self, data: Any, status: int = 200) -> None:
            payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: Any) -> None:
            LOGGER.info("%s - %s", self.address_string(), format % args)

    return ReviewHandler


def _first(query: dict[str, list[str]], key: str, default: str = "") -> str:
    values = query.get(key)
    return values[0] if values else default


def _required_string(body: dict[str, Any], key: str) -> str:
    value = body.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value
