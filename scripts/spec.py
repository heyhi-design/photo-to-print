"""spec: load the printer presets and validate a checks.json before anything runs.

Pure Python (no Blender), so print_check.py, views.py, review_sheet.py and kit.py
all share one set of rules, and the unit tests can exercise them in CI.

    import spec
    clean, limits, errors, warnings = spec.validate(raw_dict)

Every key and rule is documented in references/checks-reference.md. A typo
must never change what a test means, so unknown values are errors, not guesses:
"expect": "Clear" is rejected rather than read as "hit".
"""

import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PRESETS_PATH = os.path.join(HERE, "presets.json")
LIMIT_KEYS = ("min_feature_mm", "min_wall_mm", "min_gap_mm", "overhang_deg", "overhang_gate", "bed_layer_mm")
FACES = {          # face: (outward normal, image right, image up)
    "+Z": ((0, 0, 1), (1, 0, 0), (0, 1, 0)),
    "-Z": ((0, 0, -1), (1, 0, 0), (0, -1, 0)),
    "-Y": ((0, -1, 0), (1, 0, 0), (0, 0, 1)),
    "+Y": ((0, 1, 0), (-1, 0, 0), (0, 0, 1)),
    "+X": ((1, 0, 0), (0, 1, 0), (0, 0, 1)),
    "-X": ((-1, 0, 0), (0, -1, 0), (0, 0, 1)),
}
TOP_KEYS = {"part", "process", "limits", "envelope", "rays", "sweeps", "relief", "accepted_thin", "accepted_gaps",
            "accepted_overhang", "print_rotation_deg", "allow_untested", "view_ppmm", "views", "sheet"}
RAY_KEYS = {"name", "origin", "dir", "expect", "hit_at", "tol", "tol_mm", "max_dist", "positive_control", "control", "why"}
SWEEP_KEYS = {"name", "from", "to", "step", "dir", "allow_hits_in", "radius_mm", "max_dist", "control", "why"}
RELIEF_KEYS = {"name", "axis", "viewer", "region", "surface", "normal", "center_mm", "size_mm", "up", "surface_point",
               "expect", "depth_mm", "step_mm", "tol_mm", "min_share", "why"}
VIEW_KEYS = {"name", "face", "right", "up", "ppmm", "frame_mm", "center_mm", "margin_mm", "relief_range_mm", "base",
             "base_window_mm", "base_min_share", "max_pixels"}
SHEET_KEYS = {"view", "photo", "photo_ppmm", "photo_center_px", "photo_rotate", "label"}
MAX_RAYS = 2_000_000


def load_presets(path=PRESETS_PATH):
    with open(path) as f:
        procs = json.load(f)["processes"]
    for name, p in procs.items():
        missing = [k for k in LIMIT_KEYS if k not in p]
        if missing:
            raise ValueError(f"presets.json process '{name}' is missing {missing}")
    return procs


def _num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _vec(x, n=3):
    return isinstance(x, (list, tuple)) and len(x) == n and all(_num(v) for v in x)


def _norm(v):
    return math.sqrt(sum(c * c for c in v))


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _unknown(row, allowed, where, warnings):
    for k in row:
        if k not in allowed and not str(k).startswith("_"):
            warnings.append(f"[spec] {where}: unknown key '{k}' is ignored")


def _list(spec, key, errors, warnings):
    v = spec.get(key)
    if v is None:
        if key in spec:
            warnings.append(f"[spec] '{key}' is null; treated as empty")
        return []
    if not isinstance(v, list):
        errors.append(f"[spec] '{key}' must be a list")
        return []
    return v


def _boxes(rows, where, errors):
    out = []
    for i, b in enumerate(rows):
        if not isinstance(b, dict) or not _vec(b.get("min")) or not _vec(b.get("max")):
            errors.append(f"[spec] {where}[{i}]: needs 'min' and 'max' as [x, y, z]")
            continue
        if any(b["min"][k] > b["max"][k] for k in range(3)):
            errors.append(f"[spec] {where}[{i}]: 'min' is larger than 'max' on some axis")
            continue
        out.append(b)
    return out


