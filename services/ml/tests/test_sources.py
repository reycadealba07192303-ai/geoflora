import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from geoflora_ml.collection.gbif import GBIFSource
from geoflora_ml.collection.inaturalist import INaturalistSource
from geoflora_ml.collection.kaggle import KaggleManifestSource
from geoflora_ml.config import Species


class SourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.species = Species(
            id="chromolaena_odorata",
            scientific_name="Chromolaena odorata",
            common_name="Hagonoy",
        )

    def test_inaturalist_filters_to_matching_taxon_and_allowed_license(self) -> None:
        source = INaturalistSource(minimum_interval=0)
        with patch.object(
            source.client,
            "get_json",
            side_effect=[
                {"results": [{"id": 1, "name": "Philippines"}]},
                {
                    "results": [
                        {"id": 12, "name": "Other plant"},
                        {"id": 34, "name": "Chromolaena odorata"},
                    ]
                },
                {
                    "results": [
                        {
                            "id": 56,
                            "observed_on": "2025-01-02",
                            "location": "14.5,121.0",
                            "place_guess": "Manila, Philippines",
                            "photos": [
                                {
                                    "id": 78,
                                    "url": "https://example.org/square.jpg",
                                    "license_code": "cc-by",
                                    "attribution": "Photographer",
                                },
                                {
                                    "id": 79,
                                    "url": "https://example.org/square.jpg",
                                    "license_code": "cc-by-nc",
                                },
                            ],
                        }
                    ]
                },
            ],
        ) as get_json:
            result = list(source.candidates(self.species, limit=1))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].source_id, "78")
        self.assertEqual(result[0].image_url, "https://example.org/medium.jpg")
        self.assertEqual(result[0].group_id, "inaturalist:observation:56")
        self.assertEqual(result[0].observation_id, "56")
        self.assertEqual(result[0].latitude, 14.5)
        self.assertEqual(result[0].longitude, 121.0)
        self.assertEqual(result[0].locality, "Manila, Philippines")
        self.assertEqual(get_json.call_args_list[2].kwargs["params"]["place_id"], 1)
        params = get_json.call_args_list[2].kwargs["params"]
        self.assertEqual(params["photo_license"], "cc0,cc-by,cc-by-sa")
        self.assertNotIn("license", params)

    def test_gbif_extracts_licensed_media(self) -> None:
        source = GBIFSource(minimum_interval=0)
        with patch.object(
            source.client,
            "get_json",
            side_effect=[
                {"usageKey": 123},
                {
                    "results": [
                        {
                            "key": 456,
                            "eventDate": "2025-01-02",
                            "decimalLatitude": 14.5,
                            "decimalLongitude": 121.0,
                            "countryCode": "PH",
                            "stateProvince": "Metro Manila",
                            "media": [
                                {
                                    "key": 789,
                                    "identifier": "https://example.org/image.jpg",
                                    "license": "http://creativecommons.org/licenses/by/4.0/",
                                    "creator": "Photographer",
                                }
                            ],
                        }
                    ]
                },
            ],
        ) as get_json:
            result = list(source.candidates(self.species, limit=1))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].license, "cc-by")
        self.assertEqual(result[0].attribution, "Photographer")
        self.assertEqual(result[0].group_id, "gbif:occurrence:456")
        self.assertEqual(result[0].observation_id, "456")
        self.assertEqual(result[0].latitude, 14.5)
        self.assertEqual(result[0].longitude, 121.0)
        self.assertEqual(result[0].country_code, "PH")
        self.assertEqual(result[0].locality, "Metro Manila")
        self.assertEqual(get_json.call_args_list[1].kwargs["params"]["country"], "PH")

    def test_gbif_all_available_follows_pagination(self) -> None:
        source = GBIFSource(minimum_interval=0)
        first_page = {
            "results": [
                {
                    "key": 456,
                    "media": [
                        {
                            "key": 789,
                            "identifier": "https://example.org/first.jpg",
                            "license": "cc0",
                        }
                    ],
                }
            ],
            "endOfRecords": False,
        }
        final_page = {
            "results": [
                {
                    "key": 457,
                    "media": [
                        {
                            "key": 790,
                            "identifier": "https://example.org/second.jpg",
                            "license": "cc0",
                        }
                    ],
                }
            ],
            "endOfRecords": True,
        }
        with patch.object(
            source.client,
            "get_json",
            side_effect=[{"usageKey": 123}, first_page, final_page],
        ) as get_json:
            result = list(source.candidates(self.species, limit=None))

        self.assertEqual(len(result), 2)
        self.assertEqual(get_json.call_args_list[1].kwargs["params"]["offset"], 0)
        self.assertEqual(get_json.call_args_list[2].kwargs["params"]["offset"], 300)

    def test_kaggle_manifest_requires_rights_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = root / "image.jpg"
            image_path.write_bytes(b"image")
            manifest_path = root / "manifest.csv"
            manifest_path.write_text(
                "source_id,species,image_path,source_url,license,attribution,country,group_id\n"
                "1,Chromolaena odorata,image.jpg,https://example.org,cc-by,Author,PH,observation-1\n",
                encoding="utf-8",
            )
            source = KaggleManifestSource(manifest_path)
            self.assertEqual(len(list(source.candidates(self.species, limit=5))), 1)
