"""Install a GeoFlora-ML-Lab candidate (storage/models/candidates/<version>/) as the live model.

Use this for models trained and evaluated in ml-lab/, where scripts/model_promotion.py's automatic-training gates
(fixed v5 benchmark comparison, >=85% accuracy and >=80% recall for every class) do not apply as written. The
gate override is recorded in active_model.json with the approver and rationale, never silently.

Like model_promotion.promote(), it first saves the live files under storage/models/previous/<timestamp>/, so the
standard rollback works:
  python scripts/model_promotion.py --rollback-to storage/models/previous/<timestamp> --reason "..."

  python scripts/install_lab_model.py --candidate storage/models/candidates/geoflora-mnv2-21cls-v1 \
      --approved-by "Name" --rationale "Why this model is activated"
Restart the inference service (or POST /reload) afterwards.
"""
import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from model_promotion import LIVE, LIVE_FILES, ROOT, file_sha256

GATES = {"accuracy": 0.85, "macro_f1": 0.85, "class_recall": 0.80}  # model_promotion.promote() quality targets


def install(candidate: Path, approved_by: str, rationale: str) -> dict:
    if not approved_by.strip() or not rationale.strip():
        raise ValueError("An approver and a rationale are required")
    candidate = candidate.resolve()
    for name in ("mobilenetv2.keras", "class_mapping.json", "species.yaml", "evaluation.json"):
        if not (candidate / name).is_file():
            raise FileNotFoundError(f"candidate is missing {name}")
    evaluation = json.loads((candidate / "evaluation.json").read_text(encoding="utf-8"))
    report = evaluation["classification_report"]
    failed = {
        **({"accuracy": evaluation["accuracy"]} if evaluation["accuracy"] < GATES["accuracy"] else {}),
        **({"macro_f1": report["macro avg"]["f1-score"]} if report["macro avg"]["f1-score"] < GATES["macro_f1"] else {}),
        **{f"recall:{n}": report[n]["recall"] for n in evaluation["class_order"] if report[n]["recall"] < GATES["class_recall"]},
    }
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = LIVE / "previous" / stamp
    backup.mkdir(parents=True)
    for name in LIVE_FILES:
        if (LIVE / name).exists():
            shutil.copy2(LIVE / name, backup / name)
    try:
        for name in ("mobilenetv2.keras", "class_mapping.json", "species.yaml", "evaluation.json"):
            shutil.copy2(candidate / name, LIVE / name)
        (LIVE / "active_model.json").write_text(json.dumps({
            "candidate": candidate.name,
            "model_version": candidate.name,
            "scope": "GeoFlora-ML-Lab model installed by administrator decision",
            "activated_at": datetime.now(timezone.utc).isoformat(),
            "classes": len(json.loads((candidate / "class_mapping.json").read_text(encoding="utf-8"))["classes"]),
            "test_accuracy": evaluation["accuracy"],
            "test_accuracy_ci95": evaluation.get("accuracy_ci95"),
            "macro_f1": report["macro avg"]["f1-score"],
            "evaluation_source": evaluation.get("source"),
            "evaluation_record": (LIVE / "evaluation.json").relative_to(ROOT).as_posix(),
            "candidate_evaluation_record": (candidate / "evaluation.json").relative_to(ROOT).as_posix(),
            "evaluation_sha256": file_sha256(candidate / "evaluation.json"),
            "model_sha256": file_sha256(candidate / "mobilenetv2.keras"),
            "class_mapping_sha256": file_sha256(candidate / "class_mapping.json"),
            "promotion_approval": {"approvedBy": approved_by.strip(), "approvedAt": datetime.now(timezone.utc).isoformat(),
                                   "rationale": rationale.strip()[:1000]},
            "quality_gate_override": {"gates": GATES, "not_met": failed} if failed else None,
            "confidence_threshold": evaluation["confidence_threshold"],
            "threshold_basis": evaluation.get("threshold_basis"),
            "previous": backup.relative_to(ROOT).as_posix(),
        }, indent=2), encoding="utf-8")
    except Exception:
        for name in LIVE_FILES:
            if (backup / name).exists():
                shutil.copy2(backup / name, LIVE / name)
            elif name in {"species.yaml", "evaluation.json"}:
                (LIVE / name).unlink(missing_ok=True)
        raise
    return {"installed": candidate.name, "backup": backup.relative_to(ROOT).as_posix(), "gates_not_met": failed}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--candidate", required=True)
    p.add_argument("--approved-by", required=True)
    p.add_argument("--rationale", required=True)
    a = p.parse_args()
    c = Path(a.candidate)
    print(json.dumps(install(c if c.is_absolute() else ROOT / c, a.approved_by, a.rationale), indent=2))