def _limits(spec, presets, errors):
    process = spec.get("process", "resin")
    if not isinstance(process, str):
        errors.append("[spec] 'process' must be a string")
        process = "resin"
    process = process.lower()
    raw = spec.get("limits") or {}
    if not isinstance(raw, dict):
        errors.append("[spec] 'limits' must be an object")
        raw = {}
    for k in raw:
        if k not in LIMIT_KEYS:
            hint = next((L for L in LIMIT_KEYS if L.startswith(k) or k.startswith(L.replace("_mm", ""))), None)
            errors.append(f"[spec] unknown limits key '{k}'" + (f" (did you mean '{hint}'?)" if hint else "")
                          + f"; valid keys: {', '.join(LIMIT_KEYS)}")
    if process in presets:
        limits = dict(presets[process])
    elif process == "custom":
        limits = {}
    else:
        errors.append(f"[spec] unknown process '{process}'; use one of {sorted(presets)} or 'custom' with every "
                      f"limits key set")
        limits = dict(presets.get("resin", {}))
    limits.update({k: v for k, v in raw.items() if k in LIMIT_KEYS})
    missing = [k for k in LIMIT_KEYS if k not in limits]
    if missing:
        errors.append(f"[spec] process '{process}' is missing limits {missing}")
    for k in LIMIT_KEYS:
        if k in limits:
            if k == "overhang_gate":
                if not isinstance(limits[k], bool):
                    errors.append("[spec] limits.overhang_gate must be true or false")
            elif not _num(limits[k]) or limits[k] < 0:
                errors.append(f"[spec] limits.{k} must be a non-negative number")
    if _num(limits.get("overhang_deg")) and not 0 < limits["overhang_deg"] < 90:
        errors.append("[spec] limits.overhang_deg must be between 0 and 90 (degrees from vertical)")
    return process, limits


