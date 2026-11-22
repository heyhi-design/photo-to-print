# photo-to-print

You photograph a small part next to a ruler, an agent models it, and the first print comes back wrong in a way the model never showed you. The lettering stands up when it should be cut in. A bar sits right where something has to slide through. Nothing in the geometry was broken. Someone guessed at a thing the photos couldn't say, and nobody asked.

photo-to-print is a skill for Claude Code (or any agent that can read a `SKILL.md` and run shell commands) that turns photos of a physical part into a print-ready STL. Most of its effort goes in before any modelling: it asks the person who owns the part every question the photos leave open, writes each answer down, and turns the answers into tests the model has to pass before anyone looks at it.

Designed and built by [Cody Clark](https://github.com/codysue) at [HeyHi](https://heyhi.design). MIT licensed.

![The same 20 mm test part built twice. Left, as confirmed: letters cut in (blue on the relief map) and the slot open end to end; print_check passes. Right, the two mistakes from the first real project: letters raised (orange) and a bar across the slot; print_check fails both.](docs/review-demo.png)

## Why it asks so many questions

It was built from one real project: a cast-metal miniature brake caliper, about 20.5 × 11.5 × 5.8 mm, modelled in Blender from five phone photos for a 1:1 resin print. The first version came back with three defects. The lettering was raised when it should have been cut in, because the word "emboss" meant cut in to the person who said it and raised to the agent that wrote it down. A curved line on one face was modelled as a raised bead when it was the edge of a step down. And a crossmember ran across the slot where the brake disc has to slide through, because nobody had asked what the part has to do.

Every one of those was a question, not a modelling error. The checks the agent ran were green the whole time: they compared the model to its own numbers, and the one ray meant to prove the slot was open sat directly above the crossmember, so it hit something else first and never saw it.

Replayed through this kit, the same three defects fail seven checks before anyone opens a review sheet, and the approved version passes all of them. The numbers and the full story are in [`references/worked-example-caliper.md`](references/worked-example-caliper.md).

## How a project runs

1. **Interview.** The agent reads the photos, rings and numbers every feature it can see, and asks in rounds of up to four questions, each with the ringed photo attached. Surface detail is only ever asked as "cut into the surface", "stands up from the surface", or "a step down". Every answer is read back in plain words before it's recorded in `CLARITY.md`, the project's question ledger.
2. **Gate.** Nothing gets modelled until the ledger has no open questions and the maker has said "go" to a written summary of exactly what will be built.
3. **Measure.** Ruler calibration from the photos, mm-grid crops, and caliper readings where they exist. Every number goes into the build script with its source and a confidence level.
4. **Tests first.** The answers become `checks.json`: the part's size, a sweep along the path of anything that passes through it, clear rays through every opening (each with a positive control that must hit nearby solid material), and a polarity check for every cut-in, raised, or stepped feature.
5. **Build and verify.** Blender builds the part headless from a parametric script. `kit.py verify` runs every check on the exported STL and draws a review sheet: the maker's photo, the model lit from the upper left, and a relief map, all at the same scale.
6. **Review and deliver.** The maker checks the relief map against the real part. Any correction becomes a failing test first, then a fix.

## What you need

- [Blender](https://www.blender.org/download/) (free). Tested with Blender 5.2.1 on macOS.
- Python 3.9 or newer with Pillow and numpy: `python3 -m pip install --user pillow numpy`
- Claude Code, or another agent that can read a `SKILL.md` and run shell commands.
- A ruler or calipers, and a phone camera. A caliper reading of the part's length, width, and height is the single most useful input; photos alone get you to about ±1 mm.

A live Blender connector (an MCP server that drives an open Blender window) is optional. Every step runs headless.

## Install

Clone it into your personal skills folder, or into a project's `.claude/skills/` folder:

```bash
git clone https://github.com/heyhi-design/photo-to-print ~/.claude/skills/photo-to-print
```

Then check your setup, and prove the checks work on your machine:

```bash
python3 ~/.claude/skills/photo-to-print/scripts/kit.py doctor
```

```bash
python3 ~/.claude/skills/photo-to-print/scripts/kit.py selftest
```

`selftest` builds a small test part twice, once correct and once with a bar across its slot and its letters raised, and confirms the checks pass the first and fail the second for those two reasons. If it fails, don't trust a green result on that machine yet.

## Use it

Start a session and ask in your own words, with the photos attached:

> Here are photos of a part from a kit I'm building. I'd like to resin print a copy at the same size.

Expect questions before anything else, and expect a lot of them. That's the skill working. When the agent sends its build summary, read it closely; it's the last cheap place to catch a misunderstanding. Say "go" when it's right.

Each part gets its own folder:

```
my-part/
  CLARITY.md            every question asked, every answer, and your "go"
  checks.json           what "right" means, as tests
  scripts/build_part.py the geometry; every number with its source
  reference/            your original photos
  questions/            the ringed images that went with each question
  exports/              my-part_v1.stl (mm, the print file) and .glb (preview)
  renders/              the review sheet for each version
  reports/              print_check results
```

### Running the kit directly

The agent drives these, but they work on their own too:

| Command | What it does |
|---|---|
| `kit.py doctor` | Finds Blender and the Python packages, says what's missing |
| `kit.py selftest` | Proves the checks catch real defects on this machine |
| `kit.py new <folder> --name <part>` | Creates a project from the templates |
| `kit.py build <folder>` | Runs `scripts/build_part.py` in headless Blender and exports the STL and GLB |
| `kit.py check <folder>` | Runs every check in `checks.json` on the current STL |
| `kit.py verify <folder>` | Check, face views, and the review sheet |
| `photo_tools.py info <photos>` | Flags downscaled or stripped copies before anyone measures them |
| `photo_tools.py ruler <photo> --box ... --axis y --scan 4` | Pixels per mm from the ruler ticks, and how that drifts across the photo |
| `photo_tools.py grid <photo> --ppmm ...` | Zoomed crop with a 1 mm grid for reading sizes |
| `photo_tools.py annotate <photo> --mark x,y,1 ...` | Numbered rings for a question image |

`print_check.py` runs inside Blender's own Python on any STL, however it was made, so it's also useful on parts modelled elsewhere.

## Limits worth knowing

- **Photos are about ±1 mm.** A face sitting above the ruler reads 4 to 8% large, and two photos of the same edge can disagree by more than that. A caliper reading settles it.
- **Printer limits are starting points.** The defaults (0.2 mm detail and 0.4 mm walls on resin, double that on FDM) are rules of thumb. Print a small test card once and put your printer's real numbers in `checks.json`.
- **Tested on macOS with Blender 5.2.1.** The code looks for Blender on Windows and Linux too, but those paths haven't been run yet. Reports welcome.
- **It flags, it doesn't decide.** If a part carries someone's trademark, or copies a part from a commercial kit, the skill marks the file personal-use and says so. Whether a copy can be sold is your call, made with proper advice.
- **The judgment stays yours.** The checks prove the model matches your answers. Whether it looks right, and whether it's good enough to fit, film, or sell, is still a person looking at the part.

## Where it came from

Cody Clark built photo-to-print at HeyHi in November 2026, after the brake caliper above. The review of those two sessions, the three defects, and the measured before-and-after are in [`references/worked-example-caliper.md`](references/worked-example-caliper.md). The Blender rules each cost real time to learn; they're in [`references/blender-gotchas.md`](references/blender-gotchas.md).

## Contributing

Issues and pull requests are welcome. See [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Support

See [`SUPPORT.md`](SUPPORT.md).

## License

MIT. See [`LICENSE`](LICENSE). The MIT terms cover the code and documentation in this repository; they don't extend to the "HeyHi" name, wordmark, or logo, which are trademarks of Bay Design LLC and aren't licensed under those terms.
