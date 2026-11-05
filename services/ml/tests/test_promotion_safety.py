import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import model_promotion
from auto_training_worker import manually_reviewed_staging_row, process_approved_promotions, staging_ecology_eligible, training_report_query
from model_promotion import candidate_promotion_decision


@pytest.mark.parametrize("row", [
    {"review_status": "pending", "reviewer": "human", "review_rationale": "Reviewed the visible leaves"},
    {"review_status": "rejected", "reviewer": "human", "review_rationale": "Wrong plant"},
    {"review_status": "research_grade", "reviewer": "", "review_rationale": ""},
    {"review_status": "approved", "reviewer": "ai:vision-model", "review_rationale": "Plant appears to match"},
    {"review_status": "approved", "reviewer": "human", "review_rationale": ""},
])
def test_unverified_or_rejected_staging_rows_are_not_eligible(row):
    assert manually_reviewed_staging_row(row) is False


def test_human_approved_staging_row_needs_reviewer_and_rationale():
    assert manually_reviewed_staging_row({
        "review_status": "approved", "reviewer": "reviewer-17",
        "review_rationale": "Opposite serrated leaves and clustered purple flower heads are visible.",
    }) is True


def test_source_flagged_or_introduced_review_staging_is_not_invasive_training_eligible():
    assert not staging_ecology_eligible({"role": "invasive", "status": "source_flagged", "ecological_citation": "https://example.org", "ecological_rationale": "Reviewed"})
    assert not staging_ecology_eligible({"role": "invasive", "status": "introduced_review", "ecological_citation": "https://example.org", "ecological_rationale": "Reviewed"})
    assert not staging_ecology_eligible({"role": "lookalike", "status": "confirmed_target_invasive", "ecological_review_confirmed": True, "ecological_reviewer": "admin", "ecological_citation": "https://example.org", "ecological_rationale": "Reviewed enough to pass maybe"})
    assert not staging_ecology_eligible({"role": "invasive", "status": "confirmed_target_invasive", "ecological_citation": "https://flora.example.org/invasive", "ecological_rationale": "Accepted Philippine ecological source and rationale."})
    assert staging_ecology_eligible({"role": "invasive", "status": "confirmed_target_invasive", "ecological_review_confirmed": True, "ecological_reviewer": "admin-1", "ecological_citation": "https://flora.example.org/invasive", "ecological_rationale": "Accepted Philippine ecological source and rationale."})


def test_automated_gates_only_make_candidate_eligible_for_admin_approval():
    assert candidate_promotion_decision(False, {"promote": True})["status"] == "not_eligible"
    assert candidate_promotion_decision(True, {"promote": False, "reason": "Benchmark regression"})["status"] == "not_eligible"
    ready = candidate_promotion_decision(True, {"promote": True})
    assert ready == {"status": "awaiting_approval", "eligible": True}


def test_automatic_worker_does_not_process_pending_approval():
    class Jobs:
        def find_one(self, query):
            assert query["promotion.status"] == "approved"
            return None

    class DB:
        trainingjobs = Jobs()

    assert process_approved_promotions(DB()) is False


def test_report_training_query_requires_consent_and_approved_label():
    expected = {"status": "verified", "labelReviewStatus": "approved", "verifiedEcologicalStatus": "target_invasive", "trainingConsent": True,
                "trainingCandidateStatus": "approved", "reviewHistory": {"$elemMatch": {"basis": "human", "trainingEligible": True, "confirmed": True}}}
    assert training_report_query() == {**expected, "trainingJobId": None}
    assert training_report_query(job_id=True) == {**expected, "trainingJobId": {"$ne": None}}


def test_promote_requires_explicit_admin_approval(tmp_path, monkeypatch):
    live = tmp_path / "storage" / "models"
    candidate = live / "candidates" / "candidate_1"
    candidate.mkdir(parents=True)
    monkeypatch.setattr(model_promotion, "LIVE", live)
    with pytest.raises(ValueError, match="administrator approval"):
        model_promotion.promote(candidate, "job-1", {}, {"promote": True}, {})
    assert not (live / "mobilenetv2.keras").exists()


def test_promoted_version_records_evaluation_and_can_safely_roll_back(tmp_path, monkeypatch):
    root = tmp_path
    live = root / "storage" / "models"
    previous = live / "previous"
    candidate = live / "candidates" / "candidate_20261101"
    previous.mkdir(parents=True)
    candidate.mkdir(parents=True)
    monkeypatch.setattr(model_promotion, "ROOT", root)
    monkeypatch.setattr(model_promotion, "LIVE", live)
    monkeypatch.setattr(model_promotion, "publish", lambda *args, **kwargs: None)
    monkeypatch.setattr(model_promotion, "_reload", lambda: {"model_version": "candidate_20261101"})

    (live / "mobilenetv2.keras").write_bytes(b"active-v3-model")
    (live / "class_mapping.json").write_text(json.dumps({"classes": [{"id": "old", "scientific_name": "Old species", "common_name": "Old"}]}))
    (live / "active_model.json").write_text(json.dumps({"candidate": "mobilenetv2_v3_seed42", "model_version": "mobilenetv2_v3_seed42"}))
    (live / "species.yaml").write_text("species: []\n")

    (candidate / "mobilenetv2.keras").write_bytes(b"experimental-model")
    (candidate / "class_mapping.json").write_text(json.dumps({"classes": [{"id": "new", "scientific_name": "New species", "common_name": "New"}]}))
    (candidate / "species.yaml").write_text("species: []\n")
    evaluation = {"accuracy": 0.9, "class_order": ["new"], "classification_report": {"new": {"recall": 0.9}, "macro avg": {"f1-score": 0.9}}}
    (candidate / "evaluation.json").write_text(json.dumps(evaluation))
    approval = {"status": "approved", "approvedBy": "admin-1", "approvedUsername": "admin", "approvedAt": "2026-11-01T00:00:00Z", "rationale": "Reviewed the evaluation and approved this release."}

    result = model_promotion.promote(candidate, "job-1", {"accuracy": 0.9, "macroF1": 0.9, "qualityTargetsPassed": True}, {"promote": True, "threshold": 0.8}, approval)
    assert result["activated"] is True
    active = json.loads((live / "active_model.json").read_text())
    assert active["model_version"] == "candidate_20261101"
    assert active["promotion_approval"]["approvedUsername"] == "admin"
    assert active["evaluation_record"].endswith("evaluation.json")
    assert active["evaluation_sha256"] == model_promotion.file_sha256(candidate / "evaluation.json")
    assert (root / result["backup"] / "mobilenetv2.keras").read_bytes() == b"active-v3-model"

    rolled = model_promotion.rollback(root / result["backup"], "Candidate regression during client validation")
    assert rolled["rolled_back"] is True
    assert (live / "mobilenetv2.keras").read_bytes() == b"active-v3-model"
    assert not (live / "evaluation.json").exists()
    restored = json.loads((live / "active_model.json").read_text())
    assert restored["rollback"]["from_model_version"] == "candidate_20261101"
    assert restored["rollback"]["to_model_version"] == "mobilenetv2_v3_seed42"
    assert (root / rolled["outgoingBackup"] / "mobilenetv2.keras").read_bytes() == b"experimental-model"
