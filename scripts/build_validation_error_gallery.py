"""Recompute saved-candidate predictions on development validation only and serve a review gallery."""
from __future__ import annotations

import csv
import hashlib
import json
import mimetypes
from collections import Counter, defaultdict
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

import numpy as np
from PIL import Image
import tensorflow as tf

from geoflora_ml.inference.preprocess import preprocess_rgb_batch, rgb_array

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "storage/datasets/curated/auto_6ae5cd74af23d762feaa0889_weakreview_v3_20261101"
CANDIDATE = ROOT / "storage/models/candidates/mobilenetv2_11class_head_weakreview_v1_20261101"
OUT = ROOT / "docs/validation-error-analysis-2026-11-01.json"
ACTIVE_MODEL = ROOT / "storage/models/mobilenetv2.keras"
ACTIVE_MAPPING = ROOT / "storage/models/class_mapping.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_rows(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def quality(path: Path):
    with Image.open(path) as im:
        width, height = im.size
        rgb = np.asarray(im.convert("RGB").resize((128, 128), Image.Resampling.LANCZOS), dtype=np.float32)
        gray = np.asarray(im.convert("L").resize((128, 128), Image.Resampling.LANCZOS), dtype=np.float32)
    lap = -4 * gray + np.roll(gray, 1, 0) + np.roll(gray, -1, 0) + np.roll(gray, 1, 1) + np.roll(gray, -1, 1)
    low, high = float((gray <= 8).mean()), float((gray >= 247).mean())
    flags = []
    if min(width, height) < 320: flags.append("small_image")
    if float(lap.var()) < 18: flags.append("possible_soft_focus")
    if low + high > 0.35: flags.append("possible_exposure_loss")
    return {"width": width, "height": height, "laplacian_variance": round(float(lap.var()), 2), "clipped_fraction": round(low + high, 3), "flags": flags}


def category(true: str, predicted: str) -> str:
    if true == "mikania_micrantha" and predicted == "chromolaena_odorata" or true == "chromolaena_odorata" and predicted == "mikania_micrantha":
        return "mikania_chromolaena"
    if true == "broussonetia_papyrifera" or predicted == "broussonetia_papyrifera":
        return "broussonetia"
    if true == "coccinia_grandis" or predicted == "coccinia_grandis":
        return "coccinia_lookalike"
    return "other_error"


def build():
    dataset_meta = json.loads((DATASET / "dataset_metadata.json").read_text(encoding="utf-8"))
    if sha(DATASET / "manifest.csv") != dataset_meta["manifest_sha256"]:
        raise ValueError("Frozen validation manifest checksum mismatch")
    class_mapping = json.loads((CANDIDATE / "class_mapping.json").read_text(encoding="utf-8"))["classes"]
    class_order = [item["id"] for item in class_mapping]
    validation = [r for r in read_rows(DATASET / "manifest.csv") if r["split"] == "validation"]
    repeated = Counter(r.get("near_duplicate_group_id") or r["group_id"] for r in validation)
    arrays = []
    for row in validation:
        path = (ROOT / row["local_path"]).resolve()
        if not path.is_relative_to(ROOT.resolve()) or not path.is_file() or sha(path) != row["sha256"]:
            raise ValueError(f"Validation image integrity/path failure: {row.get('source_id')}")
        arrays.append(rgb_array(Image.open(path).convert("RGB")))
    model = tf.keras.models.load_model(CANDIDATE / "mobilenetv2.keras", compile=False)
    probabilities = np.asarray(model.predict(preprocess_rgb_batch(arrays), batch_size=16, verbose=0))
    if probabilities.shape != (len(validation), len(class_order)):
        raise ValueError("Validation prediction shape does not match split and class mapping")

    records, error_counts = [], Counter()
    for row, scores in zip(validation, probabilities):
        order = np.argsort(scores)[::-1]
        predicted, second = class_order[int(order[0])], class_order[int(order[1])]
        true = row["species_id"]
        is_error = predicted != true
        if is_error:
            error_counts[true] += 1
        group_key = row.get("near_duplicate_group_id") or row["group_id"]
        image_path = (ROOT / row["local_path"]).resolve()
        provenance = {
            "source": row.get("source", ""), "source_id": row.get("source_id", ""), "source_url": row.get("source_url", ""),
            "observation_id": row.get("observation_id", ""), "group_id": row.get("group_id", ""), "near_duplicate_group_id": row.get("near_duplicate_group_id", ""),
            "country_code": row.get("country_code", ""), "locality": row.get("locality", ""), "observed_at": row.get("observed_at", ""),
            "license": row.get("license", ""), "attribution": row.get("attribution", ""), "label_basis": row.get("label_basis", ""), "review_status": row.get("review_status", ""),
        }
        flags = quality(image_path)["flags"]
        record = {
            "sha256": row["sha256"], "image_url": "/image/" + row["sha256"], "true_label": true,
            "predicted_label": predicted, "confidence": float(scores[order[0]]), "second_label": second,
            "second_score": float(scores[order[1]]), "top_two_margin": float(scores[order[0]] - scores[order[1]]),
            "is_error": is_error, "review_category": category(true, predicted) if is_error else "correct_broussonetia_context" if true == "broussonetia_papyrifera" else "correct_other",
            "human_review_flags": ["source_label_not_independently_expert_verified", "inspect_for_visual_ambiguity"] + flags + (["repeated_near_duplicate_group_in_validation"] if repeated[group_key] > 1 else []),
            "quality": quality(image_path), "provenance": provenance, "local_path": row["local_path"],
        }
        record["low_margin_model_ambiguity_cue"] = record["top_two_margin"] <= 0.15
        records.append(record)
    errors = [r for r in records if r["is_error"]]
    result = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "candidate": "mobilenetv2_11class_head_weakreview_v1_20261101",
        "dataset": DATASET.relative_to(ROOT).as_posix(), "dataset_manifest_sha256": dataset_meta["manifest_sha256"],
        "split": "development validation only", "validation_images": len(validation), "validation_errors": len(errors),
        "errors_by_true_class": dict(error_counts),
        "priority_error_counts": {
            "mikania_chromolaena": sum(r["review_category"] == "mikania_chromolaena" for r in errors),
            "coccinia_involved": sum(r["review_category"] == "coccinia_lookalike" for r in errors),
            "broussonetia_involved": sum(r["review_category"] == "broussonetia" for r in errors),
            "broussonetia_validation_cases_including_correct": sum(r["true_label"] == "broussonetia_papyrifera" for r in records),
        },
        "historical_test_policy": "No historical test image was opened or predicted for this gallery.",
        "interpretation": "Low top-two margin is a model ambiguity cue only. Image-quality heuristics are flags, not botanical findings. Every recorded label still requires human verification; no label was changed.",
        "class_order": class_order, "records": records,
    }
    OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


