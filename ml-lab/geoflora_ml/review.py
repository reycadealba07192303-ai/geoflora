"""Botanical review workflow.

`export_review_sheets` writes, per species, a CSV the reviewer fills in plus an HTML gallery for
viewing the photos. `import_review_sheet` applies the reviewer's explicit decisions to the manifest.
There is intentionally no "approve all" shortcut: every approval must come from a filled-in
sheet with a named reviewer.
"""

from __future__ import annotations

import html
import json
import os
import shutil
from datetime import date
from pathlib import Path

import pandas as pd

from .catalog import by_id, load_catalog
from .config import project_path, project_root
from .manifest import load_manifest, save_manifest
from .utils import atomic_write_text, clean_str, resolve_path, utc_stamp, write_json

DECISIONS = {"approved", "rejected", "uncertain"}
CONDITION_COLUMNS = ["cond_lighting", "cond_background", "cond_organ", "cond_growth_stage"]
CONDITION_HINTS = {
    "cond_lighting": "bright_sun | overcast | shade | low_light | flash",
    "cond_background": "natural_clutter | plain | water | cultivated | herbarium",
    "cond_organ": "whole_plant | flower | leaf | stem | fruit | mixed",
    "cond_growth_stage": "seedling | vegetative | flowering | fruiting | senescent",
}
SHEET_COLUMNS = ["image_id", "species_id", "scientific_name", "local_path", "media_reference_url", "gbif_url",
                 "attribution", "quality_flags", "current_review_status", "decision", "review_notes", *CONDITION_COLUMNS]


def export_review_sheets(cfg: dict, species_ids: list[str] | None = None, include_reviewed: bool = False,
                         include_quality_failures: bool = False) -> list[Path]:
    root = project_root(cfg)
    catalog = by_id(load_catalog(project_path(cfg, "species_catalog")))
    df = load_manifest(project_path(cfg, "image_manifest"))
    out_dir = project_path(cfg, "reports") / "review_sheets"
    out_dir.mkdir(parents=True, exist_ok=True)
    if species_ids:
        df = df[df["species_id"].isin(species_ids) | df["scientific_name"].isin(species_ids)]
    if not include_reviewed:
        df = df[df["review_status"].isin(["pending", "uncertain", ""])]
    if not include_quality_failures:
        df = df[df["quality_pass"] != "false"]
    written = []
    for sid, g in df.groupby("species_id"):
        sp = catalog.get(sid)
        name = sp.folder if sp else sid
        sheet = pd.DataFrame({
            "image_id": g["image_id"],
            "species_id": g["species_id"],
            "scientific_name": g["scientific_name"],
            "local_path": g["local_path"],
            "media_reference_url": g["media_reference_url"],
            "gbif_url": g["gbif_occurrence_key"].map(lambda k: f"https://www.gbif.org/occurrence/{k}" if k else ""),
            "attribution": g["attribution"],
            "quality_flags": g["quality_flags"],
            "current_review_status": g["review_status"],
            "decision": "",
            "review_notes": "",
            **{c: g[c] for c in CONDITION_COLUMNS},
        })[SHEET_COLUMNS]
        csv_path = out_dir / f"{sid}_{name}.csv"
        atomic_write_text(csv_path, sheet.to_csv(index=False))
        html_path = out_dir / f"{sid}_{name}.html"
        atomic_write_text(html_path, _gallery_html(sheet, sp.scientific_name if sp else sid, html_path, root))
        written += [csv_path, html_path]
    return written


def _gallery_html(sheet: pd.DataFrame, title: str, html_path: Path, root: Path) -> str:
    """Interactive review page: one decision per photo (buttons or A/R/U keys), progress kept in the
    browser's localStorage, and a "Download CSV" button that writes a sheet `import_review_sheet` accepts.
    Deliberately no bulk-approve control."""
    rows = sheet.fillna("").to_dict("records")
    for r in rows:
        r["_img"] = os.path.relpath(resolve_path(r["local_path"], root), html_path.parent).replace("\\", "/")
    data = json.dumps({"columns": SHEET_COLUMNS, "conditions": {c: h.split(" | ") for c, h in CONDITION_HINTS.items()},
                       "csv_name": html_path.with_suffix(".csv").name, "rows": rows}).replace("</", "<\\/")
    return (_GALLERY_TEMPLATE.replace("__TITLE__", html.escape(title)).replace("__COUNT__", str(len(sheet)))
            .replace("__CSV__", html.escape(html_path.with_suffix(".csv").name)).replace("__DATA__", data))


