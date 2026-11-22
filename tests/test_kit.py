"""Tests for the parts of the kit that don't need Blender.

    python3 -m unittest discover -s tests -v

The Blender-side checks are proven by `python3 scripts/kit.py selftest`, which
builds a good part and a defective one and confirms the checks tell them apart.
"""

import json
import os
import py_compile
import re
import subprocess
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image

sys.dont_write_bytecode = True
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
sys.path.insert(0, SCRIPTS)

import photo_tools  # noqa: E402
import spec  # noqa: E402

ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")


def read(path):
    with open(path) as f:
        return f.read()


def run(*args):
    return subprocess.run([sys.executable] + list(args), capture_output=True, text=True, env=ENV)


def ruler_image(px_per_mm, path, height=1400, axis="y"):
    """A synthetic ruler: dark 1 mm ticks on a light strip, every 5th tick longer."""
    im = np.full((height, 200), 225, dtype=np.uint8)
    y, k = 10.0, 0
    while y < height - 10:
        length = 120 if k % 5 == 0 else 70
        im[int(round(y)):int(round(y)) + max(2, int(px_per_mm / 8)), 0:length] = 30
        y += px_per_mm
        k += 1
    img = Image.fromarray(im)
    if axis == "x":
        img = img.transpose(Image.Transpose.ROTATE_90)
    img.save(path)
    return path


def ruler_value(out):
    return float(out.split(": ", 1)[1].split(" px/mm")[0])


class RulerTests(unittest.TestCase):
    def test_reads_the_true_scale_from_far_to_close_up(self):
        # Close-up photos once read as half or a third of the true scale (a harmonic).
        for ppmm in (12.5, 16.5, 21.0, 32.0, 40.0, 45.0, 60.0, 100.0):
            with self.subTest(ppmm=ppmm), tempfile.TemporaryDirectory() as tmp:
                path = ruler_image(ppmm, os.path.join(tmp, "ruler.png"))
                r = run(os.path.join(SCRIPTS, "photo_tools.py"), "ruler", path, "--box", "0", "0", "60", "1400",
                        "--axis", "y")
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertAlmostEqual(ruler_value(r.stdout), ppmm, delta=0.2 + ppmm * 0.003)

    def test_horizontal_ruler(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = ruler_image(16.5, os.path.join(tmp, "ruler.png"), axis="x")
            r = run(os.path.join(SCRIPTS, "photo_tools.py"), "ruler", path, "--box", "0", "140", "1400", "200",
                    "--axis", "x")
            self.assertAlmostEqual(ruler_value(r.stdout), 16.5, delta=0.15)

    def test_short_box_is_a_message_not_a_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = ruler_image(16.5, os.path.join(tmp, "ruler.png"))
            r = run(os.path.join(SCRIPTS, "photo_tools.py"), "ruler", path, "--box", "0", "0", "60", "10", "--axis", "y")
            self.assertNotIn("Traceback", r.stderr)


class PhotoTests(unittest.TestCase):
    def test_info_flags_a_reduced_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "small.jpg")
            Image.new("RGB", (1500, 2000), (128, 128, 128)).save(path)
            r = run(os.path.join(SCRIPTS, "photo_tools.py"), "info", path)
            self.assertIn("ASK FOR ORIGINALS", r.stdout)

    def test_info_turns_photos_upright(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "phone.jpg")
            exif = Image.Exif()
            exif[0x0112] = 6                      # stored sideways, shown rotated 90 degrees
            Image.new("RGB", (400, 300), (128, 128, 128)).save(path, exif=exif)
            im, orientation = photo_tools.open_photo(path)
            self.assertEqual((orientation, im.size), (6, (300, 400)))
            self.assertIn("turned upright", run(os.path.join(SCRIPTS, "photo_tools.py"), "info", path).stdout)

    def test_unreadable_photo_is_a_message_and_others_still_listed(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "a.heic"), "wb") as f:
                f.write(b"not really an image")
            Image.new("RGB", (4032, 3024)).save(os.path.join(tmp, "b.jpg"))
            r = run(os.path.join(SCRIPTS, "photo_tools.py"), "info", os.path.join(tmp, "*"))
            self.assertNotIn("Traceback", r.stderr)
            self.assertIn("a.heic", r.stdout)
            self.assertIn("b.jpg", r.stdout)
            self.assertEqual(r.returncode, 1)

    def test_info_on_an_empty_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = run(os.path.join(SCRIPTS, "photo_tools.py"), "info", os.path.join(tmp, "*"))
            self.assertNotIn("Traceback", r.stderr)
            self.assertIn("no photos found", r.stdout)

    def test_annotate_labels_stay_on_the_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, out = os.path.join(tmp, "p.jpg"), os.path.join(tmp, "q.jpg")
            Image.new("RGB", (800, 600), (90, 90, 90)).save(src)
            r = run(os.path.join(SCRIPTS, "photo_tools.py"), "annotate", src, "--out", out,
                    "--mark", "790,5,WWW", "--mark", "400,300,slot, left end", "--mark", "10,590,2,40")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            with Image.open(out) as im:
                self.assertEqual(im.size, (800, 600))
            self.assertEqual(photo_tools.parse_mark("1,2,slot, left end", 9), (1.0, 2.0, "slot, left end", 9))
            self.assertEqual(photo_tools.parse_mark("1,2,7,40", 9), (1.0, 2.0, "7", 40.0))


