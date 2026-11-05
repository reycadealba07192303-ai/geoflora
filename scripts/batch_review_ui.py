"""Local approval UI for the research batch: http://127.0.0.1:8766."""
import hashlib
import json
import threading
from collections import Counter
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import batch_review as review
from geoflora_ml.datasets.review_app import _handler_for

PAGE = Path(__file__).with_name("batch_review_ui.html")
LOCK = threading.Lock()


def history():
    path = review.REVIEW / "review_events.jsonl"
    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line] if path.exists() else []
    return {r["record_key"]: r for r in events}


def handler():
    base = _handler_for(review.BASE)

    class Handler(base):
        def do_GET(self):
            if not self._is_local_request():
                return self._json({"error": "Local access only"}, status=403)
            parsed = urlparse(self.path)
            if parsed.path == "/":
                return self._send_file(PAGE, "text/html; charset=utf-8")
            query = parse_qs(parsed.query)
            with LOCK:
                rows = review.records()
                latest = history()
            for row in rows:
                row["review"] = latest.get(row["record_key"], {})
                row["status"] = row["review"].get("decision", "pending")
            if parsed.path == "/api/items":
                status = query.get("status", ["pending"])[0]
                species = query.get("species", [""])[0]
                filtered = [r for r in rows if (not status or r["status"] == status) and (not species or r["scientific_name"] == species)]
                try:
                    offset = max(0, int(query.get("offset", ["0"])[0]))
                except ValueError:
                    return self._json({"error": "Invalid offset"}, status=400)
                items = []
                for row in filtered[offset:offset + 20]:
                    items.append({k: v for k, v in row.items() if k != "file"})
                return self._json({"items": items, "total": len(filtered), "species": sorted({r["scientific_name"] for r in rows}), "counts": dict(Counter(r["status"] for r in rows))})
            if parsed.path == "/api/image":
                key = query.get("key", [""])[0]
                row = next((r for r in rows if r["record_key"] == key), None)
                if row is None:
                    return self._json({"error": "Unknown image"}, status=404)
                path = Path(row["file"]).resolve()
                if not path.is_relative_to(review.BASE.resolve()) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
                    return self._json({"error": "Image failed integrity check"}, status=404)
                return self._send_file(path, "image/jpeg")
            return self._json({"error": "Not found"}, status=404)

        def do_POST(self):
            if not self._is_local_request():
                return self._json({"error": "Local access only"}, status=403)
            if self.path not in {"/api/review", "/api/export"}:
                return self._json({"error": "Not found"}, status=404)
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 16384:
                    raise ValueError("Invalid body length")
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict):
                    raise ValueError("Expected JSON object")
                with LOCK:
                    if self.path == "/api/export":
                        review.apply_entries([])
                    else:
                        row = next((r for r in review.records() if r["record_key"] == data.get("record_key")), None)
                        if row is None:
                            raise ValueError("Unknown record")
                        decision = {k: data.get(k, "") for k in review.FIELDS}
                        if any(not isinstance(v, str) for v in decision.values()):
                            raise ValueError("Review fields must be text")
                        decision["scientific_name"] = row["scientific_name"]
                        if not decision["decision"].strip():
                            raise ValueError("Choose a decision")
                        review.apply_entries([decision])
                return self._json({"message": "Saved. Ecological holds remain in effect."})
            except (ValueError, OSError) as exc:
                return self._json({"error": str(exc)}, status=400)

    return Handler


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 8766), handler())
    print("Batch approval UI: http://127.0.0.1:8766", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
