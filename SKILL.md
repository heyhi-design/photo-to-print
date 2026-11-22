---
name: photo-to-print
description: >-
  Turn photos of a physical part into a verified, print-ready 3D model (STL):
  scale-model parts, replacement or upgrade pieces, small products to print.
  Starts with a thorough clarifying interview (as many questions as it takes,
  each with the feature ringed on a photo, every answer logged in a clarity
  ledger) and builds nothing until every answer is confirmed. Then measures the
  photos, writes the answers as automatic tests (what must pass through it,
  which details are cut in or stand up, its size), models it in Blender, and
  checks it before the maker ever sees it. Use when someone says "model this
  part", "make a 3D print of this", "turn these photos into an STL", "can you
  print a copy of this", "I want to resin print this", "make this at 1:12",
  "3D model from photos", "print-ready file", or sends photos of an object with
  a ruler. NOT for designing a new part from scratch with no physical
  reference, editing an existing STL, or deciding whether a copy may be sold
  (the maker's call, with proper advice).
---

# Photo to Print

*Ask everything first. Then build it right the first time.*

This skill takes someone from "here are some photos of a part" to an STL they can send to their printer, with a review sheet that shows the model beside their own photos. It was built from one real project (a 20 mm brake caliper) whose three first-build defects all came from questions nobody asked. So the interview is the main part of the work here, not a formality before it.

"The maker" below means the person you're building for: the one with the part, the photos and the printer.

**Kit:** `scripts/kit.py` (one entry point), with `photo_tools.py`, `print_check.py`, `views.py`, `review_sheet.py` and the Blender helper library `partlib.py`. Needs Blender (free) and python3 with Pillow and numpy. Run `python3 scripts/kit.py doctor` first.

**Load on demand:**
- `references/intake-interview.md`: how to ask, the full question bank, and how answers become tests. **Read it before asking the maker anything.**
- `references/photo-guide.md`: the shot list to send the maker.
- `references/print-limits.md`: resin and FDM limits, text sizes, scale-model math.
- `references/blender-gotchas.md`: rules learned the hard way. Read before writing geometry.
- `references/worked-example-caliper.md`: the project this came from, with numbers.
- `examples/caliper-checks.json`: a real `checks.json`, every test traced to an answer.

## What stays the maker's

The kit measures and checks. It never decides these, and never words them as settled:

- whether it looks right, and whether it's good enough to fit, film or sell;
- what to keep, simplify or leave off when detail is below the printer's limit;
- anything about selling a copy of someone else's design or a trademarked mark. Flag it, mark the file personal-use until the maker decides, and say it's a question for proper advice, not for this skill.

## The stages

Each stage ends at a gate. Don't pass a gate on your own judgment; the gate says what has to be true.

### 0. Set up (2 minutes)

1. `python3 scripts/kit.py doctor`. Fix anything marked `[need]` with the maker before going on.
2. `python3 scripts/kit.py selftest` once per machine: it proves the checks catch real defects here.
3. Ask where the project folder should live, then `python3 scripts/kit.py new <folder> --name <part-name>`.
4. Put the maker's photos in `<folder>/reference/` and run `python3 scripts/photo_tools.py info '<folder>/reference/*'`.

A live Blender connector (an MCP that drives an open Blender) is optional. Every step runs headless. If a live connector stalls, stop after 2 to 3 tries and go headless; never spend a session fixing it.

### 1. The interview (the main work)

Read `references/intake-interview.md` and follow it. In short:

1. **Round 0.** If `info` flagged the photos as reduced copies, the first message asks for the originals. If any side is missing, or there's no ruler at the face's height, send the shot list from `photo-guide.md`. Ask for caliper readings of length, width and height.
2. **Look, then number.** Read every photo. Write a short "here's what I think this is". Make annotated images with every visible feature ringed and numbered (`photo_tools.py annotate`), saved in `questions/`.
3. **Ask in rounds** of up to four questions, most consequential first: what it is and what it's for → what passes through or attaches → size → each ringed feature (cut in / stands up / a step) → the sides no photo shows → finish → printer → files. Every feature question goes with its annotated image, sent as a file. Plain words only: never "emboss" or "engrave" in a question.
4. **Confirm back** after each round, in plain words, before marking anything CONFIRMED in `CLARITY.md`.
5. **Keep going** until no row in `CLARITY.md` is OPEN. If the maker gives a short answer to a big question, follow up gently with what the photo can't tell you. Don't stop because there have been "enough" questions; stop when nothing is left to guess. Hidden sides get a photo or a description. A default goes in only after the maker has seen it drawn and said yes.
6. **The build summary.** One message: what you'll build, every size and where it came from, what passes through it, every ringed feature with its polarity, the defaults the maker approved, what the printer limits will do to fine detail, and the files you'll make. Ask: "Anything wrong or missing? If not, say go."

**Gate 1:** `CLARITY.md` shows 0 OPEN rows, and the maker's "go" is quoted in its Gate table. No geometry before this. Not a blockout, not a test cube.

### 2. Measure

1. Calibrate each photo: `photo_tools.py ruler <photo> --box ... --axis y --scan 4` (the scan shows perspective drift down the ruler; use the segment at the part's height).
2. Read sizes with `photo_tools.py grid` crops at a known px/mm. Correct for the face's height above the ruler (see the `ruler` output).
3. Write every number into `scripts/build_part.py` PARAMS with its source (photo, caliper, CLARITY row) and confidence. Caliper readings beat photo readings every time.
4. Any number that comes out low-confidence and matters (it sets a fit, or two photos disagree by more than the tolerance in CLARITY C4): go back to the maker for a measurement. Don't average your way past it.

### 3. Write the tests before the model

Fill `checks.json` from the ledger, using the table at the end of `intake-interview.md`: the envelope from the caliper readings; a sweep for everything that passes through, cast from the side it enters; clear rays for every through-opening, each with a positive control on nearby solid material; a relief check for every cut-in, standing-up or stepped feature; the printer's limits. Add `views` matching each photo's orientation, and a `sheet` row per photo (its px/mm and the part's centre pixel), so the review sheet lines model and photo up.

**Gate 2:** every D and E row in `CLARITY.md` has a test in `checks.json`.

### 4. Build

1. Write the geometry in `scripts/build_part.py` with `partlib` (read `blender-gotchas.md` first). Blockout first.
2. `python3 scripts/kit.py build <folder>`, then `python3 scripts/kit.py verify <folder>`. Look at the review sheet yourself: does the silhouette match each photo?
3. Add cuts and details one at a time, re-running `verify` as you go. Booleans go through `pl.boolean`, which checks every result.

**Gate 3:** `kit.py verify` says `RESULT: PASS`, and you have looked at the review sheet: every warm or cool patch on the relief map matches what the maker said in the ledger. Anything thin that print_check flags is either fixed or written into `CLARITY.md` G4 with the maker's answer and added to `accepted_thin`.

### 5. Review with the maker

1. Send the review sheet (`renders/review_<part>_<version>.jpg`) as a file, with a few lines: what to look at, what's at the printer's limit, the defaults they approved.
2. Ask the maker to check the relief map against the real part: "Orange stands up, blue is cut in. Does every patch match?"
3. Every correction: write it into the `CLARITY.md` change log **and add or fix the test first**, so the current model fails it. Then fix the model until it passes. A correction that isn't a test can come back.
4. Bump `part.version` in `checks.json` for each new version; never overwrite the previous files.

### 6. Deliver

1. The STL (mm), the GLB preview, and the review sheet, all sent as files.
2. `README.md` updated: status table, numbers and confidence, print notes (orientation, which faces stay clean, supports, features at the limit).
3. Ask the maker for one caliper reading of the printed part when it's done, and log it. That's the only real proof the print matches.

## Scorecard (fill in at the end of every project)

These are what this skill exists to move. The caliper's numbers are the baseline.

| Measure | Caliper baseline | Target |
|---|---|---|
| OPEN ledger rows when modelling started | about 10 decisions open or defaulted; 0 asked up front | 0 |
| Defects the maker finds in the first version | 3 | 0 |
| First-version defects the checks caught before the maker saw it | 0 of 3 | all of them |
| Times the maker had to ask for decisions, files or photos the agent should have offered | 5 | 0 |
| Photos found to be reduced copies | mid-build | before the first question |
| Review rounds to an approved print | 2 | 1 |
| Printed part's caliper reading vs the model | not measured | within CLARITY C4 |

If a project misses a target, write a short `references/worked-example-<part>.md` saying why, and fix the skill.

## Close-out

End each session with three short sections for the maker: **What changed** (and why), **Checks** (the print_check summary, with numbers), **Next** (the one thing that would make the next version better, usually a caliper reading or a photo).
