from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ImageCandidate:
    source: str
    source_id: str
    group_id: str
    species_id: str
    scientific_name: str
    image_url: str
    source_url: str
    license: str
    attribution: str
    observation_id: str | None = None
    observed_at: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    country_code: str | None = None
    locality: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return asdict(self)
