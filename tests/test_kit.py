"""Tests for the parts of the kit that don't need Blender.

    python3 -m unittest discover -s tests -v

The Blender-side checks are proven by `python3 scripts/kit.py selftest`, which
builds a good part and a defective one and confirms the checks tell them apart.
"""

import json
import os
import py_compile
import subprocess
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
sys.path.insert(0, SCRIPTS)

import photo_tools  # noqa: E402


def read(path):
    with open(path) as f:
        return f.read()


def ruler_image(px_per_mm, width=200, height=900, path=None):
    """A synthetic ruler: dark 1 mm ticks on a light strip, every 5th tick longer."""
    im = np.full((height, width), 225, dtype=np.uint8)
    y, k = 10.0, 0
    while y < height - 10:
        length = 120 if k % 5 == 0 else 70
        im[int(round(y)):int(round(y)) + 2, 0:length] = 30
        y += px_per_mm
        k += 1
    Image.fromarray(im).save(path)
    return path


class RulerTests(unittest.TestCase):
    def test_tick_period_recovers_known_spacing(self):
        for ppmm in (12.5, 16.5, 21.0):
            with self.subTest(ppmm=ppmm), tempfile.TemporaryDirectory() as tmp:
                path = ruler_image(ppmm, path=os.path.join(tmp, "ruler.png"))
                prof = np.asarray(Image.open(path).convert("L"), dtype=float)[:, 0:60].mean(axis=1)
                period, snr = photo_tools.tick_period(prof, 5, 80)
                self.assertAlmostEqual(period, ppmm, delta=0.15)
                self.assertGreater(snr, 8)

    def test_ruler_command_reports_px_per_mm(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = ruler_image(16.5, path=os.path.join(tmp, "ruler.png"))
            out = subprocess.run([sys.executable, os.path.join(SCRIPTS, "photo_tools.py"), "ruler", path,
                                  "--box", "0", "0", "60", "900", "--axis", "y"],
                                 capture_output=True, text=True, check=True).stdout
            value = float(out.split(":")[1].split("px/mm")[0])
            self.assertAlmostEqual(value, 16.5, delta=0.15)


class InfoTests(unittest.TestCase):
    def test_flags_a_reduced_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "small.jpg")
            Image.new("RGB", (1500, 2000), (128, 128, 128)).save(path)
            out = subprocess.run([sys.executable, os.path.join(SCRIPTS, "photo_tools.py"), "info", path],
                                 capture_output=True, text=True, check=True).stdout
            self.assertIn("ASK FOR ORIGINALS", out)


class ProjectTests(unittest.TestCase):
    def test_new_project_has_every_file_and_no_placeholders(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = os.path.join(tmp, "part")
            subprocess.run([sys.executable, os.path.join(SCRIPTS, "kit.py"), "new", proj, "--name", "test-part"],
                           capture_output=True, text=True, check=True)
            for rel in ("CLARITY.md", "README.md", "checks.json", "scripts/build_part.py"):
                path = os.path.join(proj, rel)
                self.assertTrue(os.path.exists(path), rel)
                self.assertNotIn("{{", read(path), rel)
            spec = json.loads(read(os.path.join(proj, "checks.json")))
            self.assertEqual(spec["part"]["name"], "test-part")
            self.assertEqual(spec["process"], "resin")

    def test_new_refuses_to_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = os.path.join(tmp, "part")
            cmd = [sys.executable, os.path.join(SCRIPTS, "kit.py"), "new", proj, "--name", "p"]
            subprocess.run(cmd, capture_output=True, check=True)
            self.assertNotEqual(subprocess.run(cmd, capture_output=True).returncode, 0)


class FileTests(unittest.TestCase):
    def test_every_script_compiles(self):
        for name in sorted(os.listdir(SCRIPTS)):
            if name.endswith(".py"):
                with self.subTest(script=name):
                    py_compile.compile(os.path.join(SCRIPTS, name), doraise=True,
                                       cfile=os.path.join(tempfile.gettempdir(), name + "c"))

    def test_json_files_parse(self):
        for rel in ("templates/checks.json", "examples/caliper-checks.json", "examples/caliper-checks-v1-session.json"):
            with self.subTest(file=rel):
                json.loads(read(os.path.join(ROOT, rel)))


if __name__ == "__main__":
    unittest.main()
