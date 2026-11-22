# checks.json reference

`checks.json` says what "right" means for one part, as tests. `print_check.py` runs them on the exported STL; `views.py` and `review_sheet.py` use the `views` and `sheet` sections. This file is the one place every key and rule is written down; `scripts/spec.py` enforces them before anything runs, so a typo is an error, never a different test.

**Units and frame.** Millimetres. X = length, Y = width, Z = height, Z = 0 on the face that sits on the build plate. Points are `[x, y, z]`.

**Exit codes.** `0` every check passed, `1` a check failed or the spec is invalid (nothing runs on an invalid spec), `2` a script crashed.

## Top level

| Key | Meaning |
|---|---|
| `part` | `{"name", "version", "stl"}`. `stl` defaults to `exports/{name}_{version}.stl`. |
| `process` | A process from `scripts/presets.json` (`resin`, `fdm`), or `custom` with every `limits` key set. |
| `limits` | Overrides for this part: `min_feature_mm`, `min_wall_mm`, `min_gap_mm`, `overhang_deg`, `overhang_gate`, `bed_layer_mm`. Any other key is an error. |
| `envelope` | Size check (below). |
| `rays`, `sweeps`, `relief` | The function and polarity tests (below). Entries whose name starts with `_example` are ignored. |
| `accepted_thin`, `accepted_gaps`, `accepted_overhang` | Boxes `{"min": [x,y,z], "max": [x,y,z], "why": "..."}` where a flagged region is accepted. Every sample point is tested against the boxes, so a box only has to cover the region itself. Record each one in `CLARITY.md` G4. |
| `print_rotation_deg` | `[x, y, z]` degrees: the print orientation used for the overhang check. |
| `allow_untested` | A reason string. Without it, a spec with no rays, sweeps or relief tests is INCOMPLETE and fails, because it only proves the mesh prints, not that it's right. |
| `view_ppmm`, `views`, `sheet` | The review sheet (below). |

## Process limits and how flagged regions are judged

Defaults live in `scripts/presets.json` (mirrored in `print-limits.md`).

- **thin:** a ray goes inward from every triangle to the opposite wall. Regions thinner than `min_feature_mm` FAIL unless accepted. A region whose thickness climbs from almost nothing (or that covers less than 0.01 mm²) is a **sharp tip**, a warning, because it rounds off on a print. Regions between `min_feature_mm` and `min_wall_mm` are reported as fragile.
- **gaps:** a ray goes outward to the facing wall. A groove or gap whose typical (median) width is under `min_gap_mm` FAILs unless accepted: it fills in on resin and fuses on FDM. A region under 0.01 mm² is a **hairline inside corner**, a warning.
- **overhang:** downward faces steeper than `overhang_deg` from vertical, more than `bed_layer_mm` above the bed, in the `print_rotation_deg` orientation. A FAIL only when `overhang_gate` is true (FDM); always reported with the largest regions.

## envelope

```json
"envelope": {"dims_mm": [20.5, 12.8, 6.1], "min_mm": [-10.25, -6.55, 0], "max_mm": [10.25, 6.25, 6.1], "tol_mm": 0.3}
```

Any of `dims_mm`, `min_mm`, `max_mm`; each is three values, and `null` skips an axis. `tol_mm` defaults to 0.3. Use the maker's caliper readings (CLARITY C2) and tolerance (C4).

## rays

```json
{"name": "body beside the slot", "origin": [3, 1.5, 50], "dir": [0, 0, -1], "expect": "hit", "positive_control": true, "why": "solid material beside the slot ray"},
{"name": "slot open", "origin": [3, 0, 50], "dir": [0, 0, -1], "expect": "clear", "control": "body beside the slot", "why": "CLARITY D3"}
```

| Key | Meaning |
|---|---|
| `origin`, `dir` | Start point and direction (non-zero). A ray reports only the first thing it hits. |
| `expect` | `"hit"` or `"clear"`, exactly. |
| `hit_at`, `tol` | With `hit`: where it must land, e.g. `{"z": 5.6}`, within `tol` (default 0.05; `tol_mm` is accepted too). |
| `max_dist` | How far the ray looks (default 1000). |
| `positive_control` | `true` on a `hit` ray that proves the rays reach the part. |
| `control` | On a `clear` ray or sweep: the name of the positive control right beside it. |
| `why` | The ledger row it encodes, e.g. `CLARITY D3`. `kit.py gate` looks for these ids. |

