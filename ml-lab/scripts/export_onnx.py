"""Convert a packaged GeoFlora candidate (storage/models/candidates/<version>/mobilenetv2.keras) to ONNX for the
Next.js app, and check that ONNX Runtime gives the same outputs as Keras.

The ONNX graph has one input `image` (N x 224 x 224 x 3, float32, already scaled with MobileNetV2 preprocess_input,
i.e. RGB / 127.5 - 1) and two outputs: `probs` (class probabilities) and `features` (the 1280-wide MobileNetV2
feature vector used for verified-reference search).

Run with the separate converter environment (keeps ml-lab's .venv untouched):
  .venv-onnx\\Scripts\\python.exe scripts\\export_onnx.py --candidate ..\\storage\\models\\candidates\\geoflora-mnv2-21cls-v1 \\
      --out ..\\apps\\web\\models\\geoflora-mnv2-21cls-v1 [--check-images dataset\\nissap\\test]
"""
import argparse
import json
import shutil
from pathlib import Path

import numpy as np


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--candidate", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--check-images", default=None, help="folder of photos to compare Keras and ONNX on (recursive)")
    p.add_argument("--check-count", type=int, default=200)
    args = p.parse_args()

    import onnxruntime as ort
    import tensorflow as tf
    import tf2onnx
    from PIL import Image
    from tensorflow import keras

    candidate, out = Path(args.candidate), Path(args.out)
    model = keras.models.load_model(candidate / "mobilenetv2.keras")
    feature_layers = [layer for layer in model.layers[:-1] if len(getattr(layer, "output", np.zeros((1,))).shape) == 2 and layer.output.shape[-1] == 1280]
    if not feature_layers:
        raise SystemExit("no 1280-wide feature layer found")
    dual = keras.Model(inputs=model.inputs, outputs=[model.output, feature_layers[-1].output])

    spec = [tf.TensorSpec([None, 224, 224, 3], tf.float32, name="image")]

    @tf.function(input_signature=spec)
    def serve(image):
        probs, features = dual(image, training=False)
        return {"probs": tf.identity(probs, name="probs"), "features": tf.identity(features, name="features")}

    out.mkdir(parents=True, exist_ok=True)
    onnx_path = out / "model.onnx"
    tf2onnx.convert.from_function(serve, input_signature=spec, opset=17, output_path=str(onnx_path))
    for name in ("class_mapping.json", "species.yaml", "evaluation.json"):
        if (candidate / name).exists():
            shutil.copy2(candidate / name, out / name)

    # Same preprocessing as services/ml: RGB, PIL resize to 224x224, preprocess_input.
    session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    photos = sorted(p for p in Path(args.check_images).rglob("*") if p.suffix.lower() in {".jpg", ".jpeg", ".png"})[:: max(1, len(list(Path(args.check_images).rglob("*.jpg"))) // args.check_count)] if args.check_images else []
    max_prob, max_feat, agree = 0.0, 0.0, 0
    for path in photos:
        x = np.asarray(Image.open(path).convert("RGB").resize((224, 224)), dtype=np.float32)[None] / 127.5 - 1.0
        kp, kf = dual(x, training=False)
        op, of = session.run(["probs", "features"], {"image": x})
        max_prob = max(max_prob, float(np.abs(kp.numpy() - op).max()))
        max_feat = max(max_feat, float(np.abs(kf.numpy() - of).max()))
        agree += int(kp.numpy().argmax() == op.argmax())
    report = {"onnx": onnx_path.name, "bytes": onnx_path.stat().st_size, "checked_photos": len(photos), "top1_agreement": agree / max(1, len(photos)),
              "max_abs_diff_probs": max_prob, "max_abs_diff_features": max_feat, "inputs": ["image"], "outputs": ["probs", "features"],
              "preprocess": "RGB, resize 224x224, x / 127.5 - 1"}
    (out / "onnx_check.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
