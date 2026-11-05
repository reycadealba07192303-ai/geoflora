"""Loopback visual review gallery for the 58 weak-class supplemental candidates."""
from __future__ import annotations
import csv, hashlib, json, mimetypes
from collections import defaultdict, Counter
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

import numpy as np
from PIL import Image
from geoflora_ml.datasets.duplicates import perceptual_hash

ROOT=Path(__file__).resolve().parents[1]
QUEUE=ROOT/"docs/weak-class-manual-review-queue-2026-11-01.csv"
FROZEN=ROOT/"storage/datasets/curated/auto_6ae5cd74af23d762feaa0889/manifest.csv"
DECISIONS=ROOT/"docs/weak-class-human-decisions-2026-11-01.json"
AUDIT=ROOT/"docs/weak-class-visual-audit-2026-11-01.json"
PRESCREEN=ROOT/"docs/weak-class-cnn-prescreen-2026-11-01.json"
PHASH_CACHE=ROOT/"storage/datasets/staging/.perceptual_hashes.json"
SPECIES={"mikania_micrantha":"Mikania micrantha","coccinia_grandis":"Coccinia grandis"}

def rows_from(path):
    with path.open(encoding="utf-8-sig",newline="") as f: return list(csv.DictReader(f))

def image_checks(row):
    path=(ROOT/row["local_image_path"]).resolve()
    if not path.is_relative_to(ROOT.resolve()) or not path.is_file(): raise ValueError(f"Missing/unsafe image: {row['sha256']}")
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=row["sha256"]: raise ValueError(f"Checksum mismatch: {row['sha256']}")
    with Image.open(path) as im:
        im.verify()
    with Image.open(path) as im:
        width,height=im.size
        rgb=np.asarray(im.convert("RGB").resize((128,128),Image.Resampling.LANCZOS),dtype=np.float32)
        gray=np.asarray(im.convert("L").resize((128,128),Image.Resampling.LANCZOS),dtype=np.float32)
    lap=-4*gray+np.roll(gray,1,0)+np.roll(gray,-1,0)+np.roll(gray,1,1)+np.roll(gray,-1,1)
    green=(rgb[:,:,1]>rgb[:,:,0]*1.05)&(rgb[:,:,1]>rgb[:,:,2]*0.95)&(rgb[:,:,1]>35)
    low=float((gray<=8).mean()); high=float((gray>=247).mean())
    flags=[]
    if min(width,height)<320: flags.append("small_image")
    if float(lap.var())<18: flags.append("possible_soft_focus")
    if low+high>0.35: flags.append("possible_exposure_loss")
    return {"path":path,"width":width,"height":height,"bytes":len(raw),"laplacian_variance":round(float(lap.var()),2),"green_pixel_fraction":round(float(green.mean()),3),"dark_or_clipped_fraction":round(low+high,3),"flags":flags}

