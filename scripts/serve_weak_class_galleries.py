"""Serve local-only validation-error and weak-class follow-up galleries."""
from __future__ import annotations

import csv
import hashlib
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
ERRORS = ROOT / "docs/validation-error-analysis-2026-11-01.json"
QUEUE = ROOT / "docs/weak-class-followup-review-queue-2026-11-01.csv"

ERROR_PAGE = r'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>GeoFlora validation error gallery</title><style>
body{margin:0;background:#edf1e9;color:#10261a;font:15px/1.45 system-ui,Segoe UI,sans-serif}header{position:sticky;top:0;background:#edf1e9ee;padding:15px 20px;border-bottom:1px solid #d5dfd3;z-index:2}h1{font-size:22px;margin:0}.muted{color:#5f6d62;font-size:13px}.notice{max-width:1400px;margin:12px auto;background:#fff5d9;border:1px solid #e9d9a8;border-radius:12px;padding:12px}.filters{max-width:1400px;margin:12px auto;display:flex;gap:8px;flex-wrap:wrap}.filters button{background:white;border:1px solid #d5dfd3;border-radius:99px;padding:8px 13px;cursor:pointer}.filters button.active{background:#143b29;color:white}.group{max-width:1400px;margin:12px auto;background:#e1e9df;border-radius:14px;padding:12px}.group h2{font-size:15px;margin:0 0 10px}.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:12px}.card{background:white;border:1px solid #d5dfd3;border-radius:14px;overflow:hidden}.card img{width:100%;height:300px;object-fit:contain;background:#17241d}.body{padding:12px}.labels{display:flex;gap:8px;flex-wrap:wrap;font-weight:650}.pill{border-radius:99px;padding:3px 9px;background:#f7e8e4;color:#8b3029}.amb{background:#fff2cc;color:#725a0d}dl{display:grid;grid-template-columns:125px 1fr;gap:4px 8px;font-size:13px}dt{color:#66736a}dd{margin:0;overflow-wrap:anywhere}.flags{color:#8b3029;font-size:12px}.source a{color:#17613a}</style><header><h1>Validation error analysis</h1><p id="summary" class="muted">Loading…</p><a href="/review">Open weak-class follow-up review queue</a></header><div class="notice"><b>Human review only.</b> Saved head-candidate predictions on development validation only. Low score margin is a model cue, not proof of visual ambiguity; quality flags are heuristics. Source labels are not independent expert determinations. No labels changed. Historical test images were not opened.</div><nav id="filters" class="filters"></nav><main id="grid"></main><script>
let data,filter='all';const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function load(){data=await(await fetch('/api/errors')).json();document.querySelector('#summary').textContent=`${data.validation_errors} errors among ${data.validation_images} development validation images. Groups are arranged by error family, recorded class, and observation.`;let fs=[['all','All errors'],['mikania_chromolaena','Mikania vs Chromolaena'],['coccinia_lookalike','Coccinia-involved'],['broussonetia','Broussonetia-involved'],['low_margin','Low-margin cue'],['quality','Quality flags']];document.querySelector('#filters').innerHTML=fs.map(([k,v])=>`<button data-k="${k}" class="${filter===k?'active':''}" onclick="setFilter('${k}')">${v}</button>`).join('');render()}
function setFilter(f){filter=f;document.querySelectorAll('button[data-k]').forEach(b=>b.classList.toggle('active',b.dataset.k===f));render()}
function render(){let xs=data.records.filter(r=>r.is_error||(filter==='broussonetia'&&r.true_label==='broussonetia_papyrifera'));xs=xs.filter(r=>filter==='all'?true:filter==='low_margin'?r.low_margin_model_ambiguity_cue:filter==='quality'?r.quality.flags.length>0:filter==='broussonetia'?r.true_label==='broussonetia_papyrifera'||r.predicted_label==='broussonetia_papyrifera':r.review_category===filter);let groups=new Map();for(const r of xs){let key=`${r.review_category}|${r.true_label}|${r.provenance.observation_id||r.provenance.group_id}`;if(!groups.has(key))groups.set(key,[]);groups.get(key).push(r)}document.querySelector('#grid').innerHTML=[...groups.entries()].map(([k,rs])=>{let r=rs[0];return `<section class="group"><h2>${esc(r.review_category)} · recorded ${esc(r.true_label)} · observation ${esc(r.provenance.observation_id||r.provenance.group_id)} · ${rs.length} image(s)</h2><div class="cards">${rs.map(r=>`<article class="card"><img loading="lazy" src="${r.image_url}" alt="Recorded ${esc(r.true_label)}"><div class="body"><div class="labels"><span class="pill">Recorded: ${esc(r.true_label)}</span><span class="pill">Predicted: ${esc(r.predicted_label)}</span><span class="${r.low_margin_model_ambiguity_cue?'pill amb':'pill'}">${(r.confidence*100).toFixed(1)}% score</span></div><dl><dt>Second prediction</dt><dd>${esc(r.second_label)} (${(r.second_score*100).toFixed(1)}%)</dd><dt>Observation group</dt><dd>${esc(r.provenance.observation_id||r.provenance.group_id)} / ${esc(r.provenance.near_duplicate_group_id||'no near-duplicate group recorded')}</dd><dt>Source</dt><dd>${esc(r.provenance.source)} / ${esc(r.provenance.source_id)}</dd><dt>Place/date</dt><dd>${esc(r.provenance.country_code)} · ${esc(r.provenance.locality)} · ${esc(r.provenance.observed_at)}</dd><dt>Rights</dt><dd>${esc(r.provenance.license)} · ${esc(r.provenance.attribution)}</dd><dt>Label basis</dt><dd>${esc(r.provenance.label_basis)} (${esc(r.provenance.review_status)})</dd><dt>Image size</dt><dd>${r.quality.width}×${r.quality.height}</dd><dt>Review flags</dt><dd class="flags">${esc(r.human_review_flags.join(', '))}</dd></dl><p class="source"><a href="${esc(r.provenance.source_url)}" target="_blank" rel="noopener">Open source observation</a> · SHA-256 ${esc(r.sha256)}</p></div></article>`).join('')}</div></section>`}).join('')||'<p class="notice">No images match this filter.</p>'}load().catch(e=>document.querySelector('#summary').textContent='Error: '+e.message);
</script></html>'''

REVIEW_PAGE = r'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Weak-class follow-up review queue</title><style>body{margin:0;background:#edf1e9;color:#10261a;font:15px/1.45 system-ui,Segoe UI,sans-serif}header{padding:18px 22px;background:white;border-bottom:1px solid #d5dfd3}h1{margin:0;font-size:22px}.notice{margin:16px auto;max-width:1100px;background:#fff5d9;border:1px solid #e9d9a8;border-radius:12px;padding:12px}.group{max-width:1100px;margin:16px auto;background:white;border:1px solid #d5dfd3;border-radius:14px;padding:14px}.photos{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}.photos img{width:100%;height:300px;object-fit:contain;background:#17241d;border-radius:10px}dl{display:grid;grid-template-columns:150px 1fr;gap:5px 9px;font-size:13px}dt{color:#66736a}dd{margin:0;overflow-wrap:anywhere}a{color:#17613a}</style><header><h1>Weak-class follow-up review queue</h1><p><a href="/">Back to validation error gallery</a> · <a href="/api/review.csv">Download CSV</a></p><p id="summary">Loading…</p></header><div class="notice"><b>Review status:</b> these source identifications are not independent expert verification. Owner visual review is recorded, but the candidate below still needs independent botanical confirmation and explicit training eligibility reconciliation. CC BY attribution is preserved. Nothing here is in training or a blind test set.</div><main id="items"></main><script>const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));fetch('/api/review').then(r=>r.json()).then(rows=>{document.querySelector('#summary').textContent=`${rows.length} images · ${new Set(rows.map(r=>r.species_id+'|'+r.observation_id)).size} observation groups. Queue is empty when no unresolved candidate meets current strict eligibility.`;let g=new Map();for(const r of rows){let k=r.species_id+'|'+r.observation_id;if(!g.has(k))g.set(k,[]);g.get(k).push(r)}document.querySelector('#items').innerHTML=[...g.values()].map(rs=>{let r=rs[0];return `<section class="group"><h2>${esc(r.species_id)} · observation ${esc(r.observation_id)}</h2><div class="photos">${rs.map(x=>`<figure><img src="/image/${x.image_sha256}" alt="Review candidate ${esc(x.species_id)}"><figcaption>Image ${esc(x.image_sha256)}</figcaption></figure>`).join('')}</div><dl><dt>Review status</dt><dd>${esc(r.review_status)}</dd><dt>Recorded rationale</dt><dd>${esc(r.review_rationale)}</dd><dt>Label basis</dt><dd>${esc(r.label_basis)}</dd><dt>Source</dt><dd><a href="${esc(r.source_url)}" target="_blank" rel="noopener">${esc(r.source_url)}</a></dd><dt>License</dt><dd>${esc(r.license)} · ${esc(r.attribution)}</dd><dt>Locality/date</dt><dd>${esc(r.locality)} · ${esc(r.observed_at)} · ${esc(r.country_code)}</dd><dt>Next action</dt><dd>Independent botanical verification; do not include in training until eligibility is explicitly recorded.</dd></dl></section>`}).join('')||'<section class="group">No new pending records were collected. One existing Coccinia observation group is included because owner visual approval does not establish independent botanical verification.</section>'}).catch(e=>document.querySelector('#summary').textContent=e.message)</script></html>'''


def read_review():
    if not QUEUE.exists():
        return []
    with QUEUE.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, status, body, mime="application/json; charset=utf-8"):
        if not isinstance(body, bytes):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/":
            return self.send(200, ERROR_PAGE, "text/html; charset=utf-8")
        if self.path == "/review":
            return self.send(200, REVIEW_PAGE, "text/html; charset=utf-8")
        if self.path == "/api/errors":
            return self.send(200, ERRORS.read_text(encoding="utf-8"))
        rows = read_review()
        if self.path == "/api/review":
            return self.send(200, json.dumps(rows, ensure_ascii=False))
        if self.path == "/api/review.csv":
            return self.send(200, QUEUE.read_bytes(), "text/csv; charset=utf-8")
        if self.path.startswith("/image/"):
            key = unquote(self.path.rsplit("/", 1)[-1])
            records = json.loads(ERRORS.read_text(encoding="utf-8")).get("records", [])
            paths = [r.get("local_path") for r in records if r.get("sha256") == key]
            paths += [r.get("local_path") for r in rows if r.get("image_sha256") == key]
            for rel in paths:
                path = (ROOT / str(rel)).resolve()
                if path.is_relative_to(ROOT.resolve()) and path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == key:
                    return self.send(200, path.read_bytes(), mimetypes.guess_type(path.name)[0] or "application/octet-stream")
            return self.send(404, b"Not found", "text/plain")
        return self.send(404, b"Not found", "text/plain")


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 8770), Handler)
    print("Validation gallery: http://127.0.0.1:8770/ | review queue: http://127.0.0.1:8770/review", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
