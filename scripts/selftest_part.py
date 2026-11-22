"""Build the self-test fixtures (run by `kit.py selftest`, inside Blender).

A 20 x 10 x 5 mm block with a slot through it, a pin across the slot, and "AB"
cut 0.3 mm into the -Y face: good.stl. Then the same part with the two kinds of
defect the first real project shipped: a crossmember across the slot, and the
letters standing up instead of cut in: bad.stl. print_check must PASS the first
and FAIL the second for those reasons, or the kit is not to be trusted.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mathutils import Matrix   # noqa: E402

import partlib as pl            # noqa: E402

OUT = sys.argv[sys.argv.index("--") + 1]


def text_on_minus_y(coll, cut):
    t = pl.text_mesh("CUT_text" if cut else "ADD_text", "HI", coll, extrude=0.5)
    me = t.data
    xs = [v.co.x for v in me.vertices]
    ys = [v.co.y for v in me.vertices]
    sx, sy = 4.0 / (max(xs) - min(xs)), 2.5 / (max(ys) - min(ys))
    cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
    y_in, y_out = (-5.0 + 0.3, -5.5) if cut else (-4.9, -5.3)
    rot = Matrix(((1, 0, 0, 0), (0, 0, -1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))   # glyph y -> +Z, extrude -> -Y
    depth = (y_in - y_out)
    me.transform(Matrix.Translation((0.0, (y_in + y_out) / 2, 2.5)) @ rot
                 @ Matrix.Diagonal((sx, sy, depth / 1.0, 1.0)) @ Matrix.Translation((-cx, -cy, 0.0)))
    return t


def make(name, defects):
    pl.setup_mm_scene(delete_startup_cube=True)
    coll = pl.fresh_collection("SELFTEST")
    body = pl.box("body", -10, 10, -5, 5, 0, 5, coll)
    pl.boolean(body, pl.box("CUT_slot", -6, 6, -1, 1, -1, 6, coll), 'DIFFERENCE', "slot")
    pl.boolean(body, pl.cylinder("ADD_pin", 'Y', (0, 0, 4.0), 0.4, 3.0, coll), 'UNION', "pin")
    pl.boolean(body, text_on_minus_y(coll, cut=not defects), 'UNION' if defects else 'DIFFERENCE', "text")
    if defects:
        pl.boolean(body, pl.box("ADD_crossmember", -0.5, 0.5, -1.2, 1.2, 0, 1.0, coll), 'UNION', "crossmember")
    pl.export_stl(body, os.path.join(OUT, name + ".stl"))


make("good", defects=False)
make("bad", defects=True)
print("SELFTEST_BUILT " + OUT)