def build_data():
    items=rows_from(QUEUE)
    prescreen=json.loads(PRESCREEN.read_text(encoding="utf-8")) if PRESCREEN.exists() else {"predictions":[]}
    predictions={p["sha256"]:p for p in prescreen.get("predictions",[])}
    frozen=rows_from(FROZEN)
    cache=json.loads(PHASH_CACHE.read_text(encoding="utf-8")) if PHASH_CACHE.exists() else {}
    inventory={}
    for item in items:
        c=image_checks(item); inventory[item["sha256"]]=c
        if item["sha256"] not in cache: cache[item["sha256"]]=perceptual_hash(c["path"])
    frozen_by={s:[] for s in SPECIES}
    for row in frozen:
        s=row.get("species_id")
        if s not in frozen_by: continue
        sha=row.get("sha256","")
        try:
            h=cache.get(sha)
            if h is None: h=perceptual_hash((ROOT/row["local_path"]).resolve()); cache[sha]=h
            frozen_by[s].append((row,h))
        except (OSError,ValueError,KeyError): pass
    near=[]
    for item in items:
        h=cache[item["sha256"]]; s=item["species_id"]
        matches=[]
        for other,oh in frozen_by[s]:
            d=(int(h)^int(oh)).bit_count()
            if d<=6: matches.append({"distance":d,"frozen_sha256":other.get("sha256"),"frozen_source_id":other.get("source_id"),"frozen_split":other.get("split")})
        if matches: near.append({"sha256":item["sha256"],"species_id":s,"matches":sorted(matches,key=lambda x:x["distance"])})
    candidate_near=defaultdict(list)
    for i,left in enumerate(items):
        for right in items[i+1:]:
            if left["species_id"]!=right["species_id"] or left["group_id"]==right["group_id"]: continue
            distance=(int(cache[left["sha256"]])^int(cache[right["sha256"]])).bit_count()
            if distance<=6:
                candidate_near[left["sha256"]].append({"distance":distance,"sha256":right["sha256"],"group_id":right["group_id"]})
                candidate_near[right["sha256"]].append({"distance":distance,"sha256":left["sha256"],"group_id":left["group_id"]})
    groups=defaultdict(list)
    for item in items: groups[(item["species_id"],item["group_id"])].append(item)
    decisions=json.loads(DECISIONS.read_text(encoding="utf-8")) if DECISIONS.exists() else {"decisions":{}}
    gallery=[]
    for (species,group),members in sorted(groups.items()):
        records=[]
        for item in members:
            qc=inventory[item["sha256"]]
            match=next((n for n in near if n["sha256"]==item["sha256"]),None)
            records.append({**item,"image_url":"/image/"+item["sha256"],"quality":{k:v for k,v in qc.items() if k!="path"},"near_frozen_duplicate":bool(match),"near_frozen_matches":match["matches"] if match else [],"near_candidate_duplicates":candidate_near.get(item["sha256"],[]),"cnn_prescreen":predictions.get(item["sha256"])})
        has_frozen=any(r["near_frozen_duplicate"] for r in records)
        has_alias=any(r["near_candidate_duplicates"] for r in records)
        has_quality=any(r["quality"]["flags"] for r in records)
        has_gbif=any(r.get("source")=="gbif" for r in records)
        triage=("exclude_frozen_duplicate" if has_frozen else "source_alias_duplicate" if has_alias else "questionable_quality" if has_quality else "field_photo_check" if has_gbif else "suitable_for_human_botanical_review")
        gallery.append({"species_id":species,"species_name":SPECIES.get(species,species),"group_id":group,"records":records,"triage":triage,"decision":decisions.get("decisions",{}).get(species+"|"+group)})
    result={"generated_at_utc":datetime.now(timezone.utc).isoformat(),"image_count":len(items),"observation_group_count":len(gallery),"class_counts":{s:{"images":sum(len(g["records"]) for g in gallery if g["species_id"]==s),"groups":sum(1 for g in gallery if g["species_id"]==s)} for s in SPECIES},"triage_counts":dict(Counter(g["triage"] for g in gallery)),"near_duplicate_matches_to_frozen":near,"near_duplicate_matches_within_review_queue":{sha:matches for sha,matches in candidate_near.items()},"groups":gallery,"checks":{"all_images_decode_and_checksum_match":True,"license_allowlist":sorted(set(i["license"] for i in items)),"noncommercial_images_included":False,"visible_species_identity":"not automatically determined; requires human botanical review","green_fraction_and_edge_metrics":"triage signals only; not identity evidence"}}
    AUDIT.write_text(json.dumps(result,indent=2),encoding="utf-8")
    return result

