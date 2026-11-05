"""Package an exported lab bundle as a GeoFlora model candidate (storage/models/candidates/<version>/).

The lab model scales pixels to [-1, 1] inside the network, but the GeoFlora inference service already applies
MobileNetV2 preprocess_input before calling the model. The packaged model therefore reuses the trained layers without
the lab's internal Rescaling layer, so the two paths give the same input to the backbone.

Written files follow services/ml (PlantPredictor and scripts/model_promotion.py):
  mobilenetv2.keras   class_mapping.json (id, scientific_name, common_name, role)   species.yaml
  evaluation.json     lab_bundle/ (model_metadata, species_descriptions, report, checksums from the lab export)

Role is "invasive" for catalog target_invasive species and "lookalike" for every other class: the app's word for a
class that is not a monitored target. It does not mean the species was found non-invasive.

  python scripts/package_for_geoflora.py --bundle models/exported/geoflora-mnv2-21cls-v1 --geoflora ..
"""

import json
import shutil
import sys
from pathlib import Path

from _common import parser, setup

# Common names already stored in GeoFlora records for the original three classes; keep them identical.
GEOFLORA_COMMON_NAMES = {"GF-SP-0001": "Hagonoy", "GF-SP-0002": "Lantana", "GF-SP-0003": "Water Hyacinth"}


def class_id(scientific_name: str) -> str:
    return scientific_name.strip().lower().replace(" ", "_").replace("-", "_")


def adapted_model(bundle: Path):
    """Same trained layers, minus the lab's Rescaling layer (GeoFlora preprocesses to [-1, 1] before the model)."""
    from tensorflow import keras

    lab = keras.models.load_model(bundle / "model.keras")
    names = [layer.name for layer in lab.layers]
    if names[1] != "mobilenetv2_preprocess":
        raise SystemExit(f"unexpected lab model layout: {names}")
    inp = keras.Input(shape=lab.input_shape[1:], name="image")
    x = inp
    for layer in lab.layers[2:]:
        x = layer(x)
    return lab, keras.Model(inp, x, name="geoflora_mobilenetv2")


def main():
    p = parser(__doc__)
    p.add_argument("--bundle", required=True, help="exported lab bundle directory")
    p.add_argument("--geoflora", required=True, help="GeoFlora project root")
    args = p.parse_args()
    cfg = setup(args)
    import numpy as np
    import yaml
    from geoflora_ml.utils import read_json, sha256_file

    bundle = Path(args.bundle).resolve()
    meta = read_json(bundle / "model_metadata.json")
    metrics = read_json(bundle / "evaluation_metrics.json")
    descriptions = read_json(bundle / "species_descriptions.json") if (bundle / "species_descriptions.json").exists() else {}
    version = meta["model_version"]
    out = Path(args.geoflora).resolve() / "storage" / "models" / "candidates" / version
    if out.exists():
        raise SystemExit(f"{out} already exists")

    classes = []
    for s in sorted(meta["supported_species"], key=lambda s: s["index"]):
        names = (descriptions.get(s["species_id"]) or {}).get("common_names") or [s["common_name"]]
        classes.append({"id": class_id(s["scientific_name"]), "scientific_name": s["scientific_name"],
                        "common_name": GEOFLORA_COMMON_NAMES.get(s["species_id"], names[0]),
                        "role": "invasive" if s["is_target_invasive"] else "lookalike",
                        "lab_species_id": s["species_id"], "ecological_status": s["ecological_status"],
                        "status_verification": s["status_verification"]})

    lab, model = adapted_model(bundle)
    probe = np.random.default_rng(0).uniform(0, 255, (2, *lab.input_shape[1:])).astype("float32")
    diff = float(np.abs(lab(probe, training=False).numpy() - model(probe / 127.5 - 1.0, training=False).numpy()).max())
    if diff > 1e-4:
        raise SystemExit(f"adapted model disagrees with the lab model (max diff {diff})")

    out.mkdir(parents=True)
    model.save(out / "mobilenetv2.keras")
    (out / "class_mapping.json").write_text(json.dumps({
        "classes": [{k: c[k] for k in ("id", "scientific_name", "common_name", "role")} for c in classes],
        "source": f"GeoFlora-ML-Lab bundle {version}",
    }, indent=2), encoding="utf-8")
    (out / "species.yaml").write_text(yaml.safe_dump({"species": [
        {k: c[k] for k in ("id", "scientific_name", "common_name", "role")} for c in classes]},
        sort_keys=False, allow_unicode=True), encoding="utf-8")

    t = metrics["test"]
    per = {r["species"]: r for r in t["per_class"]}
    report = {c["scientific_name"]: {"precision": per[c["scientific_name"]]["precision"],
                                     "recall": per[c["scientific_name"]]["recall"],
                                     "f1-score": per[c["scientific_name"]]["f1"],
                                     "support": per[c["scientific_name"]]["support"]} for c in classes}
    report["macro avg"] = {"precision": t["macro_precision"], "recall": t["macro_recall"], "f1-score": t["macro_f1"],
                           "support": t["images"]}
    (out / "evaluation.json").write_text(json.dumps({
        "source": "GeoFlora-ML-Lab independent test split (observation-group isolated; threshold chosen on validation only)",
        "model_version": version, "dataset_version": meta["dataset_version"], "accuracy": t["accuracy"],
        "accuracy_ci95": meta["evaluation_summary"]["test_accuracy_ci"], "macroF1": t["macro_f1"],
        "class_order": [c["scientific_name"] for c in classes], "classification_report": report,
        "confidence_threshold": meta["unknown_handling"]["threshold"],
        "threshold_basis": meta["unknown_handling"]["strategy"] + " on " + meta["unknown_handling"]["selected_on"],
        "unsupported_species": {k: v for k, v in metrics["unsupported_species"]["test"].items() if not isinstance(v, (list, dict))},
        "classes": classes,
    }, indent=2), encoding="utf-8")
    shutil.copytree(bundle, out / "lab_bundle", ignore=shutil.ignore_patterns("model.keras", "savedmodel"))
    (out / "SHA256SUMS.txt").write_text("".join(f"{sha256_file(f)}  {f.relative_to(out).as_posix()}\n"
                                                for f in sorted(out.rglob("*")) if f.is_file()), encoding="utf-8")
    print(f"GeoFlora candidate written: {out}  (adapter max diff {diff:.2e})")


if __name__ == "__main__":
    sys.exit(main())
