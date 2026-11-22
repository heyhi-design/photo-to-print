"""Parametric build of {{PART}}. The single source of truth for the geometry.

Headless (normal):   python3 <kit>/kit.py build <project>
Live, through the Blender MCP (execute_blender_code):
    P = "<project>/scripts/build_part.py"
    ns = {"__file__": P}; exec(compile(open(P).read(), P, "exec"), ns); result = ns["result"]

Rebuilds only the PART collection, so reruns are idempotent. Exports the STL (mm)
and GLB (m) named by checks.json. Every number lives in PARAMS with its source
and confidence; nothing is typed into the geometry code directly.

Frame: X = length, Y = width, Z = height. Origin at the part centre in X and Y,
Z = 0 on the face that sits on the build plate. 1 Blender unit = 1 mm.
"""

import json
import os
import sys

# Project root = the folder above scripts/, wherever it has moved to.
HERE = os.path.dirname(os.path.abspath(globals().get("__file__", "scripts/build_part.py")))
PROJECT = os.path.dirname(HERE)
if "--project" in sys.argv:
    PROJECT = sys.argv[sys.argv.index("--project") + 1]
KIT = os.environ.get("PHOTO_TO_PRINT_KIT", "{{KIT}}")
sys.path.insert(0, KIT)

import bpy                      # noqa: E402
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

    # 2. Soften primitives BEFORE any boolean (never bevel the finished mesh).
    # pl.bevel_obj(body, 0.12, "body")

    # 3. Cuts and additions, one validated boolean each (MANIFOLD, then EXACT):
    # pl.boolean(body, pl.box("CUT_slot", ...), 'DIFFERENCE', "slot")
    # pl.boolean(body, pl.cylinder("ADD_pin", 'Y', (0, 0, 4), 0.4, 6, coll), 'UNION', "pin")
    # Text: t = pl.text_mesh("CUT_text", "abc", coll, font_path=<rounded bold font>); scale/place; boolean.

    body.name = "{{PART}}"
    return body


def export(body):
    spec = json.load(open(os.path.join(PROJECT, "checks.json")))
    part = spec.get("part", {})
    stl = os.path.join(PROJECT, part.get("stl", "exports/{name}_{version}.stl").format(
        name=part.get("name", "part"), version=part.get("version", "v1")))
    pl.export_stl(body, stl)
    pl.export_glb(body, os.path.splitext(stl)[0] + ".glb")
    return stl


body = build()
st = pl.bm_stats(body)
result = {"stats": st, "log": pl.LOG}
if globals().get("DO_EXPORT", True):
    result["stl"] = export(body)
print("BUILD_JSON " + json.dumps(result, default=str))
