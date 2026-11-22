"""partlib: reusable Blender helpers for building small printable parts.

Import from a project's build script (runs inside Blender, live or headless):

    import sys, os
    sys.path.insert(0, "<skill>/scripts")
    import partlib as pl

Every helper here was proven on the 2026-11 brake caliper build (Blender 5.2.1).
Units: call setup_mm_scene() first so 1 Blender unit = 1 mm.

Rules baked in (each one cost time to learn):
  * Booleans: MANIFOLD solver first, EXACT fallback, and every result is checked
    (0 non-manifold edges, 0 loose geometry, volume changed and positive).
  * Union every detail into ONE body. A plain join leaves overlapping shells that
    pass a naive watertight check and print badly.
  * Bevel clean primitives BEFORE they meet a boolean. A whole-mesh bevel after
    the booleans collapsed to ~0 (clamped) or self-intersected (unclamped).
  * Text: Blender's built-in font gives strokes too thin for resin at ~1.3 mm
    letter height. Load a rounded bold font. Text `offset` thickens strokes but
    makes glyph outlines self-overlap, so prefer a heavier font.
  * GLB ignores the scene unit scale: export a 0.001-scaled copy or the file
    comes out 1000x too large. STL: global_scale 1, use_scene_unit False.
"""

import math
import os

import bmesh
import bpy
from mathutils import Matrix, Vector

LOG = []


def log(msg):
    LOG.append(str(msg))


# ---------------------------------------------------------------- scene ----

def setup_mm_scene(delete_startup_cube=False):
    """1 BU = 1 mm. Deletes the startup Cube only when told to (ask first)."""
    sc = bpy.context.scene
    us = sc.unit_settings
    us.system = 'METRIC'
    us.scale_length = 0.001
    us.length_unit = 'MILLIMETERS'
    if delete_startup_cube:
        cube = bpy.data.objects.get("Cube")
        if cube is not None:
            me = cube.data
            bpy.data.objects.remove(cube, do_unlink=True)
            if me is not None and me.users == 0:
                bpy.data.meshes.remove(me)
            log("deleted startup Cube")
    return sc


def fresh_collection(name):
    """Empty (or create) a collection so reruns are idempotent. Touches nothing else."""
    coll = bpy.data.collections.get(name)
    if coll is not None:
        for ob in list(coll.objects):
            remove_obj(ob)
    else:
        coll = bpy.data.collections.new(name)
    if coll.name not in bpy.context.scene.collection.children:
        bpy.context.scene.collection.children.link(coll)
    return coll


def remove_obj(ob):
    data = ob.data
    bpy.data.objects.remove(ob, do_unlink=True)
    if isinstance(data, bpy.types.Mesh) and data.users == 0:
        bpy.data.meshes.remove(data)
    elif isinstance(data, bpy.types.Curve) and data.users == 0:
        bpy.data.curves.remove(data)


def select_only(ob):
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob


# ---------------------------------------------------------- primitives ----

def obj_from_bm(name, bm, coll):
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    return ob


def obj_from_pydata(name, verts, faces, coll):
    bm = bmesh.new()
    bv = [bm.verts.new(v) for v in verts]
    for f in faces:
        bm.faces.new([bv[i] for i in f])
    return obj_from_bm(name, bm, coll)


def prism(name, poly_xy, z0, z1, coll):
    """Extrude a planar polygon [(x, y), ...] from z0 to z1."""
    n = len(poly_xy)
    verts = [(x, y, z0) for x, y in poly_xy] + [(x, y, z1) for x, y in poly_xy]
    faces = [list(range(n)), list(range(2 * n - 1, n - 1, -1))]
    for i in range(n):
        j = (i + 1) % n
        faces.append([i, j, n + j, n + i])
    return obj_from_pydata(name, verts, faces, coll)


def box(name, x0, x1, y0, y1, z0, z1, coll):
    return prism(name, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], z0, z1, coll)


