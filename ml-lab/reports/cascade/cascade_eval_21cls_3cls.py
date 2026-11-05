"""Compare 21-class alone vs. 21-class + 3-class cascade on the 21-class test set and unknown_test set.

Run from the ml-lab directory with its venv: python <this> <lab_dir>
"""
import csv
import json
import sys
from pathlib import Path

import numpy as np

LAB = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(LAB))
from geoflora_ml.inference import Predictor, preprocess_image  # noqa: E402

M21 = Predictor(LAB / "models/exported/geoflora-mnv2-21cls-v1")
M3 = Predictor(LAB / "models/exported/geoflora-mnv2-3cls-v2")
assert M21.score_type == "max_softmax" and M3.score_type == "max_softmax", (M21.score_type, M3.score_type)
c21 = [c["scientific_name"] for c in M21.mapping["classes"]]
c3 = [c["scientific_name"] for c in M3.mapping["classes"]]
TARGETS = set(c3)
print("thresholds: 21cls", M21.threshold, " 3cls", M3.threshold)

run = LAB / "models/checkpoints/nissap/run-20261104T155431Z-nissap21-v1"
items = [(LAB / r["split_path"], c21[[c["species_id"] for c in M21.mapping["classes"]].index(r["species_id"])])
         for r in csv.DictReader(open(run / "test_images.csv", encoding="utf-8"))]
items += [(p, "UNKNOWN") for p in sorted((LAB / "dataset/nissap/unknown_test").rglob("*")) if p.is_file()]


def probs(model, paths):
    out = []
    for i in range(0, len(paths), 64):
        x = np.stack([preprocess_image(p, model.image_size) for p in paths[i:i + 64]])
        out.append(model.model.predict(x, verbose=0))
    return np.concatenate(out)


paths = [p for p, _ in items]
P21, P3 = probs(M21, paths), probs(M3, paths)
truth = [t for _, t in items]


def decide_21(i):
    k = int(P21[i].argmax())
    return c21[k] if P21[i][k] >= M21.threshold else "UNCERTAIN"


def decide_cascade(i, require_3_conf, rescue_uncertain=False):
    """21-class decides first. If its top-1 is a target, the 3-class model must name the same target."""
    first = decide_21(i)
    top = c21[int(P21[i].argmax())]
    if top not in TARGETS or (first == "UNCERTAIN" and not rescue_uncertain):
        return first
    k3 = int(P3[i].argmax())
    agree = c3[k3] == top
    conf = P3[i][k3] >= M3.threshold
    if first == "UNCERTAIN":  # rescue only when the 3-class model agrees and is confident
        return top if agree and conf else "UNCERTAIN"
    return top if agree and (conf or not require_3_conf) else "UNCERTAIN"


def summarize(name, fn):
    s = {"target_correct": 0, "target_wrong_target": 0, "target_uncertain": 0, "target_missed": 0,
         "nontarget_false_alarm": 0, "unknown_false_alarm": 0, "nontarget_n": 0, "unknown_n": 0, "target_n": 0}
    for i, t in enumerate(truth):
        d = fn(i)
        if t in TARGETS:
            s["target_n"] += 1
            s["target_correct" if d == t else "target_wrong_target" if d in TARGETS else
              "target_uncertain" if d == "UNCERTAIN" else "target_missed"] += 1
        elif t == "UNKNOWN":
            s["unknown_n"] += 1
            s["unknown_false_alarm"] += d in TARGETS
        else:
            s["nontarget_n"] += 1
            s["nontarget_false_alarm"] += d in TARGETS
    per = {}
    for sp in c3:
        idx = [i for i, t in enumerate(truth) if t == sp]
        per[sp] = f"{sum(fn(i) == sp for i in idx)}/{len(idx)}"
    alarms = sum(1 for i, t in enumerate(truth) if fn(i) in TARGETS)
    correct_alarms = sum(1 for i, t in enumerate(truth) if fn(i) in TARGETS and fn(i) == t)
    print(f"\n== {name}")
    print(json.dumps(s))
    print("per-target correct:", per)
    print(f"when it says TARGET, it's right: {correct_alarms}/{alarms} = {correct_alarms / max(alarms, 1):.1%}")


summarize("21-class alone (threshold)", decide_21)
summarize("cascade: 21 says target -> 3cls must agree", lambda i: decide_cascade(i, False))
summarize("cascade: 21 says target -> 3cls must agree AND be confident", lambda i: decide_cascade(i, True))
summarize("cascade + rescue: also check 21-uncertain target guesses with 3cls", lambda i: decide_cascade(i, False, True))
