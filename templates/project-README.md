# {{PART}}

One line: what this is, who it's for, and the current version.

## Status

| Version | Date | What changed | print_check | The maker's review |
|---|---|---|---|---|
| v1 | | first build | | |

## Where things are

- `CLARITY.md`: every question asked and the maker's answer. The build gate.
- `reference/`: the maker's original photos (`photo-N-<side>.jpg`), never resized copies.
- `questions/`: the annotated images that went with each question.
- `checks.json`: what "right" means, as tests (from CLARITY.md).
- `scripts/build_part.py`: the geometry; every number in PARAMS with its source.
- `exports/`: `<name>_<version>.stl` (mm, the print file) and `.glb` (preview, metres).
- `renders/review_<name>_<version>.jpg`: photo | model | relief map, the review sheet.
- `reports/`: print_check results.

Rebuild and re-verify after any change:

```bash
python3 <kit>/kit.py build <this folder>
python3 <kit>/kit.py verify <this folder>
```

## Numbers and confidence

| Dimension | Value (mm) | Source | Confidence |
|---|---|---|---|

## Print notes

- Process, printer, resin or filament:
- Orientation on the plate, and which faces must stay clean:
- Supports:
- Features at or below the printer's limit (from print_check):
- Finished size check after printing (the maker's caliper reading of the print):

## Open follow-ups
