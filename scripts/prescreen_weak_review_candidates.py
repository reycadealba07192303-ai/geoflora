"""Non-binding CNN pre-screen for the 38 candidates not duplicated against frozen data.

This is triage only: it produces no accuracy claim, label approval, split, or training data.
Frozen perceptual duplicates (including historical test images) and the duplicate GBIF alias
are excluded before Keras inference.
"""
import json
from pathlib import Path

import numpy as np
import tensorflow as tf
from PIL import Image
from geoflora_ml.inference.preprocess import preprocess_rgb_batch, rgb_array

ROOT=Path(__file__).resolve().parents[1]
VISUAL=ROOT/"docs/weak-class-visual-audit-2026-11-01.json"
MODEL=ROOT/"storage/models/candidates/auto_6ae5cd74af23d762feaa0889/mobilenetv2.keras"
MAPPING=ROOT/"storage/models/candidates/auto_6ae5cd74af23d762feaa0889/class_mapping.json"
OUT=ROOT/"docs/weak-class-cnn-prescreen-2026-11-01.json"

def main():
    audit=json.loads(VISUAL.read_text(encoding="utf-8"))
    mapping=json.loads(MAPPING.read_text(encoding="utf-8"))["classes"]
    class_by_id={x["id"]:x for x in mapping}
    candidates=[]
    excluded_frozen=set()
    for match in audit["near_duplicate_matches_to_frozen"]: excluded_frozen.add(match["sha256"])
    for group in audit["groups"]:
        if group["triage"]=="exclude_frozen_duplicate": continue
        for row in group["records"]:
            # Same photo ID appears once directly on iNaturalist and once through GBIF.
            if row["source"]=="gbif" and "photos/28386564" in row.get("source_id",""): continue
            if row["sha256"] in excluded_frozen: continue
            candidates.append((group,row))
    if len(candidates)!=38: raise RuntimeError(f"Expected 38 de-duplicated candidates, found {len(candidates)}")
    arrays=[]
    for _,row in candidates:
        with Image.open(ROOT/row["local_image_path"]) as image: arrays.append(rgb_array(image))
    model=tf.keras.models.load_model(MODEL,compile=False)
    probabilities=np.asarray(model.predict(preprocess_rgb_batch(arrays),verbose=0))
    outputs=[]
    for (group,row),scores in zip(candidates,probabilities):
        order=np.argsort(scores)[::-1][:3]
        outputs.append({"sha256":row["sha256"],"species_id":row["species_id"],"group_id":group["group_id"],"top_predictions":[{"species_id":mapping[int(i)]["id"],"scientific_name":mapping[int(i)]["scientific_name"],"score":float(scores[i])} for i in order],"status":"non_binding_model_triage_only"})
    result={"candidate_model":"auto_6ae5cd74af23d762feaa0889","candidate_count":len(outputs),"frozen_duplicate_files_excluded":len(excluded_frozen),"historical_test_predictions_run":False,"purpose":"Weak visual-classification cue to prioritize manual review; scores do not approve labels, establish species identity, or measure accuracy.","predictions":outputs}
    OUT.write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps({"candidate_count":len(outputs),"counts_by_predicted_top_class":{c["id"]:sum(p["top_predictions"][0]["species_id"]==c["id"] for p in outputs) for c in mapping},"historical_test_predictions_run":False,"output":OUT.relative_to(ROOT).as_posix()},indent=2))

if __name__=="__main__":main()
