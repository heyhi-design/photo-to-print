# Blender and tooling gotchas

Each rule cost time on a real project (Blender 5.2.1, November 2026). The kit's scripts already follow the ones marked **(kit)**; the rest are for when you write geometry or drive Blender live.

## Running Blender

- Headless works everywhere and is the default: `Blender --background --factory-startup --python script.py -- args`. **(kit)**
- Always add `--python-exit-code 2` and check the exit code before trusting any printed output. A segfault (exit 139) once hid behind a JSON parse error. **(kit)**
- `render.opengl` fails in background mode (no OpenGL context). The kit's views ray-cast instead, so no render engine is needed. **(kit)**
- `blender` is not on the macOS PATH. Use `/Applications/Blender.app/Contents/MacOS/Blender`, or set `BLENDER`. **(kit)**
- Bundled docs (and the MCP's docs) can lag the installed version. Probe an operator before deciding it's missing: `bpy.ops.wm.stl_export.get_rna_type()`.
- Pass flags like `DO_EXPORT` through the exec namespace so one script serves live and headless runs. **(kit template)**
- Never hard-code absolute project paths in scripts. The caliper's six absolute paths all broke when its folder moved. Resolve from `__file__` or `--project`. **(kit template)**

## The Blender MCP (optional, live)

- The live tools need the add-on running inside Blender on `127.0.0.1:9876`; the desktop extension alone is not enough. Check with `lsof -nP -iTCP:9876 -sTCP:LISTEN`.
- The add-on needs Preferences > System > Allow Online Access on.
- `*_for_cli` tools need `BLENDER_PATH` set. If the open GUI file has unsaved edits, they run on a temporary copy that is deleted afterwards, so their saves are lost.
- `render_viewport_to_path` is a full camera render saved into Blender's temp folder, whatever path you pass.
- Debug budget: 2 to 3 attempts on a stalled connector, then go headless. Nothing in the kit needs the live link.
- Drive Blender with code, not clicks. Background clicks land in the wrong place in Blender's UI (one changed Undo Steps instead of a checkbox).
- Before a headless run saves the same `.blend` the GUI has open, ask the maker to close it there, or save to a new file.

## Geometry

- Set units first: `scale_length = 0.001`, length unit millimetres, so 1 unit = 1 mm. **(kit: `setup_mm_scene`)**
- Booleans: try the MANIFOLD solver, fall back to EXACT, and check every result (0 non-manifold edges, 0 loose geometry, volume changed and positive). **(kit: `boolean`)**
- Union every detail into ONE body. A plain join leaves overlapping shells that pass a simple watertight check (and report inflated volume). **(kit: print_check counts shells and self-intersections)**
- Bevel primitives before booleans. A whole-mesh bevel after the booleans collapsed to almost nothing (clamped) or self-intersected 95 times (unclamped). **(kit: `bevel_obj`)**
- Add pressed-in parts (pins, screw heads) after the bevel, with sharp junctions.
- MANIFOLD booleans can leave vertices about 7e-7 mm apart. Weld with `remove_doubles(dist=1e-5)` and `dissolve_degenerate`, then re-check. **(kit: print_check welds at 1e-5)**
- `convex_hull`: filter `geom_interior`/`geom_unused` to vertices before deleting. **(kit: `hull_obj`)**
- Text: get the mesh with `meshes.new_from_object(evaluated)` after `depsgraph.update()`. Use a rounded bold font at small sizes. **(kit: `text_mesh`)**
- Capture object references when you create them; names auto-suffix `.001`.
- Set mode, active object and selection explicitly before every operator. Edit-mode changes go through `bmesh` and must be written back.

## Checking

- `ray_cast` returns only the FIRST hit. A defect can hide behind something (the caliper's crossmember sat under the pad pin). Cast clearance rays from the side the mating part enters, and never put a positive control where a defect could hide. **(kit: sweeps + positive-control rule)**
- `scene.ray_cast` hits objects hidden from render but skips objects hidden in the viewport. Check what you hit. (The kit checks the exported STL alone, so this can't happen there.)
- Exclude triangle pairs that share a vertex from `BVHTree.overlap(self)`, or every edge counts as a self-intersection. **(kit)**
- Triangulate before thickness rays and start each ray just inside the surface, or non-flat faces give false zero readings. **(kit)**
- Thickness and gap rays: skip hits on neighbouring triangles and require an opposite-facing wall, or inside corners read as 0.005 mm walls. **(kit)**
- Re-import the STL in a fresh factory-startup process. Importing into a scratch scene inside the running session crashed Blender 5.2.1. **(kit)**
- `is_dirty` can read True right after a save. Check the file's modification time instead.

## Export

- STL: `global_scale=1.0`, `use_scene_unit=False`, `apply_modifiers=True`, Z up. Round-trips exactly in mm. **(kit: `export_stl`)**
- GLB: glTF ignores the scene unit scale, so a direct export is 1000x too large. Export a copy scaled by 0.001. **(kit: `export_glb`; print_check fails a 1000x GLB)**

## Rendering for review

- Light comparison views from the upper left. A lower-left key light made raised letters look cut in and hid two defects from the agent's own review. **(kit: views)**
- Straight-on, a 0.2 mm detail's walls are parallel to the line of sight and invisible; only shadows show it. The relief map shows polarity without depending on light at all. **(kit: views)**

## Shell and machine

- zsh does not word-split `$VAR`: use `${=VAR}` when a variable holds several arguments.
- `python3 -I` drops user site-packages (Pillow disappears). Run the kit's scripts without `-I`.
- `AskUserQuestion` takes at most 4 questions per card.
