from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from geoflora_ml.collection.http import ApiClient
from geoflora_ml.collection.licensing import normalize_license
from geoflora_ml.collection.models import ImageCandidate
from geoflora_ml.config import Species

BASE_URL = "https://api.gbif.org/v1"


class GBIFSource:
    def __init__(self, minimum_interval: float = 0.25, max_retries: int = 4) -> None:
        self.client = ApiClient("GBIF", minimum_interval, max_retries)

    def candidates(
        self, species: Species, limit: int | None, pages: int | None = None
    ) -> Iterator[ImageCandidate]:
        match = self.client.get_json(
            f"{BASE_URL}/species/match",
            params={"name": species.scientific_name, "rank": "SPECIES"},
        )
        taxon_key = match.get("usageKey")
        if not taxon_key:
            raise ValueError(f"GBIF taxon not found for {species.scientific_name}")

        page_size = 300 if limit is None else min(300, limit)
        max_pages = pages
        if max_pages is None and limit is not None:
            max_pages = (limit + page_size - 1) // page_size
        emitted = 0
        page = 0
        while max_pages is None or page < max_pages:
            payload = self.client.get_json(
                f"{BASE_URL}/occurrence/search",
                params={
                    "taxonKey": taxon_key,
                    "country": "PH",
                    "mediaType": "StillImage",
                    "limit": page_size,
                    "offset": page * page_size,
                },
            )
            results = payload.get("results", [])
            if not results:
                break
            for occurrence in results:
                occurrence_id = occurrence.get("key")
                for media in occurrence.get("media") or []:
                    license_code = normalize_license(media.get("license"))
                    image_url = media.get("identifier", "")
                    if (
                        not occurrence_id
                        or not license_code
                        or not isinstance(image_url, str)
                        or not image_url.startswith("https://")
                    ):
                        continue
                    attribution = _attribution(media)
                    if license_code != "cc0" and not attribution:
                        continue
                    media_id = media.get("key") or media.get("identifier")
                    yield ImageCandidate(
                        source="gbif",
                        source_id=f"{occurrence_id}:{media_id}",
                        group_id=f"gbif:occurrence:{occurrence_id}",
                        species_id=species.id,
                        scientific_name=species.scientific_name,
                        image_url=image_url,
                        source_url=f"https://www.gbif.org/occurrence/{occurrence_id}",
                        license=license_code,
                        attribution=attribution or "CC0",
                        observation_id=str(occurrence_id),
                        observed_at=occurrence.get("eventDate"),
                        latitude=_coordinate(occurrence.get("decimalLatitude"), -90, 90),
                        longitude=_coordinate(occurrence.get("decimalLongitude"), -180, 180),
                        country_code=occurrence.get("countryCode"),
                        locality=occurrence.get("locality")
                        or occurrence.get("stateProvince"),
                    )
                    emitted += 1
                    if limit is not None and emitted >= limit:
                        return
            if payload.get("endOfRecords") is True or (
                "endOfRecords" not in payload and len(results) < page_size
            ):
                break
            page += 1


def _attribution(media: dict[str, Any]) -> str:
    parts = [
        str(media[key]).strip()
        for key in ("rightsHolder", "creator", "publisher")
        if media.get(key)
    ]
    return " | ".join(dict.fromkeys(parts))


def _coordinate(value: Any, minimum: float, maximum: float) -> float | None:
    try:
        coordinate = float(value)
    except (TypeError, ValueError):
        return None
    return coordinate if minimum <= coordinate <= maximum else None
