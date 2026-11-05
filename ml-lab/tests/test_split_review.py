import json
from pathlib import Path

import pandas as pd
import pytest
from PIL import Image

from geoflora_ml.config import project_path
from geoflora_ml.manifest import append_rows, load_manifest, save_manifest
from geoflora_ml.review import export_review_sheets, import_review_sheet
from geoflora_ml.splitting import prepare_splits
from geoflora_ml.training import TrainingBlocked, check_training_readiness
from geoflora_ml.utils import read_json
from geoflora_ml.validation import validate_manifest

from conftest import TEST_OVERRIDES


def _assignments(cfg):
    df = pd.read_csv(project_path(cfg, "split_assignments"), dtype=str, keep_default_na=False)
    return df[df["active"] == "true"]


def test_split_is_group_aware_and_leakage_free(make_project):
    cfg = make_project(n_per_species=16)
    # add a near-duplicate (resized copy) under a different observation id
    m = load_manifest(project_path(cfg, "image_manifest"))
    src = m.iloc[0]
    root = Path(cfg["paths"]["root"])
    dup_rel = src["local_path"].replace(".jpg", "_copy.jpg")
    Image.open(root / src["local_path"]).resize((300, 300)).save(root / dup_rel, quality=70)
    dup = src.to_dict() | {"image_id": src["image_id"] + "-copy", "observation_id": "obs:other", "local_path": dup_rel,
                           "recorded_by": "someone-else", "event_date": "2024-12-31"}
    save_manifest(append_rows(m, [dup]), project_path(cfg, "image_manifest"))

    validate_manifest(cfg)
    report = prepare_splits(cfg)
    assert report["ready_for_training"]
    assert report["leakage_check"]["violations"] == 0
    a = _assignments(cfg).set_index("image_id")
    assert a.loc[src["image_id"], "split"] == a.loc[src["image_id"] + "-copy", "split"]
    assert a.groupby("observation_group")["split"].nunique().max() == 1

    mapping = read_json(project_path(cfg, "class_mapping"))
    assert [c["index"] for c in mapping["classes"]] == [0, 1, 2]
    assert mapping["num_classes"] == 3 and {c["species_id"] for c in mapping["classes"]} == {"GF-SP-0001", "GF-SP-0002", "GF-SP-0003"}
    # unsupported species are species-disjoint between unknown_val and unknown_test
    u = a[a["split"].str.startswith("unknown")]
    assert u.groupby("species_id")["split"].nunique().max() == 1
    assert set(u["split"]) == {"unknown_val", "unknown_test"}
    # folders materialised with labels matching the mapping
    for split in ("train", "val", "test"):
        for c in mapping["classes"]:
            files = list((project_path(cfg, split) / c["folder"]).glob("*.jpg"))
            assert len(files) == ((a["split"] == split) & (a["species_id"] == c["species_id"])).sum() > 0
    check_training_readiness(cfg)  # does not raise


def test_unreviewed_data_blocks_training(make_project):
    cfg = make_project(n_per_species=16, approve=False)
    validate_manifest(cfg)
    report = prepare_splits(cfg)
    assert not report["ready_for_training"]
    assert all(not r["ready"] for r in report["class_readiness"])
    assert read_json(project_path(cfg, "class_mapping"))["status"] == "insufficient_verified_data"
    with pytest.raises(TrainingBlocked):
        check_training_readiness(cfg)


def test_pending_images_never_enter_partitions(make_project):
    cfg = make_project(n_per_species=16)
    mp = project_path(cfg, "image_manifest")
    m = load_manifest(mp)
    pending = m["image_id"].iloc[:5].tolist()
    m.loc[m["image_id"].isin(pending), ["review_status", "reviewer"]] = ["pending", ""]
    save_manifest(m, mp)
    validate_manifest(cfg)
    prepare_splits(cfg)
    assert not set(pending) & set(_assignments(cfg)["image_id"])


def test_revoked_approval_is_caught_by_training_gate(make_project):
    cfg = make_project(n_per_species=16)
    validate_manifest(cfg)
    prepare_splits(cfg)
    mp = project_path(cfg, "image_manifest")
    m = load_manifest(mp)
    victim = _assignments(cfg).query("split == 'train'")["image_id"].iloc[0]
    m.loc[m["image_id"] == victim, "review_status"] = "rejected"
    save_manifest(m, mp)
    with pytest.raises(TrainingBlocked, match="no longer approved"):
        check_training_readiness(cfg)