def good_spec():
    return {
        "process": "resin",
        "envelope": {"dims_mm": [20, 10, 5]},
        "rays": [
            {"name": "control", "origin": [3, 1.5, 50], "dir": [0, 0, -1], "expect": "hit", "positive_control": True},
            {"name": "slot", "origin": [3, 0, 50], "dir": [0, 0, -1], "expect": "clear", "control": "control"}],
        "relief": [{"name": "letters", "axis": "y", "viewer": "-", "surface": -5, "region": {"x": [-2, 2], "z": [1, 3]},
                    "expect": "recessed", "depth_mm": 0.3}],
    }


class SpecTests(unittest.TestCase):
    def errors(self, s):
        return spec.validate(s)[2]

    def test_good_spec_is_clean(self):
        self.assertEqual(self.errors(good_spec()), [])

    def test_typo_in_expect_is_an_error(self):
        s = good_spec()
        s["rays"][1]["expect"] = "Clear"
        self.assertTrue(any("expect must be" in e for e in self.errors(s)))

    def test_unknown_limits_key_is_an_error(self):
        s = good_spec()
        s["limits"] = {"min_wall": 5}
        self.assertTrue(any("min_wall_mm" in e for e in self.errors(s)))

    def test_unknown_process_is_an_error_not_a_crash(self):
        s = good_spec()
        s["process"] = "sla"
        self.assertTrue(any("unknown process" in e for e in self.errors(s)))

    def test_no_tests_is_incomplete_unless_explained(self):
        self.assertTrue(any("INCOMPLETE" in e for e in self.errors({"process": "resin"})))
        self.assertEqual(self.errors({"process": "resin", "allow_untested": "fit test print only"}), [])

    def test_examples_are_ignored(self):
        s = good_spec()
        s["rays"].append({"name": "_example x", "origin": [0, 0, 0], "dir": [0, 0, 0], "expect": "maybe"})
        self.assertEqual(self.errors(s), [])

    def test_bad_values_are_errors(self):
        cases = [("rays", 1, "dir", [0, 0, 0]), ("relief", 0, "depth_mm", 0.04), ("relief", 0, "viewer", "-y"),
                 ("relief", 0, "step_mm", 0), ("rays", 1, "control", "nope")]
        for key, i, field, value in cases:
            with self.subTest(field=field):
                s = good_spec()
                s[key][i][field] = value
                self.assertTrue(self.errors(s), f"{field}={value!r} should be rejected")

    def test_null_lists_and_short_envelope(self):
        s = good_spec()
        s["sweeps"] = None
        self.assertEqual(self.errors(s), [])
        s["envelope"] = {"dims_mm": [20, 10]}
        self.assertTrue(any("envelope.dims_mm" in e for e in self.errors(s)))

    def test_view_orientation_rules(self):
        with self.assertRaises(ValueError):
            spec.view_axes({"name": "a", "face": "top"})
        with self.assertRaises(ValueError):
            spec.view_axes({"name": "a", "face": "+Z", "up": [0, 1, 0]})
        with self.assertRaises(ValueError):
            spec.view_axes({"name": "a", "face": "+Z", "right": [0, 1, 0], "up": [1, 0, 0]})
        n, _, _ = spec.view_axes({"name": "a", "face": "+Z", "right": [0, 1, 0], "up": [-1, 0, 0]})
        self.assertEqual([round(c) for c in n], [0, 0, 1])

    def test_sheet_rows_need_a_view(self):
        self.assertTrue(spec.validate_sheet([{"photo": "p.jpg", "photo_ppmm": 16, "photo_center_px": [1, 2]}], ["top"]))
        self.assertEqual(spec.validate_sheet([{"view": "top", "photo": "p.jpg", "photo_ppmm": 16,
                                               "photo_center_px": [1, 2]}], ["top"]), [])

    def test_presets_match_the_print_limits_table(self):
        presets = spec.load_presets()
        table = read(os.path.join(ROOT, "references", "print-limits.md"))
        for key in ("min_feature_mm", "min_wall_mm", "min_gap_mm"):
            row = next(line for line in table.splitlines() if f"`{key}`" in line)
            resin, fdm = [float(c) for c in re.findall(r"\|\s*([0-9.]+)\s*", row)][:2]
            self.assertEqual((resin, fdm), (presets["resin"][key], presets["fdm"][key]), key)

    def test_shipped_example_specs_are_valid(self):
        for rel in ("examples/caliper-checks.json",):
            with self.subTest(rel=rel):
                self.assertEqual(self.errors(json.loads(read(os.path.join(ROOT, rel)))), [])