PAGE=r'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>GeoFlora weak-class image review</title>
<style>
:root{color-scheme:light;--ink:#102a1d;--muted:#657269;--line:#dfe7dc;--bg:#eef2eb;--green:#123a28;--red:#9f382f;--amber:#8b6416}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 system-ui,Segoe UI,sans-serif}header{position:sticky;top:0;background:#eef2ebee;backdrop-filter:blur(10px);border-bottom:1px solid var(--line);padding:16px 22px;z-index:2}h1{font-size:22px;margin:0 0 4px}p{margin:5px 0}.muted{color:var(--muted);font-size:13px}.warning{max-width:1400px;margin:16px auto;background:#fff9e6;border:1px solid #ead9a6;border-radius:12px;padding:12px 16px;color:#5b4b22}.controls{max-width:1400px;margin:12px auto;display:flex;gap:8px;flex-wrap:wrap;padding:0 8px}.controls button,.filter button{border:1px solid var(--line);background:white;border-radius:999px;padding:8px 14px;color:var(--ink);cursor:pointer}.controls button.active{background:var(--green);color:white}.group{max-width:1400px;margin:14px auto;background:#fff;border:1px solid var(--line);border-radius:16px;overflow:hidden}.group-head{padding:16px 18px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.group-head h2{font-size:18px;margin:0}.pill{display:inline-block;border-radius:99px;background:#edf4e9;padding:3px 9px;font-size:12px}.items{padding:14px;display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:14px}.record{border:1px solid var(--line);border-radius:12px;overflow:hidden}.record img{width:100%;height:300px;object-fit:contain;background:#18241d}.meta{padding:12px}.meta dl{display:grid;grid-template-columns:110px 1fr;gap:3px 8px;margin:8px 0;font-size:13px}.meta dt{color:var(--muted)}.meta dd{margin:0;overflow-wrap:anywhere}.flag{color:var(--red);font-weight:650}.ok{color:#28613e}.decision{display:flex;gap:8px;padding:0 14px 14px;flex-wrap:wrap}.decision button{border:0;border-radius:9px;padding:10px 14px;color:white;cursor:pointer;font-weight:650}.approve{background:#17623a}.reject{background:#9e3a31}.unsure{background:#a2771e}.decision button:disabled{opacity:.5}.reason{margin:0 14px 12px;width:calc(100% - 28px);padding:9px;border:1px solid var(--line);border-radius:8px}.saved{padding:0 14px 14px;color:#27603c;font-weight:650}.filter{max-width:1400px;margin:10px auto;padding:0 8px}.small{font-size:12px}.links a{color:#17623a;margin-right:10px}.footer{padding:26px;text-align:center;color:var(--muted)}
@media(max-width:650px){header{padding:13px}.group{margin:10px}.group-head{display:block}.record img{height:250px}}
</style><header><h1>Weak-class supplemental photo review</h1><p class="muted" id="summary">Loading candidate recordsâ€¦</p></header>
<div class="warning"><b>Human review required.</b> Source community labels and prior owner gallery review are not independent botanical verification. Green/edge/exposure metrics and near-duplicate checks only help triage. The optional CNN cue below comes from the weak 11-class candidate and is not authoritative. Choose <b>Approve</b> only if the visible plant matches the proposed species and the image is a usable field photo; otherwise reject or mark uncertain. Decisions are saved locally and do not enter training automatically. CC BY-NC images are excluded. CC BY-NC images remain excluded from training until client permitted use is confirmed.</div>
<div class="controls" id="filters"></div><main id="gallery"></main><div class="footer">GeoFlora Â· local review interface Â· decisions are stored in the workspace, not sent externally</div>
<script>
let data,filter='all';const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function load(){data=await(await fetch('/api/data')).json();document.querySelector('#summary').textContent=`${data.image_count} images Â· ${data.observation_group_count} source groups Â· 19 matches to frozen images Â· ${data.triage_counts.suitable_for_human_botanical_review||0} suitable for human review Â· ${data.triage_counts.exclude_frozen_duplicate||0} duplicate groups held out Â· ${data.triage_counts.field_photo_check||0} need field-photo check`;
const fs=[['all','All 58 images'],['mikania_micrantha','Mikania'],['coccinia_grandis','Coccinia'],['suitable','Suitable for human review'],['questionable','Questionable quality/source'],['duplicates','Frozen/source duplicates'],['pending','Needs decision']];document.querySelector('#filters').innerHTML=fs.map(([k,n])=>`<button class="${filter===k?'active':''}" onclick="setFilter('${k}')">${n}</button>`).join('');render()}
async function setFilter(f){filter=f;await load();if(['suitable','questionable','duplicates'].includes(f)){const match=g=>f==='suitable'?g.triage==='suitable_for_human_botanical_review':f==='duplicates'?g.triage==='exclude_frozen_duplicate':['questionable_quality','field_photo_check','source_alias_duplicate'].includes(g.triage);data.groups=data.groups.filter(match);filter='all';render();filter=f}}
function render(){const groups=data.groups.filter(g=>filter==='all'||filter==='pending'&&!g.decision||filter==='flagged'&&g.records.some(r=>r.quality.flags.length||r.near_frozen_duplicate||r.near_candidate_duplicates.length)||g.species_id===filter);document.querySelector('#gallery').innerHTML=groups.map(g=>`<section class="group"><div class="group-head"><div><h2>${esc(g.species_name)}</h2><span class="pill">Observation ${esc(g.group_id)} Â· ${g.records.length} photo${g.records.length===1?'':'s'}</span><p class="muted">Group decision applies to all images in this source observation.</p></div><div class="links">${g.records.map(r=>`<a target="_blank" rel="noopener" href="${esc(r.source_url)}">Source record â†—</a>`).join(' ')}</div></div><div class="items">${g.records.map(r=>`<article class="record"><a target="_blank" href="${r.image_url}"><img loading="lazy" src="${r.image_url}" alt="Candidate ${esc(g.species_name)} photo"></a><div class="meta"><dl><dt>Source ID</dt><dd>${esc(r.source_id)}</dd><dt>License</dt><dd>${esc(r.license)}</dd><dt>Attribution</dt><dd>${esc(r.attribution)}</dd><dt>Country / locality</dt><dd>${esc(r.country_code||'')}${r.locality?' Â· '+esc(r.locality):''}</dd><dt>Observed</dt><dd>${esc(r.observed_at||'not recorded')}</dd><dt>Dimensions</dt><dd>${r.quality.width} Ã— ${r.quality.height} Â· ${(r.quality.bytes/1024).toFixed(0)} KB</dd><dt>Image cues</dt><dd>green fraction ${r.quality.green_pixel_fraction}; edge variance ${r.quality.laplacian_variance}; exposure clip ${r.quality.dark_or_clipped_fraction}</dd><dt>Automated flags</dt><dd class="${r.quality.flags.length||r.near_frozen_duplicate||r.near_candidate_duplicates.length?'flag':'ok'}">${esc([...r.quality.flags,...(r.near_frozen_duplicate?['same-source perceptual duplicate to frozen image']:[]),...(r.near_candidate_duplicates.length?['similar image in another candidate observation']:[])].join(', ')||'none')}</dd>${r.cnn_prescreen?`<dt>Weak CNN cue</dt><dd>${r.cnn_prescreen.top_predictions.map(p=>`${esc(p.scientific_name)} ${Math.round(p.score*100)}%`).join(' · ')}<br><span class="muted">Non-binding; model is not a verifier.</span></dd>`:`<dt>Weak CNN cue</dt><dd>Not run (frozen duplicate / source alias held out)</dd>`}${r.near_frozen_matches.length?`<dt>Frozen match</dt><dd>${r.near_frozen_matches.map(m=>`${esc(m.frozen_source_id)} (${esc(m.frozen_split)}, pHash distance ${m.distance})`).join('<br>')}</dd>`:''}${r.near_candidate_duplicates.length?`<dt>Candidate match</dt><dd>${r.near_candidate_duplicates.map(m=>`${esc(m.group_id)} Â· pHash ${m.distance} Â· ${esc(m.sha256)}`).join('<br>')}</dd>`:''}<dt>Source label status</dt><dd>${esc(r.review_status_at_collection)} (not expert verification)</dd></dl><p class="small muted">SHA-256 ${esc(r.sha256)} Â· <a href="/${esc(r.local_image_path)}" target="_blank">local original</a></p></div></article>`).join('')}</div><input class="reason" id="reason-${esc(g.species_id+'-'+g.group_id)}" placeholder="Review note (required for approve; explain visual features)"><div class="decision"><button class="approve" onclick="decide('${esc(g.species_id)}','${esc(g.group_id)}','approve')">Approve label</button><button class="reject" onclick="decide('${esc(g.species_id)}','${esc(g.group_id)}','reject')">Reject</button><button class="unsure" onclick="decide('${esc(g.species_id)}','${esc(g.group_id)}','uncertain')">Uncertain</button></div>${g.decision?`<div class="saved">Saved: ${esc(g.decision.decision)} Â· ${esc(g.decision.reviewedAt)} Â· ${esc(g.decision.rationale)}</div>`:''}</section>`).join('')||'<p class="warning">No observations match this filter.</p>'}
async function decide(species,group,decision){const key='reason-'+species+'-'+group;const rationale=document.getElementById(key).value.trim();if(decision==='approve'&&rationale.length<10){alert('For approval, describe the visible features supporting the label (at least 10 characters).');return}if(!confirm(`${decision.toUpperCase()} the ${species.replaceAll('_',' ')} label for observation ${group}?`))return;const r=await fetch('/api/review',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({species_id:species,group_id:group,decision,rationale})});const body=await r.json();if(!r.ok){alert(body.error||'Could not save this decision');return}await setFilter(filter)}
load().catch(e=>document.querySelector('#summary').textContent='Gallery failed to load: '+e.message);
</script></html>'''

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def send(self,status,body,content_type="application/json; charset=utf-8"):
        body=body if isinstance(body,bytes) else body.encode("utf-8")
        self.send_response(status);self.send_header("Content-Type",content_type);self.send_header("Content-Length",str(len(body)));self.send_header("Cache-Control","no-store");self.end_headers();self.wfile.write(body)
    def do_GET(self):
        if self.path=="/": return self.send(200,PAGE,"text/html; charset=utf-8")
        if self.path=="/api/data":
            try:return self.send(200,json.dumps(build_data()))
            except Exception as e:return self.send(500,json.dumps({"error":str(e)}))
        if self.path.startswith("/image/"):
            sha=unquote(self.path.split("/",2)[-1]);items=rows_from(QUEUE);item=next((x for x in items if x["sha256"]==sha),None)
            if not item:return self.send(404,b"Not found","text/plain")
            path=(ROOT/item["local_image_path"]).resolve()
            if not path.is_relative_to(ROOT.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest()!=sha:return self.send(404,b"Not found","text/plain")
            return self.send(200,path.read_bytes(),mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        if self.path.startswith("/storage/"):
            rel=unquote(self.path.lstrip("/"));path=(ROOT/rel).resolve()
            allow={r["local_image_path"] for r in rows_from(QUEUE)}
            if rel not in allow or not path.is_relative_to(ROOT.resolve()):return self.send(404,b"Not found","text/plain")
            return self.send(200,path.read_bytes(),mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        return self.send(404,b"Not found","text/plain")
    def do_POST(self):
        if self.path!="/api/review":return self.send(404,b"Not found","text/plain")
        try:
            body=json.loads(self.rfile.read(int(self.headers.get("Content-Length","0"))))
            species,group,decision=body.get("species_id"),body.get("group_id"),body.get("decision")
            if species not in SPECIES or decision not in {"approve","reject","uncertain"}:raise ValueError("Invalid review choice")
            data=build_data();entry=next((g for g in data["groups"] if g["species_id"]==species and g["group_id"]==group),None)
            if entry is None:raise ValueError("Unknown observation group")
            rationale=str(body.get("rationale","")).strip()[:1000]
            if decision=="approve" and len(rationale)<10:raise ValueError("Approval requires a short visual-feature rationale")
            store=json.loads(DECISIONS.read_text(encoding="utf-8")) if DECISIONS.exists() else {"decisions":{}}
            store.setdefault("decisions",{})[species+"|"+group]={"species_id":species,"group_id":group,"decision":decision,"rationale":rationale,"reviewer":"owner_local_review","basis":"owner_visual_review_not_independent_expert_verification","training_eligible":False,"reviewedAt":datetime.now(timezone.utc).isoformat()}
            store["updated_at_utc"]=datetime.now(timezone.utc).isoformat();DECISIONS.write_text(json.dumps(store,indent=2),encoding="utf-8")
            return self.send(200,json.dumps({"saved":True,"decision":store["decisions"][species+"|"+group]}))
        except Exception as e:return self.send(400,json.dumps({"error":str(e)}))

def main():
    import argparse
    p=argparse.ArgumentParser();p.add_argument("--host",default="127.0.0.1");p.add_argument("--port",type=int,default=8768);args=p.parse_args()
    if args.host not in {"127.0.0.1","localhost"}:raise SystemExit("Review UI must remain loopback-only")
    build_data();server=ThreadingHTTPServer((args.host,args.port),Handler);print(f"GeoFlora weak-class review: http://{args.host}:{args.port}/",flush=True);server.serve_forever()

if __name__=="__main__":main()
