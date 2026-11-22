"""photo_tools: read reference photos for measurement and for questions.

Runs with the system python3 + Pillow + numpy (no Blender needed).

    python3 photo_tools.py info  reference/*.jpg
        Size, EXIF, and a warning when a photo looks like a downscaled copy.
    python3 photo_tools.py ruler reference/photo-1.jpg --box 770 1250 850 1500 --axis y
        Pixels per mm from the ruler ticks inside a box (tick-spacing FFT).
    python3 photo_tools.py grid  reference/photo-1.jpg --box 600 850 830 1110 --ppmm 16.5 --zoom 3 --out q/grid.png
        Crop + zoom with a 1 mm grid (0.5 mm minor) for reading sizes off the photo.
    python3 photo_tools.py annotate reference/photo-2.jpg --out questions/q03.png \
        --mark 410,600,1 --mark 470,520,2 [--box 300 280 620 940] [--zoom 2] [--title "..."]
        Numbered rings on the features a question is about. Every question the maker gets
        comes with one of these, so "feature 2" means the same thing to both of you.
"""

import argparse
import glob
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ExifTags

RING = (226, 84, 70)
INK = (255, 255, 255)
GRID_MAJOR = (90, 200, 255)
GRID_MINOR = (90, 200, 255, 90)


def font(size, bold=False):
    paths = (["/System/Library/Fonts/Supplemental/Arial Bold.ttf"] if bold else
             ["/System/Library/Fonts/Supplemental/Arial.ttf"]) + [
        "/System/Library/Fonts/Helvetica.ttc", "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


# ------------------------------------------------------------------ info ----

def cmd_info(a):
    files = []
    for pat in a.photos:
        files += sorted(glob.glob(pat)) or [pat]
    worst = []
    for f in files:
        im = Image.open(f)
        ex = im.getexif()
        tags = {ExifTags.TAGS.get(k, k): v for k, v in ex.items()} if ex else {}
        long_side = max(im.size)
        flags = []
        if long_side < 3000:
            flags.append(f"only {long_side} px on the long side (phone originals are usually 4000+)")
        if not tags.get("Make") and not tags.get("Model"):
            flags.append("no camera EXIF (stripped: a screenshot, a messaging-app copy, or an export)")
        print(f"{f}: {im.size[0]} x {im.size[1]}, {im.mode}, camera: {tags.get('Model') or '-'}")
        for fl in flags:
            print(f"    ! {fl}")
        if flags:
            worst.append(f)
    if worst:
        print("\nASK FOR ORIGINALS: these look like reduced copies. Fine detail (small text, edges, "
              "anything under ~0.5 mm) blurs at this size. Ask for the full-resolution originals: "
              "AirDrop, or share/email with 'Actual Size', or copy straight off the phone. Not a "
              "screenshot and not through a messaging app.")
    return 0


# ----------------------------------------------------------------- ruler ----

def tick_period(profile, pmin, pmax, pad=16):
    """Dominant spacing (px) of a 1-D tick pattern, and its signal-to-noise."""
    p = profile - np.convolve(profile, np.ones(31) / 31, mode="same")
    p = p[15:-15] if len(p) > 60 else p
    p = p * np.hanning(len(p))
    n = len(p) * pad
    spec = np.abs(np.fft.rfft(p, n))
    freqs = np.fft.rfftfreq(n)
    with np.errstate(divide="ignore"):
        periods = np.where(freqs > 0, 1.0 / np.maximum(freqs, 1e-12), np.inf)
    band = (periods >= pmin) & (periods <= pmax)
    if not band.any():
        return None, 0.0
    idx = np.argmax(np.where(band, spec, 0))
    snr = spec[idx] / (np.median(spec[band]) + 1e-9)
    return float(periods[idx]), float(snr)


def cmd_ruler(a):
    if a.scan and a.scan > 1:
        x0, y0, x1, y1 = a.box
        print(f"{a.photo}: scale along the ruler ({a.scan} segments; a drift means perspective)")
        for k in range(a.scan):
            if a.axis == "y":
                seg = (x0, y0 + (y1 - y0) * k // a.scan, x1, y0 + (y1 - y0) * (k + 1) // a.scan)
            else:
                seg = (x0 + (x1 - x0) * k // a.scan, y0, x0 + (x1 - x0) * (k + 1) // a.scan, y1)
            r = ruler_scale(a, seg)
            print(f"  box {seg}: " + (f"{r[0]:.2f} px/mm (SNR {r[1]:.0f})" if r else "no pattern"))
        return 0
    return ruler_report(a)


def ruler_scale(a, box):
    im = np.asarray(Image.open(a.photo).convert("L"), dtype=float)
    x0, y0, x1, y1 = box
    crop = im[y0:y1, x0:x1]
    profiles = ([s.mean(axis=0) for s in np.array_split(crop, a.strips, axis=0)] if a.axis == "x"
                else [s.mean(axis=1) for s in np.array_split(crop, a.strips, axis=1)])
    rows = sorted(((snr, per) for per, snr in (tick_period(pr, a.min_px, a.max_px) for pr in profiles) if per),
                  reverse=True)
    return (rows[0][1] / a.tick_mm, rows[0][0]) if rows else None


def ruler_report(a):
    im = np.asarray(Image.open(a.photo).convert("L"), dtype=float)
    x0, y0, x1, y1 = a.box
    crop = im[y0:y1, x0:x1]
    if a.axis == "x":                       # ticks repeat left-right: strips are rows
        strips = np.array_split(crop, a.strips, axis=0)
        profiles = [s.mean(axis=0) for s in strips]
    else:                                   # ticks repeat top-bottom: strips are columns
        strips = np.array_split(crop, a.strips, axis=1)
        profiles = [s.mean(axis=1) for s in strips]
    rows = []
    for i, prof in enumerate(profiles):
        per, snr = tick_period(prof, a.min_px, a.max_px)
        if per:
            rows.append((snr, per, i))
    if not rows:
        print("no tick pattern found: widen the box, or set --min-px/--max-px")
        return 1
    rows.sort(reverse=True)
    best_snr, best_per, _ = rows[0]
    good = [per for snr, per, _ in rows if snr >= max(5.0, best_snr * 0.5)]
    ppmm = best_per / a.tick_mm
    spread = (max(good) - min(good)) / a.tick_mm if len(good) > 1 else 0.0
    print(f"{a.photo}: {ppmm:.2f} px/mm  (tick {best_per:.2f} px, SNR {best_snr:.0f}, "
          f"{len(good)} strips agree within {spread:.2f} px/mm)")
    if best_snr < 8:
        print("  ! weak pattern (SNR < 8): check the box covers the fine ticks only, not the numbers")
    print("  This is the scale AT THE RULER. A face sitting above the ruler reads larger: "
          "correct by about (height above ruler) / (camera distance), typically 4-8 % for a phone at "
          "10-20 cm. Prefer photos with the ruler at the same height as the face being measured.")
    return 0


# ------------------------------------------------------------------ grid ----

def crop_zoom(im, box, zoom):
    if box:
        im = im.crop(tuple(box))
    if zoom and zoom != 1:
        im = im.resize((round(im.width * zoom), round(im.height * zoom)), Image.LANCZOS)
    return im


def cmd_grid(a):
    im = crop_zoom(Image.open(a.photo).convert("RGB"), a.box, a.zoom).convert("RGBA")
    over = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    step = a.ppmm * a.zoom                 # px per mm in the zoomed crop
    f = font(max(11, int(step * 0.35)))
    k = 0
    x = 0.0
    while x < im.width:
        major = k % 2 == 0
        d.line([(x, 0), (x, im.height)], fill=GRID_MAJOR + (200,) if major else GRID_MINOR, width=1)
        if major:
            d.text((x + 2, 2), f"{k // 2}", font=f, fill=GRID_MAJOR + (255,))
        x += step / 2
        k += 1
    k = 0
    y = 0.0
    while y < im.height:
        major = k % 2 == 0
        d.line([(0, y), (im.width, y)], fill=GRID_MAJOR + (200,) if major else GRID_MINOR, width=1)
        if major and k:
            d.text((2, y + 2), f"{k // 2}", font=f, fill=GRID_MAJOR + (255,))
        y += step / 2
        k += 1
    out = Image.alpha_composite(im, over).convert("RGB")
    out.save(a.out)
    print(f"wrote {a.out}: {out.width} x {out.height}, 1 mm = {step:.1f} px (grid origin = crop top-left)")
    if a.zoom > 2 and min(Image.open(a.photo).size) < 2000:
        print("  ! zoomed past 2x on a reduced photo: edges are interpolated, not real detail")
    return 0


# -------------------------------------------------------------- annotate ----

def cmd_annotate(a):
    src = Image.open(a.photo).convert("RGB")
    ox, oy = (a.box[0], a.box[1]) if a.box else (0, 0)
    im = crop_zoom(src, a.box, a.zoom)
    z = a.zoom or 1.0
    head = 56 if a.title else 0
    canvas = Image.new("RGB", (im.width, im.height + head), (30, 31, 34))
    canvas.paste(im, (0, head))
    d = ImageDraw.Draw(canvas)
    if a.title:
        d.text((14, 14), a.title, font=font(24, True), fill=INK)
    for m in a.mark:
        parts = m.split(",")
        x, y, label = float(parts[0]), float(parts[1]), parts[2]
        r = float(parts[3]) if len(parts) > 3 else 28.0
        cx, cy = (x - ox) * z, (y - oy) * z + head
        for w, col in ((7, (0, 0, 0)), (4, RING)):
            d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=col, width=w)
        tx, ty = cx + r * 0.75, cy - r * 1.6
        bw = 22 + 14 * len(label)
        d.rounded_rectangle([tx, ty, tx + bw, ty + 34], radius=8, fill=RING)
        d.text((tx + 10, ty + 3), label, font=font(24, True), fill=INK)
    canvas.save(a.out, quality=92)
    print(f"wrote {a.out}: {canvas.width} x {canvas.height}, {len(a.mark)} marks")
    return 0


def main():
    ap = argparse.ArgumentParser(prog="photo_tools")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("info")
    p.add_argument("photos", nargs="+")
    p = sub.add_parser("ruler")
    p.add_argument("photo")
    p.add_argument("--box", nargs=4, type=int, required=True, metavar=("X0", "Y0", "X1", "Y1"))
    p.add_argument("--axis", choices=["x", "y"], required=True, help="direction the ticks repeat along")
    p.add_argument("--tick-mm", type=float, default=1.0)
    p.add_argument("--strips", type=int, default=8)
    p.add_argument("--min-px", type=float, default=5.0)
    p.add_argument("--max-px", type=float, default=80.0)
    p.add_argument("--scan", type=int, default=0, help="split the box into N segments along the ticks")
    p = sub.add_parser("grid")
    p.add_argument("photo")
    p.add_argument("--box", nargs=4, type=int)
    p.add_argument("--ppmm", type=float, required=True)
    p.add_argument("--zoom", type=float, default=2.0)
    p.add_argument("--out", required=True)
    p = sub.add_parser("annotate")
    p.add_argument("photo")
    p.add_argument("--out", required=True)
    p.add_argument("--mark", action="append", default=[], help="x,y,label[,radius] in photo pixels")
    p.add_argument("--box", nargs=4, type=int)
    p.add_argument("--zoom", type=float, default=1.0)
    p.add_argument("--title", default="")
    a = ap.parse_args()
    return {"info": cmd_info, "ruler": cmd_ruler, "grid": cmd_grid, "annotate": cmd_annotate}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
