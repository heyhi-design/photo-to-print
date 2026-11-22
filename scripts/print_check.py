"""print_check: verify an exported STL is printable and matches its spec.

Runs inside Blender's bundled Python (no pip installs), on the STL file itself,
so it checks what will actually print, however the part was modelled.

    <blender> --background --factory-startup --python-exit-code 2 \
        --python print_check.py -- exports/part_v1.stl --spec checks.json --out reports/check_v1.json

Exit code 0 = every check passed, 1 = at least one FAIL (or the spec is
invalid), 2 = the script crashed. Usually run through `kit.py check|verify`.
Every spec key and rule: references/checks-reference.md.

Checks
  mesh      one shell, 0 non-manifold edges, 0 loose geometry, consistent winding,
            0 self-intersections, positive volume
  envelope  bounding box against spec["envelope"]
  thin      material thinner than the process minimums (ray inward from every triangle);
            sharp wedge tips (thickness climbing from ~0) are warnings, not failures
  gaps      grooves/clearances narrower than min_gap_mm (ray outward): FAIL unless accepted
  overhang  downward faces steeper than the limit, in print orientation (FDM gate)
  rays      single-ray assertions; every "clear" ray must cross the part's bounding box
  sweeps    lines (or tubes, with radius_mm) of rays that must stay clear
  relief    raised / cut-in polarity and depth of a region
  glb       the preview GLB is in metres (STL dims / 1000)
The positive-control rule: if any test expects "clear", at least one ray marked
"positive_control" (expect "hit") must pass, and each clear test should name its
own control beside it. A clear result that never touched the part proves nothing.
"""

import argparse
import json
import math
import os
import sys
from collections import defaultdict

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bmesh  # noqa: E402
import bpy  # noqa: E402
from mathutils import Euler, Vector  # noqa: E402
from mathutils.bvhtree import BVHTree  # noqa: E402

