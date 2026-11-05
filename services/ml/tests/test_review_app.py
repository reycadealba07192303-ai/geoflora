import json
import hashlib
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from PIL import Image

from geoflora_ml.datasets.review_app import _handler_for
from geoflora_ml.datasets.manifest import append_jsonl


class ReviewAppTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.data_dir = Path(self.temp_dir.name)
        image_dir = self.data_dir / "raw" / "images"
        image_dir.mkdir(parents=True)
        for index in range(5):
            image_path = image_dir / f"{index}.jpg"
            color_index = 0 if index == 1 else index
            Image.new(
                "RGB", (96, 96), color=(color_index * 40, color_index * 25, 120)
            ).save(
                image_path, format="JPEG"
            )
            append_jsonl(
                self.data_dir / "raw" / "manifest.jsonl",
                {
                    "source": "inaturalist" if index < 3 else "gbif",
                    "source_id": f"photo-{index}",
                    "observation_id": f"observation-{index}",
                    "species_id": "chromolaena_odorata",
                    "scientific_name": "Chromolaena odorata",
                    "source_url": f"https://example.org/{index}",
                    "license": "cc-by",
                    "attribution": "Contributor",
                    "group_id": f"source-group-{index}",
                    "sha256": hashlib.sha256(image_path.read_bytes()).hexdigest(),
                    "local_path": image_path.relative_to(self.data_dir).as_posix(),
                },
            )

    def test_local_http_ui_filters_and_records_reviews(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), _handler_for(self.data_dir))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join, 2)
        self.addCleanup(server.shutdown)
        url = f"http://127.0.0.1:{server.server_port}"

        with urlopen(f"{url}/", timeout=3) as response:
            self.assertEqual(response.status, 200)
            self.assertIn(b"GeoFlora Dataset Review", response.read())
        with urlopen(f"{url}/api/items?limit=2", timeout=3) as response:
            result = json.loads(response.read())
        self.assertEqual(result["total"], 5)
        self.assertEqual(len(result["items"]), 2)
        self.assertEqual(len(result["filter_options"]["sources"]), 2)

        request = Request(
            f"{url}/api/review",
            data=json.dumps(
                {
                    "source": "inaturalist",
                    "source_id": "photo-0",
                    "decision": "approved",
                    "reviewer": "Reviewer",
                    "rationale": "Confirmed",
                }
            ).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=3) as response:
            self.assertEqual(response.status, 200)

        invalid_review = Request(
            f"{url}/api/review",
            data=b'{"source":"inaturalist","source_id":"photo-1"}',
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(HTTPError) as validation_error:
            urlopen(invalid_review, timeout=3)
        self.assertEqual(validation_error.exception.code, 400)

        malicious_request = Request(
            f"{url}/api/stats",
            headers={"Origin": "http://attacker.example"},
        )
        with self.assertRaises(HTTPError) as error:
            urlopen(malicious_request, timeout=3)
        self.assertEqual(error.exception.code, 403)
