import pandas as pd
import pytest

from geoflora_ml.catalog import ECOLOGICAL_STATUSES, CatalogError, load_catalog
from geoflora_ml.licenses import build_attribution, is_license_allowed, normalize_license
from geoflora_ml.utils import PROJECT_ROOT


@pytest.mark.parametrize("raw,code", [
    ("http://creativecommons.org/licenses/by-nc/4.0/", "CC-BY-NC-4.0"),
    ("http://creativecommons.org/licenses/by-nc/4.0/legalcode", "CC-BY-NC-4.0"),
    ("https://creativecommons.org/licenses/by/4.0/", "CC-BY-4.0"),
    ("http://creativecommons.org/publicdomain/zero/1.0/", "CC0-1.0"),
    ("CC_BY_NC_4_0", "CC-BY-NC-4.0"),
    ("CC_BY_4_0", "CC-BY-4.0"),
    ("CC0_1_0", "CC0-1.0"),
    ("http://creativecommons.org/licenses/by-nc-nd/4.0/", "CC-BY-NC-ND-4.0"),
    ("All rights reserved", None),
    ("", None),
    (None, None),
])
def test_normalize_license(raw, code):
    assert normalize_license(raw) == code


def test_license_allowlist():
    allowed = ["CC0-1.0", "CC-BY-4.0", "CC-BY-NC-4.0"]
    assert is_license_allowed("CC-BY-NC-4.0", allowed)
    assert not is_license_allowed("CC-BY-NC-ND-4.0", allowed)
    assert not is_license_allowed(None, allowed)


def test_attribution_mentions_creator_and_license():
    a = build_attribution("Jane Doe", None, "CC-BY-4.0", "iNaturalist", "https://example.org/1")
    assert "Jane Doe" in a and "CC BY 4.0" in a and "https://example.org/1" in a


def test_project_catalog_is_valid_and_keeps_statuses_separate():
    cat = load_catalog(PROJECT_ROOT / "metadata" / "species_catalog.csv")
    names = {s.scientific_name: s for s in cat}
    baseline = ["Chromolaena odorata", "Lantana camara", "Pontederia crassipes"]
    for n in baseline:
        assert names[n].training_enabled and names[n].role == "target"
    # every target_invasive species has a named verifier, a date and Philippine evidence (NISSAP)
    targets = [s for s in cat if s.ecological_status == "target_invasive"]
    assert set(baseline) <= {s.scientific_name for s in targets}
    for s in targets:
        assert s.status_verification == "verified" and s.status_verified_by and s.status_verified_date, s.scientific_name
        assert "NISSAP" in s.status_evidence, s.scientific_name
    # anything not marked invasive stays unverified rather than being labelled non-invasive by default
    assert all(s.status_verification == "unverified" for s in cat if s.ecological_status != "target_invasive")
    assert all(s.ecological_status in ECOLOGICAL_STATUSES for s in cat)
    assert not any(s.training_enabled for s in cat if s.role == "unknown_eval")


def test_catalog_rejects_unverified_claims(tmp_path):
    df = pd.read_csv(PROJECT_ROOT / "metadata" / "species_catalog.csv", dtype=str, keep_default_na=False)
    df.loc[0, ["status_verification", "status_verified_by", "status_verified_date"]] = ["verified", "", ""]  # no verifier/date
    p = tmp_path / "cat.csv"
    df.to_csv(p, index=False)
    with pytest.raises(CatalogError, match="requires status_verified_by"):
        load_catalog(p)


def test_catalog_rejects_duplicate_ids(tmp_path):
    df = pd.read_csv(PROJECT_ROOT / "metadata" / "species_catalog.csv", dtype=str, keep_default_na=False)
    df.loc[1, "species_id"] = df.loc[0, "species_id"]
    p = tmp_path / "cat.csv"
    df.to_csv(p, index=False)
    with pytest.raises(CatalogError, match="duplicate species_id"):
        load_catalog(p)
