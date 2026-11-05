"""Numbered contact sheets of pending photos, for the AI-assisted pre-screen (the reviewer still decides).

  python scripts/contact_sheets.py --species GF-SP-0001 GF-SP-0101 --out reports/review_sheets/contact_20261106
Writes sheet_XX.jpg (8 x 6 thumbnails, numbered) and index.csv (number -> image_id).
"""
import csv
from pathlib import Path

from _common import parser, setup


def main():
    p = parser(__doc__)
    p.add_argument("--species", nargs="+", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--cols", type=int, default=8)
    p.add_argument("--rows", type=int, default=6)
    p.add_argument("--thumb", type=int, default=170)
    args = p.parse_args()
    cfg = setup(args)
    from PIL import Image, ImageDraw, ImageFont, ImageOps
    from geoflora_ml.config import project_path, project_root
    from geoflora_ml.manifest import load_manifest

    root = project_root(cfg)
    m = load_manifest(project_path(cfg, "image_manifest"))
    rows = m[m.species_id.isin(args.species) & (m.review_status == "pending") & (m.quality_pass == "true") & (m.exact_duplicate_of == "")]
    rows = rows.sort_values(["species_id", "image_id"])
    out = root / args.out
    out.mkdir(parents=True, exist_ok=True)
    per = args.cols * args.rows
    t = args.thumb
    try:
        font = ImageFont.truetype("arial.ttf", 18)
    except OSError:
        font = ImageFont.load_default()
    index = []
    records = rows.to_dict("records")
    for s in range(0, len(records), per):
        sheet = Image.new("RGB", (args.cols * t, args.rows * t), "white")
        draw = ImageDraw.Draw(sheet)
        for k, rec in enumerate(records[s:s + per]):
            n = s + k + 1
            with Image.open(root / rec["local_path"]) as im:
                im = ImageOps.exif_transpose(im).convert("RGB")
                im.thumbnail((t - 4, t - 4))
            x, y = (k % args.cols) * t, (k // args.cols) * t
            sheet.paste(im, (x + (t - im.width) // 2, y + (t - im.height) // 2))
            draw.rectangle([x, y, x + 44, y + 22], fill="black")
            draw.text((x + 3, y + 1), str(n), fill="yellow", font=font)
            index.append({"n": n, "sheet": f"sheet_{s // per + 1:02d}.jpg", "image_id": rec["image_id"], "species_id": rec["species_id"], "scientific_name": rec["scientific_name"], "local_path": rec["local_path"], "attribution": rec["attribution"]})
        sheet.save(out / f"sheet_{s // per + 1:02d}.jpg", quality=88)
    with open(out / "index.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(index[0].keys()))
        w.writeheader(); w.writerows(index)
    print(f"{len(index)} photos on {(len(index) + per - 1) // per} sheets in {out}")


if __name__ == "__main__":
    main()