def rounded_rect(cx, cy, sx, sy, r, segs=8):
    """Outline of a rounded rectangle (CCW)."""
    pts = []
    hx, hy = sx / 2 - r, sy / 2 - r
    for (ox, oy, a0) in ((hx, -hy, -90), (hx, hy, 0), (-hx, hy, 90), (-hx, -hy, 180)):
        for i in range(segs + 1):
            a = math.radians(a0 + 90 * i / segs)
            pts.append((cx + ox + r * math.cos(a), cy + oy + r * math.sin(a)))
    return pts


def cylinder(name, axis, center, r, length, coll, segs=48):
    """Closed cylinder along 'X' | 'Y' | 'Z', centred at center."""
    circle = [(r * math.cos(2 * math.pi * i / segs), r * math.sin(2 * math.pi * i / segs)) for i in range(segs)]
    ob = prism(name, circle, -length / 2, length / 2, coll)
    rot = {'Z': Matrix.Identity(4),
           'X': Matrix.Rotation(math.radians(90), 4, 'Y'),
           'Y': Matrix.Rotation(math.radians(-90), 4, 'X')}[axis]
    ob.data.transform(Matrix.Translation(Vector(center)) @ rot)
    return ob


def dome(name, center_surface, outward, base_d, height, coll):
    """Spherical cap (screw head, rivet) standing on a surface point."""
    a = base_d / 2
    R = (a * a + height * height) / (2 * height)
    c = Vector(center_surface) + Vector(outward).normalized() * (height - R)
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=40, v_segments=20, radius=R)
    bmesh.ops.translate(bm, verts=bm.verts, vec=c)
    return obj_from_bm(name, bm, coll)


def hull_obj(name, points, coll):
    bm = bmesh.new()
    for p in points:
        bm.verts.new(p)
    res = bmesh.ops.convex_hull(bm, input=bm.verts)
    junk = [g for g in res["geom_interior"] + res["geom_unused"] if isinstance(g, bmesh.types.BMVert)]
    if junk:
        bmesh.ops.delete(bm, geom=junk, context='VERTS')
    return obj_from_bm(name, bm, coll)


def offset_convex(poly, d):
    """Offset a CCW convex polygon outward by d (negative d shrinks it)."""
    n = len(poly)
    lines = []
    for i in range(n):
        p, q = Vector(poly[i]), Vector(poly[(i + 1) % n])
        t = (q - p).normalized()
        lines.append((p + Vector((t.y, -t.x)) * d, t))
    out = []
    for i in range(n):
        p1, t1 = lines[i - 1]
        p2, t2 = lines[i]
        den = t1.x * t2.y - t1.y * t2.x
        s = ((p2.x - p1.x) * t2.y - (p2.y - p1.y) * t2.x) / den
        out.append(tuple(p1 + t1 * s))
    return out


# --------------------------------------------------- checks + booleans ----

def bm_stats(ob):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    st = {"non_manifold": sum(1 for e in bm.edges if len(e.link_faces) != 2),
          "loose_v": sum(1 for v in bm.verts if not v.link_edges),
          "loose_e": sum(1 for e in bm.edges if not e.link_faces),
          "volume": bm.calc_volume(signed=True), "faces": len(bm.faces)}
    bm.free()
    return st


