import numpy as np
import pandas as pd
from PIL import Image, ImageFilter

from geoflora_ml.config import load_config
from geoflora_ml.grouping import compute_groups, near_duplicate_pairs
from geoflora_ml.imaging import inspect_image, phash_distance, quality_flags

from conftest import synthetic_image

VCFG = load_config()["validation"]


def test_quality_flags(tmp_path):
    rng = np.random.default_rng(1)
    good = tmp_path / "good.jpg"
    synthetic_image(good, (200, 40, 40), rng)
    assert quality_flags(inspect_image(good), VCFG) == []

    small = tmp_path / "small.jpg"
    Image.open(good).resize((100, 100)).save(small)
    assert "low_resolution" in quality_flags(inspect_image(small), VCFG)

    blurry = tmp_path / "blurry.jpg"
    Image.open(good).filter(ImageFilter.GaussianBlur(12)).save(blurry)
    assert "blurry" in quality_flags(inspect_image(blurry), VCFG)

    dark = tmp_path / "dark.jpg"
    Image.new("RGB", (300, 300), (3, 3, 3)).save(dark)
    assert "too_dark" in quality_flags(inspect_image(dark), VCFG)

    broken = tmp_path / "broken.jpg"
    broken.write_bytes(b"not an image")
    info = inspect_image(broken)
    assert not info.readable and quality_flags(info, VCFG) == ["unreadable"]


def test_phash_detects_resized_recompressed_copy(tmp_path):
    rng = np.random.default_rng(2)
    a, b, c = tmp_path / "a.jpg", tmp_path / "b.jpg", tmp_path / "c.jpg"
    synthetic_image(a, (40, 170, 40), rng)
    Image.open(a).resize((400, 400)).save(b, quality=60)
    synthetic_image(c, (40, 170, 40), rng)
    ha, hb, hc = (inspect_image(p).phash for p in (a, b, c))
    assert phash_distance(ha, hb) <= VCFG["phash_hamming_threshold"]
    assert phash_distance(ha, hc) > VCFG["phash_hamming_threshold"]
    pairs = near_duplicate_pairs(["a", "b", "c"], [ha, hb, hc], VCFG["phash_hamming_threshold"])
    assert [(p[0], p[1]) for p in pairs] == [("a", "b")]


def _frame(rows):
    cols = ["image_id", "species_id", "observation_id", "file_sha256", "phash", "recorded_by", "event_date"]
    return pd.DataFrame(rows, columns=cols).fillna("")


def test_grouping_links_observation_duplicate_and_visit():
    df = _frame([
        ["i1", "S1", "o1", "h1", "", "ann", "2025-01-01"],
        ["i2", "S1", "o1", "h2", "", "ann", "2025-01-01"],   # same observation
        ["i3", "S1", "o2", "h1", "", "bob", "2025-02-01"],   # exact duplicate of i1
        ["i4", "S1", "o3", "h4", "", "ann", "2025-01-01"],   # same recorder & day & species
        ["i5", "S1", "o4", "h5", "", "cat", "2025-03-01"],   # independent
        ["i6", "S2", "o5", "h1", "", "dan", "2025-04-01"],   # duplicate bytes but another species -> conflict
    ])
    g = compute_groups(df, 6, group_by_recorder_and_date=True).set_index(df["image_id"])
    assert len({g.loc[i, "observation_group"] for i in ["i1", "i2", "i3", "i4", "i6"]}) == 1
    assert g.loc["i5", "observation_group"] != g.loc["i1", "observation_group"]
    assert g.loc["i3", "exact_duplicate_of"] == "i1"
    assert g.loc["i1", "label_conflict"] == "true" and g.loc["i5", "label_conflict"] == "false"


def test_grouping_without_visit_rule():
    df = _frame([
        ["i1", "S1", "o1", "h1", "", "ann", "2025-01-01"],
        ["i2", "S1", "o2", "h2", "", "ann", "2025-01-01"],
    ])
    g = compute_groups(df, 6, group_by_recorder_and_date=False)
    assert g["observation_group"].nunique() == 2
