"""views: orthographic face views of an STL at an exact px/mm, made by ray casting.

    <blender> --background --factory-startup --python-exit-code 2 \
        --python views.py -- exports/part_v1.stl --spec checks.json --out-dir renders/v1

For every view it writes two PNGs and one entry in views.json:
  <name>_shaded.png  grey shading, key light from the image's UPPER LEFT
                     (people read relief assuming light from above-left; a
                     lower-left light makes raised detail look sunken, which hid
                     two defects on the 2026-11 caliper)
  <name>_relief.png  height map that does not depend on lighting at all:
                     WARM = stands up toward you, NEUTRAL = the main face,
                     COOL = cut in / sunk, BLACK = see-through (no material)
views.json also lists each face's "levels" (the surface heights found and how
much of the face sits at each), so polarity can be read as numbers too.

No render engine, camera or GPU: pure geometry, so it runs headless anywhere
Blender runs, and 1 mm is exactly ppmm pixels (photo comparisons line up).

Spec (optional) -> "views": [{"name": "top", "face": "+Z", "right": [0,1,0], "up": [-1,0,0],
    "ppmm": 24, "frame_mm": [20, 30], "center_mm": [0, 0, 0], "relief_range_mm": 0.5,
    "base": "mode" | "outermost" | <coordinate>}]
Without "views", all six faces are rendered with default orientations.
"""

import argparse
import json
import os
import sys
from collections import Counter

import bmesh
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

DEFAULT_AXES = {          # face: (outward normal, image right, image up)
    "+Z": ((0, 0, 1), (1, 0, 0), (0, 1, 0)),
    "-Z": ((0, 0, -1), (1, 0, 0), (0, -1, 0)),
    "-Y": ((0, -1, 0), (1, 0, 0), (0, 0, 1)),
    "+Y": ((0, 1, 0), (-1, 0, 0), (0, 0, 1)),
    "+X": ((1, 0, 0), (0, 1, 0), (0, 0, 1)),
    "-X": ((-1, 0, 0), (0, -1, 0), (0, 0, 1)),
}
BG = np.array([0.169, 0.176, 0.192])
SEE_THROUGH = np.array([0.03, 0.03, 0.035])
NEUTRAL = np.array([0.80, 0.80, 0.78])
WARM = np.array([0.93, 0.42, 0.10])
WARM_MAX = np.array([0.62, 0.08, 0.04])
COOL = np.array([0.16, 0.45, 0.88])
COOL_MAX = np.array([0.05, 0.10, 0.36])


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


