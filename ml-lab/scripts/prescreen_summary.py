"""Turn contact-sheet flags into (1) a proposals CSV in review-sheet format and (2) an HTML summary for the reviewer.

  python scripts/prescreen_summary.py --dir reports/review_sheets/contact_20261106 --stamp 20261106
The flags file (<dir>/flags.py) maps reasons to contact-sheet numbers. Nothing is imported here: after the reviewer
OKs the list, run  python scripts/review_images.py import <dir>/proposals_<stamp>.csv --reviewer "Full Name"
"""
import csv
import html
import importlib.util
from collections import Counter
from pathlib import Path

from _common import parser, setup


def main():
    p = parser(__doc__)
    p.add_argument("--dir", required=True)
    p.add_argument("--stamp", required=True)
    args = p.parse_args()
    cfg = setup(args)
    from geoflora_ml.config import project_root

    root = project_root(cfg)
    folder = root / args.dir
    spec = importlib.util.spec_from_file_location("flags", folder / "flags.py")
    flags = importlib.util.module_from_spec(spec); spec.loader.exec_module(flags)
    reason_of = {}
    for reason, numbers in flags.FLAGS.items():
        for n in numbers:
            reason_of.setdefault(n, reason)
    index = list(csv.DictReader(open(folder / "index.csv", encoding="utf-8")))
    rows, counts = [], Counter()
    for item in index:
        n = int(item["n"])
        flagged = n in reason_of
        decision = "uncertain" if flagged else "approved"
        counts[(item["scientific_name"], decision)] += 1
        rows.append({"image_id": item["image_id"], "species_id": item["species_id"], "decision": decision,
                     "review_notes": f"flagged in AI-assisted pre-screen: {reason_of[n]}" if flagged else "",
                     "n": n, "scientific_name": item["scientific_name"], "local_path": item["local_path"], "reason": reason_of.get(n, "")})
    proposals = folder / f"proposals_{args.stamp}.csv"
    with open(proposals, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["image_id", "species_id", "decision", "review_notes"])
        w.writeheader(); w.writerows({k: r[k] for k in ("image_id", "species_id", "decision", "review_notes")} for r in rows)

    species = sorted({r["scientific_name"] for r in rows})
    parts = [f"""<!doctype html><meta charset="utf-8"><title>GeoFlora pre-screen {args.stamp}</title>
<style>body{{font-family:system-ui,Segoe UI,Arial;margin:24px;color:#1d2b22;max-width:1200px}}h1{{margin:0 0 4px}}.muted{{color:#5f6b62}}
table{{border-collapse:collapse;margin:12px 0}}td,th{{border:1px solid #dbe2d6;padding:6px 10px;text-align:left}}
.grid{{display:flex;flex-wrap:wrap;gap:8px}}figure{{margin:0;width:150px;font-size:11px}}figure img{{width:150px;height:150px;object-fit:cover;border-radius:8px;border:3px solid #e7a641}}
h3{{margin:22px 0 6px}}.sheets a{{margin-right:10px}}</style>
<h1>Pre-screen: new Hagonoy and Ageratum photos</h1>
<p class="muted">{len(rows)} new photos from GBIF/iNaturalist (research-grade, licensed). Claude looked at every photo and flagged the questionable ones.
<b>Flagged photos are proposed as "uncertain"</b> (not used for training). All others are proposed as <b>approved</b>. Nothing is saved until you OK it.</p>
<table><tr><th>Species</th><th>Proposed approved</th><th>Flagged (uncertain)</th></tr>"""]
    for s in species:
        parts.append(f"<tr><td><i>{html.escape(s)}</i></td><td>{counts[(s, 'approved')]}</td><td>{counts[(s, 'uncertain')]}</td></tr>")
    parts.append("</table><p class='sheets'>All photos, numbered: " + " ".join(f"<a href='{f.name}'>{f.stem}</a>" for f in sorted(folder.glob("sheet_*.jpg"))) + "</p>")
    for s in species:
        parts.append(f"<h2><i>{html.escape(s)}</i>: flagged photos</h2>")
        for reason in flags.FLAGS:
            group = [r for r in rows if r["scientific_name"] == s and r["reason"] == reason]
            if not group:
                continue
            parts.append(f"<h3>{html.escape(reason)} ({len(group)})</h3><div class='grid'>")
            for r in group:
                src = Path("../../..") / r["local_path"]
                parts.append(f"<figure><img loading='lazy' src='{html.escape(src.as_posix())}'><figcaption>#{r['n']} · {html.escape(r['image_id'])}</figcaption></figure>")
            parts.append("</div>")
    out = folder / f"prescreen_summary_{args.stamp}.html"
    out.write_text("\n".join(parts), encoding="utf-8")
    print(f"{proposals}\n{out}\n" + "\n".join(f"{s}: approved {counts[(s, 'approved')]}, uncertain {counts[(s, 'uncertain')]}" for s in species))


if __name__ == "__main__":
    main()