def validate(raw, presets=None):
    """Return (clean_spec, limits, errors, warnings). Errors mean: do not run."""
    presets = presets if presets is not None else load_presets()
    errors, warnings = [], []
    if not isinstance(raw, dict):
        return {}, {}, ["[spec] checks.json must be a JSON object"], []
    spec = {k: v for k, v in raw.items()}
    _unknown(spec, TOP_KEYS, "checks.json", warnings)
    process, limits = _limits(spec, presets, errors)
    clean = {"process": process, "part": spec.get("part") or {}}

    # envelope
    env = spec.get("envelope")
    if env is not None:
        if not isinstance(env, dict):
            errors.append("[spec] 'envelope' must be an object")
        else:
            e = {"tol_mm": env.get("tol_mm", 0.3)}
            if not _num(e["tol_mm"]) or e["tol_mm"] <= 0:
                errors.append("[spec] envelope.tol_mm must be a positive number")
            for key in ("dims_mm", "min_mm", "max_mm"):
                v = env.get(key)
                if v is None:
                    continue
                if not isinstance(v, list) or len(v) != 3 or not all(x is None or _num(x) for x in v):
                    errors.append(f"[spec] envelope.{key} must be [x, y, z] (numbers, or null to skip an axis)")
                    continue
                if any(x is not None for x in v):
                    e[key] = v
            if any(k in e for k in ("dims_mm", "min_mm", "max_mm")):
                clean["envelope"] = e

    # rays
    names = set()
    rays = []
    for i, r in enumerate(_list(spec, "rays", errors, warnings)):
        if not isinstance(r, dict):
            errors.append(f"[spec] rays[{i}] must be an object")
            continue
        name = r.get("name", f"rays[{i}]")
        if str(name).startswith("_example"):
            continue
        _unknown(r, RAY_KEYS, f"ray '{name}'", warnings)
        if name in names:
            errors.append(f"[spec] duplicate test name '{name}'")
        names.add(name)
        if r.get("expect") not in ("hit", "clear"):
            errors.append(f"[spec] ray '{name}': expect must be \"hit\" or \"clear\" (got {r.get('expect')!r})")
        if not _vec(r.get("origin")):
            errors.append(f"[spec] ray '{name}': origin must be [x, y, z]")
        if not _vec(r.get("dir")) or _norm(r.get("dir")) < 1e-9:
            errors.append(f"[spec] ray '{name}': dir must be a non-zero [x, y, z]")
        tol = r.get("tol", r.get("tol_mm", 0.05))
        if not _num(tol) or tol <= 0:
            errors.append(f"[spec] ray '{name}': tol must be a positive number")
        hit_at = r.get("hit_at") or {}
        if not isinstance(hit_at, dict) or any(k not in "xyz" or len(k) != 1 or not _num(v) for k, v in hit_at.items()):
            errors.append(f"[spec] ray '{name}': hit_at must look like {{\"z\": 5.6}}")
            hit_at = {}
        if hit_at and r.get("expect") == "clear":
            errors.append(f"[spec] ray '{name}': hit_at only makes sense with expect \"hit\"")
        if r.get("positive_control") and r.get("expect") != "hit":
            errors.append(f"[spec] ray '{name}': a positive_control must expect \"hit\" (it proves the rays reach the part)")
        md = r.get("max_dist", 1000.0)
        if not _num(md) or md <= 0:
            errors.append(f"[spec] ray '{name}': max_dist must be positive")
        rays.append(dict(r, name=name, tol=tol, hit_at=hit_at, max_dist=md))
    clean["rays"] = rays

    # sweeps
    sweeps = []
    for i, s in enumerate(_list(spec, "sweeps", errors, warnings)):
        if not isinstance(s, dict):
            errors.append(f"[spec] sweeps[{i}] must be an object")
            continue
        name = s.get("name", f"sweeps[{i}]")
        if str(name).startswith("_example"):
            continue
        _unknown(s, SWEEP_KEYS, f"sweep '{name}'", warnings)
        if name in names:
            errors.append(f"[spec] duplicate test name '{name}'")
        names.add(name)
        ok = _vec(s.get("from")) and _vec(s.get("to"))
        if not ok:
            errors.append(f"[spec] sweep '{name}': from and to must be [x, y, z]")
        if not _vec(s.get("dir")) or _norm(s.get("dir")) < 1e-9:
            errors.append(f"[spec] sweep '{name}': dir must be a non-zero [x, y, z]")
        step = s.get("step", 0.1)
        if not _num(step) or step <= 0:
            errors.append(f"[spec] sweep '{name}': step must be a positive number")
            step = 0.1
        rad = s.get("radius_mm", 0)
        if not _num(rad) or rad < 0:
            errors.append(f"[spec] sweep '{name}': radius_mm must be zero or positive")
            rad = 0
        if ok:
            length = _norm([b - a for a, b in zip(s["from"], s["to"])])
            if length / step > MAX_RAYS:
                errors.append(f"[spec] sweep '{name}': {int(length / step)} steps is too many; raise step")
        allow = _boxes(s.get("allow_hits_in") or [], f"sweep '{name}' allow_hits_in", errors)
        sweeps.append(dict(s, name=name, step=step, radius_mm=rad, allow_hits_in=allow,
                           max_dist=s.get("max_dist", 1000.0)))
    clean["sweeps"] = sweeps

    # control references
    controls = {r["name"] for r in rays if r.get("positive_control") and r.get("expect") == "hit"}
    for t in [r for r in rays if r.get("expect") == "clear"] + sweeps:
        c = t.get("control")
        if c is None:
            warnings.append(f"[spec] '{t['name']}' names no control; add \"control\": \"<a positive_control ray "
                            f"beside it>\" so a miss can't read as clear")
        elif c not in controls:
            errors.append(f"[spec] '{t['name']}': control '{c}' is not a positive_control ray that expects \"hit\"")

    # relief
    reliefs = []
    for i, r in enumerate(_list(spec, "relief", errors, warnings)):
        if not isinstance(r, dict):
            errors.append(f"[spec] relief[{i}] must be an object")
            continue
        name = r.get("name", f"relief[{i}]")
        if str(name).startswith("_example"):
            continue
        _unknown(r, RELIEF_KEYS, f"relief '{name}'", warnings)
        if name in names:
            errors.append(f"[spec] duplicate test name '{name}'")
        names.add(name)
        if r.get("expect") not in ("recessed", "raised"):
            errors.append(f"[spec] relief '{name}': expect must be \"recessed\" or \"raised\" (got {r.get('expect')!r}); "
                          f"a flat feature has no relief test")
        tol = r.get("tol_mm", 0.05)
        step = r.get("step_mm", 0.05)
        share = r.get("min_share", 0.05)
        if not _num(tol) or tol <= 0:
            errors.append(f"[spec] relief '{name}': tol_mm must be positive")
            tol = 0.05
        if not _num(step) or step <= 0:
            errors.append(f"[spec] relief '{name}': step_mm must be positive")
            step = 0.05
        if not _num(share) or not 0 < share <= 1:
            errors.append(f"[spec] relief '{name}': min_share must be between 0 and 1")
        depth = r.get("depth_mm")
        if depth is not None and (not _num(depth) or depth <= tol):
            errors.append(f"[spec] relief '{name}': depth_mm must be larger than tol_mm ({tol}); lower tol_mm for "
                          f"very shallow detail")
        row = dict(r, name=name, tol_mm=tol, step_mm=step, min_share=share)
        if "normal" in r:
            if not _vec(r.get("normal")) or _norm(r["normal"]) < 1e-9:
                errors.append(f"[spec] relief '{name}': normal must be a non-zero [x, y, z] pointing toward the viewer")
            elif not (_vec(r.get("center_mm")) and _vec(r.get("size_mm"), 2) and min(r["size_mm"]) > 0
                      and _vec(r.get("surface_point"))):
                errors.append(f"[spec] relief '{name}': the normal form needs center_mm [x,y,z], size_mm [w,h] and "
                              f"surface_point [x,y,z] (a point on the surrounding face)")
            elif "up" in r and (not _vec(r["up"]) or _norm(_cross(r["up"], r["normal"])) < 1e-6):
                errors.append(f"[spec] relief '{name}': up must be a vector not parallel to normal")
            else:
                cells = (r["size_mm"][0] / step + 1) * (r["size_mm"][1] / step + 1)
                if cells > MAX_RAYS:
                    errors.append(f"[spec] relief '{name}': {int(cells)} rays is too many; raise step_mm")
        else:
            ax = r.get("axis")
            if ax not in ("x", "y", "z"):
                errors.append(f"[spec] relief '{name}': axis must be \"x\", \"y\" or \"z\" (or use the normal form)")
            elif r.get("viewer") not in ("-", "+"):
                errors.append(f"[spec] relief '{name}': viewer must be \"-\" or \"+\" (the side you look from); "
                              f"got {r.get('viewer')!r}")
            elif not _num(r.get("surface")):
                errors.append(f"[spec] relief '{name}': surface must be the face's {ax} coordinate")
            else:
                others = [a for a in "xyz" if a != ax]
                reg = r.get("region") or {}
                bad = [a for a in others if not (_vec(reg.get(a), 2) and reg[a][0] < reg[a][1])]
                if bad:
                    errors.append(f"[spec] relief '{name}': region needs {others[0]} and {others[1]} as [min, max] "
                                  f"(missing or wrong: {', '.join(bad)})")
                else:
                    cells = ((reg[others[0]][1] - reg[others[0]][0]) / step + 1) * \
                            ((reg[others[1]][1] - reg[others[1]][0]) / step + 1)
                    if cells > MAX_RAYS:
                        errors.append(f"[spec] relief '{name}': {int(cells)} rays is too many; raise step_mm")
        reliefs.append(row)
    clean["relief"] = reliefs

    for key in ("accepted_thin", "accepted_gaps", "accepted_overhang"):
        clean[key] = _boxes(_list(spec, key, errors, warnings), key, errors)
    rot = spec.get("print_rotation_deg")
    if rot is not None and not _vec(rot):
        errors.append("[spec] print_rotation_deg must be [x, y, z] degrees")
    clean["print_rotation_deg"] = rot or [0, 0, 0]

    # a spec that tests nothing about the part's function proves only that the mesh prints
    if not rays and not sweeps and not reliefs:
        why = spec.get("allow_untested")
        if isinstance(why, str) and why.strip():
            warnings.append(f"[spec] no function or relief tests (allowed: {why.strip()})")
        else:
            errors.append("[spec] INCOMPLETE: no function or relief tests. Write them from CLARITY.md (see "
                          "references/checks-reference.md), or set \"allow_untested\": \"<why>\"")
    clean["allow_untested"] = spec.get("allow_untested")
    clean["view_ppmm"] = spec.get("view_ppmm", 20)
    clean["views"] = spec.get("views") or []
    clean["sheet"] = spec.get("sheet") or []
    return clean, limits, errors, warnings


