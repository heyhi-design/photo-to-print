"""kit: one entry point for a photo-to-print project. System python3 (Pillow + numpy).

    python3 kit.py doctor                     what is installed, what is missing, how to fix it
    python3 kit.py selftest                   prove the checks catch real defects on this machine
    python3 kit.py new  <project> --name brake-caliper [--process resin|fdm]
    python3 kit.py build <project> [--blend file.blend]
                                              run scripts/build_part.py headless, export the STL
    python3 kit.py check <project>            print_check on the current version's STL
    python3 kit.py verify <project>           check + face views + review sheet (the gate artifact)

A project is a folder (see templates/): CLARITY.md (the question ledger),
README.md, checks.json (what "right" means, as tests), scripts/build_part.py,
reference/, questions/, exports/, renders/, reports/. Every path inside it is
relative to the project folder, so the folder can move without breaking.
"""

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys

KIT = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(KIT)
TEMPLATES = os.path.join(SKILL, "templates")


def find_blender():
    cands = [os.environ.get("BLENDER"), os.environ.get("BLENDER_PATH"),
             "/Applications/Blender.app/Contents/MacOS/Blender", shutil.which("blender")]
    cands += sorted(glob.glob(r"C:\Program Files\Blender Foundation\Blender*\blender.exe"), reverse=True)
    cands += sorted(glob.glob("/opt/blender*/blender"), reverse=True)
    for c in cands:
        if c and os.path.exists(c):
            return c
    return None


def blender_run(script, args, blend=None, quiet=True):
    exe = find_blender()
    if not exe:
        sys.exit("Blender not found. Install Blender (free, blender.org), or set BLENDER=/path/to/blender.")
    cmd = [exe, "--background"] + ([blend] if blend else ["--factory-startup"]) + \
          ["--python-exit-code", "2", "--python", script, "--"] + args
    p = subprocess.run(cmd, capture_output=True, text=True)
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
    return json.load(open(path)), path


def stl_path(project, spec, override=None):
    if override:
        return override
    part = spec.get("part", {})
    rel = part.get("stl", "exports/{name}_{version}.stl").format(name=part.get("name", "part"),
                                                                  version=part.get("version", "v1"))
    return os.path.join(project, rel)


# ---------------------------------------------------------------- commands ----

def cmd_doctor(a):
    ok = True
    exe = find_blender()
    if exe:
        v = subprocess.run([exe, "--version"], capture_output=True, text=True).stdout.splitlines()[:1]
        print(f"[ok]   Blender: {exe} ({v[0] if v else '?'})")
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
    print("[info] Blender MCP (optional): lets Claude drive an open Blender live. The kit never needs it;")
    print("       every step runs headless. If a live connector stalls, stop after 2-3 tries and go headless.")
    print("ready" if ok else "fix the [need] lines, then run doctor again")
    return 0 if ok else 1


def cmd_new(a):
    p = a.project
    if os.path.exists(os.path.join(p, "checks.json")):
        sys.exit(f"{p} already has a project; not overwriting")
    for d in ("reference", "questions", "exports", "renders", "reports", "scripts"):
        os.makedirs(os.path.join(p, d), exist_ok=True)
    subs = {"{{PART}}": a.name, "{{PROCESS}}": a.process, "{{KIT}}": KIT}
    for src, dst in (("project-README.md", "README.md"), ("CLARITY.md", "CLARITY.md"),
                     ("checks.json", "checks.json"), ("build_part.py", "scripts/build_part.py")):
        text = open(os.path.join(TEMPLATES, src)).read()
        for k, v in subs.items():
            text = text.replace(k, v)
        open(os.path.join(p, dst), "w").write(text)
    print(f"new project at {p}\n  next: put the maker's ORIGINAL photos in {p}/reference/, run\n"
          f"  python3 {KIT}/photo_tools.py info '{p}/reference/*'\n  then start the intake interview (CLARITY.md).")
    return 0


def cmd_build(a):
    spec, _ = load_spec(a.project)
    script = os.path.join(a.project, "scripts", "build_part.py")
    rc, out = blender_run(script, ["--project", os.path.abspath(a.project)], blend=a.blend)
    print(out)
    return rc


