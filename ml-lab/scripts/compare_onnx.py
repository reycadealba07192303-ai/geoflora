"""Top-1 accuracy of two ONNX models on the same test photos (prints JSON).

  python scripts/compare_onnx.py --candidate ../apps/web/models/<new> --live ../apps/web/models/<old> --test-csv <run>/test_images.csv
Preprocessing matches the app: RGB, resize to 224 x 224, x / 127.5 - 1.
"""
import argparse
import csv
import json
from pathlib import Path

import numpy as np


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--candidate", required=True)
    p.add_argument("--live", required=True)
    p.add_argument("--test-csv", required=True)
    args = p.parse_args()
    import onnxruntime as ort
    from PIL import Image

    lab = Path(__file__).resolve().parents[1]
    catalog = {r["species_id"]: r["scientific_name"] for r in csv.DictReader(open(lab / "metadata" / "species_catalog.csv", encoding="utf-8"))}
    rows = list(csv.DictReader(open(args.test_csv, encoding="utf-8")))
    for r in rows:
        r["scientific_name"] = catalog.get(r["species_id"], "")
    result = {"photos": len(rows)}
    for name, folder in (("candidate", args.candidate), ("live", args.live)):
        folder = Path(folder)
        classes = json.loads((folder / "class_mapping.json").read_text(encoding="utf-8"))["classes"]
        session = ort.InferenceSession(str(folder / "model.onnx"), providers=["CPUExecutionProvider"])
        names = [c["scientific_name"] for c in classes]
        correct = 0
        for i in range(0, len(rows), 64):
            batch = rows[i:i + 64]
            x = np.stack([np.asarray(Image.open(lab / r["split_path"]).convert("RGB").resize((224, 224)), dtype=np.float32) / 127.5 - 1.0 for r in batch])
            probs = session.run(["probs"], {"image": x})[0]
            truth = [r.get("scientific_name") or "" for r in batch]
            correct += sum(names[int(p.argmax())] == t for p, t in zip(probs, truth))
        result[name] = correct / max(1, len(rows))
    print(json.dumps(result))


if __name__ == "__main__":
    main()