import spec as specmod  # noqa: E402


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(prog="print_check")
    ap.add_argument("stl")
    ap.add_argument("--spec", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--process", default=None, help="a process in presets.json (overrides the spec)")
    ap.add_argument("--glb", default=None, help="preview GLB to check is in metres (STL dims / 1000)")
    return ap.parse_args(argv)


def load_mesh(path):
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
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    return bm


def shells(bm):
    seen, count = set(), 0
    for f in bm.faces:
        if f.index in seen:
            continue
        count += 1
        stack = [f]
        seen.add(f.index)
        while stack:
            for e in stack.pop().edges:
                for g in e.link_faces:
                    if g.index not in seen:
                        seen.add(g.index)
                        stack.append(g)
    return count


# ---------------------------------------------------------------- checks ----

def check_mesh(ctx):
    bm, bvh = ctx["bm"], ctx["bvh"]
    nm = sum(1 for e in bm.edges if len(e.link_faces) != 2)
    flipped = sum(1 for e in bm.edges if len(e.link_faces) == 2 and not e.is_contiguous)
    loose_v = sum(1 for v in bm.verts if not v.link_edges)
    loose_e = sum(1 for e in bm.edges if not e.link_faces)
    vol = bm.calc_volume(signed=True)
    tri_verts = ctx["vert_sets"]
    real = [(i, j) for i, j in bvh.overlap(bvh) if i < j and not (tri_verts[i] & tri_verts[j])]
    sample = []
    for i, _ in real[:5]:
        c = bm.faces[i].calc_center_median()
        sample.append([round(c.x, 2), round(c.y, 2), round(c.z, 2)])
    n_shells = shells(bm)
    fails = []
    if n_shells != 1:
        fails.append(f"{n_shells} separate shells (a printable part is ONE body: union, don't join; "
                     f"separate pieces are separate projects)")
    if nm:
        fails.append(f"{nm} non-manifold edges")
    if flipped:
        fails.append(f"{flipped} edges where neighbouring faces wind opposite ways (some normals are flipped)")
    if loose_v or loose_e:
        fails.append(f"loose geometry: {loose_v} verts, {loose_e} edges")
    if real:
        fails.append(f"{len(real)} self-intersecting triangle pairs, e.g. at {sample[:2]}")
    if vol <= 0:
        fails.append("volume is not positive (normals point inward)")
    return {"shells": n_shells, "non_manifold_edges": nm, "inconsistent_winding_edges": flipped,
            "loose_verts": loose_v, "loose_edges": loose_e, "self_intersections": len(real),
            "self_int_sample": sample, "volume_mm3": round(vol, 3), "triangles": len(bm.faces),
            "pass": not fails, "fails": fails}


def check_envelope(ctx):
    mn, mx = ctx["bbox"]
    dims = [mx[i] - mn[i] for i in range(3)]
    out = {"min": [round(v, 3) for v in mn], "max": [round(v, 3) for v in mx], "dims": [round(v, 3) for v in dims]}
    env = ctx["spec"].get("envelope")
    if not env:
        out.update({"pass": True, "note": "no envelope in spec: dimensions reported, not checked"})
        return out
    tol = float(env["tol_mm"])
    fails = []
    for key, got in (("dims_mm", dims), ("min_mm", mn), ("max_mm", mx)):
        want = env.get(key)
        if want is None:
            continue
        for ax, g, w in zip("XYZ", got, want):
            if w is not None and abs(g - w) > tol:
                fails.append(f"{key} {ax}: {g:.3f} vs expected {w} (tol {tol})")
    out.update({"expected": {k: env[k] for k in ("dims_mm", "min_mm", "max_mm") if k in env},
                "tol_mm": tol, "pass": not fails, "fails": fails})
    return out


TINY_MM2 = 0.01        # a thin/gap region smaller than this is a corner speck, not a feature


def in_box(p, box):
    return all(box["min"][i] - 1e-9 <= p[i] <= box["max"][i] + 1e-9 for i in range(3))


def facing_hit(bvh, f_index, origin, direction, max_dist, vert_sets, exiting):
    """Distance to the first genuinely opposite wall along direction. Skips
    triangles sharing a vertex with the start face (corner grazes) and walls
    whose normal is not within ~45 deg of opposite (fillets, angled neighbours)."""
    start, travelled = origin, 0.0
    for _ in range(6):
        loc, nrm, idx, dist = bvh.ray_cast(start, direction, max_dist - travelled)
        if loc is None:
            return None
        travelled += dist
        if idx is not None and (vert_sets[idx] & vert_sets[f_index]):
            start = loc + direction * 1e-5
            continue
        facing = nrm.dot(direction)
        if (exiting and facing > 0.7) or (not exiting and facing < -0.7):
            return travelled
        start = loc + direction * 1e-5
    return None


def cluster(samples):
    """samples: [(point, value, area)] -> rows on a 0.5 mm grid, worst first, with the real extent."""
    groups = defaultdict(list)
    for p, d, a in samples:
        groups[(round(p.x * 2) / 2, round(p.y * 2) / 2, round(p.z * 2) / 2)].append((p, d, a))
    rows = []
    for _, items in groups.items():
        ds = sorted(d for _, d, _ in items)
        worst = min(items, key=lambda t: t[1])[0]
        xs, ys, zs = ([p[k] for p, _, _ in items] for k in range(3))
        rows.append({"worst_at_mm": [round(worst.x, 3), round(worst.y, 3), round(worst.z, 3)],
                     "extent_min_mm": [round(min(xs), 3), round(min(ys), 3), round(min(zs), 3)],
                     "extent_max_mm": [round(max(xs), 3), round(max(ys), 3), round(max(zs), 3)],
                     "tris": len(items), "area_mm2": round(sum(a for _, _, a in items), 4),
                     "min_mm": round(ds[0], 3), "median_mm": round(ds[len(ds) // 2], 3),
                     "p90_mm": round(ds[int(len(ds) * 0.9)] if len(ds) > 1 else ds[0], 3)})
    rows.sort(key=lambda r: r["min_mm"])
    return rows


def check_thin_and_gaps(ctx):
    bm, bvh, limits, spec = ctx["bm"], ctx["bvh"], ctx["limits"], ctx["spec"]
    min_feat, min_wall, min_gap = limits["min_feature_mm"], limits["min_wall_mm"], limits["min_gap_mm"]
    vs = ctx["vert_sets"]
    thin, gaps, acc_thin, acc_gap = [], [], 0, 0
    for f in bm.faces:
        area = f.calc_area()
        if area < 1e-9:                       # degenerate only; fine tessellation is still scanned
            continue
        c, n = f.calc_center_median(), f.normal
        d = facing_hit(bvh, f.index, c - n * 1e-5, -n, max(min_wall, 1.0) * 2, vs, True)
        if d is not None and d < min_wall:
            if any(in_box(c, b) for b in spec["accepted_thin"]):
                acc_thin += 1
            else:
                thin.append((c, d, area))
        d = facing_hit(bvh, f.index, c + n * 1e-5, n, max(min_gap, 1.0) * 2, vs, False)
        if d is not None and d < min_gap:
            if any(in_box(c, b) for b in spec["accepted_gaps"]):
                acc_gap += 1
            else:
                gaps.append((c, d, area))
    thin_rows = cluster(thin)
    fails, warns = [], []
    for r in thin_rows:
        if r["min_mm"] >= min_feat:
            r["kind"] = "fragile"
        elif r["area_mm2"] < TINY_MM2 or (r["min_mm"] < min_feat / 2 and r["p90_mm"] >= 3 * max(r["min_mm"], 0.01)):
            r["kind"] = "tip"           # thickness climbs from ~0 or covers a speck: a sharp corner that rounds off
        else:
            r["kind"] = "too thin"
    for r in thin_rows:
        if r["kind"] == "too thin" and len(fails) < 6:
            fails.append(f"material {r['min_mm']} mm thick at {r['worst_at_mm']} (region {r['extent_min_mm']} to "
                         f"{r['extent_max_mm']}; < {min_feat}): thicken it, or record it in CLARITY G4 and add a box "
                         f"around it to accepted_thin")
    tips = [r for r in thin_rows if r["kind"] == "tip"]
    if tips:
        warns.append(f"{len(tips)} sharp wedge tip(s) thinner than {min_feat} mm, worst at {tips[0]['worst_at_mm']}: "
                     f"these round off on a print")
    thin_out = {"min_feature_mm": min_feat, "min_wall_mm": min_wall, "regions": len(thin_rows),
                "too_thin": sum(1 for r in thin_rows if r["kind"] == "too thin"), "tips": len(tips),
                "fragile": sum(1 for r in thin_rows if r["kind"] == "fragile"), "accepted_tris": acc_thin,
                "worst": thin_rows[:10], "pass": not any(r["kind"] == "too thin" for r in thin_rows),
                "fails": fails, "warns": warns}
    gap_rows = cluster(gaps)
    for r in gap_rows:
        # A groove is judged on its typical width: rounded groove ends read narrower than the groove.
        # A speck of area is an inside corner (a crevice), which simply fills: a warning, not a failure.
        r["kind"] = "crevice" if r["area_mm2"] < TINY_MM2 else ("narrow" if r["median_mm"] < min_gap else "end")
    narrow = sorted([r for r in gap_rows if r["kind"] == "narrow"], key=lambda r: r["median_mm"])
    crevices = [r for r in gap_rows if r["kind"] == "crevice"]
    gfails = [f"groove or gap about {r['median_mm']} mm wide (narrowest {r['min_mm']}) at {r['worst_at_mm']} "
              f"(region {r['extent_min_mm']} to {r['extent_max_mm']}; < {min_gap}): it will fill in or fuse. Widen "
              f"it, or record it in CLARITY G4 and add a box around it to accepted_gaps" for r in narrow[:6]]
    gwarns = [f"{len(crevices)} hairline inside corner(s) narrower than {min_gap} mm, first at "
              f"{crevices[0]['worst_at_mm']}: these fill in on a print"] if crevices else []
    gap_out = {"min_gap_mm": min_gap, "regions": len(narrow), "crevices": len(crevices), "accepted_tris": acc_gap,
               "worst": narrow[:10], "pass": not narrow, "fails": gfails, "warns": gwarns}
    return thin_out, gap_out


def check_overhang(ctx):
    bm, limits, spec = ctx["bm"], ctx["limits"], ctx["spec"]
    deg = limits["overhang_deg"]
    rot = Euler([math.radians(a) for a in spec["print_rotation_deg"]], 'XYZ').to_matrix()
    lim = -math.sin(math.radians(deg))        # normal.z below this: steeper than `deg` from vertical
    zs = [(rot @ v.co).z for v in bm.verts]
    zmin = min(zs)
    total, samples = 0.0, []
    for f in bm.faces:
        a = f.calc_area()
        total += a
        nz = (rot @ f.normal).z
        c = f.calc_center_median()
        if nz < lim and (rot @ c).z > zmin + limits["bed_layer_mm"]:
            if not any(in_box(c, b) for b in spec["accepted_overhang"]):
                samples.append((c, -nz, a))
    rows = cluster(samples)
    over = sum(a for _, _, a in samples)
    out = {"limit_deg_from_vertical": deg, "print_rotation_deg": spec["print_rotation_deg"],
           "unsupported_mm2": round(over, 3), "share_pct": round(100 * over / total, 2) if total else 0.0,
           "gate": limits["overhang_gate"],
           "worst_regions": [{"at_mm": r["worst_at_mm"], "area_mm2": r["area_mm2"]}
                             for r in sorted(rows, key=lambda r: -r["area_mm2"])[:5]]}
    out["pass"] = (over < 0.01) if limits["overhang_gate"] else True
    if limits["overhang_gate"] and over >= 0.01:
        where = ", ".join(f"{w['at_mm']} ({w['area_mm2']} mm2)" for w in out["worst_regions"][:3])
        out["fails"] = [f"{over:.2f} mm2 of downward faces steeper than {deg} deg from vertical need supports; "
                        f"largest at {where}. Reorient (print_rotation_deg), chamfer, or accept with accepted_overhang"]
    return out


def seg_crosses_box(origin, d, length, mn, mx):
    """Does the segment origin + t*d, 0 <= t <= length, pass through the box?"""
    t0, t1 = 0.0, length
    for i in range(3):
        if abs(d[i]) < 1e-12:
            if origin[i] < mn[i] or origin[i] > mx[i]:
                return False
            continue
        a, b = (mn[i] - origin[i]) / d[i], (mx[i] - origin[i]) / d[i]
        t0, t1 = max(t0, min(a, b)), min(t1, max(a, b))
        if t0 > t1:
            return False
    return True


def check_rays(ctx):
    spec, bvh = ctx["spec"], ctx["bvh"]
    mn, mx = ctx["bbox"]
    pad_mn, pad_mx = [v - 0.01 for v in mn], [v + 0.01 for v in mx]
    rays, sweeps = spec["rays"], spec["sweeps"]
    if not rays and not sweeps:
        return {"pass": True, "note": "no rays or sweeps in spec"}
    results, fails, warns = [], [], []
    passed = {}
    for r in rays:
        d = Vector(r["dir"]).normalized()
        loc, nrm, idx, dist = bvh.ray_cast(Vector(r["origin"]), d, r["max_dist"])
        hit = loc is not None
        detail = {"name": r["name"], "expect": r["expect"], "hit": hit,
                  "hit_point": [round(v, 3) for v in loc] if hit else None}
        if r["expect"] == "clear":
            good = not hit
            if good and not seg_crosses_box(r["origin"], d, r["max_dist"], pad_mn, pad_mx):
                good = False
                detail["mismatch"] = "never crosses the part's bounding box, so 'clear' proves nothing (typo in origin/dir?)"
        else:
            good = hit
            for ax, want in r["hit_at"].items():
                if hit and abs(loc["xyz".index(ax)] - want) > r["tol"]:
                    good = False
                    detail["mismatch"] = f"{ax} = {loc['xyz'.index(ax)]:.3f}, expected {want} (tol {r['tol']})"
        detail["pass"] = good
        for k in ("why", "control"):
            if r.get(k):
                detail[k] = r[k]
        if r.get("positive_control"):
            detail["positive_control"] = True
        passed[r["name"]] = good
        if not good:
            fails.append(f"ray '{r['name']}': expected {r['expect']}, "
                         + (detail.get("mismatch") or ("hit at " + str(detail["hit_point"]) if hit else "no hit")))
        results.append(detail)
    sweep_out = []
    for s in sweeps:
        a, b = Vector(s["from"]), Vector(s["to"])
        d = Vector(s["dir"]).normalized()
        n = max(1, int(round((b - a).length / s["step"])))
        offsets = [Vector((0, 0, 0))]
        if s["radius_mm"] > 0:
            helper = Vector((1, 0, 0)) if abs(d.x) < 0.9 else Vector((0, 1, 0))
            u = d.cross(helper).normalized()
            w = d.cross(u).normalized()
            offsets += [(u * math.cos(k * math.pi / 4) + w * math.sin(k * math.pi / 4)) * s["radius_mm"]
                        for k in range(8)]
        blocked, missed, total = [], 0, 0
        for k in range(n + 1):
            base = a.lerp(b, k / n)
            for off in offsets:
                p = base + off
                total += 1
                if not seg_crosses_box(p, d, s["max_dist"], pad_mn, pad_mx):
                    missed += 1
                    continue
                loc, nrm, idx, dist = bvh.ray_cast(p, d, s["max_dist"])
                if loc is None or any(in_box(loc, box) for box in s["allow_hits_in"]):
                    continue
                blocked.append({"ray_from": [round(v, 2) for v in p], "hit": [round(v, 3) for v in loc]})
        good = not blocked and not missed
        sweep_out.append({"name": s["name"], "rays": total, "blocked": len(blocked), "missed_part": missed,
                          "first_blocks": blocked[:5], "why": s.get("why"), "pass": good})
        passed[s["name"]] = good
        if blocked:
            fails.append(f"sweep '{s['name']}': {len(blocked)} of {total} rays blocked, first at {blocked[0]['hit']}")
        if missed:
            fails.append(f"sweep '{s['name']}': {missed} of {total} rays never cross the part's bounding box "
                         f"(check from/to/dir; a ray that misses the part proves nothing)")
    controls = [r for r in rays if r.get("positive_control") and r["expect"] == "hit"]
    clears = [r for r in rays if r["expect"] == "clear"] + sweeps
    if clears and not any(passed[c["name"]] for c in controls):
        fails.append("no working positive control: add a ray with \"positive_control\": true that must hit solid "
                     "material beside each opening, or the 'clear' results prove nothing")
    for t in clears:
        c = t.get("control")
        if c and not passed.get(c, False):
            fails.append(f"'{t['name']}': its control '{c}' did not hit where expected, so its clear result is "
                         f"unproven")
    return {"rays": results, "sweeps": sweep_out,
            "positive_controls_passing": sum(1 for c in controls if passed[c["name"]]),
            "pass": not fails, "fails": fails, "warns": warns}


def relief_grid(r):
    """Yield (origin, direction, along_n_height_fn) for a relief row in either form."""
    if "normal" in r:
        n = Vector(r["normal"]).normalized()
        up = Vector(r.get("up") or ((0, 1, 0) if abs(n.z) > 0.9 else (0, 0, 1)))
        right = up.cross(n).normalized()
        up = n.cross(right).normalized()
        c = Vector(r["center_mm"])
        w, h = r["size_mm"]
        surf = Vector(r["surface_point"]).dot(n)
        us = [-w / 2 + k * r["step_mm"] for k in range(int(w / r["step_mm"]) + 1)]
        vs = [-h / 2 + k * r["step_mm"] for k in range(int(h / r["step_mm"]) + 1)]
        for u in us:
            for v in vs:
                p = c + right * u + up * v
                yield p + n * 50.0, -n, (lambda loc, n=n, surf=surf: loc.dot(n) - surf)
        return
    ax = "xyz".index(r["axis"])
    s = -1.0 if r["viewer"] == "-" else 1.0
    others = [i for i in range(3) if i != ax]
    (u0, u1), (v0, v1) = r["region"]["xyz"[others[0]]], r["region"]["xyz"[others[1]]]
    step = r["step_mm"]
    d = [0.0, 0.0, 0.0]
    d[ax] = -s
    for i in range(int((u1 - u0) / step + 1e-9) + 1):
        for j in range(int((v1 - v0) / step + 1e-9) + 1):
            o = [0.0, 0.0, 0.0]
            o[others[0]], o[others[1]] = u0 + i * step, v0 + j * step
            o[ax] = r["surface"] + s * 50.0
            yield Vector(o), Vector(d), (lambda loc, ax=ax, s=s: (loc[ax] - r["surface"]) * s)


def check_relief(ctx):
    """Relief polarity: is a region raised above, cut into, or flush with the face
    around it? Turns a confirmed ledger answer into a test."""
    items, bvh = ctx["spec"]["relief"], ctx["bvh"]
    if not items:
        return {"pass": True, "note": "no relief checks in spec"}
    out, fails = [], []
    for r in items:
        tol = r["tol_mm"]
        counts = {"raised": 0, "recessed": 0, "flush": 0, "miss": 0}
        heights = {"raised": [], "recessed": []}
        for o, d, height in relief_grid(r):
            loc, nrm, idx, dist = bvh.ray_cast(o, d, 100.0)
            if loc is None:
                counts["miss"] += 1
                continue
            h = height(loc)
            k = "raised" if h > tol else "recessed" if h < -tol else "flush"
            counts[k] += 1
            if k in heights:
                heights[k].append(abs(h))
        hits = counts["raised"] + counts["recessed"] + counts["flush"]
        share = {k: round(counts[k] / hits, 3) if hits else 0.0 for k in ("raised", "recessed", "flush")}
        want = r["expect"]
        other = "raised" if want == "recessed" else "recessed"
        med = sorted(heights[want])[len(heights[want]) // 2] if heights[want] else None
        polarity_ok = hits > 0 and share[want] >= r["min_share"] and share[other] < 0.01
        depth_ok = r.get("depth_mm") is None or (med is not None and abs(med - r["depth_mm"]) <= max(tol, 0.05))
        good = polarity_ok and depth_ok
        row = {"name": r["name"], "expect": want, "share": share,
               "median_relief_mm": round(med, 3) if med is not None else None,
               "expected_relief_mm": r.get("depth_mm"), "rays": hits + counts["miss"], "hits": hits, "pass": good}
        if r.get("why"):
            row["why"] = r["why"]
        out.append(row)
        if hits == 0:
            fails.append(f"relief '{r['name']}': no ray hit the part in this region (check axis, viewer, region)")
        elif not polarity_ok:
            found = max(("raised", "recessed"), key=lambda k: share[k])
            fails.append(f"relief '{r['name']}': expected {want}, found {share['raised'] * 100:.0f}% raised / "
                         f"{share['recessed'] * 100:.0f}% recessed"
                         + (f" (mostly {found})" if share[found] > 0 else " (flat)"))
        elif not depth_ok:
            fails.append(f"relief '{r['name']}': {want} as expected, but {med:.3f} mm deep/high, expected "
                         f"{r['depth_mm']} mm")
    return {"checks": out, "pass": not fails, "fails": fails}


def check_glb(path, stl_dims):
    """The GLB preview must be in metres: glTF ignores Blender's unit scale."""
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    bpy.ops.import_scene.gltf(filepath=path)
    pts = [o.matrix_world @ v.co for o in bpy.context.scene.objects if o.type == 'MESH' for v in o.data.vertices]
    if not pts:
        return {"pass": False, "fails": ["GLB has no mesh"]}
    dims = [max(p[i] for p in pts) - min(p[i] for p in pts) for i in range(3)]
    want = sorted(d / 1000.0 for d in stl_dims)
    got = sorted(dims)                       # glTF is Y-up, so compare sorted extents
    good = all(abs(g - w) <= max(1e-6, w * 1e-3) for g, w in zip(got, want))
    out = {"dims_m": [round(d, 6) for d in dims], "expected_m": [round(w, 6) for w in want], "pass": good}
    if not good:
        ratio = got[-1] / want[-1] if want[-1] else 0
        out["fails"] = [f"GLB is {ratio:.0f}x the expected size (glTF ignores the unit scale: export a 0.001-scaled copy)"]
    return out


CHECKS = [("mesh", check_mesh), ("envelope", check_envelope), ("thin+gaps", check_thin_and_gaps),
          ("overhang", check_overhang), ("rays", check_rays), ("relief", check_relief)]


def finish(rep, fails, warns, out_path):
    rep["summary"] = {"pass": not fails, "fails": fails, "warns": warns}
    if out_path:
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(rep, f, indent=1)
    print("PRINT_CHECK_JSON " + json.dumps(rep["summary"]))
    sys.stdout.flush()
    sys.exit(0 if not fails else 1)


def main():
    a = parse_args()
    raw = {}
    if a.spec:
        with open(a.spec) as f:
            raw = json.load(f)
    if a.process:
        raw["process"] = a.process
    spec, limits, errors, warns = specmod.validate(raw)
    rep = {"file": os.path.abspath(a.stl), "process": spec.get("process"), "limits": limits}
    if errors:
        print(f"print_check {os.path.basename(a.stl)}: the spec has {len(errors)} problem(s); nothing was checked")
        for e in errors:
            print("  FAIL " + e)
        print(f"RESULT: FAIL ({len(errors)})")
        finish(rep, errors, warns, a.out)
    bm = load_mesh(a.stl)
    if len(bm.faces) == 0:
        print(f"print_check {os.path.basename(a.stl)}: FAIL, the STL has no triangles")
        finish(rep, ["[mesh] the STL has no triangles"], warns, a.out)
    xs, ys, zs = [v.co.x for v in bm.verts], [v.co.y for v in bm.verts], [v.co.z for v in bm.verts]
    ctx = {"bm": bm, "bvh": BVHTree.FromBMesh(bm), "spec": spec, "limits": limits,
           "vert_sets": [set(v.index for v in f.verts) for f in bm.faces],
           "bbox": ([min(xs), min(ys), min(zs)], [max(xs), max(ys), max(zs)])}
    for key, fn in CHECKS:
        res = fn(ctx)
        if key == "thin+gaps":
            rep["thin"], rep["gaps"] = res
        else:
            rep[key] = res
    bm.free()
    if a.glb and os.path.exists(a.glb):
        rep["glb"] = check_glb(a.glb, rep["envelope"]["dims"])
    fails = []
    for key in ("mesh", "envelope", "thin", "gaps", "overhang", "rays", "relief", "glb"):
        if key in rep:
            fails += [f"[{key}] {m}" for m in rep[key].get("fails", [])]
            warns += [f"[{key}] {m}" for m in rep[key].get("warns", [])]

    m, e, t, g, o = rep["mesh"], rep["envelope"], rep["thin"], rep["gaps"], rep["overhang"]
    ok = lambda x: "PASS" if x["pass"] else "FAIL"  # noqa: E731
    lines = [f"print_check {os.path.basename(a.stl)} ({spec['process']})",
             f"  mesh      {ok(m)}  shells {m['shells']}, non-manifold {m['non_manifold_edges']}, flipped "
             f"{m['inconsistent_winding_edges']}, self-int {m['self_intersections']}, volume {m['volume_mm3']} mm3, "
             f"{m['triangles']} tris",
             f"  envelope  {ok(e)}  {e['dims'][0]} x {e['dims'][1]} x {e['dims'][2]} mm",
             f"  thin      {ok(t)}  {t['too_thin']} too thin, {t['tips']} sharp tips, {t['fragile']} fragile "
             f"(< {limits['min_wall_mm']} mm), {t['accepted_tris']} accepted tris",
             f"  gaps      {ok(g)}  {g['regions']} narrower than {limits['min_gap_mm']} mm, {g['crevices']} "
             f"hairline corners, {g['accepted_tris']} accepted tris",
             f"  overhang  {ok(o)}  {o['unsupported_mm2']} mm2" + ("" if o["gate"] else " (reported only)"),
             f"  rays      {ok(rep['rays'])}  positive controls passing: {rep['rays'].get('positive_controls_passing', 0)}",
             f"  relief    {ok(rep['relief'])}  "
             + ", ".join(f"{c['name']}: {c['median_relief_mm'] if c['median_relief_mm'] is not None else '-'} mm"
                         for c in rep["relief"].get("checks", []))]
    if "glb" in rep:
        lines.append(f"  glb       {ok(rep['glb'])}  {rep['glb']['dims_m']} m")
    lines += [f"  FAIL {x}" for x in fails] + [f"  warn {x}" for x in warns]
    lines.append("RESULT: " + ("PASS" if not fails else f"FAIL ({len(fails)})"))
    print("\n".join(lines))
    finish(rep, fails, warns, a.out)


main()
