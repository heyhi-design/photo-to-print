"""kit: one entry point for a photo-to-print project. System python3 (Pillow + numpy).

    python3 kit.py doctor                     what is installed, what is missing, how to fix it
    python3 kit.py selftest                   prove the checks catch real defects on this machine
    python3 kit.py new  <project> --name brake-caliper [--process resin|fdm]
    python3 kit.py gate <project> [--only 1|2] open ledger rows, the maker's "go", untested rows
    python3 kit.py build <project> [--blend file.blend]
                                              run <project>/scripts/build_part.py headless, export the STL
    python3 kit.py check <project>            print_check on the current version's STL
    python3 kit.py verify <project>           check + face views + review sheet (the gate artifact)

A project is a folder (see templates/): CLARITY.md (the question ledger),
README.md, checks.json (what "right" means, as tests), scripts/build_part.py,
reference/, questions/, exports/, renders/, reports/. Nothing inside it names
where the kit is installed: kit.py tells the build script (PHOTO_TO_PRINT_KIT),
so both the project and the skill can move.
"""

import argparse
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
KIT = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(KIT)
TEMPLATES = os.path.join(SKILL, "templates")
sys.path.insert(0, KIT)
import spec as specmod  # noqa: E402

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def find_blender():
    cands = [os.environ.get("BLENDER"), os.environ.get("BLENDER_PATH"),
             "/Applications/Blender.app/Contents/MacOS/Blender", shutil.which("blender")]
    cands += sorted(glob.glob(r"C:\Program Files\Blender Foundation\Blender*\blender.exe"), reverse=True)
    cands += sorted(glob.glob("/opt/blender*/blender"), reverse=True)
    for c in cands:
        if c and os.path.exists(c):
            return c
    return None


def blender_version(exe):
    out = subprocess.run([exe, "--version"], capture_output=True, text=True).stdout
    m = re.search(r"Blender (\d+)\.(\d+)(?:\.(\d+))?", out)
    return (tuple(int(g or 0) for g in m.groups()), out.splitlines()[0]) if m else (None, out[:60])


def blender_run(script, args, blend=None, quiet=True):
    exe = find_blender()
    if not exe:
        sys.exit("Blender not found. Install Blender (free, blender.org), or set BLENDER=/path/to/blender.")
    cmd = [exe, "--background"] + ([blend] if blend else ["--factory-startup"]) + \
          ["--python-exit-code", "2", "--python", script, "--"] + args
    env = dict(os.environ, PHOTO_TO_PRINT_KIT=KIT, PYTHONDONTWRITEBYTECODE="1")
    p = subprocess.run(cmd, capture_output=True, text=True, env=env)
    out = p.stdout
    if quiet:
        keep = []
        for line in out.splitlines():
            if line.startswith(("Blender ", "Read ", "Import finished", "Timer ", "Info:", "Saved ")) or not line.strip():
                continue
            if "STL import" in line or line.startswith("Fra:") or "| INFO:" in line or line.startswith("INFO "):
                continue
            keep.append(line)
        out = "\n".join(keep)
    if p.returncode == 2 or p.returncode < 0 or p.returncode > 2:
        sys.stderr.write(p.stdout[-3000:] + "\n" + p.stderr[-3000:] + "\n")
        sys.exit(f"Blender script failed (exit {p.returncode}): {os.path.basename(script)}")
    return p.returncode, out


def load_spec(project):
    path = os.path.join(project, "checks.json")
    if not os.path.exists(path):
        sys.exit(f"no checks.json in {project}. Run: kit.py new {project} --name <part>")
    with open(path) as f:
        try:
            return json.load(f), path
        except json.JSONDecodeError as ex:
            sys.exit(f"{path} is not valid JSON: {ex}")


def stl_path(project, spec, override=None):
    if override:
        return override
    part = spec.get("part") or {}
    rel = part.get("stl", "exports/{name}_{version}.stl").format(name=part.get("name", "part"),
                                                                  version=part.get("version", "v1"))
    return os.path.join(project, rel)


def sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def build_record_problem(project, stl):
    """Return a reason the STL can't be trusted to match the build script, or None."""
    script = os.path.join(project, "scripts", "build_part.py")
    rec_path = os.path.splitext(stl)[0] + ".build.json"
    if not os.path.exists(script):
        return None
    if not os.path.exists(rec_path):
        return (f"no build record next to the STL ({os.path.basename(rec_path)}); rebuild with kit.py build, or pass "
                f"--stl to check a file made elsewhere")
    with open(rec_path) as f:
        rec = json.load(f)
    if rec.get("script_sha256") != sha256(script):
        return (f"the STL was built from an older scripts/build_part.py (built {rec.get('built_at', '?')}); "
                f"run kit.py build first. If the last build failed, its error is the thing to fix")
    return None


