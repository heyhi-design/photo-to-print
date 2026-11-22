"""partlib: reusable Blender helpers for building small printable parts.

A project's build script imports it (kit.py tells Blender where it is):

    import partlib as pl
    pl.setup_mm_scene()                       # 1 Blender unit = 1 mm
    body = pl.box("body", -10, 10, -4, 4, 0, 4, coll)
    pl.boolean(body, pl.hole("h1", (6, 0, 4), (0, 0, -1), 2.2, 4, coll), 'DIFFERENCE', "hole 1")
    pl.boolean(body, pl.place_text("label", "BR2", coll, "+Z", (0, 0, 4), 1.5, 0.3, "cut"), 'DIFFERENCE', "label")

Every helper was proven on a real build; the rules behind them (boolean order,
bevel order, fonts, GLB scale) are in references/blender-gotchas.md.
"""

import math
import os
import sys

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
            remove_obj(cube)
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
    bpy.context.view_layer.update()            # removed objects can leave None entries until an update
    for o in bpy.context.view_layer.objects:
        if o is not None:
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


def _axis_vector(axis):
    if isinstance(axis, str):
        return Vector({'X': (1, 0, 0), 'Y': (0, 1, 0), 'Z': (0, 0, 1)}[axis.upper()])
    v = Vector(axis)
    if v.length < 1e-9:
        raise ValueError("axis must be 'X', 'Y', 'Z' or a non-zero vector")
    return v.normalized()


def cylinder(name, axis, center, r, length, coll, segs=48, r_top=None):
    """Closed cylinder (or cone, with r_top) along axis 'X' | 'Y' | 'Z' or any
    direction vector, centred at center."""
    r_top = r if r_top is None else r_top
    ring = [(math.cos(2 * math.pi * i / segs), math.sin(2 * math.pi * i / segs)) for i in range(segs)]
    verts = [(r * c, r * s, -length / 2) for c, s in ring] + [(r_top * c, r_top * s, length / 2) for c, s in ring]
    faces = [list(range(segs)), list(range(2 * segs - 1, segs - 1, -1))]
    faces += [[i, (i + 1) % segs, segs + (i + 1) % segs, segs + i] for i in range(segs)]
    ob = obj_from_pydata(name, verts, faces, coll)
    rot = Vector((0, 0, 1)).rotation_difference(_axis_vector(axis)).to_matrix().to_4x4()
    ob.data.transform(Matrix.Translation(Vector(center)) @ rot)
    return ob


def hole(name, surface_point, direction, d, depth, coll, segs=48, counterbore=None, countersink=None):
    """A hole cutter: starts 0.5 mm outside surface_point and runs `depth` mm along
    `direction` (into the part). Use a depth past the far side for a through hole.
    counterbore=(diameter, depth), or countersink=(mouth diameter, included angle
    in degrees, e.g. 90), shapes the mouth. Returns the cutter: DIFFERENCE it from
    the body with boolean()."""
    v = _axis_vector(direction)
    p = Vector(surface_point)
    total = depth + 0.5
    cut = cylinder(name, v, p + v * (total / 2 - 0.5), d / 2, total, coll, segs)
    if counterbore:
        cd, cdep = counterbore
        cb = cylinder(name + "_cb", v, p + v * ((cdep + 0.5) / 2 - 0.5), cd / 2, cdep + 0.5, coll, segs)
        boolean(cut, cb, 'UNION', name + " counterbore")
    if countersink:
        dm, angle = countersink
        h = (dm - d) / 2 / math.tan(math.radians(angle / 2))
        cone = cylinder(name + "_cs", v, p + v * (h / 2), dm / 2, h, coll, segs, r_top=d / 2)
        lip = cylinder(name + "_lip", v, p - v * 0.25, dm / 2, 0.5, coll, segs)
        boolean(cone, lip, 'UNION', name + " countersink lip")
        boolean(cut, cone, 'UNION', name + " countersink")
    return cut


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


def copy_obj(ob, name, coll=None):
    new = ob.copy()
    new.data = ob.data.copy()
    new.name = name
    (coll or ob.users_collection[0]).objects.link(new)
    return new


def mirror_copy(ob, axis, name=None, about=0.0):
    """A mirrored copy across the plane axis = about (axis 'X' | 'Y' | 'Z'). Normals are fixed."""
    k = "XYZ".index(axis.upper())
    s = [1.0, 1.0, 1.0]
    s[k] = -1.0
    t = [0.0, 0.0, 0.0]
    t[k] = 2 * about
    new = copy_obj(ob, name or ob.name + "_mirror")
    new.data.transform(Matrix.Translation(Vector(t)) @ Matrix.Diagonal((*s, 1.0)))
    new.data.flip_normals()
    return new


