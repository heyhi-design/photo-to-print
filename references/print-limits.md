# Print limits and scale

Starting points, not facts about the maker's printer. Every printer, resin and setting differs: print a small test card of grooves and ridges at 0.1 mm steps once, write the real numbers into `checks.json` → `limits`, and keep them for every later part.

## What `print_check` uses by default

| | Resin (MSLA) | FDM (0.4 mm nozzle) |
|---|---|---|
| Smallest detail that stands up and survives (`min_feature_mm`) | 0.2 | 0.4 |
| Thinnest wall that's not fragile (`min_wall_mm`) | 0.4 | 0.8 |
| Narrowest groove or gap that stays open (`min_gap_mm`) | 0.3 | 0.5 |
| Overhang that needs support | reported only (resin uses supports anyway) | steeper than 45 deg from vertical: FAIL |

## Text and fine detail

- Cut-in letters: stroke (groove) at least 0.25 to 0.3 mm wide and 0.2 mm deep on resin. Paint fills 0.05 to 0.1 mm, so go deeper if it will be painted.
- Raised letters: at least 0.2 mm high and 0.25 mm wide on resin.
- Blender's built-in font is too thin at small sizes (0.18 mm strokes at 1.3 mm letter height). Use a rounded bold font. Thickening text with Blender's `offset` makes the letter outlines overlap themselves; switch fonts instead.
- Sharp inside points of letters (where a bowl meets a stem) will soften. That's normal; note it, don't fight it.

## Scale models

If the maker wants a part at model scale, the size can come from two places. Ask which (CLARITY C1):

- **Measure the object** (a kit part he has): build 1:1 from caliper readings.
- **Scale the real thing:** model size = real size ÷ scale. A real 250 mm brake caliper is 20.8 mm at 1:12, 12.5 mm at 1:20, 10.4 mm at 1:24, 5.8 mm at 1:43.

At 1:43 and smaller, much real-world detail falls below the printer's limits. Decide with the maker what to keep (CLARITY G4) before modelling, not after.

## Orientation (resin)

- Faces the maker needs clean (CLARITY H2) point away from the build plate and the supports.
- Angle small parts 30 to 45 degrees so each layer's area changes slowly.
- Small solid parts don't need hollowing.
- The kit exports the STL in the model frame (Z = 0 on the face that sits on the plate); the slicer does the tilt.
