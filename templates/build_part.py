"""Parametric build of {{PART}}. The single source of truth for the geometry.

Headless (normal):   python3 "<skill>/scripts/kit.py" build <project>
Live, through a Blender MCP (execute_blender_code), pass the kit's scripts folder in:
    P = "<project>/scripts/build_part.py"
    ns = {"__file__": P, "KIT": "<skill>/scripts"}; exec(compile(open(P).read(), P, "exec"), ns)
    result = ns["result"]

Rebuilds only the PART collection, so reruns are idempotent. Exports the STL (mm),
the GLB (m) and a build record (so kit.py verify can tell a stale STL from a fresh
one), named by checks.json. Every number lives in PARAMS with its source and
confidence; nothing is typed into the geometry code directly.

Frame: X = length, Y = width, Z = height. Origin at the part centre in X and Y,
Z = 0 on the face that sits on the build plate. 1 Blender unit = 1 mm.
"""

import datetime
import hashlib
import json
import os
import sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(globals().get("__file__", "scripts/build_part.py")))
PROJECT = os.path.dirname(HERE)
if "--project" in sys.argv:
    PROJECT = sys.argv[sys.argv.index("--project") + 1]
KIT = globals().get("KIT") or os.environ.get("PHOTO_TO_PRINT_KIT")
if not KIT or not os.path.exists(os.path.join(KIT, "partlib.py")):
    raise SystemExit("Can't find the photo-to-print kit. Run this through `kit.py build <project>`, or when running "
                     "it live pass KIT=<skill>/scripts in the exec namespace.")
sys.path.insert(0, KIT)

import bpy                      # noqa: E402,F401
import partlib as pl            # noqa: E402

PARAMS = {
    # name: value,          # source (photo / caliper / CLARITY row), confidence (high / medium / low)
    "L": 20.0,              # CLARITY C2 caliper reading. high
    "W": 10.0,              # CLARITY C2. high
    "H": 5.0,               # CLARITY C2. high
}

COLL = "PART"


def build():
    P = PARAMS
    pl.setup_mm_scene(delete_startup_cube=bool(globals().get("DELETE_CUBE", False)))
    coll = pl.fresh_collection(COLL)

    # 1. Blockout: the main body. Compare its silhouette against the photos before cutting.
    body = pl.box("body", -P["L"] / 2, P["L"] / 2, -P["W"] / 2, P["W"] / 2, 0.0, P["H"], coll)

    # 2. Soften primitives BEFORE any boolean (never bevel the finished mesh). On FDM, a bevel
    #    on the bottom edges makes overhangs; bevel only the top edges there, or skip it.
    # pl.bevel_obj(body, 0.12, "body")

    # 3. Cuts and additions, one validated boolean each:
    # pl.boolean(body, pl.hole("hole_1", (6, 0, P["H"]), (0, 0, -1), 2.2, P["H"] + 1, coll), 'DIFFERENCE', "hole 1")
    # pl.boolean(body, pl.cylinder("pin", 'Y', (0, 0, 4), 0.4, 6, coll), 'UNION', "pin")
    # pl.boolean(body, pl.place_text("label", "AB", coll, "+Z", (0, 0, P["H"]), 1.5, 0.3, "cut"),
    #            'DIFFERENCE', "label")        # font: pl.find_font() unless you pass font_path

    body.name = "{{PART}}"
    return body


def export(body):
    with open(os.path.join(PROJECT, "checks.json")) as f:
        part = json.load(f).get("part") or {}
    stl = os.path.join(PROJECT, part.get("stl", "exports/{name}_{version}.stl").format(
        name=part.get("name", "part"), version=part.get("version", "v1")))
    pl.export_stl(body, stl)
    pl.export_glb(body, os.path.splitext(stl)[0] + ".glb")
    script = os.path.join(PROJECT, "scripts", "build_part.py")
    with open(script, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    with open(os.path.splitext(stl)[0] + ".build.json", "w") as f:
        json.dump({"script_sha256": digest, "built_at": datetime.datetime.now().isoformat(timespec="seconds"),
                   "stl": os.path.basename(stl), "blender": bpy.app.version_string}, f, indent=1)
    return stl


body = build()
st = pl.bm_stats(body)
result = {"stats": st, "log": pl.LOG}
if globals().get("DO_EXPORT", True):
    result["stl"] = export(body)
pl.print_log()
print(f"built {body.name}: {st['faces']} faces, volume {st['volume']:.3f} mm3, non-manifold {st['non_manifold']}"
      + (f"; exported {os.path.basename(result['stl'])}" if "stl" in result else ""))
