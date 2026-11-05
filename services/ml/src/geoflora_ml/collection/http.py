from __future__ import annotations

import os
import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class ApiClient:
    def __init__(
        self, source_name: str, minimum_interval: float, max_retries: int = 4
    ) -> None:
        self.source_name = source_name
        self.minimum_interval = minimum_interval
        self._last_request = 0.0
        contact = os.environ.get("GEOFLORA_CONTACT_EMAIL", "")
        user_agent = "GeoFlora/0.1 (research dataset collection)"
        if contact:
            user_agent += f" ({contact})"

        retry = Retry(
            total=max_retries,
            connect=max_retries,
            read=max_retries,
            status=max_retries,
            backoff_factor=1,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
            respect_retry_after_header=True,
        )
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})
        self.session.mount("https://", HTTPAdapter(max_retries=retry))

    def get_json(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self._throttle()
        response = self.session.get(url, params=params, timeout=(10, 45))
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError(f"{self.source_name} returned a non-object JSON response")
        return payload

    def get_bytes(self, url: str, max_bytes: int) -> bytes:
        self._throttle()
        with self.session.get(url, timeout=(10, 60), stream=True) as response:
            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "").split(";")[0].lower()
            if content_type and not content_type.startswith("image/"):
                raise ValueError(f"Image URL returned unexpected content type: {content_type}")
            declared_size = response.headers.get("Content-Length")
            if declared_size and int(declared_size) > max_bytes:
                raise ValueError(f"Image exceeds the {max_bytes}-byte download limit")

            chunks: list[bytes] = []
            total = 0
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                total += len(chunk)
                if total > max_bytes:
                    raise ValueError(f"Image exceeds the {max_bytes}-byte download limit")
                chunks.append(chunk)
            return b"".join(chunks)

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < self.minimum_interval:
            time.sleep(self.minimum_interval - elapsed)
        self._last_request = time.monotonic()