def cmd_check(a, quiet=False):
    spec, spec_path = load_spec(a.project)
    stl = stl_path(a.project, spec, a.stl)
    if not os.path.exists(stl):
        sys.exit(f"no STL at {stl}. Build first (kit.py build) or pass --stl")
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
    rc, report, text = cmd_check(a, quiet=True)
    print(text)
    tag = os.path.splitext(os.path.basename(stl))[0]
    vdir = os.path.join(a.project, "renders", tag)
    _, vout = blender_run(os.path.join(KIT, "views.py"), [stl, "--spec", spec_path, "--out-dir", vdir])
    print("\nface views:\n" + vout.split("VIEWS_JSON")[0].rstrip())
    sys.stdout.flush()
    sheet = os.path.join(a.project, "renders", f"review_{tag}.jpg")
    title = f"{spec.get('part', {}).get('name', 'part')} {spec.get('part', {}).get('version', '')}: model vs reference"
    subprocess.run([sys.executable, os.path.join(KIT, "review_sheet.py"), "--views", os.path.join(vdir, "views.json"),
                    "--spec", spec_path, "--report", report, "--out", sheet, "--title", title,
                    "--project", a.project], check=True)
    print(f"\nreview sheet: {os.path.abspath(sheet)}\ncheck report: {os.path.abspath(report)}")
    print("Look at the sheet yourself first. Then show it to the maker (send the file; never just name a path).")
    return rc


SELFTEST_SPEC = {
    "process": "resin",
    "envelope": {"dims_mm": [20, 10, 5], "tol_mm": 0.05},
    "rays": [
        {"name": "pin top (positive control)", "origin": [0, 0, 50], "dir": [0, 0, -1], "expect": "hit",
         "hit_at": {"z": 4.4}, "tol": 0.05, "positive_control": True},
        {"name": "slot open", "origin": [3, 0, 50], "dir": [0, 0, -1], "expect": "clear"}],
    "sweeps": [{"name": "mating part enters from below", "from": [-5.9, 0, -20], "to": [5.9, 0, -20], "step": 0.1,
                "dir": [0, 0, 1], "allow_hits_in": [{"min": [-0.45, -1.1, 3.55], "max": [0.45, 1.1, 4.45]}]}],
    "relief": [{"name": "letters are cut in", "axis": "y", "viewer": "-", "region": {"x": [-2.2, 2.2], "z": [1.4, 3.6]},
                "surface": -5.0, "expect": "recessed", "depth_mm": 0.3}],
}


def cmd_selftest(a):
    """Positive and negative control for the checks themselves, on this machine."""
    import tempfile
    tmp = tempfile.mkdtemp(prefix="photo-to-print-selftest-")
    blender_run(os.path.join(KIT, "selftest_part.py"), [tmp])
    spec = os.path.join(tmp, "checks.json")
    json.dump(SELFTEST_SPEC, open(spec, "w"))
    results = {}
    for name in ("good", "bad"):
        rep = os.path.join(tmp, f"{name}.json")
        rc, _ = blender_run(os.path.join(KIT, "print_check.py"), [os.path.join(tmp, f"{name}.stl"), "--spec", spec, "--out", rep])
        results[name] = (rc, json.load(open(rep))["summary"])
    good_rc, good = results["good"]
    bad_rc, bad = results["bad"]
    fails = " ".join(bad["fails"])
    expect = {"good part passes": good_rc == 0,
              "bad part fails": bad_rc == 1,
              "crossmember caught (sweep)": "sweep 'mating part enters from below'" in fails,
              "raised letters caught (relief)": "relief 'letters are cut in'" in fails}
    for k, v in expect.items():
        print(f"[{'ok' if v else 'FAIL'}] {k}")
    if good_rc != 0:
        print("  good part failures: " + "; ".join(good["fails"]))
    ok = all(expect.values())
    print("selftest " + ("PASSED: the checks catch what they claim to" if ok else "FAILED: do not trust print_check on this machine yet"))
    if ok:
        shutil.rmtree(tmp, ignore_errors=True)
    else:
        print(f"  fixtures kept in {tmp}")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(prog="kit")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor")
    sub.add_parser("selftest")
    p = sub.add_parser("new")
    p.add_argument("project")
    p.add_argument("--name", required=True)
    p.add_argument("--process", choices=["resin", "fdm"], default="resin")
    p = sub.add_parser("build")
    p.add_argument("project")
    p.add_argument("--blend", default=None)
    for name in ("check", "verify"):
        p = sub.add_parser(name)
        p.add_argument("project")
        p.add_argument("--stl", default=None)
    a = ap.parse_args()
    if a.cmd == "check":
        return cmd_check(a)[0]
    return {"doctor": cmd_doctor, "selftest": cmd_selftest, "new": cmd_new, "build": cmd_build,
            "verify": cmd_verify}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