**The positive-control rule.** A clear result only means something if the test could have hit. So:
1. every `clear` ray and sweep must cross the part's bounding box (a typo that points it off the part fails);
2. at least one `positive_control` ray must pass when any clear test exists;
3. each clear test should name its own `control`, placed on solid material right beside it, never where a defect could hide (on the first real project the only control over the slot sat directly above the defect, and hit something else first). A named control that fails fails the test it vouches for.

## sweeps

```json
{"name": "disc enters from below", "from": [-6.49, 0, -20], "to": [6.49, 0, -20], "step": 0.1, "dir": [0, 0, 1],
 "radius_mm": 0, "control": "block beside the slot", "why": "CLARITY D1",
 "allow_hits_in": [{"min": [-0.41, -0.5, 4.79], "max": [0.41, 0.5, 5.21], "why": "pad pin underside"}]}
```

A line of rays from `from` to `to` every `step` mm, each cast along `dir`; none may hit anything outside `allow_hits_in`. Cast from the side the mating part enters. `radius_mm` > 0 casts a ring of 8 more rays around each point, so a round pin of that radius must pass, not just its centre line. Every ray must cross the part's bounding box.

## relief

Is a region cut into, or standing up from, the face around it, and by how much?

Axis form (an axis-aligned face):

```json
{"name": "letters are cut in", "axis": "y", "viewer": "-", "surface": -5.75,
 "region": {"x": [-3.8, 3.8], "z": [1.8, 3.2]}, "expect": "recessed", "depth_mm": 0.2, "why": "CLARITY E2"}
```

`axis` is the face's normal axis, `viewer` the side you look from (`"-"` or `"+"`), `surface` the surrounding face's coordinate on that axis, `region` the two other axes as `[min, max]`.

Normal form (any face):

```json
{"name": "logo is raised", "normal": [0.707, 0, 0.707], "center_mm": [5, 0, 5], "size_mm": [4, 2],
 "surface_point": [5, 0, 5], "up": [0, 1, 0], "expect": "raised", "depth_mm": 0.3}
```

`normal` points toward the viewer, `surface_point` is any point on the surrounding face, `size_mm` is width by height across the face, `up` (optional) orients the region.

| Key | Meaning |
|---|---|
| `expect` | `"recessed"` (cut in) or `"raised"` (stands up). A flat feature has no relief test. |
| `depth_mm` | Expected depth or height; must be larger than `tol_mm`. |
| `tol_mm` | Height treated as flush (default 0.05). Lower it for very shallow detail. |
| `step_mm` | Ray spacing across the region (default 0.05). |
| `min_share` | Share of the region that must show the expected polarity (default 0.05). |

A step where one area sits lower is a `recessed` test on the lower area.

## views

```json
"view_ppmm": 24,
"views": [{"name": "top", "face": "+Z", "right": [0, 1, 0], "up": [-1, 0, 0], "frame_mm": [20, 30], "center_mm": [0, 0, 3]}]
```

| Key | Meaning |
|---|---|
| `face` | `+X -X +Y -Y +Z -Z`: the side you look at. |
| `right`, `up` | Both or neither: image right and up in model axes, to match a photo's orientation. They must be perpendicular, and right × up must point out of `face`. |
| `ppmm`, `frame_mm`, `center_mm`, `margin_mm` | Scale, frame size (default: the part plus `margin_mm`), and centre. |
| `base` | The relief map's main face: `auto` (default: the outermost level covering at least `base_min_share`, 15%, of the view), `mode` (the largest level), `outermost`, `local` (a moving average over `base_window_mm`, default 2: for curved faces), or a number (the face's world coordinate). |
| `relief_range_mm` | Height at which the colours saturate (default 0.5). |
| `max_pixels` | Cap per view (default 6,000,000); ppmm is lowered with a note above it. |

## sheet

```json
"sheet": [{"view": "top", "photo": "reference/photo-1-top.jpg", "photo_ppmm": 16.5, "photo_center_px": [711, 978], "label": "Top"}]
```

`view` names one of the `views`. `photo_ppmm` is that photo's scale at the part (from `photo_tools.py ruler`), and `photo_center_px` the part's centre in the photo as you see it (EXIF-upright). `photo_rotate` (0, 90, 180 or 270, counter-clockwise) turns the photo to match the view; the centre point turns with it.
