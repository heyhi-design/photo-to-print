"""views: orthographic face views of an STL at an exact px/mm, made by ray casting.

    <blender> --background --factory-startup --python-exit-code 2 \
        --python views.py -- exports/part_v1.stl --spec checks.json --out-dir renders/v1

For every view it writes two PNGs and one entry in views.json:
  <name>_shaded.png  grey shading with cast shadows, key light from the image's UPPER
                     LEFT (people read relief assuming light from above-left; a
                     lower-left light makes raised detail look sunken, which hid
                     two defects on the 2026-11 caliper)
  <name>_relief.png  height map that does not depend on lighting at all:
                     WARM = stands up toward you, NEUTRAL = the main face,
                     COOL = cut in / farther away, BLACK = no material
views.json lists each face's "levels" (the surface heights found and how much of
the face sits at each) in true world coordinates, so polarity can be read as numbers.

No render engine, camera or GPU: pure geometry, so it runs headless anywhere
Blender runs, and 1 mm is exactly ppmm pixels (photo comparisons line up).
View keys (face, right/up, ppmm, frame_mm, center_mm, base, ...) are documented
in references/checks-reference.md. Without "views", all six faces are rendered.
"""

import argparse
import json
import os
import sys
from collections import Counter

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bmesh  # noqa: E402
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Vector  # noqa: E402
from mathutils.bvhtree import BVHTree  # noqa: E402

import spec as specmod  # noqa: E402

BG = np.array([0.169, 0.176, 0.192], dtype=np.float32)
SEE_THROUGH = np.array([0.03, 0.03, 0.035], dtype=np.float32)
NEUTRAL = np.array([0.80, 0.80, 0.78], dtype=np.float32)
WARM = np.array([0.93, 0.42, 0.10], dtype=np.float32)
WARM_MAX = np.array([0.62, 0.08, 0.04], dtype=np.float32)
COOL = np.array([0.16, 0.45, 0.88], dtype=np.float32)
COOL_MAX = np.array([0.05, 0.10, 0.36], dtype=np.float32)
BIN = 0.02                    # level histogram bin, mm


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(prog="views")
    ap.add_argument("stl")
    ap.add_argument("--spec", default=None)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--ppmm", type=float, default=None, help="override every view's px/mm")
    return ap.parse_args(argv)


def load_bvh(path):
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    bpy.ops.wm.stl_import(filepath=path)
    bm = bmesh.new()
    for o in [o for o in bpy.context.scene.objects if o.type == 'MESH']:
        me = o.data.copy()
        me.transform(o.matrix_world)
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    bmesh.ops.triangulate(bm, faces=bm.faces)
    if not bm.verts:
        raise SystemExit("views: the STL has no triangles")
    xs = [v.co for v in bm.verts]
    mn = Vector((min(v.x for v in xs), min(v.y for v in xs), min(v.z for v in xs)))
    mx = Vector((max(v.x for v in xs), max(v.y for v in xs), max(v.z for v in xs)))
    bvh = BVHTree.FromBMesh(bm)
    bm.free()
    return bvh, mn, mx


def save_png(rgb, path):
    h, w, _ = rgb.shape
    rgba = np.ones((h, w, 4), dtype=np.float32)
    rgba[:, :, :3] = np.clip(rgb, 0, 1)
    img = bpy.data.images.new(os.path.basename(path), w, h, alpha=False)
    img.pixels.foreach_set(rgba[::-1].ravel())          # Blender rows run bottom-up
    img.filepath_raw = path
    img.file_format = 'PNG'
    img.save()
    bpy.data.images.remove(img)


def lerp(a, b, t):
    return a + (b - a) * t[..., None]


def box_mean(values, mask, k):
    """Mean of values over a (2k+1)^2 window, counting only mask pixels."""
    v = np.where(mask, values, 0.0).astype(np.float64)
    m = mask.astype(np.float64)
    pv = np.pad(v, ((1, 0), (1, 0))).cumsum(0).cumsum(1)
    pm = np.pad(m, ((1, 0), (1, 0))).cumsum(0).cumsum(1)
    h, w = values.shape
    ys, xs = np.arange(h), np.arange(w)
    y0, y1 = np.clip(ys - k, 0, h), np.clip(ys + k + 1, 0, h)
    x0, x1 = np.clip(xs - k, 0, w), np.clip(xs + k + 1, 0, w)

    def win(P):
        return P[y1][:, x1] - P[y0][:, x1] - P[y1][:, x0] + P[y0][:, x0]
    cnt = win(pm)
    return np.where(cnt > 0, win(pv) / np.maximum(cnt, 1), 0.0)