def apply_modifiers(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    dg.update()
    me_new = bpy.data.meshes.new_from_object(ob.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
    old = ob.data
    ob.modifiers.clear()
    ob.data = me_new
    me_new.name = ob.name
    if old.users == 0:
        bpy.data.meshes.remove(old)


def bevel_obj(ob, width, label, segs=2, angle_deg=40.0):
    """Cast softness on a clean primitive, before any boolean touches it."""
    vol0 = bm_stats(ob)["volume"]
    mod = ob.modifiers.new("bevel", 'BEVEL')
    mod.width = width
    mod.segments = segs
    mod.limit_method = 'ANGLE'
    mod.angle_limit = math.radians(angle_deg)
    mod.use_clamp_overlap = False
    apply_modifiers(ob)
    st = bm_stats(ob)
    log(f"bevel {width} on {label}: removed {vol0 - st['volume']:.3f} mm3")
    if st["non_manifold"] or st["loose_v"] or st["loose_e"]:
        raise RuntimeError(f"bevel broke {label}: {st}")
    return ob


def boolean(target, tool, op, label):
    """Apply one boolean ('UNION' | 'DIFFERENCE' | 'INTERSECT'), MANIFOLD then
    EXACT; validate the result; delete the tool. Raises if both solvers fail."""
    before = bm_stats(target)
    backup = target.data.copy()
    st = None
    for solver in ('MANIFOLD', 'EXACT'):
        mod = target.modifiers.new("bool", 'BOOLEAN')
        mod.operation = op
        mod.solver = solver
        mod.object = tool
        apply_modifiers(target)
        st = bm_stats(target)
        changed = abs(st["volume"] - before["volume"]) > 1e-6
        ok = (st["non_manifold"] == 0 and st["loose_v"] == 0 and st["loose_e"] == 0
              and st["faces"] > 0 and st["volume"] > 0 and changed)
        if ok:
            log(f"{label}: {op} {solver} ok, vol {before['volume']:.3f} -> {st['volume']:.3f}")
            break
        log(f"{label}: {op} {solver} FAILED {st}; retrying")
        old = target.data
        target.data = backup.copy()
        if old.users == 0:
            bpy.data.meshes.remove(old)
    else:
        raise RuntimeError(f"boolean failed for {label}: {st}")
    bpy.data.meshes.remove(backup)
    remove_obj(tool)
    return st


def text_mesh(name, text, coll, font_path=None, spacing=1.0, resolution=6, extrude=0.5):
    """Text as a closed mesh in local XY (glyphs), Z = -extrude..+extrude.
    Caller scales and places it (see place_on_face). Returns the object."""
    cu = bpy.data.curves.new(name + "_curve", 'FONT')
    cu.body = text
    cu.size = 1.0
    cu.extrude = extrude
    cu.space_character = spacing
    cu.resolution_u = resolution
    font = None
    if font_path:
        try:
            font = bpy.data.fonts.load(font_path, check_existing=True)
            cu.font = font
        except Exception as ex:                       # noqa: BLE001
            log(f"font load failed ({ex}); built-in font used: CHECK STROKE WIDTH")
    try:
        cu.fill_mode = 'BOTH'
    except Exception:                                  # noqa: BLE001
        pass
    tmp = bpy.data.objects.new("tmp_" + name, cu)
    coll.objects.link(tmp)
    dg = bpy.context.evaluated_depsgraph_get()
    dg.update()
    me = bpy.data.meshes.new_from_object(tmp.evaluated_get(dg), depsgraph=dg)
    bpy.data.objects.remove(tmp, do_unlink=True)
    bpy.data.curves.remove(cu)
    if font is not None and font.users == 0:
        bpy.data.fonts.remove(font)
    bm = bmesh.new()
    bm.from_mesh(me)
    bpy.data.meshes.remove(me)
    return obj_from_bm(name, bm, coll)


# -------------------------------------------------------------- export ----

def export_stl(ob, path):
    """Millimetre STL of one object, modifiers applied, Z up."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    select_only(ob)
    bpy.ops.wm.stl_export(filepath=path, export_selected_objects=True, global_scale=1.0,
                          use_scene_unit=False, apply_modifiers=True,
                          forward_axis='Y', up_axis='Z', ascii_format=False)
    return os.path.getsize(path)


def export_glb(ob, path):
    """GLB in metres (glTF ignores the scene unit scale, so scale a copy by 0.001)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    coll = ob.users_collection[0]
    tmp = ob.copy()
    tmp.data = ob.data.copy()
    tmp.name = "TMP_glb_export"
    coll.objects.link(tmp)
    tmp.data.transform(ob.matrix_world)
    tmp.data.transform(Matrix.Scale(0.001, 4))
    tmp.matrix_world = Matrix.Identity(4)
    select_only(tmp)
    try:
        bpy.ops.export_scene.gltf(filepath=path, export_format='GLB', use_selection=True,
                                  export_apply=True, export_yup=True)
    finally:
        remove_obj(tmp)
    select_only(ob)
    return os.path.getsize(path)