def view_axes(v):
    """(normal, right, up) for a view row, or raise ValueError with a reason."""
    face = v.get("face")
    if face is not None and face not in FACES:
        raise ValueError(f"view '{v.get('name')}': face must be one of {', '.join(FACES)} (got {face!r})")
    if ("right" in v) != ("up" in v):
        raise ValueError(f"view '{v.get('name')}': give both right and up, or neither")
    if "right" in v:
        r, u = v["right"], v["up"]
        if not (_vec(r) and _vec(u)):
            raise ValueError(f"view '{v.get('name')}': right and up must be [x, y, z]")
        nr, nu = _norm(r), _norm(u)
        if nr < 1e-9 or nu < 1e-9 or abs(_dot(r, u)) / (nr * nu) > 1e-3:
            raise ValueError(f"view '{v.get('name')}': right and up must be non-zero and perpendicular")
        r = tuple(c / nr for c in r)
        u = tuple(c / nu for c in u)
        n = _cross(r, u)
        if face is not None and _dot(n, FACES[face][0]) < 0.99:
            raise ValueError(f"view '{v.get('name')}': right x up points {tuple(round(c, 3) for c in n)}, which is "
                             f"not the {face} face; swap right and up or fix face")
        return n, r, u
    if face is None:
        raise ValueError(f"view '{v.get('name')}': needs face (or right and up)")
    return FACES[face]