def axis_of(n):
    """(index, sign) when n is axis-aligned, else (None, None)."""
    k = int(np.argmax(np.abs(n)))
    if abs(abs(n[k]) - 1.0) < 1e-6:
        return k, 1.0 if n[k] > 0 else -1.0
    return None, None


def render_view(bvh, mn, mx, v, default_ppmm):
    n, right, up = (Vector(x) for x in specmod.view_axes(v))
    face = v.get("face") or "custom"
    ppmm = float(v.get("ppmm", default_ppmm))
    centre = Vector(v["center_mm"]) if "center_mm" in v else (mn + mx) / 2
    corners = [Vector((x, y, z)) for x in (mn.x, mx.x) for y in (mn.y, mx.y) for z in (mn.z, mx.z)]
    if "frame_mm" in v:
        fw, fh = v["frame_mm"]
    else:
        margin = float(v.get("margin_mm", 1.0))
        fw = max(abs((c - centre).dot(right)) for c in corners) * 2 + 2 * margin
        fh = max(abs((c - centre).dot(up)) for c in corners) * 2 + 2 * margin
    note = None
    cap = float(v.get("max_pixels", 6_000_000))
    if fw * fh * ppmm * ppmm > cap:
        new = (cap / (fw * fh)) ** 0.5
        note = f"ppmm lowered from {ppmm:g} to {new:.2f} to stay under {int(cap)} pixels"
        ppmm = new
    w, h = max(1, int(round(fw * ppmm))), max(1, int(round(fh * ppmm)))
    reach = max((c - centre).dot(n) for c in corners) + 5.0
    span = (mx - mn).length + 20.0
    d = -n
    depth = np.full((h, w), np.nan, dtype=np.float32)
    ndotl = np.zeros((h, w), dtype=np.float32)
    light = (-0.55 * right + 0.70 * up + 0.45 * n).normalized()        # upper left, in front
    for j in range(h):
        row_o = centre + up * (fh / 2 - (j + 0.5) / ppmm) + n * reach
        for i in range(w):
            loc, nrm, idx, dist = bvh.ray_cast(row_o + right * (-fw / 2 + (i + 0.5) / ppmm), d, span)
            if loc is not None:
                depth[j, i] = dist
                ndotl[j, i] = max(0.0, nrm.dot(light))
    hit = ~np.isnan(depth)
    coord = np.where(hit, reach - depth, np.nan)          # along n, relative to the centre
    # Cast shadows from the upper-left light: straight on, a 0.2 mm detail's walls
    # are parallel to the rays and invisible; only shadows show raised vs cut in.
    hgt = np.where(hit, coord, -1e9)
    lit = np.ones((h, w), dtype=bool)
    tan_elev = 0.45 / float(np.hypot(0.55, 0.70))
    for k in range(1, int(0.8 * ppmm) + 1):
        dy, dx = int(round(k * 0.70 / 0.89)), int(round(k * 0.55 / 0.89))
        if dy >= h or dx >= w:
            break
        nb = np.full((h, w), -1e9, dtype=np.float32)
        nb[dy:, dx:] = hgt[:h - dy, :w - dx]
        lit &= ~(nb - hgt > (k / ppmm) * tan_elev + 1e-3)
    shade = (0.16 + 0.84 * ndotl) * np.where(lit, 1.0, 0.55)
    shaded = np.where(hit[..., None], np.repeat(shade[..., None], 3, axis=2), BG)

    # main face (base): see checks-reference.md "views". World coordinates are true world values.
    c_n = centre.dot(n)
    k_ax, sign = axis_of(np.array(n))
    bins = Counter(np.round(coord[hit] / BIN).astype(int).tolist()) if hit.any() else Counter()
    total = int(hit.sum())
    base_rule = v.get("base", "auto")
    local = None
    if isinstance(base_rule, (int, float)) and not isinstance(base_rule, bool):
        along = base_rule * sign if k_ax is not None else base_rule      # world value -> along n
        base = along - c_n
    elif base_rule == "outermost":
        base = float(np.nanmax(coord)) if total else 0.0
    elif base_rule == "mode":
        base = bins.most_common(1)[0][0] * BIN if bins else 0.0
    else:                     # auto (and the reference level for local): outermost level covering >= min share
        min_share = float(v.get("base_min_share", 0.15))
        base = bins.most_common(1)[0][0] * BIN if bins else 0.0
        for b in sorted(bins, reverse=True):
            if bins[b] / max(total, 1) >= min_share:
                base = b * BIN
                break
        if base_rule == "local" and total:
            k = max(1, int(round(float(v.get("base_window_mm", 2.0)) * ppmm / 2)))
            local = box_mean(coord, hit, k)
    rng = float(v.get("relief_range_mm", 0.5))
    rel = np.where(hit, coord - (local if local is not None else base), 0.0)
    t = np.clip(rel / rng, -1, 1)
    up_col = np.where((rel > rng)[..., None], WARM_MAX, lerp(NEUTRAL, WARM, np.clip(t, 0, 1)))
    dn_col = np.where((rel < -rng)[..., None], COOL_MAX, lerp(NEUTRAL, COOL, np.clip(-t, 0, 1)))
    col = np.where((rel >= 0)[..., None], up_col, dn_col)
    col = col * (0.72 + 0.28 * shade[..., None])
    relief = np.where(hit[..., None], col, SEE_THROUGH)

    def world(along_rel):
        a = along_rel + c_n
        return (round(a * sign, 3) if k_ax is not None else round(a, 3)) + 0.0   # no "-0.0"
    levels = [{"relative_mm": round(b * BIN - base, 2), "world_coord_mm": world(b * BIN),
               "share_pct": round(100 * cnt / total, 1)} for b, cnt in bins.most_common(6)]
    info = {"name": v["name"], "face": face, "normal": [round(c, 6) for c in n], "right": [round(c, 6) for c in right],
            "up": [round(c, 6) for c in up], "ppmm": ppmm, "frame_mm": [round(fw, 3), round(fh, 3)], "px": [w, h],
            "center_mm": [round(c, 4) for c in centre],
            "world_axis": "xyz"[k_ax] if k_ax is not None else "along normal",
            "base_world_coord_mm": world(base), "base_rule": str(base_rule), "relief_range_mm": rng,
            "no_material_pct": round(100 * (1 - hit.mean()), 1), "levels": levels}
    if note:
        info["note"] = note
    return shaded, relief, info


