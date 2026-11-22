"""photo_tools: read reference photos for measurement and for questions.

Runs with the system python3 + Pillow + numpy (no Blender needed). Photos are
turned upright from their EXIF orientation first, so every pixel coordinate
below is in the photo as you see it. HEIC needs `pip install pillow-heif`.

    python3 photo_tools.py info  reference/*.jpg
        Size, orientation, camera, and a warning when a photo looks like a downscaled copy.
    python3 photo_tools.py ruler reference/photo-1.jpg --box 770 1250 850 1500 --axis y [--scan 4]
        Pixels per mm from the ruler ticks inside a box (--axis: the direction the ticks repeat along).
    python3 photo_tools.py grid  reference/photo-1.jpg --box 600 850 830 1110 --ppmm 16.5 --zoom 3 --out q/grid.png
        Crop + zoom with a 1 mm grid (0.5 mm minor) for reading sizes off the photo.
    python3 photo_tools.py annotate reference/photo-2.jpg --out questions/q03.png \
        --mark 410,600,1 --mark 470,520,2 [--box 300 280 620 940] [--zoom 2] [--title "..."] [--radius 40]
        Numbered rings on the features a question is about. Every question the maker gets
        comes with one of these, so "feature 2" means the same thing to both of you.
        A mark is x,y,label[,radius] in photo pixels; a label may contain commas.
"""

import argparse
import glob
import sys

import numpy as np
from PIL import ExifTags, Image, ImageDraw, ImageFont, ImageOps

try:                                  # optional: read iPhone HEIC photos directly
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pillow_heif = None

RING = (226, 84, 70)
INK = (255, 255, 255)
GRID_MAJOR = (90, 200, 255)
GRID_MINOR = (90, 200, 255, 90)
PERSPECTIVE_NOTE = ("This is the scale AT THE RULER. A face sitting above the ruler reads larger by about "
                    "(its height above the ruler) / (camera distance): 10 mm at 15 cm is about 7%. Measure faces "
                    "with the ruler at their own height (references/photo-guide.md).")
FONT_PATHS = {
    True: ["/System/Library/Fonts/Supplemental/Arial Bold.ttf", "C:/Windows/Fonts/arialbd.ttf",
           "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
           "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"],
    False: ["/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Helvetica.ttc",
            "C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/dejavu/DejaVuSans.ttf", "/usr/share/fonts/TTF/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"],
}


class PhotoError(Exception):
    pass


def font(size, bold=False):
    for p in FONT_PATHS[bold] + FONT_PATHS[not bold]:
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)        # Pillow 10.1+: a scalable default
    except TypeError:
        return ImageFont.load_default()


def open_photo(path):
    """Open a photo upright (EXIF orientation applied). Raises PhotoError with advice."""
    try:
        im = Image.open(path)
        im.load()
    except FileNotFoundError:
        raise PhotoError(f"{path}: file not found")
    except Exception as ex:                             # noqa: BLE001
        if str(path).lower().endswith((".heic", ".heif")) and pillow_heif is None:
            raise PhotoError(f"{path}: HEIC can't be read without pillow-heif. Install it "
                             f"(python3 -m pip install --user pillow-heif), or convert on a Mac: "
                             f"sips -s format jpeg \"{path}\" --out photo.jpg")
        raise PhotoError(f"{path}: not a readable image ({ex.__class__.__name__})")
    orientation = im.getexif().get(0x0112, 1) if hasattr(im, "getexif") else 1
    return ImageOps.exif_transpose(im), orientation


# ------------------------------------------------------------------ info ----

def cmd_info(a):
    files = []
    for pat in a.photos:
        files += sorted(glob.glob(pat))
    if not files:
        print("no photos found at " + " ".join(a.photos) + ": put the maker's originals there first")
        return 1
    worst, unreadable = [], []
    for f in files:
        try:
            im, orientation = open_photo(f)
        except PhotoError as ex:
            print(f"{ex}")
            unreadable.append(f)
            continue
        with Image.open(f) as raw:
            ex = raw.getexif()
        tags = {ExifTags.TAGS.get(k, k): v for k, v in ex.items()} if ex else {}
        long_side = max(im.size)
        flags = []
        if long_side < 3000:
            flags.append(f"only {long_side} px on the long side (phone originals are usually 4000+)")
        if not tags.get("Make") and not tags.get("Model"):
            flags.append("no camera EXIF (stripped: a screenshot, a messaging-app copy, or an export)")
        turned = f", turned upright from EXIF orientation {orientation}" if orientation not in (1, None) else ""
        print(f"{f}: {im.size[0]} x {im.size[1]} as seen{turned}, {im.mode}, camera: {tags.get('Model') or '-'}")
        for fl in flags:
            print(f"    ! {fl}")
        if flags:
            worst.append(f)
    if worst:
        print("\nASK FOR ORIGINALS: these look like reduced copies. Fine detail (small text, edges, "
              "anything under ~0.5 mm) blurs at this size. Ask for the full-resolution originals as JPEG: "
              "AirDrop, or share/email with 'Actual Size', or copy straight off the phone. Not a "
              "screenshot and not through a messaging app.")
    return 1 if unreadable else 0


