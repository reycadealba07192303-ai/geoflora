from __future__ import annotations

import re
from collections.abc import Iterator

from geoflora_ml.collection.http import ApiClient
from geoflora_ml.collection.licensing import normalize_license
from geoflora_ml.collection.models import ImageCandidate
from geoflora_ml.config import Species

BASE_URL = "https://api.inaturalist.org/v1"


class INaturalistSource:
    def __init__(self, minimum_interval: float = 1.0, max_retries: int = 4, allow_noncommercial: bool = False) -> None:
        self.client = ApiClient("iNaturalist", minimum_interval, max_retries)
        self.allow_noncommercial = allow_noncommercial

    def candidates(
        self, species: Species, limit: int | None, pages: int | None = None,
        id_above: int | None = None,
    ) -> Iterator[ImageCandidate]:
        places = self.client.get_json(
            f"{BASE_URL}/places/autocomplete", params={"q": "Philippines"}
        ).get("results", [])
        philippines = next(
            (
                place
                for place in places
                if _normalize_name(place.get("name", "")) == "philippines"
                or _normalize_name(place.get("display_name", "")) == "philippines"
            ),
            None,
        )
        if philippines is None:
            raise ValueError("iNaturalist Philippines place was not found")

        taxa = self.client.get_json(
            f"{BASE_URL}/taxa",
            params={"q": species.scientific_name, "rank": "species", "is_active": "true"},
        ).get("results", [])
        taxon = next(
            (
                result
                for result in taxa
                if _normalize_name(result.get("name", "")) == _normalize_name(species.scientific_name)
            ),
            None,
        )
        if taxon is None:
            raise ValueError(f"iNaturalist taxon not found for {species.scientific_name}")

        page_size = 200 if limit is None else min(200, limit)
        max_pages = pages
        if max_pages is None and limit is not None:
            max_pages = (limit + page_size - 1) // page_size
        emitted = 0
        page = 1
        while max_pages is None or page <= max_pages:
            params = {
                "taxon_id": taxon["id"],
                "place_id": philippines["id"],
                "photos": "true",
                "quality_grade": "research",
                "photo_license": "cc0,cc-by,cc-by-sa" + (",cc-by-nc,cc-by-nc-sa" if self.allow_noncommercial else ""),
                "per_page": page_size,
                "page": page,
                "order": "asc",
                "order_by": "id",
            }
            if id_above is not None:
                params["id_above"] = id_above
            payload = self.client.get_json(
                f"{BASE_URL}/observations",
                params=params,
            )
            results = payload.get("results", [])
            if not results:
                break
            for observation in results:
                for photo in observation.get("photos", []):
                    license_code = normalize_license(photo.get("license_code"), self.allow_noncommercial)
                    image_url = _medium_image_url(photo.get("url", ""))
                    if not license_code or not image_url:
                        continue
                    photo_id = photo.get("id")
                    if photo_id is None:
                        continue
                    attribution = str(photo.get("attribution") or "").strip()
                    if license_code != "cc0" and not attribution:
                        continue
                    location = observation.get("location")
                    latitude: float | None = None
                    longitude: float | None = None
                    if isinstance(location, str) and "," in location:
                        try:
                            latitude_text, longitude_text = location.split(",", maxsplit=1)
                            latitude = float(latitude_text)
                            longitude = float(longitude_text)
                        except ValueError:
                            latitude = None
                            longitude = None
                    yield ImageCandidate(
                        source="inaturalist",
                        source_id=str(photo_id),
                        group_id=f"inaturalist:observation:{observation['id']}",
                        species_id=species.id,
                        scientific_name=species.scientific_name,
                        image_url=image_url,
                        source_url=f"https://www.inaturalist.org/observations/{observation['id']}",
                        license=license_code,
                        attribution=attribution or "CC0",
                        observation_id=str(observation["id"]),
                        observed_at=observation.get("observed_on"),
                        latitude=latitude,
                        longitude=longitude,
                        country_code="PH",
                        locality=observation.get("place_guess"),
                    )
                    emitted += 1
                    if limit is not None and emitted >= limit:
                        return
            if len(results) < page_size:
                break
            page += 1


def _normalize_name(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def _medium_image_url(url: str) -> str:
    if not url.startswith("https://"):
        return ""
    return re.sub(r"/(square|small|thumb)\.", "/medium.", url)