def main():
    a = parse_args()
    spec = {}
    if a.spec:
        with open(a.spec) as f:
            spec = json.load(f)
    views = spec.get("views") or [{"name": f.replace("+", "pos").replace("-", "neg"), "face": f} for f in specmod.FACES]
    default_ppmm = a.ppmm or float(spec.get("view_ppmm", 20))
    views, errors = specmod.validate_views(views, default_ppmm)
    if errors:
        for e in errors:
            print("FAIL " + e)
        sys.exit(1)
    os.makedirs(a.out_dir, exist_ok=True)
    bvh, mn, mx = load_bvh(a.stl)
    meta = {"stl": os.path.abspath(a.stl), "bbox_min": list(mn), "bbox_max": list(mx), "views": []}
    for v in views:
        if a.ppmm:
            v = dict(v, ppmm=a.ppmm)
        shaded, relief, info = render_view(bvh, mn, mx, v, default_ppmm)
        info["shaded"] = os.path.join(a.out_dir, f"{v['name']}_shaded.png")
        info["relief"] = os.path.join(a.out_dir, f"{v['name']}_relief.png")
        save_png(shaded, info["shaded"])
        save_png(relief, info["relief"])
        meta["views"].append(info)
        lv = ", ".join(f"{x['relative_mm']:+.2f} mm {x['share_pct']}%" for x in info["levels"][:4])
        print(f"{v['name']:>12} ({info['face']}) {info['px'][0]}x{info['px'][1]} px, main face at "
              f"{info['world_axis']} {info['base_world_coord_mm']}, no-material {info['no_material_pct']}%, "
              f"levels: {lv}" + (f"  [{info['note']}]" if "note" in info else ""))
    with open(os.path.join(a.out_dir, "views.json"), "w") as f:
        json.dump(meta, f, indent=1)
    print("VIEWS_JSON " + os.path.join(a.out_dir, "views.json"))


main()