PAGE = r'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>GeoFlora validation error gallery</title>
<style>
body{margin:0;background:#edf1e9;color:#10261a;font:15px/1.45 system-ui,Segoe UI,sans-serif}header{position:sticky;top:0;z-index:2;background:#edf1e9ee;padding:15px 20px;border-bottom:1px solid #d5dfd3;backdrop-filter:blur(8px)}h1{font-size:22px;margin:0}p{margin:5px 0}.muted{color:#5f6d62;font-size:13px}.notice{max-width:1400px;margin:12px auto;background:#fff5d9;border:1px solid #e9d9a8;border-radius:12px;padding:12px}.filters{max-width:1400px;margin:12px auto;display:flex;gap:8px;flex-wrap:wrap}.filters button{background:white;border:1px solid #d5dfd3;border-radius:99px;padding:8px 13px;cursor:pointer}.filters button.active{background:#143b29;color:white}.grid{max-width:1400px;margin:12px auto;display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:12px}.card{background:white;border:1px solid #d5dfd3;border-radius:14px;overflow:hidden}.card img{width:100%;height:300px;object-fit:contain;background:#17241d}.body{padding:12px}.labels{display:flex;gap:8px;flex-wrap:wrap;font-weight:650}.pill{border-radius:99px;padding:3px 9px;background:#f7e8e4;color:#8b3029}.good{background:#e8f2e6;color:#2c6438}.amb{background:#fff2cc;color:#725a0d}dl{display:grid;grid-template-columns:125px 1fr;gap:4px 8px;font-size:13px}dt{color:#66736a}dd{margin:0;overflow-wrap:anywhere}.flags{color:#8b3029;font-size:12px}.source a{color:#17613a}.hidden{display:none}
</style><header><h1>Validation error analysis</h1><p id="summary" class="muted">Loading...</p></header><div class="notice"><b>Human review only.</b> Predictions and scores are from the saved head candidate on development validation. Low score margin is a model ambiguity cue, not proof that a specimen is visually ambiguous. Image metrics flag possible quality issues only. Source labels are not independent expert determinations. Do not relabel from this gallery alone. Historical test images were not opened.</div><nav id="filters" class="filters"></nav><main id="grid" class="grid"></main><script>
let data,filter='all';const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function load(){data=await(await fetch('/api/data')).json();document.querySelector('#summary').textContent=`${data.validation_errors} errors among ${data.validation_images} validation images; grouped filters prioritize Mikania-Chromolaena, Coccinia-involved errors, and all Broussonetia cases.`;const fs=[['all','All errors'],['mikania_chromolaena','Mikania vs Chromolaena'],['coccinia_lookalike','Coccinia-involved'],['broussonetia','Broussonetia-involved'],['low_margin','Low-margin ambiguity cue'],['quality','Quality flags']];document.querySelector('#filters').innerHTML=fs.map(([k,v])=>`<button class="${filter===k?'active':''}" onclick="setFilter('${k}')">${v}</button>`).join('');render()}
function setFilter(f){filter=f;document.querySelectorAll('.filters button').forEach(b=>b.classList.toggle('active',b.textContent.toLowerCase().includes(f.replaceAll('_',' '))));render()}
function render(){let xs=data.records.filter(r=>r.is_error||(filter==='broussonetia'&&r.true_label==='broussonetia_papyrifera'));xs=xs.filter(r=>filter==='all'?true:filter==='low_margin'?r.low_margin_model_ambiguity_cue:filter==='quality'?r.quality.flags.length>0:filter==='broussonetia'?r.true_label==='broussonetia_papyrifera'||r.predicted_label==='broussonetia_papyrifera':r.review_category===filter);document.querySelector('#grid').innerHTML=xs.map(r=>`<article class="card"><img loading="lazy" src="${r.image_url}" alt="Validation image; recorded ${esc(r.true_label)}"><div class="body"><div class="labels"><span class="pill">Recorded: ${esc(r.true_label)}</span><span class="pill">Predicted: ${esc(r.predicted_label)}</span><span class="${r.low_margin_model_ambiguity_cue?'pill amb':'pill'}">${(r.confidence*100).toFixed(1)}% score</span></div><dl><dt>Second prediction</dt><dd>${esc(r.second_label)} (${(r.second_score*100).toFixed(1)}%)</dd><dt>Top-two margin</dt><dd>${(r.top_two_margin*100).toFixed(1)} pp${r.low_margin_model_ambiguity_cue?' - low-margin cue':''}</dd><dt>Observation</dt><dd>${esc(r.provenance.observation_id||r.provenance.group_id)}; near-duplicate group ${esc(r.provenance.near_duplicate_group_id||'none')}</dd><dt>Source / ID</dt><dd>${esc(r.provenance.source)} / ${esc(r.provenance.source_id)}</dd><dt>Location/date</dt><dd>${esc(r.provenance.country_code)}; ${esc(r.provenance.locality)}; ${esc(r.provenance.observed_at)}</dd><dt>License / attribution</dt><dd>${esc(r.provenance.license)}; ${esc(r.provenance.attribution)}</dd><dt>Label basis</dt><dd>${esc(r.provenance.label_basis)} (${esc(r.provenance.review_status)})</dd><dt>Image size</dt><dd>${r.quality.width} x ${r.quality.height}</dd></dl><p class="flags">Review flags: ${esc(r.human_review_flags.join(', '))}</p><p class="source"><a href="${esc(r.provenance.source_url)}" target="_blank" rel="noopener">Open source observation</a> · SHA-256 ${esc(r.sha256)}</p></div></article>`).join('')||'<p class="notice">No records match this filter.</p>'}
load().catch(e=>document.querySelector('#summary').textContent='Could not load: '+e.message);
</script></html>'''


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def send(self, status, body, mime="application/json; charset=utf-8"):
        if not isinstance(body, bytes): body = body.encode("utf-8")
        self.send_response(status); self.send_header("Content-Type", mime); self.send_header("Content-Length", str(len(body))); self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        if self.path == "/": return self.send(200, PAGE, "text/html; charset=utf-8")
        if self.path == "/api/data": return self.send(200, OUT.read_text(encoding="utf-8"))
        if self.path.startswith("/image/"):
            key = unquote(self.path.rsplit("/", 1)[-1])
            result = json.loads(OUT.read_text(encoding="utf-8"))
            row = next((r for r in result["records"] if r["sha256"] == key), None)
            if row is None: return self.send(404, b"Not found", "text/plain")
            path = (ROOT / row["local_path"]).resolve()
            if not path.is_relative_to(ROOT.resolve()) or sha(path) != key: return self.send(404, b"Not found", "text/plain")
            return self.send(200, path.read_bytes(), mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        return self.send(404, b"Not found", "text/plain")


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8769)
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "localhost"}: raise SystemExit("Local-only gallery")
    result = build()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(json.dumps({"url": f"http://{args.host}:{args.port}/", "validation_images": result["validation_images"], "errors": result["validation_errors"], "priorities": result["priority_error_counts"]}), flush=True)
    server.serve_forever()


if __name__ == "__main__": main()
