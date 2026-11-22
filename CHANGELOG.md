# Changelog

All notable changes to this project are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/).

## [0.1.1] - 2026-11-22

An adversarial review (code, docs and a fresh-install reuse test) found day-0 bugs. All fixed.

### Fixed
- `photo_tools.py ruler` reported half (or a third of) the true scale on close-up photos above about 31 px/mm: it now finds the tick spacing by autocorrelation and refines it, correct from 12.5 to 120 px/mm.
- A clear ray or sweep that missed the part entirely passed. Every clear test must now cross the part's bounding box, only `expect: "hit"` rays count as positive controls, and a clear test can name its own `control`.
- A typo could change what a test meant (`"expect": "Clear"` ran as "hit"; `"min_wall"` in `limits` was ignored). `checks.json` is now validated before anything runs (`scripts/spec.py`), and invalid values are errors.
- A project with no function or relief tests passed. It is now INCOMPLETE unless `allow_untested` gives a reason.
- `kit.py verify` checked an STL left over from an older build. Builds now write a build record, and check/verify refuse a stale STL.
- Projects stored the kit's absolute path, so they broke when the skill moved, and on Windows the path made the build script a syntax error. The kit now passes its location to Blender at run time.
- The overhang limit was wrong at any angle other than 45 degrees.
- `accepted_thin` / `accepted_gaps` boxes were tested against rounded cluster points; every sample point is now tested.
- Narrow grooves never failed. Gaps under `min_gap_mm` now fail unless accepted, judged on the region's median width; hairline inside corners and sharp wedge tips are warnings.
- Finely tessellated thin fins were skipped, and a face with flipped winding passed the mesh check.
- `views.py` ignored `face` when `right`/`up` were given, and reported negative faces' coordinates with the wrong sign. Views are validated, coordinates are true world values, and the relief map's main face defaults to the outermost large level (`base: auto`).
- Phone photos were read sideways (EXIF orientation ignored), and HEIC files crashed `info`.
- `annotate` labels overflowed or left the image, and a comma in a label crashed it.
- `select_only` could crash after objects were removed; a missing font silently fell back to Blender's thin built-in font; booleans failed on Blender versions without the MANIFOLD solver.
- A missing sheet photo crashed `verify` after printing PASS, leaving the previous review sheet in place.
- Part names with quotes broke the generated files; names are now restricted to letters, digits, `.`, `_` and `-`.
- Docs: the README's account of the original ray failure, gendered pronouns, Gate 2 wording, perspective figures and several cross-references.

### Added
- `kit.py gate`: counts open ledger rows, looks for the maker's "go", and lists D and E rows no test cites.
- `references/checks-reference.md`: every `checks.json` key and rule in one place.
- `scripts/presets.json`: the one home for printer-process limits.
- `partlib`: `place_text` (lettering on any face, scaled uniformly), `hole` (through, blind, counterbore, countersink), `cylinder` on any axis or as a cone, `mirror_copy`, `array_copies`, `find_font`, `print_log`.
- Sweeps take `radius_mm` (a round pin, not just its centre line); relief checks take a normal form for faces that aren't axis-aligned; views take `base: local` for curved faces and a pixel cap.
- `print_rotation_deg` and `accepted_overhang` for the overhang check.
- `kit.py selftest` now has seven cases, including an off-part ray, a reversed sweep, a typo and an empty spec.
- More unit tests (ruler scales and axes, EXIF, HEIC message, annotate, spec validation, presets mirror, gate).

## [0.1.0] - 2026-11-22

First public release.

### Added
- `SKILL.md`: the staged process (set up, interview, measure, tests first, build, review, deliver), with gates after the interview, the tests and the build. No modelling until the clarity ledger has no open questions and the maker has said go.
- `references/intake-interview.md`: how to ask (rounds of four, a ringed photo with every feature question, plain words for surface detail, confirm-back), the full question bank, and how each answer becomes a test.
- `scripts/kit.py`: `doctor`, `selftest`, `new`, `build`, `check`, `verify`.
- `scripts/print_check.py`: checks any STL inside Blender's Python. Single body, manifold, self-intersections, thin walls and narrow gaps against resin or FDM limits, overhangs, ray and sweep clearance with a required positive control, raised-or-cut-in relief checks, and a GLB scale guard.
- `scripts/views.py`: ray-cast face views at an exact px/mm, lit from the upper left with cast shadows, plus a relief map that doesn't depend on lighting.
- `scripts/review_sheet.py`: photo, model and relief map side by side, with the check results.
- `scripts/photo_tools.py`: `info` (flags downscaled copies), `ruler` (px/mm from tick spacing, with a drift scan), `grid`, `annotate`.
- `scripts/partlib.py`: Blender helpers proven on the first project (validated booleans, bevel order, text, unit-safe STL and GLB export).
- Templates for the clarity ledger, `checks.json`, the build script and the project README.
- References: photo guide, print limits and scale math, Blender rules, and the brake caliper worked example.
- Unit tests for the parts that don't need Blender, and a Blender self-test with positive and negative controls.
- `examples/` (the caliper's real checks), `docs/review-demo.png`, community files (contributing, code of conduct, security, support, issue and pull-request templates) and CI.