def test_assignments_are_sticky_and_locked_groups_go_to_test(make_project):
    cfg = make_project(n_per_species=16)
    validate_manifest(cfg)
    prepare_splits(cfg)
    first = _assignments(cfg).set_index("image_id")["split"].to_dict()

    # lock one current training observation into test, and add new images
    m = load_manifest(project_path(cfg, "image_manifest"))
    train_ids = [i for i, s in first.items() if s == "train"]
    locked_obs = m.set_index("image_id").loc[train_ids[0], "observation_id"]
    project_path(cfg, "locked_test_groups").write_text(f"# historical test data\n{locked_obs}\n", encoding="utf-8")
    from conftest import synthetic_image
    import numpy as np
    rng = np.random.default_rng(99)
    root = Path(cfg["paths"]["root"])
    rows = []
    for i in range(6):
        rel = f"dataset/raw/Alpha_testii/new-{i}.jpg"
        synthetic_image(root / rel, (200, 40, 40), rng)
        rows.append({"image_id": f"new-{i}", "species_id": "GF-SP-0001", "scientific_name": "Alpha testii",
                     "ecological_role": "target", "observation_id": f"obs:new:{i}", "license": "CC0-1.0",
                     "local_path": rel, "review_status": "approved", "reviewer": "Test Reviewer",
                     "recorded_by": f"new{i}", "event_date": "2025-06-01"})
    save_manifest(append_rows(m, rows), project_path(cfg, "image_manifest"))
    validate_manifest(cfg)
    prepare_splits(cfg)
    second = _assignments(cfg).set_index("image_id")["split"].to_dict()

    assert second[train_ids[0]] == "test"
    for iid, split in first.items():
        if split == "test":
            assert second[iid] == "test"  # historical test isolation
        if iid != train_ids[0]:
            assert second[iid] == split
    assert all(f"new-{i}" in second for i in range(6))


def test_review_round_trip(make_project):
    cfg = make_project(n_per_species=4, approve=False)
    validate_manifest(cfg)
    files = export_review_sheets(cfg, ["GF-SP-0001"])
    sheet_path = next(f for f in files if f.suffix == ".csv")
    assert any(f.suffix == ".html" for f in files)
    sheet = pd.read_csv(sheet_path, dtype=str, keep_default_na=False)
    sheet.loc[0, "decision"] = "approved"
    sheet.loc[1, "decision"] = "rejected"
    sheet.loc[2, "decision"] = "maybe"  # invalid
    sheet.to_csv(sheet_path, index=False)

    with pytest.raises(ValueError, match="reviewer name"):
        import_review_sheet(cfg, sheet_path, "  ")
    with pytest.raises(ValueError, match="invalid decision"):
        import_review_sheet(cfg, sheet_path, "Dr. Botanist")
    assert set(load_manifest(project_path(cfg, "image_manifest"))["review_status"]) == {"pending"}  # nothing saved
    assert not list(project_path(cfg, "reviewed").rglob("*.jpg"))  # and no files copied

    sheet.loc[2, "decision"] = "uncertain"
    sheet.to_csv(sheet_path, index=False)
    log = import_review_sheet(cfg, sheet_path, "Dr. Botanist", "2026-11-01")
    assert (log["approved"], log["rejected"], log["uncertain"]) == (1, 1, 1)
    m = load_manifest(project_path(cfg, "image_manifest")).set_index("image_id")
    assert m.loc[sheet.loc[0, "image_id"], "review_status"] == "approved"
    assert m.loc[sheet.loc[0, "image_id"], "reviewer"] == "Dr. Botanist"
    assert len(list(project_path(cfg, "reviewed").rglob("*.jpg"))) == 1


def test_review_gallery_embeds_sheet(make_project):
    cfg = make_project(n_per_species=4, approve=False)
    validate_manifest(cfg)
    files = export_review_sheets(cfg, ["GF-SP-0001"])
    csv_path = next(f for f in files if f.suffix == ".csv")
    page = next(f for f in files if f.suffix == ".html").read_text(encoding="utf-8")
    data = json.loads(page.split('<script id="data" type="application/json">', 1)[1].split("</script>", 1)[0])
    sheet = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    assert data["csv_name"] == csv_path.name
    assert data["columns"] == list(sheet.columns)  # the downloaded CSV has the importable layout
    assert [r["image_id"] for r in data["rows"]] == list(sheet["image_id"])
    assert all((csv_path.parent / r["_img"]).exists() for r in data["rows"])
    assert "approve all" not in page.lower()


def test_extra_class_species_become_classes_without_catalog_change(make_project):
    cfg = make_project(n_per_species=16, overrides={"split": {**TEST_OVERRIDES["split"], "extra_class_species": ["GF-SP-0201"]}})
    catalog_before = project_path(cfg, "species_catalog").read_text(encoding="utf-8")
    validate_manifest(cfg)
    prepare_splits(cfg)
    mapping = read_json(project_path(cfg, "class_mapping"))
    assert [c["species_id"] for c in mapping["classes"]] == ["GF-SP-0001", "GF-SP-0002", "GF-SP-0003", "GF-SP-0201"]
    a = _assignments(cfg)
    assert set(a.loc[a["species_id"] == "GF-SP-0201", "split"]) <= {"train", "val", "test"}
    assert set(a.loc[a["species_id"] == "GF-SP-0202", "split"]) <= {"unknown_val", "unknown_test"}
    assert project_path(cfg, "species_catalog").read_text(encoding="utf-8") == catalog_before
