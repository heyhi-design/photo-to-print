"""review_sheet: one image the maker reviews at every gate. Each row is one face:
photo | model (lit from upper left) | relief map, all at the same mm scale.

    python3 review_sheet.py --views renders/v1/views.json --spec checks.json \
        --report reports/check_v1.json --out renders/review_v1.jpg --title "Part v1"

Rows come from spec["sheet"] (photo, photo_ppmm, photo_center_px, optional
photo_rotate degrees, label). Views without a sheet row get model columns only.
The relief map is the polarity check: warm = stands up, cool = cut in, black =
no material. Ask the maker to check every warm/cool patch against the real part.
"""

import argparse
import json
import os

from PIL import Image, ImageDraw

from photo_tools import font

BG = (43, 45, 49)
FG = (232, 232, 235)
DIM = (160, 162, 168)
ACCENT = (226, 84, 70)
OK = (98, 190, 120)


def photo_tile(row, view, project):
    path = row["photo"] if os.path.isabs(row["photo"]) else os.path.join(project, row["photo"])
    im = Image.open(path).convert("RGB")
    if row.get("photo_rotate"):
        im = im.rotate(row["photo_rotate"], expand=True, resample=Image.BICUBIC)
    fw, fh = view["frame_mm"]
    s = row["photo_ppmm"]
    cx, cy = row["photo_center_px"]
    box = (round(cx - fw * s / 2), round(cy - fh * s / 2), round(cx + fw * s / 2), round(cy + fh * s / 2))
    return im.crop(box).resize(tuple(view["px"]), Image.LANCZOS)


def legend(d, x, y):
    items = [((238, 107, 26), "stands up toward you"), ((204, 204, 199), "main face"),
             ((41, 115, 224), "cut in / sunk"), ((8, 8, 9), "no material (see-through)")]
    for col, text in items:
        d.rectangle([x, y, x + 22, y + 22], fill=col, outline=DIM)
        d.text((x + 32, y + 1), text, font=font(18), fill=FG)
        x += 60 + int(d.textlength(text, font=font(18)))


def main():
    ap = argparse.ArgumentParser(prog="review_sheet")
    ap.add_argument("--views", required=True)
    ap.add_argument("--spec", default=None)
    ap.add_argument("--report", default=None, help="print_check JSON, summarised at the bottom")
    ap.add_argument("--out", required=True)
    ap.add_argument("--title", default="Model vs reference")
    ap.add_argument("--project", default=".")
    a = ap.parse_args()
    meta = json.load(open(a.views))
    spec = json.load(open(a.spec)) if a.spec else {}
    rows = {r["view"]: r for r in spec.get("sheet", [])}
    pad, gap = 28, 12
    tiles = []
    for v in meta["views"]:
        cols = []
        if v["name"] in rows:
            cols.append(("photo", photo_tile(rows[v["name"]], v, a.project)))
        cols.append(("model, lit from upper left", Image.open(v["shaded"]).convert("RGB")))
        cols.append(("relief map", Image.open(v["relief"]).convert("RGB")))
        label = rows.get(v["name"], {}).get("label", v["name"])
        tiles.append((label, v, cols))
    row_w = max(sum(c[1].width for c in cols) + gap * (len(cols) - 1) for _, _, cols in tiles)
    width = max(row_w + 2 * pad, 1100)
    heights = [max(c[1].height for c in cols) + 90 for _, _, cols in tiles]
    report = json.load(open(a.report)) if a.report else None
    foot = 120 + (24 * (len(report["summary"]["fails"]) + min(len(report["summary"]["warns"]), 4)) if report else 0)
    sheet = Image.new("RGB", (width, 150 + sum(heights) + foot), BG)
    d = ImageDraw.Draw(sheet)
    d.text((pad, 22), a.title, font=font(32, True), fill=FG)
    ppmm = meta["views"][0]["ppmm"]
    d.text((pad, 64), f"Every image at {ppmm:g} px = 1 mm. Photo, model and relief map show the same face, "
           "same way up.", font=font(18), fill=DIM)
    legend(d, pad, 98)
    y = 150
    for (label, v, cols), h in zip(tiles, heights):
        d.text((pad, y), label, font=font(22, True), fill=FG)
        lv = ", ".join(f"{x['relative_mm']:+.2f} mm ({x['share_pct']:.0f}%)" for x in v["levels"][:4])
        d.text((pad, y + 30), f"surface levels vs main face: {lv}", font=font(16), fill=DIM)
        x = pad
        for name, im in cols:
            sheet.paste(im, (x, y + 58))
            d.text((x, y + 58 + im.height + 4), name, font=font(15), fill=DIM)
            x += im.width + gap
        y += h
    d.line([(pad, y), (pad + 5 * ppmm, y)], fill=ACCENT, width=4)
    d.text((pad + 5 * ppmm + 10, y - 11), "5 mm", font=font(18, True), fill=FG)
    if report:
        s = report["summary"]
        y += 30
        d.text((pad, y), "print_check: " + ("PASS" if s["pass"] else f"FAIL ({len(s['fails'])})"),
               font=font(22, True), fill=OK if s["pass"] else ACCENT)
        y += 34
        for m in s["fails"]:
            d.text((pad, y), "FAIL " + m[:150], font=font(16), fill=ACCENT)
            y += 24
        for m in s["warns"][:4]:
            d.text((pad, y), "warn " + m[:150], font=font(16), fill=DIM)
            y += 24
    sheet = sheet.crop((0, 0, width, y + pad))
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    sheet.save(a.out, quality=90)
    print(f"wrote {a.out}: {sheet.width} x {sheet.height}")


if __name__ == "__main__":
    main()
