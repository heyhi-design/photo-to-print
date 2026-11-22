"""review_sheet: one image the maker reviews at every gate. Each row is one face:
photo | model (lit from upper left) | relief map, all at that row's mm scale.

    python3 review_sheet.py --views renders/v1/views.json --spec checks.json \
        --report reports/check_v1.json --out renders/review_v1.jpg --title "Part v1"

Rows come from spec["sheet"]: {"view", "photo", "photo_ppmm", "photo_center_px",
optional "photo_rotate" (0/90/180/270, counter-clockwise), "label"}.
photo_center_px is in the photo as you see it (EXIF-upright), before any
photo_rotate: the sheet rotates the point with the photo. Views without a sheet
row get model columns only. The relief map is the polarity check: warm = stands
up, cool = cut in, black = no material. Ask the maker to check every warm/cool
patch against the real part.
"""

import argparse
import json
import os
import sys

from PIL import Image, ImageDraw

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from photo_tools import PhotoError, font, open_photo  # noqa: E402
import spec as specmod  # noqa: E402

BG = (43, 45, 49)
FG = (232, 232, 235)
DIM = (160, 162, 168)
ACCENT = (226, 84, 70)
OK = (98, 190, 120)
ROTATE = {0: None, 90: Image.Transpose.ROTATE_90, 180: Image.Transpose.ROTATE_180, 270: Image.Transpose.ROTATE_270}


def rotate_point(x, y, w, h, deg):
    """Where pixel (x, y) of a w x h image lands after a counter-clockwise rotation."""
    if deg == 90:
        return y, w - x
    if deg == 180:
        return w - x, h - y
    if deg == 270:
        return h - y, x
    return x, y


def photo_tile(row, view, project):
    path = row["photo"] if os.path.isabs(row["photo"]) else os.path.join(project, row["photo"])
    im, _ = open_photo(path)
    im = im.convert("RGB")
    cx, cy = row["photo_center_px"]
    deg = row.get("photo_rotate", 0)
    if ROTATE[deg] is not None:
        cx, cy = rotate_point(cx, cy, im.width, im.height, deg)
        im = im.transpose(ROTATE[deg])
    fw, fh = view["frame_mm"]
    s = row["photo_ppmm"]
    box = (round(cx - fw * s / 2), round(cy - fh * s / 2), round(cx + fw * s / 2), round(cy + fh * s / 2))
    return im.crop(box).resize(tuple(view["px"]), Image.LANCZOS)


def legend(d, x, y):
    items = [((238, 107, 26), "stands up toward you"), ((204, 204, 199), "main face"),
             ((41, 115, 224), "cut in / farther away"), ((8, 8, 9), "no material")]
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
    with open(a.views) as f:
        meta = json.load(f)
    spec = {}
    if a.spec:
        with open(a.spec) as f:
            spec = json.load(f)
    names = [v["name"] for v in meta["views"]]
    errors = specmod.validate_sheet(spec.get("sheet"), names)
    if errors:
        sys.exit("review_sheet: " + "; ".join(errors))
    rows = {r["view"]: r for r in spec.get("sheet") or []}
    pad, gap = 28, 12
    tiles = []
    for v in meta["views"]:
        cols = []
        if v["name"] in rows:
            try:
                cols.append(("photo", photo_tile(rows[v["name"]], v, a.project)))
            except PhotoError as ex:
                sys.exit(f"review_sheet: {ex}")
        cols.append(("model, lit from upper left", Image.open(v["shaded"]).convert("RGB")))
        cols.append(("relief map", Image.open(v["relief"]).convert("RGB")))
        tiles.append((rows.get(v["name"], {}).get("label", v["name"]), v, cols))
    row_w = max(sum(c[1].width for c in cols) + gap * (len(cols) - 1) for _, _, cols in tiles)
    width = max(row_w + 2 * pad, 1100)
    heights = [max(c[1].height for c in cols) + 120 for _, _, cols in tiles]
    report = None
    if a.report:
        with open(a.report) as f:
            report = json.load(f)
    foot = 120 + (24 * (len(report["summary"]["fails"]) + min(len(report["summary"]["warns"]), 4)) if report else 0)
    sheet = Image.new("RGB", (width, 150 + sum(heights) + foot), BG)
    d = ImageDraw.Draw(sheet)
    d.text((pad, 22), a.title, font=font(32, True), fill=FG)
    d.text((pad, 64), "In each row, photo, model and relief map show the same face, the same way up, at the same "
           "scale.", font=font(18), fill=DIM)
    legend(d, pad, 98)
    y = 150
    for (label, v, cols), h in zip(tiles, heights):
        ppmm = v["ppmm"]
        d.text((pad, y), f"{label}  ({ppmm:g} px = 1 mm)", font=font(22, True), fill=FG)
        lv = ", ".join(f"{x['relative_mm']:+.2f} mm ({x['share_pct']:.0f}%)" for x in v["levels"][:4])
        d.text((pad, y + 30), f"main face at {v.get('world_axis', '')} {v.get('base_world_coord_mm', '')}; "
               f"levels vs main face: {lv}", font=font(16), fill=DIM)
        x = pad
        for name, im in cols:
            sheet.paste(im, (x, y + 58))
            d.text((x, y + 58 + im.height + 4), name, font=font(15), fill=DIM)
            x += im.width + gap
        by = y + 58 + max(c[1].height for c in cols) + 34
        d.line([(pad, by), (pad + 5 * ppmm, by)], fill=ACCENT, width=4)
        d.text((pad + 5 * ppmm + 10, by - 11), "5 mm", font=font(16, True), fill=FG)
        y += h
    if report:
        s = report["summary"]
        y += 10
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