# ---------------------------------------------------------------- commands ----

def cmd_doctor(a):
    ok = True
    exe = find_blender()
    if exe:
        ver, line = blender_version(exe)
        if ver and ver < (4, 5):
            print(f"[warn] Blender: {exe} ({line}). Older than 4.5: booleans fall back to the slower EXACT solver; "
                  f"tested on 5.2.1")
        else:
            print(f"[ok]   Blender: {exe} ({line})")
    else:
        ok = False
        print("[need] Blender not found. Install it free from blender.org, or set BLENDER=/path/to/blender")
    for mod in ("PIL", "numpy"):
        try:
            __import__(mod)
            print(f"[ok]   python3 {mod}")
        except ImportError:
            ok = False
            print(f"[need] python3 {mod}: run  python3 -m pip install --user {'pillow' if mod == 'PIL' else 'numpy'}")
    try:
        __import__("pillow_heif")
        print("[ok]   pillow-heif: iPhone HEIC photos can be read directly")
    except ImportError:
        print("[info] pillow-heif not installed: convert HEIC photos to JPEG first (see references/photo-guide.md)")
    print("[info] A live Blender connector (MCP) is optional; every step runs headless.")
    print("ready" if ok else "fix the [need] lines, then run doctor again")
    return 0 if ok else 1


def cmd_new(a):
    p = a.project
    if not NAME_RE.match(a.name):
        sys.exit("--name: letters, digits, '.', '_' and '-' only (it becomes file names), up to 64 characters")
    if os.path.abspath(p).startswith(SKILL + os.sep):
        sys.exit("put the project outside the skill folder (updating the skill would otherwise touch it)")
    if os.path.exists(os.path.join(p, "checks.json")):
        sys.exit(f"{p} already has a project; not overwriting")
    for d in ("reference", "questions", "exports", "renders", "reports", "scripts"):
        os.makedirs(os.path.join(p, d), exist_ok=True)
    subs = {"{{PART}}": a.name, "{{PROCESS}}": a.process}
    for src, dst in (("project-README.md", "README.md"), ("CLARITY.md", "CLARITY.md"),
                     ("checks.json", "checks.json"), ("build_part.py", "scripts/build_part.py")):
        with open(os.path.join(TEMPLATES, src)) as f:
            text = f.read()
        for k, v in subs.items():
            text = text.replace(k, v)
        with open(os.path.join(p, dst), "w") as f:
            f.write(text)
    print(f"new project at {p}\n  next: put the maker's ORIGINAL photos in {p}/reference/, then run\n"
          f"  python3 \"{KIT}/photo_tools.py\" info '{p}/reference/*'\n  and start the intake interview (CLARITY.md).")
    return 0


GO_PLACEHOLDER = "(their words)"


def ledger_rows(text):
    """{row id: (cells, status)} for every ledger row like | D3 | ... | OPEN |."""
    rows = {}
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 3 and re.fullmatch(r"[A-I]\d+", cells[0]):
            rows[cells[0]] = (cells, cells[-1].upper())
    return rows


def cmd_gate(a):
    path = os.path.join(a.project, "CLARITY.md")
    if not os.path.exists(path):
        sys.exit(f"no CLARITY.md in {a.project}")
    with open(path) as f:
        text = f.read()
    rows = ledger_rows(text)
    open_rows = [rid for rid, (_, st) in rows.items() if st == "OPEN"]
    go = re.search(r"\|\s*The maker's go\s*\|\s*(.+?)\s*\|", text)
    go_text = go.group(1) if go else ""
    has_go = bool(go_text) and GO_PLACEHOLDER not in go_text and "go" in go_text.lower()
    g1 = not open_rows and has_go
    results = []
    if a.only in (None, "1"):
        print(f"Gate 1 (interview): {'PASS' if g1 else 'FAIL'}")
        print(f"  open rows: {len(open_rows)}" + (f" ({', '.join(open_rows[:20])})" if open_rows else ""))
        print(f"  the maker's go: {go_text if has_go else 'not recorded yet'}")
        results.append(g1)
    if a.only in (None, "2"):
        spec, _ = load_spec(a.project)
        whys = " ".join(str(t.get("why", "")) for key in ("rays", "sweeps", "relief", "envelope")
                        for t in (spec.get(key) or [] if key != "envelope" else [spec.get("envelope") or {}])
                        if not str(t.get("name", "")).startswith("_example"))
        need = []
        for rid, (cells, st) in rows.items():
            if st == "N/A":
                continue
            if rid in ("D1", "D2", "D3"):
                need.append(rid)
            elif rid.startswith("E") and len(cells) >= 4 and re.search(r"cut|stand|step|raised|recess",
                                                                         cells[3], re.I):
                need.append(rid)
        missing = [rid for rid in need if not re.search(rf"\b{rid}\b", whys)]
        g2 = not missing
        print(f"Gate 2 (tests written): {'PASS' if g2 else 'FAIL'}")
        print(f"  rows that need a test: {', '.join(need) or 'none'}")
        if missing:
            print(f"  no test cites: {', '.join(missing)} (put the row id in a test's \"why\")")
        results.append(g2)
    return 0 if all(results) else 1


