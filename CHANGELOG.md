# Changelog

All notable changes to this project are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-11-22

First public release.

### Added
- `SKILL.md`: the six-stage process (interview, measure, tests first, build, review, deliver) with a gate at each stage. No modelling until the clarity ledger has no open questions and the maker has said go.
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