def validate_views(views, default_ppmm):
    errors, out = [], []
    seen = set()
    for i, v in enumerate(views or []):
        if not isinstance(v, dict) or not v.get("name"):
            errors.append(f"[spec] views[{i}] needs a name")
            continue
        if v["name"] in seen:
            errors.append(f"[spec] duplicate view name '{v['name']}'")
        seen.add(v["name"])
        try:
            view_axes(v)
        except ValueError as ex:
            errors.append(f"[spec] {ex}")
        ppmm = v.get("ppmm", default_ppmm)
        if not _num(ppmm) or ppmm <= 0:
            errors.append(f"[spec] view '{v['name']}': ppmm must be positive")
        if "frame_mm" in v and not (_vec(v["frame_mm"], 2) and min(v["frame_mm"]) > 0):
            errors.append(f"[spec] view '{v['name']}': frame_mm must be [width, height] > 0")
        b = v.get("base", "auto")
        if not (_num(b) or b in ("auto", "mode", "outermost", "local")):
            errors.append(f"[spec] view '{v['name']}': base must be auto, mode, outermost, local or a number")
        out.append(v)
    return out, errors


def validate_sheet(rows, view_names):
    errors = []
    for i, r in enumerate(rows or []):
        if not isinstance(r, dict):
            errors.append(f"[spec] sheet[{i}] must be an object")
            continue
        if r.get("view") not in view_names:
            errors.append(f"[spec] sheet[{i}]: 'view' must name one of the views ({', '.join(view_names) or 'none'})")
        for k in ("photo", "photo_ppmm", "photo_center_px"):
            if k not in r:
                errors.append(f"[spec] sheet[{i}]: missing '{k}'")
        if "photo_ppmm" in r and (not _num(r["photo_ppmm"]) or r["photo_ppmm"] <= 0):
            errors.append(f"[spec] sheet[{i}]: photo_ppmm must be positive")
        if "photo_center_px" in r and not _vec(r["photo_center_px"], 2):
            errors.append(f"[spec] sheet[{i}]: photo_center_px must be [x, y]")
        if r.get("photo_rotate", 0) not in (0, 90, 180, 270):
            errors.append(f"[spec] sheet[{i}]: photo_rotate must be 0, 90, 180 or 270 (degrees counter-clockwise)")
    return errors
