"""print_check: verify an exported STL is printable and matches its spec.

Runs inside Blender's bundled Python (no pip installs), on the STL file itself,
so it checks what will actually print, however the part was modelled.

    <blender> --background --factory-startup --python-exit-code 2 \
        --python print_check.py -- exports/part_v1.stl --spec checks.json --out reports/check_v1.json

Exit code 0 = every check passed, 1 = at least one FAIL, 2 = the script crashed.
Usually run through `kit.py verify <project>`.

Checks
  mesh      single shell, 0 non-manifold edges, 0 loose geometry, 0 self-intersections,
            positive volume (outward normals)
  envelope  bounding box against spec["envelope"] (dims and/or min/max, with tol)
  thin      material thinner than the process minimums (ray inward from every triangle)
  gaps      grooves/clearances narrower than the process minimum (ray outward)
  overhang  downward faces steeper than the process limit (FDM gate; resin reports only)
  rays      single-ray assertions: "clear" or "hit" (optionally at a coordinate)
  sweeps    a line of rays that must stay clear, with allowed-hit boxes

The positive-control rule: if any ray or sweep expects "clear", at least one
ray marked "positive_control": true must hit where expected. A clear result
with no working positive control proves nothing (it also passes when the rays
miss the part entirely), so the rays group FAILS without one.
"""

import argparse
import json
import math
import os
import sys
from collections import defaultdict

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

