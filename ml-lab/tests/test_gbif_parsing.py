"""GBIF record parsing (offline, using a fixture shaped like a real occurrence/search result)."""


from geoflora_ml.catalog import Species
from geoflora_ml.gbif import eligible_media, manifest_row, resize_inaturalist_url

OCC = {
    "key": 5938539520, "datasetKey": "50c9509d-22c7-4a22-a47d-8c48425ef4a7",
    "datasetName": "iNaturalist research-grade observations",
    "occurrenceID": "https://www.inaturalist.org/observations/333068642", "basisOfRecord": "HUMAN_OBSERVATION",
    "license": "http://creativecommons.org/licenses/by-nc/4.0/legalcode", "rightsHolder": "Observer A",
    "recordedBy": "Observer A", "identifiedBy": "Observer A", "eventDate": "2026-01-02T07:03:07", "countryCode": "PH",
    "scientificName": "Chromolaena odorata (L.) R.M.King & H.Rob.", "institutionCode": "iNaturalist",
    "media": [
        {"type": "StillImage", "format": "image/jpeg", "references": "https://www.inaturalist.org/photos/1",
         "creator": "Observer A", "publisher": "iNaturalist", "license": "http://creativecommons.org/licenses/by-nc-nd/4.0/",
         "rightsHolder": "Observer A", "identifier": "https://inaturalist-open-data.s3.amazonaws.com/photos/1/original.jpg"},
        {"type": "StillImage", "format": "image/jpeg", "references": "https://www.inaturalist.org/photos/2",
         "creator": "Observer A", "publisher": "iNaturalist", "license": "http://creativecommons.org/licenses/by/4.0/",
         "rightsHolder": "Observer A", "identifier": "https://inaturalist-open-data.s3.amazonaws.com/photos/2/original.jpeg"},
        {"type": "Sound", "identifier": "https://example.org/a.mp3", "license": "http://creativecommons.org/licenses/by/4.0/"},
    ],
}
SP = Species("GF-SP-0001", "Chromolaena odorata", "", "Hagonoy", "Asteraceae", 3087725, "target_invasive",
             "unverified", "", "", "", "target", True, True, "")


def test_media_license_is_checked_per_image():
    cands = eligible_media(OCC, ["CC0-1.0", "CC-BY-4.0", "CC-BY-NC-4.0"], max_per_occurrence=5)
    assert [c.media_index for c in cands] == [1]  # ND-licensed image and the sound file are excluded
    assert cands[0].license_code == "CC-BY-4.0"


def test_inaturalist_size_rewrite():
    url = "https://inaturalist-open-data.s3.amazonaws.com/photos/2/original.jpeg"
    assert resize_inaturalist_url(url, "medium").endswith("/2/medium.jpeg")
    assert resize_inaturalist_url(url, "original") == url
    assert resize_inaturalist_url("https://other.org/original.jpg", "medium") == "https://other.org/original.jpg"


def test_manifest_row_preserves_provenance(tmp_path):
    cand = eligible_media(OCC, ["CC-BY-4.0"], 1)[0]
    path = tmp_path / "dataset" / "raw" / "Chromolaena_odorata" / "gbif-5938539520-1.jpg"
    row = manifest_row(SP, 3087725, cand, "https://x/medium.jpeg", path, b"bytes", ".jpg", "meta#1", tmp_path)
    assert row["image_id"] == "gbif-5938539520-1"
    assert row["observation_id"] == "gbif:5938539520"
    assert row["original_image_url"].endswith("original.jpeg") and row["fetched_image_url"] == "https://x/medium.jpeg"
    assert row["license"] == "CC-BY-4.0" and "Observer A" in row["attribution"]
    assert row["review_status"] == "pending"
    assert row["is_geoflora_field_observation"] == "false"
    assert row["local_path"] == "dataset/raw/Chromolaena_odorata/gbif-5938539520-1.jpg"
    for key in ("creator", "rights_holder", "source_dataset_key", "occurrence_id", "download_timestamp",
                "accepted_taxon_key", "occurrence_metadata_ref", "file_sha256"):
        assert row[key], key


def test_download_does_not_overwrite_concurrent_review(make_project, monkeypatch):
    from geoflora_ml import acquisition
    from geoflora_ml.config import project_path
    from geoflora_ml.manifest import load_manifest, save_manifest

    cfg = make_project(n_per_species=2, approve=False)
    path = project_path(cfg, "image_manifest")
    reviewed_id = load_manifest(path)["image_id"].iloc[0]

    def fake_download(cfg, sp, limit, session, manifest, budget):
        # a review import lands on disk while this species is downloading
        disk = load_manifest(path)
        disk.loc[disk["image_id"] == reviewed_id, ["review_status", "reviewer"]] = ["approved", "Concurrent Reviewer"]
        save_manifest(disk, path)
        row = manifest.iloc[0].to_dict() | {"image_id": f"new-{sp.species_id}", "review_status": "pending", "reviewer": ""}
        return acquisition.append_rows(manifest, [row]), acquisition.SpeciesResult(sp.species_id, sp.scientific_name, limit, 0, 1)

    monkeypatch.setattr(acquisition, "download_species", fake_download)
    monkeypatch.setattr(acquisition, "write_json", lambda *a, **k: None)
    acquisition.run_download(cfg, species_ids=["GF-SP-0001"], max_per_species=5)
    m = load_manifest(path).set_index("image_id")
    assert m.loc[reviewed_id, "reviewer"] == "Concurrent Reviewer"  # the concurrent review survived
    assert "new-GF-SP-0001" in m.index