def cmd_build(a):
    load_spec(a.project)
    script = os.path.join(a.project, "scripts", "build_part.py")
    if not os.path.exists(script):
        sys.exit(f"no {script}")
    rc, out = blender_run(script, ["--project", os.path.abspath(a.project)], blend=a.blend)
    print(out)
    return rc


def cmd_check(a, quiet=False):
    spec, spec_path = load_spec(a.project)
    stl = stl_path(a.project, spec, a.stl)
    if not os.path.exists(stl):
        sys.exit(f"no STL at {stl}. Build first (kit.py build) or pass --stl")
    if not a.stl:
        problem = build_record_problem(a.project, stl)
        if problem:
            print(f"RESULT: FAIL (stale STL): {problem}")
            return 1, None, ""
    tag = os.path.splitext(os.path.basename(stl))[0]
    report = os.path.join(a.project, "reports", f"check_{tag}.json")
    glb = os.path.splitext(stl)[0] + ".glb"
    extra = ["--glb", glb] if os.path.exists(glb) else []
    rc, out = blender_run(os.path.join(KIT, "print_check.py"), [stl, "--spec", spec_path, "--out", report] + extra)
    text = out.split("PRINT_CHECK_JSON")[0].rstrip()
    if not quiet:
        print(text)
    return rc, report, text


