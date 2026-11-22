"""Build the self-test fixtures (run by `kit.py selftest`, inside Blender).

A 20 x 10 x 5 mm block with a slot through it, a pin across the slot, and "HI"
cut 0.3 mm into the -Y face: good.stl. Then the same part with the two kinds of
defect the first real project shipped: a crossmember across the slot, and the
letters standing up instead of cut in: bad.stl. print_check must PASS the first
and FAIL the second for those reasons (and reject the broken specs kit.py feeds
it), or the kit is not to be trusted on this machine.
"""

import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import partlib as pl            # noqa: E402

OUT = sys.argv[sys.argv.index("--") + 1]


def make(name, defects):
    pl.setup_mm_scene(delete_startup_cube=True)
    coll = pl.fresh_collection("SELFTEST")
    body = pl.box("body", -10, 10, -5, 5, 0, 5, coll)
    pl.boolean(body, pl.box("CUT_slot", -6, 6, -1, 1, -1, 6, coll), 'DIFFERENCE', "slot")
    pl.boolean(body, pl.cylinder("ADD_pin", 'Y', (0, 0, 4.0), 0.4, 3.0, coll), 'UNION', "pin")
    # Blender's built-in font, so the fixture is identical on every machine; large enough to print.
    text = pl.place_text("text", "HI", coll, "-Y", (0, -5, 2.5), 2.5, 0.3, "raised" if defects else "cut",
                         allow_builtin_font=True)
    pl.boolean(body, text, 'UNION' if defects else 'DIFFERENCE', "text")
    if defects:
        pl.boolean(body, pl.box("ADD_crossmember", -0.5, 0.5, -1.2, 1.2, 0, 1.0, coll), 'UNION', "crossmember")
    pl.export_stl(body, os.path.join(OUT, name + ".stl"))


make("good", defects=False)
make("bad", defects=True)
print("SELFTEST_BUILT " + OUT)
