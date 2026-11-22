# Worked example: the miniature brake caliper (November 2026)

The project this skill was built from. A cast-metal miniature brake caliper about 20.5 × 11.5 × 5.8 mm, modelled in Blender from five ruler photos for a 1:1 resin print. It was a personal model (it carries a real manufacturer's wordmark, so it stays off anything sold or posted).

## How it ran

Two sessions, 117 minutes, 334 tool calls.

| Session | Minutes | What happened |
|---|---|---|
| Discovery | 58.5 | Read the photos, calibrated the rulers (3 passes), surveyed the Blender MCP, wrote a build prompt, adversarial review found 13 issues, installed the MCP add-on mid-session |
| Build | 58.6 | Re-measured photos by hand (16.5 min), wrote an 893-line build script, debugged Blender quirks (~11 min), verified, rendered, sent v1; the owner's review found 3 defects; v1.1 cycle (14.4 min) |

## The three defects in v1, and where each really came from

| Defect | What v1 did | Real cause | One question that would have prevented it |
|---|---|---|---|
| A crossmember blocked the slot, so a brake disc couldn't slide in | A rib ran across the slot on the bottom face, and the slot was closed at both ends by default | Nobody asked what the part does. The slot's purpose (a disc enters from the bottom and runs out the ends) was never written down, so nothing tested it | "Does anything pass through this part? Which way does it come in and go out?" (CLARITY D1/D2) |
| The wordmark was raised; it should be cut in | Raised 0.2 mm | The owner said "emboss" meaning cut in; it was recorded as raised and locked "do not re-ask". The comparison render was lit from the lower left, which made raised letters look cut in, so the agent's own review passed it | "Is the word cut into the surface, or does it stand up from it?" with a ringed photo, then a confirm-back (intake rule 5 and 6) |
| A curve read as a raised bead; it was a step where the face above is lower | A 0.2 × 0.6 mm raised line | Under one-sided light, a step's edge shows a highlight and a shadow, which looks like a bead's two edges. The prompt asserted "raised line" | "Ring 4: a line standing up, or a step where one side sits lower?" (CLARITY E, step wording) |

None of the three was a modelling error. Every one was a question not asked, or a word not confirmed, before modelling. That is why this skill puts the interview first and blocks the build on it.

## Why the original checks were green anyway

The v1 checks compared the mesh to the build script's own numbers, never to what the part is for:

- The "slot is open" rays came down from the top. A ray reports only the first thing it hits, and the positive-control ray at the centre hit the pad pin, which sat directly above the crossmember. The defect was behind the control.
- No check tested raised vs cut in at all.

Replayed through this kit (a v1-like model regenerated from the build script with the v1 wordmark choice, no step, and the crossmember seeded back in):

| Check set | v1-like geometry | v1.1 (approved) |
|---|---|---|
| The checks v1 actually ran | PASS (0 of 3 defects caught) | PASS |
| This kit, with tests written from the answers | FAIL, 7 failures covering 3 of 3 defects | PASS |

The kit's failures read like the owner's review: "sweep 'disc enters from Face B': 17 of 131 rays blocked, first at [-0.8, 0, 0]", "relief 'wordmark is cut in': expected recessed 0.2 mm, found 30% raised", "relief 'band above the arch is sunk': found flat".

Both check sets are in `examples/`: `caliper-checks-v1-session.json` (what v1 ran) and `caliper-checks.json` (written from the answers).

## Other numbers from the replay

- print_check on the approved STL matches the session's own verification exactly: volume 700.668 mm³ (session: 700.67), 8,844 triangles, 20.5 × 12.8 × 6.1 mm.
- The thin-feature scan found, unaided, the issue the session documented by hand: the wordmark's letter islands come to near-zero points. It also found a 0.013 mm crevice where each screw-head dome meets the block end wall, which the session never recorded (harmless on resin: it fills in).
- `photo_tools.py info` flagged all five photos as reduced copies (1500 × 2000, metadata stripped) at minute 0. In the session this surfaced mid-build, when the owner said the agent's crops were "so blurry".
- `photo_tools.py ruler --scan` read 16.90 → 16.57 → 16.31 px/mm down Photo 1's ruler in one command (the session took three passes to reach 16.7 / 16.5 / 16.3).
- A full verify (checks, three photo-matched face views with relief maps, review sheet) takes about 2 seconds. The session spent about 8 minutes on the same ground, plus four rounds of lighting fixes.
- A GLB exported without the 0.001 scale fails the check with the fix in the message (the session's adversarial review had to catch this by reading the prompt).

## What it would look like with this skill

1. Photos arrive → `info` flags reduced copies → ask for originals, send the photo guide (end shots, ruler at face height, side-lit detail shots, an end label).
2. Interview rounds, each with ringed photos: what is it and what's it for (a 1:1 replica for a model), what passes through (a disc, from the bottom, out both ends), caliper readings of L/W/H, then each ring: the word is cut in, the curve is a step down, the screw heads stand up. Unseen ends: a photo, not a default.
3. `checks.json` written from those answers: a disc sweep from below, end-to-end clear rays, relief checks on the word and the band, the envelope from the caliper readings.
4. Blockout, then details, each verified; the first thing the owner sees already passes every test written from their own answers.