PRESETS = {
    # min_feature: positive detail below this usually does not form at all.
    # min_wall: below this it forms but is fragile (review it).
    # min_gap: grooves / clearances below this fill in (resin) or fuse (FDM).
    "resin": {"min_feature_mm": 0.2, "min_wall_mm": 0.4, "min_gap_mm": 0.3, "overhang_deg": 45, "overhang_gate": False},
    "fdm": {"min_feature_mm": 0.4, "min_wall_mm": 0.8, "min_gap_mm": 0.5, "overhang_deg": 45, "overhang_gate": True},
}


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(prog="print_check")
    ap.add_argument("stl")
    ap.add_argument("--spec", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--process", default=None, help="resin | fdm (overrides spec)")
    ap.add_argument("--glb", default=None, help="preview GLB to check is in metres (STL dims / 1000)")
    return ap.parse_args(argv)


def load_mesh(path):
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    bpy.ops.wm.stl_import(filepath=path)
    obs = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    if not obs:
        raise RuntimeError(f"no mesh imported from {path}")
    bm = bmesh.new()
    for o in obs:
        tmp = bmesh.new()
        tmp.from_mesh(o.data)
        tmp.transform(o.matrix_world)
        me = bpy.data.meshes.new("tmp")
        tmp.to_mesh(me)
        tmp.free()
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
            cur = stack.pop()
            for e in cur.edges:
                for g in e.link_faces:
                    if g.index not in seen:
                        seen.add(g.index)
                        stack.append(g)
    return count


def check_mesh(bm, bvh):
    nm = sum(1 for e in bm.edges if len(e.link_faces) != 2)
    loose_v = sum(1 for v in bm.verts if not v.link_edges)
    loose_e = sum(1 for e in bm.edges if not e.link_faces)
    vol = bm.calc_volume(signed=True)
    tri_verts = [set(v.index for v in f.verts) for f in bm.faces]
    pairs = bvh.overlap(bvh)
    real = [(i, j) for i, j in pairs if i < j and not (tri_verts[i] & tri_verts[j])]
    sample = []
    for i, _ in real[:5]:
        c = bm.faces[i].calc_center_median()
        sample.append([round(c.x, 2), round(c.y, 2), round(c.z, 2)])
    n_shells = shells(bm)
    fails = []
    if n_shells != 1:
        fails.append(f"{n_shells} separate shells (a printable part is ONE body: union, don't join)")
    if nm:
        fails.append(f"{nm} non-manifold edges")
    if loose_v or loose_e:
        fails.append(f"loose geometry: {loose_v} verts, {loose_e} edges")
    if real:
        fails.append(f"{len(real)} self-intersecting triangle pairs, e.g. at {sample[:2]}")
    if vol <= 0:
        fails.append("volume is not positive (normals point inward)")
    return {"shells": n_shells, "non_manifold_edges": nm, "loose_verts": loose_v, "loose_edges": loose_e,
            "self_intersections": len(real), "self_int_sample": sample,
            "volume_mm3": round(vol, 3), "triangles": len(bm.faces),
            "pass": not fails, "fails": fails}


def bbox(bm):
    xs = [v.co.x for v in bm.verts]
    ys = [v.co.y for v in bm.verts]
    zs = [v.co.z for v in bm.verts]
    return [min(xs), min(ys), min(zs)], [max(xs), max(ys), max(zs)]


def check_envelope(bm, spec):
    mn, mx = bbox(bm)
    dims = [mx[i] - mn[i] for i in range(3)]
    out = {"min": [round(v, 3) for v in mn], "max": [round(v, 3) for v in mx],
           "dims": [round(v, 3) for v in dims]}
    env = spec.get("envelope")
    if not env:
        out.update({"pass": True, "note": "no envelope in spec: dimensions reported, not checked"})
        return out
    tol = float(env.get("tol_mm", 0.3))
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


def in_box(p, box):
    return all(box["min"][i] - 1e-9 <= p[i] <= box["max"][i] + 1e-9 for i in range(3))


def cluster(samples, accepted):
    """samples: list of (point, value). Groups on a 0.5 mm grid, worst first."""
    groups = defaultdict(list)
    for p, d in samples:
        groups[(round(p.x * 2) / 2, round(p.y * 2) / 2, round(p.z * 2) / 2)].append(d)
    rows = []
    for k, ds in groups.items():
        reason = next((a.get("why", "accepted") for a in accepted if in_box(k, a)), None)
        rows.append({"at_mm": list(k), "tris": len(ds), "min_mm": round(min(ds), 3), "accepted": reason})
    rows.sort(key=lambda r: r["min_mm"])
    return rows


def facing_hit(bvh, bm, f, origin, direction, max_dist, vert_sets, exiting):
    """First hit along direction that is a genuinely opposite wall: skips
    triangles that share a vertex with f (corner grazes at concave edges) and
    hits whose normal is not roughly opposed (angled neighbours)."""
    start, travelled = origin, 0.0
    for _ in range(4):
        loc, nrm, idx, dist = bvh.ray_cast(start, direction, max_dist - travelled)
        if loc is None:
            return None
        travelled += dist
        if idx is not None and (vert_sets[idx] & vert_sets[f.index]):
            start = loc + direction * 1e-5
            continue
        facing = nrm.dot(direction)
        # inward scan (exiting=True): leaves the material through a wall facing away from f.
        # outward scan: meets a wall facing back toward f across the gap.
        if (exiting and facing > 0.3) or (not exiting and facing < -0.3):
            return travelled
        start = loc + direction * 1e-5        # grazing / same-facing hit: look further
    return None


def thickness_scans(bm, bvh, limits, spec):
    """Inward ray from each triangle centroid: local material thickness.
    Outward ray: width of the gap/groove in front of the face."""
    min_feat, min_wall, min_gap = limits["min_feature_mm"], limits["min_wall_mm"], limits["min_gap_mm"]
    vert_sets = [set(v.index for v in g.verts) for g in bm.faces]
    thin, gaps = [], []
    for f in bm.faces:
        if f.calc_area() < 2e-4:
            continue
        c, n = f.calc_center_median(), f.normal
        d = facing_hit(bvh, bm, f, c - n * 1e-5, -n, max(min_wall, 1.0) * 2, vert_sets, True)
        if d is not None and d < min_wall:
            thin.append((c, d))
        # outward: the wall across the gap faces back toward f (normal opposite to travel)
        d = facing_hit(bvh, bm, f, c + n * 1e-5, n, max(min_gap, 1.0) * 2, vert_sets, False)
        if d is not None and d < min_gap:
            gaps.append((c, d))
    accepted = spec.get("accepted_thin", [])
    thin_rows = cluster(thin, accepted)
    gap_rows = cluster(gaps, spec.get("accepted_gaps", []))
    below_feat = [r for r in thin_rows if r["min_mm"] < min_feat and not r["accepted"]]
    thin_out = {"min_feature_mm": min_feat, "min_wall_mm": min_wall,
                "regions_below_min_wall": len(thin_rows),
                "regions_below_min_feature_unaccepted": len(below_feat),
                "worst": thin_rows[:10],
                "pass": not below_feat,
                "fails": [f"material {r['min_mm']} mm thick near {r['at_mm']} (< {min_feat}; thicken it, "
                          f"or record it in the clarity ledger and add it to accepted_thin)" for r in below_feat[:5]]}
    gap_out = {"min_gap_mm": min_gap, "regions_below_min_gap": len(gap_rows), "worst": gap_rows[:10],
               "pass": True,
               "warns": [f"gap {r['min_mm']} mm near {r['at_mm']} may fill in / fuse" for r in gap_rows
                         if not r["accepted"]][:5]}
    return thin_out, gap_out


def check_overhang(bm, limits):
    deg = limits["overhang_deg"]
    zmin = min(v.co.z for v in bm.verts)
    lim = -math.sin(math.radians(90 - deg))      # normal.z below this = steeper than the limit
    total = sum(f.calc_area() for f in bm.faces)
    over = 0.0
    for f in bm.faces:
        if f.normal.z < lim and f.calc_center_median().z > zmin + 0.02:
            over += f.calc_area()
    out = {"limit_deg_from_vertical": deg, "unsupported_mm2": round(over, 3),
           "share_pct": round(100 * over / total, 2) if total else 0.0, "gate": limits["overhang_gate"]}
    out["pass"] = (over < 0.01) if limits["overhang_gate"] else True
    if limits["overhang_gate"] and over >= 0.01:
        out["fails"] = [f"{over:.2f} mm2 of downward faces steeper than {deg} deg need supports"]
    return out


def cast(bvh, origin, direction, max_dist=1000.0):
    d = Vector(direction).normalized()
    loc, nrm, idx, dist = bvh.ray_cast(Vector(origin), d, max_dist)
    return loc, nrm, dist


def check_rays(bvh, spec):
    rays, sweeps = spec.get("rays", []), spec.get("sweeps", [])
    if not rays and not sweeps:
        return {"pass": True, "note": "no rays or sweeps in spec"}
    results, fails = [], []
    has_clear = any(r.get("expect") == "clear" for r in rays) or bool(sweeps)
    controls_ok = 0
    for r in rays:
        loc, nrm, dist = cast(bvh, r["origin"], r["dir"], r.get("max_dist", 1000.0))
        hit = loc is not None
        good = (not hit) if r["expect"] == "clear" else hit
        detail = {"name": r["name"], "expect": r["expect"], "hit": hit,
                  "hit_point": [round(v, 3) for v in loc] if hit else None}
        if hit and r["expect"] == "hit" and r.get("hit_at"):
            tol = float(r.get("tol", 0.05))
            for ax, want in r["hit_at"].items():
                got = loc["xyz".index(ax)]
                if abs(got - want) > tol:
                    good = False
                    detail["mismatch"] = f"{ax} = {got:.3f}, expected {want} (tol {tol})"
        detail["pass"] = good
        if r.get("why"):
            detail["why"] = r["why"]
        if r.get("positive_control"):
            detail["positive_control"] = True
            controls_ok += 1 if good else 0
        if not good:
            fails.append(f"ray '{r['name']}': expected {r['expect']}, "
                         + (detail.get("mismatch") or ("hit at " + str(detail["hit_point"]) if hit else "no hit")))
        results.append(detail)
    sweep_out = []
    for s in sweeps:
        a, b = Vector(s["from"]), Vector(s["to"])
        length = (b - a).length
        n = max(1, int(round(length / float(s.get("step", 0.1)))))
        blocked = []
        for k in range(n + 1):
            p = a.lerp(b, k / n)
            loc, nrm, dist = cast(bvh, p, s["dir"], s.get("max_dist", 1000.0))
            if loc is None:
                continue
            if any(in_box(loc, box) for box in s.get("allow_hits_in", [])):
                continue
            blocked.append({"ray_from": [round(v, 2) for v in p], "hit": [round(v, 3) for v in loc]})
        good = not blocked
        sweep_out.append({"name": s["name"], "rays": n + 1, "blocked": len(blocked), "first_blocks": blocked[:5],
                          "why": s.get("why"), "pass": good})
        if not good:
            fails.append(f"sweep '{s['name']}': {len(blocked)} of {n + 1} rays blocked, first at {blocked[0]['hit']}")
    if has_clear and controls_ok == 0:
        fails.append("no working positive control: add a ray with \"positive_control\": true that must hit a "
                     "known surface, or the 'clear' results prove nothing")
    return {"rays": results, "sweeps": sweep_out, "positive_controls_passing": controls_ok,
            "pass": not fails, "fails": fails}


def check_relief(bvh, spec):
    """Relief polarity: is a region raised above, cut into, or flush with the
    face around it? Turns a confirmed ledger answer ("the letters are cut in")
    into a test, so polarity cannot silently flip between question and print.

    {"name": ..., "axis": "y", "viewer": "-",        # looking at the -Y face from -Y
     "region": {"x": [-3.8, 3.8], "z": [1.8, 3.2]},  # the two other axes, world mm
     "surface": -5.75,                                # the surrounding face's coordinate on axis
     "expect": "recessed" | "raised", "depth_mm": 0.2, "step_mm": 0.05}
    """
    items = spec.get("relief", [])
    if not items:
        return {"pass": True, "note": "no relief checks in spec"}
    out, fails = [], []
    for r in items:
        ax = "xyz".index(r["axis"])
        s = -1.0 if r.get("viewer", "-") == "-" else 1.0
        others = [i for i in range(3) if i != ax]
        (u0, u1) = r["region"]["xyz"[others[0]]]
        (v0, v1) = r["region"]["xyz"[others[1]]]
        step = float(r.get("step_mm", 0.05))
        tol = float(r.get("tol_mm", 0.05))
        surface = float(r["surface"])
        direction = [0.0, 0.0, 0.0]
        direction[ax] = -s                         # travel from the viewer toward the part
        counts = {"raised": 0, "recessed": 0, "flush": 0, "miss": 0}
        heights = {"raised": [], "recessed": []}
        u = u0
        while u <= u1 + 1e-9:
            v = v0
            while v <= v1 + 1e-9:
                o = [0.0, 0.0, 0.0]
                o[others[0]], o[others[1]] = u, v
                o[ax] = surface + s * 50.0
                loc, nrm, dist = cast(bvh, o, direction, 100.0)
                if loc is None:
                    counts["miss"] += 1
                else:
                    h = (loc[ax] - surface) * s     # + = toward the viewer = stands up
                    k = "raised" if h > tol else "recessed" if h < -tol else "flush"
                    counts[k] += 1
                    if k in heights:
                        heights[k].append(abs(h))
                v += step
            u += step
        hits = counts["raised"] + counts["recessed"] + counts["flush"]
        share = {k: round(counts[k] / hits, 3) if hits else 0.0 for k in ("raised", "recessed", "flush")}
        want, other = r["expect"], ("raised" if r["expect"] == "recessed" else "recessed")
        med = sorted(heights[want])[len(heights[want]) // 2] if heights[want] else None
        good = hits > 0 and share[want] >= float(r.get("min_share", 0.05)) and share[other] < 0.01
        if good and r.get("depth_mm") is not None and med is not None:
            good = abs(med - float(r["depth_mm"])) <= max(tol, 0.05)
        row = {"name": r["name"], "expect": want, "share": share, "median_relief_mm": round(med, 3) if med else None,
               "expected_relief_mm": r.get("depth_mm"), "rays": hits + counts["miss"], "pass": good}
        if r.get("why"):
            row["why"] = r["why"]
        out.append(row)
        if not good:
            found = max(("raised", "recessed"), key=lambda k: share[k])
            fails.append(f"relief '{r['name']}': expected {want}"
                         + (f" {r['depth_mm']} mm" if r.get("depth_mm") is not None else "")
                         + f", found {share['raised'] * 100:.0f}% raised / {share['recessed'] * 100:.0f}% recessed"
                         + (f" (mostly {found})" if share[found] > 0 else " (flat)"))
    return {"checks": out, "pass": not fails, "fails": fails}


def drop_examples(spec):
    """Template placeholders (names starting with _example) are never run as tests."""
    dropped = 0
    for key in ("rays", "sweeps", "relief"):
        keep = [r for r in spec.get(key, []) if not str(r.get("name", "")).startswith("_example")]
        dropped += len(spec.get(key, [])) - len(keep)
        spec[key] = keep
    env = spec.get("envelope") or {}
    if env and all(v is None for v in env.get("dims_mm", [None])) and "min_mm" not in env and "max_mm" not in env:
        spec.pop("envelope")
    return dropped


def check_glb(path, stl_dims):
    """The GLB preview must be in metres: glTF ignores Blender's unit scale, and
    an unscaled export comes out 1000x too large."""
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    bpy.ops.import_scene.gltf(filepath=path)
    pts = [o.matrix_world @ v.co for o in bpy.context.scene.objects if o.type == 'MESH' for v in o.data.vertices]
    if not pts:
        return {"pass": False, "fails": ["GLB has no mesh"]}
    dims = [max(p[i] for p in pts) - min(p[i] for p in pts) for i in range(3)]
    want = sorted(d / 1000.0 for d in stl_dims)
    got = sorted(dims)                      # glTF swaps Y/Z (Y-up), so compare sorted extents
    good = all(abs(g - w) <= max(1e-6, w * 1e-3) for g, w in zip(got, want))
    out = {"dims_m": [round(d, 6) for d in dims], "expected_m": [round(w, 6) for w in want], "pass": good}
    if not good:
        ratio = got[-1] / want[-1] if want[-1] else 0
        out["fails"] = [f"GLB is {ratio:.0f}x the expected size (glTF ignores the unit scale: export a 0.001-scaled copy)"]
    return out


def main():
    a = parse_args()
    spec = json.load(open(a.spec)) if a.spec else {}
    dropped = drop_examples(spec)
    process = (a.process or spec.get("process") or "resin").lower()
    limits = dict(PRESETS[process])
    limits.update({k: v for k, v in spec.get("limits", {}).items() if k in limits})
    bm = load_mesh(a.stl)
    bvh = BVHTree.FromBMesh(bm)
    rep = {"file": os.path.abspath(a.stl), "process": process, "limits": limits}
    rep["mesh"] = check_mesh(bm, bvh)
    rep["envelope"] = check_envelope(bm, spec)
    rep["thin"], rep["gaps"] = thickness_scans(bm, bvh, limits, spec)
    rep["overhang"] = check_overhang(bm, limits)
    rep["rays"] = check_rays(bvh, spec)
    rep["relief"] = check_relief(bvh, spec)
    bm.free()
    if a.glb and os.path.exists(a.glb):
        rep["glb"] = check_glb(a.glb, rep["envelope"]["dims"])
    fails, warns = [], []
    for key in ("mesh", "envelope", "thin", "gaps", "overhang", "rays", "relief", "glb"):
        if key not in rep:
            continue
        fails += [f"[{key}] {m}" for m in rep[key].get("fails", [])]
        warns += [f"[{key}] {m}" for m in rep[key].get("warns", [])]
    if dropped:
        warns.append(f"[spec] {dropped} template _example entries ignored: write the real tests from CLARITY.md")
    if not spec.get("rays") and not spec.get("sweeps") and not spec.get("relief"):
        warns.append("[spec] no function or relief tests: this only proves the mesh is printable, not that it is right")
    rep["summary"] = {"pass": not fails, "fails": fails, "warns": warns}

    m, e = rep["mesh"], rep["envelope"]
    lines = [f"print_check {os.path.basename(a.stl)} ({process})",
             f"  mesh      {'PASS' if m['pass'] else 'FAIL'}  shells {m['shells']}, non-manifold {m['non_manifold_edges']}, "
             f"self-int {m['self_intersections']}, volume {m['volume_mm3']} mm3, {m['triangles']} tris",
             f"  envelope  {'PASS' if e['pass'] else 'FAIL'}  {e['dims'][0]} x {e['dims'][1]} x {e['dims'][2]} mm",
             f"  thin      {'PASS' if rep['thin']['pass'] else 'FAIL'}  {rep['thin']['regions_below_min_wall']} regions < "
             f"{limits['min_wall_mm']} mm, {rep['thin']['regions_below_min_feature_unaccepted']} unaccepted < {limits['min_feature_mm']} mm",
             f"  gaps      WARN x{len(rep['gaps']['warns'])}" if rep['gaps']['warns'] else "  gaps      PASS",
             f"  overhang  {'PASS' if rep['overhang']['pass'] else 'FAIL'}  {rep['overhang']['unsupported_mm2']} mm2"
             + ("" if rep['overhang']['gate'] else " (reported only for resin)"),
             f"  rays      {'PASS' if rep['rays']['pass'] else 'FAIL'}  positive controls passing: "
             f"{rep['rays'].get('positive_controls_passing', 0)}",
             f"  relief    {'PASS' if rep['relief']['pass'] else 'FAIL'}  "
             + ", ".join(f"{c['name']}: {c['median_relief_mm']} mm" for c in rep['relief'].get('checks', []))]
    if "glb" in rep:
        lines.append(f"  glb       {'PASS' if rep['glb']['pass'] else 'FAIL'}  {rep['glb']['dims_m']} m")
    lines += [f"  FAIL {x}" for x in fails] + [f"  warn {x}" for x in warns]
    lines.append("RESULT: " + ("PASS" if not fails else f"FAIL ({len(fails)})"))
    print("\n".join(lines))
    if a.out:
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        json.dump(rep, open(a.out, "w"), indent=1)
    print("PRINT_CHECK_JSON " + json.dumps(rep["summary"]))
    sys.stdout.flush()
    sys.exit(0 if not fails else 1)


main()