_GALLERY_TEMPLATE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Review: __TITLE__</title>
<style>
body{font-family:system-ui,sans-serif;margin:0;color:#1d2a1f;background:#f4f7f4}
header{position:sticky;top:0;z-index:2;background:#fff;border-bottom:1px solid #ccd5cc;padding:12px 24px}
header h1{font-size:20px;margin:0 0 6px}
.bar{display:flex;flex-wrap:wrap;gap:12px;align-items:center;font-size:14px}
.bar button{font-size:14px;padding:6px 14px;cursor:pointer}
#progress{font-weight:600}
details.help{padding:8px 24px;font-size:14px;line-height:1.5}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:14px;padding:16px 24px}
figure{margin:0;border:3px solid #ccd5cc;border-radius:8px;padding:8px;background:#fff;outline:none}
figure:focus{box-shadow:0 0 0 3px #3b82f6}
figure.approved{border-color:#2e7d32}figure.rejected{border-color:#c62828}figure.uncertain{border-color:#f9a825}
img{width:100%;height:240px;object-fit:cover;border-radius:4px;display:block}
figcaption{font-size:12px;line-height:1.4;margin-top:6px;word-break:break-word}
.dec{display:flex;gap:6px;margin:8px 0}
.dec button{flex:1;padding:8px 0;font-size:13px;cursor:pointer;border:1px solid #999;border-radius:4px;background:#f7f7f7}
.dec button.on[data-d=approved]{background:#2e7d32;color:#fff}
.dec button.on[data-d=rejected]{background:#c62828;color:#fff}
.dec button.on[data-d=uncertain]{background:#f9a825;color:#000}
input.notes{width:100%;box-sizing:border-box;font-size:12px;padding:4px}
.cond{display:grid;grid-template-columns:1fr 1fr;gap:4px;margin-top:6px}
.cond select{font-size:11px}
.flag{color:#c62828}
</style></head><body>
<header>
<h1>Label review: <i>__TITLE__</i> (__COUNT__ images)</h1>
<div class="bar">
<span id="progress"></span>
<label><input type="checkbox" id="undecided"> show undecided only</label>
<button id="download">Download CSV</button>
<button id="reset">Clear my decisions</button>
</div>
</header>
<details class="help"><summary>How to review</summary>
<ul>
<li>Click a photo card (or press Tab) and press <b>A</b> = approved, <b>R</b> = rejected, <b>U</b> = uncertain,
<b>C</b> = clear. Focus jumps to the next photo. Click a photo to open it full-size.</li>
<li><b>Approve</b> only when the photo clearly shows this species. <b>Reject</b> when it is a different plant, not a plant,
or the plant is not identifiable (for example a map, herbarium label only, or a blurry patch). Use <b>uncertain</b> when you cannot tell:
uncertain images are not used for training.</li>
<li>The GBIF record and source links show the original observation and its community identification.</li>
<li>Decisions are saved in this browser automatically. Close the page at any time and continue later.</li>
<li>When done, click <b>Download CSV</b>. It saves <code>__CSV__</code> (usually in Downloads). Then run:<br>
<code>python scripts/review_images.py import "&lt;path to downloaded __CSV__&gt;" --reviewer "Your Full Name"</code></li>
<li>Condition tags (lighting, background, organ, growth stage) are optional but help the robustness analysis.</li>
</ul></details>
<div class="grid" id="grid"></div>
<script id="data" type="application/json">__DATA__</script>
<script>
const D = JSON.parse(document.getElementById("data").textContent);
const KEY = "geoflora-review:" + D.csv_name;
const state = JSON.parse(localStorage.getItem(KEY) || "{}");
const COND = Object.keys(D.conditions);
const grid = document.getElementById("grid");
const save = () => { localStorage.setItem(KEY, JSON.stringify(state)); progress(); };
const st = id => (state[id] = state[id] || {});
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));

function progress() {
  const n = {approved: 0, rejected: 0, uncertain: 0};
  for (const r of D.rows) { const d = (state[r.image_id] || {}).decision; if (d) n[d]++; }
  const done = n.approved + n.rejected + n.uncertain;
  document.getElementById("progress").textContent =
    `${done}/${D.rows.length} decided: ${n.approved} approved, ${n.rejected} rejected, ${n.uncertain} uncertain`;
}

function paint(fig, id) {
  const d = (state[id] || {}).decision || "";
  fig.className = d;
  fig.querySelectorAll(".dec button").forEach(b => b.classList.toggle("on", b.dataset.d === d));
  fig.hidden = document.getElementById("undecided").checked && !!d && fig !== document.activeElement;
}

function decide(fig, id, d) {
  st(id).decision = d; save(); paint(fig, id);
}

for (const r of D.rows) {
  const fig = document.createElement("figure");
  fig.tabIndex = 0; fig.dataset.id = r.image_id;
  const conds = COND.map(c => `<select data-c="${c}" title="${c}"><option value="">${c.replace("cond_", "")}</option>` +
    D.conditions[c].map(o => `<option>${esc(o)}</option>`).join("") + "</select>").join("");
  fig.innerHTML =
    `<a href="${esc(r._img)}" target="_blank"><img loading="lazy" src="${esc(r._img)}"></a>` +
    `<div class="dec"><button data-d="approved">Approve (A)</button><button data-d="rejected">Reject (R)</button>` +
    `<button data-d="uncertain">Unsure (U)</button></div>` +
    `<input class="notes" placeholder="notes (optional)">` +
    `<div class="cond">${conds}</div>` +
    `<figcaption><b>${esc(r.image_id)}</b> ${r.quality_flags ? `<span class="flag">${esc(r.quality_flags)}</span>` : ""}<br>` +
    `<a href="${esc(r.gbif_url)}" target="_blank">GBIF record</a> &middot; <a href="${esc(r.media_reference_url)}" target="_blank">source</a><br>` +
    `<small>${esc(r.attribution)}</small></figcaption>`;
  const s = state[r.image_id] || {};
  const notes = fig.querySelector(".notes");
  notes.value = s.review_notes ?? r.review_notes ?? "";
  notes.oninput = () => { st(r.image_id).review_notes = notes.value; save(); };
  fig.querySelectorAll("select").forEach(sel => {
    sel.value = s[sel.dataset.c] ?? r[sel.dataset.c] ?? "";
    sel.onchange = () => { st(r.image_id)[sel.dataset.c] = sel.value; save(); };
  });
  fig.querySelectorAll(".dec button").forEach(b => b.onclick = () => decide(fig, r.image_id, b.dataset.d));
  grid.appendChild(fig);
  paint(fig, r.image_id);
}

document.addEventListener("keydown", e => {
  const fig = document.activeElement;
  if (!fig || fig.tagName !== "FIGURE" || e.ctrlKey || e.metaKey || e.altKey) return;
  const d = {a: "approved", r: "rejected", u: "uncertain", c: ""}[e.key.toLowerCase()];
  if (d === undefined) return;
  e.preventDefault();
  decide(fig, fig.dataset.id, d);
  let next = fig.nextElementSibling;
  while (next && next.hidden) next = next.nextElementSibling;
  if (next) { next.focus(); next.scrollIntoView({block: "nearest", behavior: "smooth"}); }
  if (d) paint(fig, fig.dataset.id);
});

document.getElementById("undecided").onchange = () =>
  grid.querySelectorAll("figure").forEach(f => paint(f, f.dataset.id));

document.getElementById("reset").onclick = () => {
  if (!confirm("Clear every decision, note and tag on this page?")) return;
  for (const k of Object.keys(state)) delete state[k];
  save(); location.reload();
};

document.getElementById("download").onclick = () => {
  const cell = v => { v = String(v ?? ""); return /[",\\n\\r]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; };
  const lines = [D.columns.join(",")];
  for (const r of D.rows) {
    const s = state[r.image_id] || {};
    lines.push(D.columns.map(c => cell(c in s ? s[c] : r[c])).join(","));
  }
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([lines.join("\\n") + "\\n"], {type: "text/csv"}));
  a.download = D.csv_name;
  a.click();
};

progress();
</script></body></html>
"""


def import_review_sheet(cfg: dict, sheet_path: str | Path, reviewer: str, review_date: str | None = None) -> dict:
    reviewer = reviewer.strip()
    if not reviewer:
        raise ValueError("a reviewer name is required to import review decisions")
    review_date = review_date or date.today().isoformat()
    root = project_root(cfg)
    catalog = by_id(load_catalog(project_path(cfg, "species_catalog")))
    manifest_path = project_path(cfg, "image_manifest")
    df = load_manifest(manifest_path)
    sheet = pd.read_csv(sheet_path, dtype=str, keep_default_na=False)
    for col in ("image_id", "decision"):
        if col not in sheet.columns:
            raise ValueError(f"review sheet missing column '{col}'")

    index = {iid: i for i, iid in enumerate(df["image_id"])}
    counts = {"approved": 0, "rejected": 0, "uncertain": 0, "skipped_blank": 0}
    errors: list[str] = []
    applied: list[tuple[int, str]] = []
    for _, r in sheet.iterrows():
        decision = clean_str(r["decision"]).lower()
        if not decision:
            counts["skipped_blank"] += 1
            continue
        if decision not in DECISIONS:
            errors.append(f"{r['image_id']}: invalid decision '{decision}'")
            continue
        i = index.get(r["image_id"])
        if i is None:
            errors.append(f"{r['image_id']}: not in manifest")
            continue
        if "species_id" in sheet.columns and r["species_id"] and r["species_id"] != df.at[i, "species_id"]:
            errors.append(f"{r['image_id']}: sheet species_id differs from manifest; relabelling is not supported here")
            continue
        df.at[i, "review_status"] = decision
        df.at[i, "reviewer"] = reviewer
        df.at[i, "review_date"] = review_date
        df.at[i, "review_notes"] = clean_str(r.get("review_notes", ""))
        for c in CONDITION_COLUMNS:
            if c in sheet.columns:
                df.at[i, c] = clean_str(r[c])
        applied.append((i, decision))
        counts[decision] += 1
    if errors:
        raise ValueError("review sheet has errors (nothing was saved):\n  " + "\n  ".join(errors[:50]))
    for i, decision in applied:
        _sync_reviewed_copy(df.loc[i], decision, catalog, cfg, root)
    save_manifest(df, manifest_path)
    log = {"imported": utc_stamp(), "sheet": str(sheet_path), "reviewer": reviewer, "review_date": review_date, **counts}
    write_json(project_path(cfg, "reports") / "review_logs" / f"review_{utc_stamp()}.json", log)
    return log


def _sync_reviewed_copy(row: pd.Series, decision: str, catalog: dict, cfg: dict, root: Path) -> None:
    """Approved images get a copy in dataset/reviewed/<species>/; others are removed from there."""
    sp = catalog.get(row["species_id"])
    if sp is None or not row["local_path"]:
        return
    src = resolve_path(row["local_path"], root)
    dst = project_path(cfg, "reviewed") / sp.folder / src.name
    if decision == "approved":
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.exists() and not dst.exists():
            shutil.copy2(src, dst)
    elif dst.exists():
        dst.unlink()


def reviewed_path(cfg: dict, row: pd.Series, catalog: dict) -> Path:
    sp = catalog[row["species_id"]]
    return project_path(cfg, "reviewed") / sp.folder / Path(row["local_path"]).name
