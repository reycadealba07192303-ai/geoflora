"""Provisional pilot mode must stay isolated, never touch real labels, and never be exportable."""

import pandas as pd
import pytest
import yaml

from geoflora_ml.config import load_config, project_path
from geoflora_ml.export import ExportBlocked, export_run
from geoflora_ml.manifest import load_manifest, save_manifest
from geoflora_ml.splitting import prepare_splits
from geoflora_ml.training import TrainingBlocked, check_training_readiness
from geoflora_ml.utils import PROJECT_ROOT, read_json
from geoflora_ml.validation import training_eligible_mask, validate_manifest

INAT = "50c9509d-22c7-4a22-a47d-8c48425ef4a7"


def _provisional(cfg):
    pilot = yaml.safe_load((PROJECT_ROOT / "configs" / "provisional_pilot.yaml").read_text(encoding="utf-8"))
    pilot["paths"]["root"] = cfg["paths"]["root"]
    from geoflora_ml.config import deep_update
    return deep_update(cfg, pilot)


def test_provisional_mask_only_admits_pending_from_accepted_sources():
    cfg = _provisional(load_config())
    base = {"readable": "true", "quality_pass": "true", "license_eligible": "true", "exact_duplicate_of": "",
            "label_conflict": "false", "reviewer": ""}
    df = pd.DataFrame([
        base | {"review_status": "pending", "source_dataset_key": INAT},
        base | {"review_status": "pending", "source_dataset_key": "other-dataset"},
        base | {"review_status": "rejected", "source_dataset_key": INAT},
        base | {"review_status": "uncertain", "source_dataset_key": INAT},
    ])
    assert training_eligible_mask(df, cfg).tolist() == [True, False, False, False]
    assert training_eligible_mask(df, load_config()).tolist() == [False, False, False, False]


def test_provisional_split_is_isolated(make_project):
    cfg = make_project(n_per_species=16, approve=False)
    mp = project_path(cfg, "image_manifest")
    m = load_manifest(mp)
    m["source_dataset_key"] = INAT
    save_manifest(m, mp)
    validate_manifest(cfg)
    before = mp.read_bytes()

    pcfg = _provisional(cfg)
    report = prepare_splits(pcfg)
    assert report["ready_for_training"] and report["provisional"]
    assert read_json(project_path(pcfg, "class_mapping"))["provisional"] is True
    assert mp.read_bytes() == before                       # manifest (real labels/splits) untouched
    assert not project_path(cfg, "class_mapping").exists()  # real mapping not written
    assert "provisional" in str(project_path(pcfg, "train"))
    with pytest.raises(TrainingBlocked):
        check_training_readiness(cfg)                       # the real gate is still closed
    check_training_readiness(pcfg)


def test_provisional_run_cannot_be_exported(tmp_path):
    run = tmp_path / "run-x"
    run.mkdir()
    (run / "run_config.yaml").write_text(yaml.safe_dump({"provisional": {"enabled": True}}), encoding="utf-8")
    with pytest.raises(ExportBlocked, match="PROVISIONAL"):
        export_run(load_config(overrides={"paths": {"root": str(tmp_path)}}), run)