# ----------------------------------------------------------------- ruler ----

def tick_period(profile, pmin, pmax, pad=16):
    """Fundamental spacing (px) of a 1-D tick pattern, and its signal-to-noise.

    Autocorrelation finds the fundamental (its first strong peak is one tick
    spacing; FFT peaks alone can lock onto a harmonic and report half the true
    scale on close-up photos). The FFT then refines that period to a fraction
    of a pixel.
    """
    p = np.asarray(profile, dtype=float)
    n = len(p)
    if n < 3 * pmin + 2:
        return None, 0.0
    x = np.arange(n)
    p = p - np.polyval(np.polyfit(x, p, 1), x)          # remove lighting gradient, keep every period
    ac = np.correlate(p, p, mode="full")[n - 1:]
    if ac[0] <= 0:
        return None, 0.0
    ac = ac / (ac[0] * (n - np.arange(n)) / n)           # normalised, unbiased
    hi = int(min(pmax, n // 3))
    lo = int(max(2, pmin))
    if hi <= lo + 1:
        return None, 0.0
    seg = ac[lo:hi + 1]
    peaks = [i for i in range(1, len(seg) - 1) if seg[i] >= seg[i - 1] and seg[i] >= seg[i + 1] and seg[i] > 0.1]
    if not peaks:
        return None, 0.0
    top = max(seg[i] for i in peaks)
    first = next(i for i in peaks if seg[i] >= 0.6 * top)
    rough = lo + first
    w = p * np.hanning(n)
    m = n * pad
    spec = np.abs(np.fft.rfft(w, m))
    freqs = np.fft.rfftfreq(m)
    with np.errstate(divide="ignore"):
        periods = np.where(freqs > 0, 1.0 / np.maximum(freqs, 1e-12), np.inf)
    near = (periods >= rough * 0.85) & (periods <= rough * 1.15)
    band = (periods >= pmin) & (periods <= pmax)
    if not near.any():
        return float(rough), 0.0
    idx = int(np.argmax(np.where(near, spec, 0)))
    snr = spec[idx] / (np.median(spec[band]) + 1e-9) if band.any() else 0.0
    return float(periods[idx]), float(snr)


def _profiles(a, box):
    im, _ = open_photo(a.photo)
    g = np.asarray(im.convert("L"), dtype=float)
    x0, y0, x1, y1 = box
    crop = g[y0:y1, x0:x1]
    if crop.size == 0:
        raise PhotoError(f"box {box} is outside the photo ({g.shape[1]} x {g.shape[0]} px as seen)")
    along = crop.shape[1] if a.axis == "x" else crop.shape[0]
    if along < 3 * a.min_px + 2:
        raise PhotoError(f"box is only {along} px along the ticks: make it at least 3 tick spacings long")
    strips = max(1, min(a.strips, (crop.shape[0] if a.axis == "x" else crop.shape[1])))
    return ([s.mean(axis=0) for s in np.array_split(crop, strips, axis=0)] if a.axis == "x"
            else [s.mean(axis=1) for s in np.array_split(crop, strips, axis=1)])


def ruler_scale(a, box):
    rows = sorted(((snr, per) for per, snr in (tick_period(pr, a.min_px, a.max_px) for pr in _profiles(a, box))
                   if per), reverse=True)
    return (rows[0][1] / a.tick_mm, rows[0][0]) if rows else None


def cmd_ruler(a):
    try:
        if a.scan and a.scan > 1:
            x0, y0, x1, y1 = a.box
            print(f"{a.photo}: scale along the ruler ({a.scan} segments; a steady drift means perspective)")
            for k in range(a.scan):
                if a.axis == "y":
                    seg = (x0, y0 + (y1 - y0) * k // a.scan, x1, y0 + (y1 - y0) * (k + 1) // a.scan)
                else:
                    seg = (x0 + (x1 - x0) * k // a.scan, y0, x0 + (x1 - x0) * (k + 1) // a.scan, y1)
                r = ruler_scale(a, seg)
                print(f"  box {seg}: " + (f"{r[0]:.2f} px/mm (SNR {r[1]:.0f})" if r else "no pattern"))
            print("  " + PERSPECTIVE_NOTE)
            return 0
        profiles = _profiles(a, a.box)
    except PhotoError as ex:
        print(ex)
        return 1
    rows = []
    for prof in profiles:
        per, snr = tick_period(prof, a.min_px, a.max_px)
        if per:
            rows.append((snr, per))
    if not rows:
        print("no tick pattern found: put the box over the fine ticks only, or set --min-px/--max-px")
        return 1
    rows.sort(reverse=True)
    best_snr, best_per = rows[0]
    good = [per for snr, per in rows if snr >= max(5.0, best_snr * 0.5)]
    ppmm = best_per / a.tick_mm
    spread = (max(good) - min(good)) / a.tick_mm if len(good) > 1 else 0.0
    print(f"{a.photo}: {ppmm:.2f} px/mm  (tick {best_per:.2f} px, SNR {best_snr:.0f}, "
          f"{len(good)} strips agree within {spread:.2f} px/mm)")
    if best_snr < 8:
        print("  ! weak pattern (SNR < 8): check the box covers the fine ticks only, not the numbers")
    print("  " + PERSPECTIVE_NOTE)
    return 0


# ------------------------------------------------------------------ grid ----

def crop_zoom(im, box, zoom):
    if box:
        im = im.crop(tuple(box))
    if zoom and zoom != 1:
        im = im.resize((round(im.width * zoom), round(im.height * zoom)), Image.LANCZOS)
    return im


def cmd_grid(a):
    try:
        src, _ = open_photo(a.photo)
    except PhotoError as ex:
        print(ex)
        return 1
    im = crop_zoom(src.convert("RGB"), a.box, a.zoom).convert("RGBA")
    over = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    step = a.ppmm * a.zoom                 # px per mm in the zoomed crop
    f = font(max(11, int(step * 0.35)))
    k, x = 0, 0.0
    while x < im.width:
        major = k % 2 == 0
        d.line([(x, 0), (x, im.height)], fill=GRID_MAJOR + (200,) if major else GRID_MINOR, width=1)
        if major:
            d.text((x + 2, 2), f"{k // 2}", font=f, fill=GRID_MAJOR + (255,))
        x += step / 2
        k += 1
    k, y = 0, 0.0
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
    if a.zoom > 2 and min(src.size) < 2000:
        print("  ! zoomed past 2x on a reduced photo: edges are interpolated, not real detail")
    return 0


# -------------------------------------------------------------- annotate ----

def parse_mark(m, default_r):
    x, y, rest = m.split(",", 2)
    label, r = rest, default_r
    head, _, tail = rest.rpartition(",")
    if head:
        try:
            r = float(tail)
            label = head
        except ValueError:
            pass
    return float(x), float(y), label, r


def cmd_annotate(a):
    try:
        src, _ = open_photo(a.photo)
    except PhotoError as ex:
        print(ex)
        return 1
    src = src.convert("RGB")
    ox, oy = (a.box[0], a.box[1]) if a.box else (0, 0)
    im = crop_zoom(src, a.box, a.zoom)
    z = a.zoom or 1.0
    scale = max(1.0, max(im.size) / 1000.0)           # rings and labels readable on 4000 px originals
    fsize = int(24 * scale)
    lab_font = font(fsize, True)
    head = int(56 * scale) if a.title else 0
    canvas = Image.new("RGB", (im.width, im.height + head), (30, 31, 34))
    canvas.paste(im, (0, head))
    d = ImageDraw.Draw(canvas)
    if a.title:
        d.text((int(14 * scale), int(14 * scale)), a.title, font=font(fsize, True), fill=INK)
    default_r = a.radius if a.radius else 28.0 * scale / z
    W, H = canvas.size
    for m in a.mark:
        try:
            x, y, label, r = parse_mark(m, default_r)
        except ValueError:
            print(f"bad --mark {m!r}: use x,y,label[,radius]")
            return 1
        cx, cy, rr = (x - ox) * z, (y - oy) * z + head, r * z
        for w, col in ((int(7 * scale), (0, 0, 0)), (int(4 * scale), RING)):
            d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=col, width=max(1, w))
        tw = d.textlength(label, font=lab_font)
        bw, bh = tw + 20 * scale, fsize + 10 * scale
        tx, ty = cx + rr * 0.75, cy - rr - bh
        if tx + bw > W:
            tx = cx - rr * 0.75 - bw
        if ty < head:
            ty = cy + rr
        tx, ty = min(max(0, tx), W - bw), min(max(head, ty), H - bh)
        d.rounded_rectangle([tx, ty, tx + bw, ty + bh], radius=int(8 * scale), fill=RING)
        d.text((tx + 10 * scale, ty + 3 * scale), label, font=lab_font, fill=INK)
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
    p.add_argument("--min-px", type=float, default=4.0)
    p.add_argument("--max-px", type=float, default=250.0)
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
    p.add_argument("--radius", type=float, default=None, help="ring radius in photo pixels (default scales with size)")
    a = ap.parse_args()
    return {"info": cmd_info, "ruler": cmd_ruler, "grid": cmd_grid, "annotate": cmd_annotate}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