def render_view(bvh, mn, mx, v, default_ppmm):
    face = v.get("face", "+Z")
    n, right, up = (Vector(x) for x in DEFAULT_AXES[face])
    if "right" in v:
        right = Vector(v["right"])
    if "up" in v:
        up = Vector(v["up"])
    n = right.cross(up).normalized() if "right" in v or "up" in v else n
    ppmm = float(v.get("ppmm", default_ppmm))
    centre = Vector(v["center_mm"]) if "center_mm" in v else (mn + mx) / 2
    corners = [Vector((x, y, z)) for x in (mn.x, mx.x) for y in (mn.y, mx.y) for z in (mn.z, mx.z)]
    if "frame_mm" in v:
        fw, fh = v["frame_mm"]
    else:
        margin = float(v.get("margin_mm", 1.0))
        fw = max(abs((c - centre).dot(right)) for c in corners) * 2 + 2 * margin
        fh = max(abs((c - centre).dot(up)) for c in corners) * 2 + 2 * margin
    w, h = int(round(fw * ppmm)), int(round(fh * ppmm))
    reach = max((c - centre).dot(n) for c in corners) + 5.0
    span = (mx - mn).length + 20.0
    d = -n
    depth = np.full((h, w), np.nan)
    ndotl = np.zeros((h, w))
    light = (-0.55 * right + 0.70 * up + 0.45 * n).normalized()        # upper left, in front
    for j in range(h):
        vv = fh / 2 - (j + 0.5) / ppmm
        row_o = centre + up * vv + n * reach
        for i in range(w):
            uu = -fw / 2 + (i + 0.5) / ppmm
            loc, nrm, idx, dist = bvh.ray_cast(row_o + right * uu, d, span)
            if loc is not None:
                depth[j, i] = dist
                ndotl[j, i] = max(0.0, nrm.dot(light))
    hit = ~np.isnan(depth)
    coord = np.where(hit, reach - depth, np.nan)          # position along n, measured from the centre
    # Cast shadows from the upper-left light. Straight on, a 0.2 mm letter's walls
    # are parallel to the rays and invisible; only shadows show raised vs cut in
    # (raised: shadow falls outside, lower right; cut in: shadow inside, upper left).
    hgt = np.where(hit, coord, -1e9)
    lit = np.ones((h, w), dtype=bool)
    tan_elev = 0.45 / float(np.hypot(0.55, 0.70))         # light elevation above the face (~27 deg)
    for k in range(1, int(0.8 * ppmm) + 1):
        dy, dx = int(round(k * 0.70 / 0.89)), int(round(k * 0.55 / 0.89))   # k px toward the light (up-left)
        if dy >= h or dx >= w:
            break
        nb = np.full((h, w), -1e9)
        nb[dy:, dx:] = hgt[:h - dy, :w - dx]
        lit &= ~(nb - hgt > (k / ppmm) * tan_elev + 1e-3)
    shade = (0.16 + 0.84 * ndotl) * np.where(lit, 1.0, 0.55)
    shaded = np.where(hit[..., None], np.repeat(shade[..., None], 3, axis=2), BG)
    # relief: height relative to the base plane, + toward the viewer
    base_mode = v.get("base", "mode")
    bins = Counter(np.round(coord[hit] / 0.02).astype(int).tolist()) if hit.any() else Counter()
    if base_mode == "outermost":
        base = float(np.nanmax(coord))
    elif isinstance(base_mode, (int, float)):
        base = float(base_mode) - centre.dot(n)
    else:
        base = bins.most_common(1)[0][0] * 0.02 if bins else 0.0
    rng = float(v.get("relief_range_mm", 0.5))
    rel = np.where(hit, coord - base, 0.0)
    t = np.clip(rel / rng, -1, 1)
    up_col = np.where((rel > rng)[..., None], WARM_MAX, lerp(NEUTRAL, WARM, np.clip(t, 0, 1)))
    dn_col = np.where((rel < -rng)[..., None], COOL_MAX, lerp(NEUTRAL, COOL, np.clip(-t, 0, 1)))
    col = np.where((rel >= 0)[..., None], up_col, dn_col)
    col = col * (0.72 + 0.28 * shade[..., None])          # a little shading keeps shapes legible
    relief = np.where(hit[..., None], col, SEE_THROUGH)
    levels = []
    total = int(hit.sum())
    for b, cnt in bins.most_common(6):
        levels.append({"relative_mm": round(b * 0.02 - base, 2),
                       "world_coord_mm": round(b * 0.02 + centre.dot(n), 3),
                       "share_pct": round(100 * cnt / total, 1)})
    return shaded, relief, {
        "name": v["name"], "face": face, "normal": list(n), "right": list(right), "up": list(up),
        "ppmm": ppmm, "frame_mm": [round(fw, 3), round(fh, 3)], "px": [w, h],
        "center_mm": [round(c, 4) for c in centre],
        "base_world_coord_mm": round(base + centre.dot(n), 3), "base_rule": str(base_mode),
        "relief_range_mm": rng, "see_through_pct": round(100 * (1 - hit.mean()), 1),
        "levels": levels}


def main():
    a = parse_args()
    spec = json.load(open(a.spec)) if a.spec else {}
    views = spec.get("views") or [{"name": f.replace("+", "pos").replace("-", "neg"), "face": f} for f in DEFAULT_AXES]
    default_ppmm = a.ppmm or float(spec.get("view_ppmm", 20))
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
        print(f"{v['name']:>12} ({info['face']}) {info['px'][0]}x{info['px'][1]} px, "
              f"no-material {info['see_through_pct']}%, levels: {lv}")
    json.dump(meta, open(os.path.join(a.out_dir, "views.json"), "w"), indent=1)
    print("VIEWS_JSON " + os.path.join(a.out_dir, "views.json"))


main()