class ProjectTests(unittest.TestCase):
    def new(self, tmp, name="test-part", *extra):
        proj = os.path.join(tmp, "part")
        r = run(os.path.join(SCRIPTS, "kit.py"), "new", proj, "--name", name, *extra)
        return proj, r

    def test_new_project_has_every_file_and_no_placeholders_or_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj, r = self.new(tmp)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            for rel in ("CLARITY.md", "README.md", "checks.json", "scripts/build_part.py"):
                text = read(os.path.join(proj, rel))
                self.assertNotIn("{{", text, rel)
                self.assertNotIn(SCRIPTS, text, f"{rel} must not name where the kit is installed")
            spec_ = json.loads(read(os.path.join(proj, "checks.json")))
            self.assertEqual((spec_["part"]["name"], spec_["process"]), ("test-part", "resin"))

    def test_new_rejects_unsafe_names_and_overwrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, r = self.new(tmp, 'my "best" part')
            self.assertNotEqual(r.returncode, 0)
            self.new(tmp)
            _, r = self.new(tmp)
            self.assertNotEqual(r.returncode, 0)

    def test_gate_reads_the_ledger_and_the_tests(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj, _ = self.new(tmp)
            r = run(os.path.join(SCRIPTS, "kit.py"), "gate", proj)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("open rows", r.stdout)
            clarity = os.path.join(proj, "CLARITY.md")
            text = read(clarity).replace("| OPEN |", "| CONFIRMED |").replace(
                '"(their words)" (date)', '"looks right, go" (2026-11-22)')
            with open(clarity, "w") as f:
                f.write(text)
            s = good_spec()
            s["rays"][1]["why"] = "CLARITY D1 D2 D3"
            with open(os.path.join(proj, "checks.json"), "w") as f:
                json.dump(s, f)
            r = run(os.path.join(SCRIPTS, "kit.py"), "gate", proj)
            self.assertEqual(r.returncode, 0, r.stdout)


class FileTests(unittest.TestCase):
    def test_every_script_compiles(self):
        for name in sorted(os.listdir(SCRIPTS)):
            if name.endswith(".py"):
                with self.subTest(script=name):
                    py_compile.compile(os.path.join(SCRIPTS, name), doraise=True,
                                       cfile=os.path.join(tempfile.gettempdir(), name + "c"))

    def test_json_files_parse(self):
        for rel in ("templates/checks.json", "examples/caliper-checks.json", "examples/caliper-checks-v1-session.json",
                    "scripts/presets.json"):
            with self.subTest(file=rel):
                json.loads(read(os.path.join(ROOT, rel)))


if __name__ == "__main__":
    unittest.main()