def cmd_verify(a):
    spec, spec_path = load_spec(a.project)
    stl = stl_path(a.project, spec, a.stl)
    tag = os.path.splitext(os.path.basename(stl))[0]
    sheet = os.path.join(a.project, "renders", f"review_{tag}.jpg")
    if os.path.exists(sheet):
        os.remove(sheet)              # never leave last run's sheet looking current
    views = spec.get("views") or [{"name": f.replace("+", "pos").replace("-", "neg"), "face": f} for f in specmod.FACES]
    errors = specmod.validate_sheet(spec.get("sheet"), [v.get("name") for v in views])
    for r in spec.get("sheet") or []:
        if isinstance(r, dict) and r.get("photo"):
            ph = r["photo"] if os.path.isabs(r["photo"]) else os.path.join(a.project, r["photo"])
            if not os.path.exists(ph):
                errors.append(f"[spec] sheet: photo not found: {r['photo']}")
    if errors:
        print("RESULT: FAIL (the review sheet can't be drawn):\n  " + "\n  ".join(errors))
        return 1
    rc, report, text = cmd_check(a, quiet=True)
    print(text)
    if report is None:
        return rc
    vdir = os.path.join(a.project, "renders", tag)
    vrc, vout = blender_run(os.path.join(KIT, "views.py"), [stl, "--spec", spec_path, "--out-dir", vdir])
    print("\nface views:\n" + vout.split("VIEWS_JSON")[0].rstrip())
    sys.stdout.flush()
    if vrc != 0:
        return 1
    part = spec.get("part") or {}
    title = f"{part.get('name', 'part')} {part.get('version', '')}: model vs reference"
    subprocess.run([sys.executable, os.path.join(KIT, "review_sheet.py"), "--views", os.path.join(vdir, "views.json"),
                    "--spec", spec_path, "--report", report, "--out", sheet, "--title", title,
                    "--project", a.project], check=True, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    print(f"\nreview sheet: {os.path.abspath(sheet)}\ncheck report: {os.path.abspath(report)}")
    print("Look at the sheet yourself first. Then show it to the maker (send the file; never just name a path).")
    return rc


SELFTEST_SPEC = {
    "process": "resin",
    "envelope": {"dims_mm": [20, 10, 5], "tol_mm": 0.05},
    "rays": [
        {"name": "pin top", "origin": [0, 0, 50], "dir": [0, 0, -1], "expect": "hit", "hit_at": {"z": 4.4}, "tol": 0.05,
         "positive_control": True, "why": "known surface"},
        {"name": "body beside the slot", "origin": [3, 1.5, 50], "dir": [0, 0, -1], "expect": "hit",
         "positive_control": True, "why": "solid material right beside the slot ray"},
        {"name": "slot open", "origin": [3, 0, 50], "dir": [0, 0, -1], "expect": "clear",
         "control": "body beside the slot", "why": "CLARITY D3"}],
    "sweeps": [{"name": "mating part enters from below", "from": [-5.9, 0, -20], "to": [5.9, 0, -20], "step": 0.1,
                "dir": [0, 0, 1], "control": "body beside the slot", "why": "CLARITY D1",
                "allow_hits_in": [{"min": [-0.45, -1.1, 3.55], "max": [0.45, 1.1, 4.45]}]}],
    "relief": [{"name": "letters are cut in", "axis": "y", "viewer": "-", "region": {"x": [-2.2, 2.2], "z": [1.4, 3.6]},
                "surface": -5.0, "expect": "recessed", "depth_mm": 0.3, "why": "CLARITY E1"}],
}


def _variant(**changes):
    s = json.loads(json.dumps(SELFTEST_SPEC))
    for path, value in changes.items():
        key, idx, field = path.split(".")
        s[key][int(idx)][field] = value
    return s


SELFTEST_CASES = [
    # (label, stl, spec, expect exit code, substring that must appear in the failures)
    ("good part passes", "good", SELFTEST_SPEC, 0, None),
    ("crossmember caught (sweep)", "bad", SELFTEST_SPEC, 1, "sweep 'mating part enters from below'"),
    ("raised letters caught (relief)", "bad", SELFTEST_SPEC, 1, "relief 'letters are cut in'"),
    ("clear ray that misses the part fails", "good", _variant(**{"rays.2.origin": [110, 0, 50]}), 1,
     "never crosses the part's bounding box"),
    ("sweep cast the wrong way fails", "good", _variant(**{"sweeps.0.dir": [0, 0, -1]}), 1, "never cross"),
    ("typo in expect is rejected", "good", _variant(**{"rays.2.expect": "Clear"}), 1, "expect must be"),
    ("spec with no tests is incomplete", "good", {"process": "resin"}, 1, "INCOMPLETE"),
]


def cmd_selftest(a):
    """Positive and negative controls for the checks themselves, on this machine."""
    import tempfile
    tmp = tempfile.mkdtemp(prefix="photo-to-print-selftest-")
    blender_run(os.path.join(KIT, "selftest_part.py"), [tmp])
    ok = True
    for i, (label, stl, spec, want_rc, needle) in enumerate(SELFTEST_CASES):
        sp = os.path.join(tmp, f"spec{i}.json")
        rep = os.path.join(tmp, f"report{i}.json")
        with open(sp, "w") as f:
            json.dump(spec, f)
        rc, _ = blender_run(os.path.join(KIT, "print_check.py"), [os.path.join(tmp, f"{stl}.stl"), "--spec", sp,
                                                                  "--out", rep])
        with open(rep) as f:
            summary = json.load(f)["summary"]
        good = rc == want_rc and (needle is None or needle in " ".join(summary["fails"]))
        ok &= good
        print(f"[{'ok' if good else 'FAIL'}] {label}")
        if not good:
            print(f"    exit {rc} (wanted {want_rc}); failures: {'; '.join(summary['fails'])[:400]}")
    print("selftest " + ("PASSED: the checks catch what they claim to" if ok
                         else "FAILED: do not trust print_check on this machine yet"))
    if ok:
        shutil.rmtree(tmp, ignore_errors=True)
    else:
        print(f"  fixtures kept in {tmp}")
    return 0 if ok else 1


def main():
    presets = sorted(specmod.load_presets())
    ap = argparse.ArgumentParser(prog="kit")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor")
    sub.add_parser("selftest")
    p = sub.add_parser("new")
    p.add_argument("project")
    p.add_argument("--name", required=True)
    p.add_argument("--process", choices=presets, default="resin")
    p = sub.add_parser("gate")
    p.add_argument("project")
    p.add_argument("--only", choices=["1", "2"], default=None)
    p = sub.add_parser("build")
    p.add_argument("project")
    p.add_argument("--blend", default=None)
    for name in ("check", "verify"):
        p = sub.add_parser(name)
        p.add_argument("project")
        p.add_argument("--stl", default=None, help="check this STL instead (skips the build-record check)")
    a = ap.parse_args()
    if a.cmd == "check":
        return cmd_check(a)[0]
    return {"doctor": cmd_doctor, "selftest": cmd_selftest, "new": cmd_new, "gate": cmd_gate, "build": cmd_build,
            "verify": cmd_verify}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
