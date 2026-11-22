# Clarity ledger: {{PART}}

Nothing gets modelled until this ledger has **0 OPEN rows** and the maker has read the build summary and said go. Every answer is written here the moment the maker gives it, in their words where possible. Questions and option wording come from `references/intake-interview.md` in the skill.

**Status key:** `OPEN` not answered yet · `CONFIRMED` the maker said it (quote or paraphrase, confirmed back) · `MEASURED` read from photos or a caliper, and the maker agreed with the number · `ASSUMED-OK` a default the maker explicitly approved after seeing it on a picture · `N/A` does not apply (say why)

A default is never written as `ASSUMED-OK` without the maker's yes. An ambiguous word (emboss, engrave, relief, flush, through) is never `CONFIRMED` until the confirm-back used plain words and a picture.

## Gate

| Check | Value |
|---|---|
| OPEN rows | (count; must be 0) |
| Questions asked so far | (count) |
| Rounds | (count) |
| Build summary sent | (date) |
| The maker's go | "(their words)" (date) |

## A. The subject and the ask

| # | Question | Answer | Evidence | Status |
|---|---|---|---|---|
| A1 | What is this object, exactly? (part name, what it belongs to, kit and scale if it's a model part) | | | OPEN |
| A2 | Where does this one come from? (kit part, real object, your scratch-build, an existing file) | | | OPEN |
| A3 | Exact copy, improved copy, modified copy (how?), or a new design inspired by it? | | | OPEN |
| A4 | What is the print for? (fitting to a model, spare part, product to sell, test print, display or photo prop) | | | OPEN |
| A5 | How many, and any variants? (mirrored left/right pair, several sizes) | | | OPEN |
| A6 | What would make you say "that's it"? What matters most: accuracy, detail, strength, or easy printing? | | | OPEN |

## B. Use, selling and markings

| # | Question | Answer | Evidence | Status |
|---|---|---|---|---|
| B1 | Personal use, or sold / given away / posted or shown online? | | | OPEN |
| B2 | Any brand names, logos, team marks or other trademarks on it? Keep, remove, make generic, or leave a blank area for a decal? | | | OPEN |
| B3 | Is it a copy of a part from a commercial kit? (If it will be sold, this is the maker's call to make with proper advice; the skill flags it and does not decide.) | | | OPEN |

## C. Size and scale

| # | Question | Answer | Evidence | Status |
|---|---|---|---|---|
| C1 | Same size as the object (1:1), or a different scale? If scaled, from what to what, and which dimension sets it? | | | OPEN |
| C2 | Caliper readings: overall length, width, height (the single most valuable input; photos alone are about ±1 mm) | | | OPEN |
| C3 | Critical sizes: holes, slots, pins, anything that must fit something | | | OPEN |
| C4 | How close is close enough? (±0.1 must fit, ±0.3 looks right, ±1 rough) | | | OPEN |

## D. Function and fit

| # | Question | Answer | Evidence | Status |
|---|---|---|---|---|
| D1 | Does anything pass through, slide into, sit in, clip onto or mount on this part? Name each one. | | | OPEN |
| D2 | For each: its size, the side it comes in from, the side it leaves from, and how much clearance | | | OPEN |
| D3 | Which openings go all the way through, and which stop partway? (one row per opening, ringed on a photo) | | | OPEN |
| D4 | How does it attach to the model? (glue face, pin, peg, press fit) Where? | | | OPEN |
| D5 | One solid piece, or separate pieces (moving parts, pins)? Separate pieces are one project each. | | | OPEN |

D1 to D3 answers become ray or sweep tests in `checks.json`, cast from the side the mating part enters (a ray only reports the first thing it hits). D4 and D5 are recorded here only; they have no geometric test.

## E. Features (one row per numbered feature on the annotated photos in `questions/`)

Ask polarity in these words only: **"cut into the surface"** (a groove you could fill with paint) · **"stands up from the surface"** (you could catch a fingernail on its edge) · **"a step where one area sits lower"** (no line on its own, just a change of level).

| # | Feature (ring no. + photo) | What it is | Cut in / stands up / step / flat print (flat: recorded only) | Depth or height (mm) | Keep / nice-to-have / leave off | Status |
|---|---|---|---|---|---|---|
| E1 | | | | | | OPEN |

Any text: exact characters, upper/lower case, reading direction, which side reads correctly, and roughly what weight of letter.

## F. Sides the photos don't show

| # | Question | Answer | Evidence | Status |
|---|---|---|---|---|
| F1 | List every side with no photo. For each: a new photo (best), the maker's description, or a default the maker approves after seeing it drawn | | | OPEN |
| F2 | Which features are one-sided, and which end are they on? (marked across photos with the same sticky-note label) | | | OPEN |
| F3 | Mirror symmetry: left = right? front = back? | | | OPEN |
| F4 | Anything hidden inside? (hollow, channels) | | | OPEN |

## G. Finish and detail

| # | Question | Answer | Evidence | Status |
|---|---|---|---|---|
| G1 | Surface: smooth, cast texture, machined? Should the print copy it? | | | OPEN |
| G2 | Edges: crisp or softened like a casting? | | | OPEN |
| G3 | Will it be primed or painted? (paint fills about 0.05 to 0.1 mm, so very fine cut-in detail may vanish) | | | OPEN |
| G4 | Detail below what the printer can make: thicken it, keep it at the limit, or drop it? | | | OPEN |

## H. Printing

| # | Question | Answer | Evidence | Status |
|---|---|---|---|---|
| H1 | Which printer and process? (resin printer + resin, or FDM + nozzle size) | | | OPEN |
| H2 | Which faces must come out clean (no support marks)? | | | OPEN |
| H3 | Solid or hollow? Need an attachment tab or sprue? Several on one plate? | | | OPEN |

## I. Files and logistics

| # | Question | Answer | Evidence | Status |
|---|---|---|---|---|
| I1 | Files wanted: STL (always), 3MF, Blender file, preview renders? | | | OPEN |
| I2 | Where should the project folder live? | | | OPEN |
| I3 | Any deadline (an event, a shoot, a build day)? | | | OPEN |
| I4 | Anything else I should know that I haven't asked? | | | OPEN |

## Change log

Every answer that changes after the first build is added here with the date, the old answer, the new one, and the test added to `checks.json` so it can't regress.

| Date | Row | Was | Now | Test added |
|---|---|---|---|---|