def array_copies(ob, count, offset, name=None):
    """count copies of ob (including the original) spaced by offset [x, y, z]."""
    out = [ob]
    for i in range(1, count):
        c = copy_obj(ob, f"{name or ob.name}_{i}")
        c.data.transform(Matrix.Translation(Vector(offset) * i))
        out.append(c)
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
    """Cast softness on a clean primitive, before any boolean touches it.
    On FDM, a bevel on bottom edges creates overhangs; bevel top edges only there."""
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


def _solvers():
    """Boolean solvers this Blender has, best first (MANIFOLD needs Blender 4.5+)."""
    have = set(bpy.types.BooleanModifier.bl_rna.properties["solver"].enum_items.keys())
    return [s for s in ('MANIFOLD', 'EXACT') if s in have] or ['EXACT']


def boolean(target, tool, op, label):
    """Apply one boolean ('UNION' | 'DIFFERENCE' | 'INTERSECT'), best solver first;
    validate the result; delete the tool. Raises if every solver fails."""
    before = bm_stats(target)
    backup = target.data.copy()
    st = None
    for solver in _solvers():
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
        raise RuntimeError(f"boolean failed for {label}: {st} (does the tool actually touch the body?)")
    bpy.data.meshes.remove(backup)
    remove_obj(tool)
    return st


# ------------------------------------------------------------------ text ----

FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "C:/Windows/Fonts/ARLRDBD.TTF", "C:/Windows/Fonts/arialbd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]


def find_font():
    """A bold font that exists on this machine (rounded where available), or None."""
    return next((p for p in FONT_CANDIDATES if os.path.exists(p)), None)


def text_mesh(name, text, coll, font_path=None, spacing=1.0, resolution=6, extrude=0.5, allow_builtin_font=False):
    """Text as a closed mesh in local XY (glyphs), Z = -extrude..+extrude.
    Uses font_path, else the first bold font find_font() locates. Raises rather
    than silently using Blender's built-in font, whose strokes are too thin to
    print at small sizes, unless allow_builtin_font=True."""
    font_path = font_path or find_font()
    if font_path is None and not allow_builtin_font:
        raise RuntimeError("no bold font found: pass font_path=<a .ttf/.otf on this machine> "
                           "(or allow_builtin_font=True for large lettering)")
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
        except Exception as ex:                       # noqa: BLE001
            bpy.data.curves.remove(cu)
            raise RuntimeError(f"font {font_path!r} would not load ({ex})") from ex
        cu.font = font
        log(f"font for {name}: {os.path.basename(font_path)}")
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


def place_text(name, text, coll, face, center, height, depth, mode, font_path=None, up=None, spacing=1.0,
               allow_builtin_font=False):
    """Lettering on a face, ready to boolean into the body.

    face:   '+X' '-X' '+Y' '-Y' '+Z' '-Z', the outward side the text is read from
    center: a point on that face where the text is centred
    height: letter height in mm (scaled uniformly, so glyph proportions are kept)
    depth:  how far it is cut in (mode 'cut') or stands up (mode 'raised'), mm
    up:     reading-up direction on the face (default: +Z on side faces, +Y on top/bottom)
    Returns the cutter/adder: DIFFERENCE it for 'cut', UNION it for 'raised'.
    """
    normals = {'+X': (1, 0, 0), '-X': (-1, 0, 0), '+Y': (0, 1, 0), '-Y': (0, -1, 0), '+Z': (0, 0, 1),
               '-Z': (0, 0, -1)}
    if face not in normals or mode not in ('cut', 'raised'):
        raise ValueError("face must be one of +X -X +Y -Y +Z -Z, and mode 'cut' or 'raised'")
    n = Vector(normals[face])
    u = Vector(up) if up else (Vector((0, 1, 0)) if abs(n.z) > 0.5 else Vector((0, 0, 1)))
    right = u.cross(n).normalized()
    u = n.cross(right).normalized()
    ob = text_mesh(name, text, coll, font_path=font_path, spacing=spacing, extrude=0.5,
                   allow_builtin_font=allow_builtin_font)
    me = ob.data
    xs = [v.co.x for v in me.vertices]
    ys = [v.co.y for v in me.vertices]
    s = height / (max(ys) - min(ys))
    cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
    inside, outside = (depth, 0.3) if mode == 'cut' else (0.1, depth)   # mm into / out of the face
    thickness = inside + outside
    basis = Matrix(((right.x, u.x, n.x, 0), (right.y, u.y, n.y, 0), (right.z, u.z, n.z, 0), (0, 0, 0, 1)))
    mid = Vector(center) + n * ((outside - inside) / 2)
    me.transform(Matrix.Translation(mid) @ basis @ Matrix.Diagonal((s, s, thickness, 1.0))
                 @ Matrix.Translation((-cx, -cy, 0.0)))
    log(f"{name}: '{text}' {height} mm high, {mode} {depth} mm on {face}, {(max(xs) - min(xs)) * s:.2f} mm long")
    return ob


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
    tmp = copy_obj(ob, "TMP_glb_export")
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


def print_log():
    """The build log as readable lines (call at the end of a build script)."""
    for line in LOG:
        print("  " + line)
    sys.stdout.flush()
