# The intake interview

**Rule: ask until there is nothing left to guess. Then build.** When the maker sends photos, the first job is not to model, measure or plan. It is to understand the subject and the intent completely, through as many questions as it takes, and to write every answer into `CLARITY.md`. The build starts only when the ledger has zero OPEN rows and the maker has said go to a written summary of exactly what will be built.

Why this is the rule: on the first project (a 20 mm brake caliper, November 2026) every defect in the first build came from something that was guessed or misheard before modelling started, not from the modelling itself. A word meant two things ("emboss"), a step on one face was read from a photo as a raised line and never asked about, and nobody asked what the part had to *do* (let a brake disc slide through it), while a side no photo showed was filled with a default. Each would have cost one question. The rework round they caused cost a full review cycle. See `worked-example-caliper.md`.

## How to ask

1. **Look first, then ask.** Read every photo (`photo_tools.py info` first: if they are reduced copies, the very first question is a request for the originals). Write a short "here is what I think this is" description and number every feature you can see on annotated photos (`photo_tools.py annotate`). Questions refer to those numbers.
2. **Rounds of at most four questions,** grouped by theme, most consequential first: intent and use → function and fit → size → features and polarity → hidden sides → finish → printing → files. The question tool takes at most 4 questions per card. If the question tool is not available, ask in chat as a numbered list with lettered options.
3. **One decision per question.** Concrete, mutually exclusive options, each with what it means for the print. Add "Not sure" when it's realistic, and say what you'll do to find out (a photo, a measurement).
4. **Every feature question carries a picture.** Send the annotated image with the question (send the file itself; a path is invisible to the maker). "Ring 3" must mean the same thing to both of you.
5. **Plain words, never jargon with two meanings.** For surface detail use only: **"cut into the surface"** (a groove you could fill with paint), **"stands up from the surface"** (you could catch a fingernail on its edge), **"a step, where one area sits lower"**. Never "emboss", "deboss", "engrave", "relief", "positive/negative", "proud" or "flush" in a question. The maker may use those words; when they do, translate and confirm.
6. **Confirm back after every round.** Restate the answers in plain words, with the picture for anything visual: "So ring 2, the word, is cut into the surface about 0.2 mm, like the grooves in a coin. Right?" A misheard answer is caught here, before it becomes geometry. Nothing is CONFIRMED until the confirm-back is.
7. **Never lock an ambiguous answer.** "Decided, do not re-ask" is only allowed after the confirm-back. If a later photo or measurement contradicts an answer, ask again.
8. **Hidden sides are questions, not defaults.** For every side no photo shows, ask for a photo first, a description second. A default is allowed only after the maker has seen it drawn and said yes, and it is recorded as ASSUMED-OK with exactly what was assumed.
9. **Ask while you work, never wait idle.** Measuring, calibrating or a review agent running? Send the next round meanwhile.
10. **Close with the build summary.** One message: what it is, what it's for, the size and where each number came from, what passes through it, every feature with its ring number and polarity, the defaults the maker approved, the printer limits that bite, and the files you'll make. End with: "Anything wrong or missing? If not, say go." Quote their go in the ledger.

People often give the short version, especially about their own work. A one-line answer to a big question ("just make it like the photo") gets a gentle follow-up: "Like the photo it is. Two things the photo can't tell me: ..." Push for specifics; respect the answer once it's specific.

## Round 0: before anything else

- Photos are reduced copies (`info` warns): ask for the originals, and say why ("fine detail under half a millimetre blurs at this size").
- Fewer than all six sides, or no ruler or caliper in frame: send `photo-guide.md`'s shot list and ask for the missing shots. Start the other rounds meanwhile.
- No caliper reading: ask for length, width and height. One reading beats any amount of photo measuring (photos are about ±1 mm; the caliper project's height disagreed by 20% between two photos).

## The question bank

Use the rows in `CLARITY.md` as the minimum. These are the follow-ups that turn a vague answer into a buildable one. Skip only what an earlier answer has already made `N/A`, and write the N/A with its reason.

### A. Subject and intent
- What is it, in your words? What is it from (kit, brand, scale)?
- Is this the only one you have? Can you measure it, or is it already glued to a model?
- Exact copy, or should anything change (thicker, simpler, sharper, a different size)?
- What happens to the print: fitted to a build, sold, filmed, gifted, a test?
- One, a set, a mirrored left/right pair?
- What would make you say "that's exactly it"? What's the one thing it must get right?

### B. Selling and markings
- Will anyone else ever have it: sold, given away, posted or shown online?
- Brand names, logos or trademarks on it (for example a manufacturer's name cast into the part): keep them (personal only), remove them, replace with a generic mark, or leave a flat area for a decal?
- Is the original part from someone else's commercial kit or product? If the print will be sold, flag it as the maker's call to make with proper advice. The skill does not give legal answers and does not decide this.

### C. Size
- Same size as the object, or scaled? If it's for a scale model: which scale, and should the size come from this object or from the real thing's dimensions?
- Caliper readings: overall L, W, H. Then every size something must fit: holes, slots, pins, mounting faces.
- How close is close enough, per dimension?

### D. Function and fit (ask even when it seems obvious)
- Does anything pass through it, slide into it, sit in it, clip onto it, or bolt to it? For a brake caliper: the disc. For a wheel: the axle. For a bracket: the screw.
- For each one: how big is it, which side does it come in from, which side does it leave from, how much room around it?
- Each opening on the photos (ring it): all the way through, or does it stop? Through to where?
- How will it attach to the model: glue face, peg, pin hole, press fit? Where exactly?
- One piece, or separate pieces that assemble or move?

### E. Each feature (ring by ring)
- What is ring N? (Name it in the maker's words.)
- Cut into the surface, standing up from it, or a step down? (Plain words, picture attached.)
- Roughly how deep or high? ("Like the photo" is fine; the photos will be measured.)
- Must keep, nice to have, or leave off if it's too small to print?
- Text: the exact letters, case, which way it reads, which side faces out, letter weight (thin, normal, bold).

### F. What the photos don't show
- For each side not photographed: can you send a photo? If not, describe it. (Offer a drawn default only as the last option.)
- Which features are on one side or one end only? Use the same sticky-note label across photos (see the photo guide) so "this end" means the same end in every picture.
- Is it the same left and right? Front and back?
- Anything inside: hollow, channels, holes you can't see into?

### G. Finish
- Smooth, cast texture, machined? Copy the texture or print smooth?
- Edges crisp or softened like a casting?
- Primer and paint planned? (Paint fills about 0.05 to 0.1 mm, so very fine cut-in detail can vanish; it may need to be deeper.)
- Detail that's below the printer's limit: thicken it, keep it at the limit, or drop it?

### H. Printing
- Which printer and material? (Resin: which resin. FDM: nozzle size.)
- Which faces must come out clean, with no support marks?
- Solid or hollow; tab or sprue to hold it; how many per plate?

### I. Files and timing
- STL only, or also 3MF, the Blender file, or preview renders (for a listing, a post or a video)?
- Where should the project folder live?
- Any date it's needed by?
- Last question, every time: "Anything else I should know that I haven't asked?"

## Writing the answers into checks

Every answer that describes *what is right* becomes a test in `checks.json` before modelling starts, so the model cannot drift from the ledger:

| Ledger answer | Test |
|---|---|
| C2 sizes | `envelope.dims_mm` with the tolerance from C4 |
| D1/D2 something passes through | a `sweep` cast from the side it enters, along its path; `allow_hits_in` only for parts the maker confirmed sit in the path (like a pad pin) |
| D3 an opening goes all the way through | a `clear` ray through it, naming its `control`: a `positive_control` ray that must hit solid material right beside the opening |
| E polarity: cut in / stands up | a `relief` check on the feature's region, with the depth |
| E step down | a `relief` check on the lower area (recessed by the step), or a `hit_at` ray on each level |
| G4 / H1 printer limits | `process` and `limits` |
| D4 attach points, D5 separate pieces, E "flat print" | recorded in the ledger only: no geometric test. A part that prints as separate pieces is one project per piece (print_check expects one solid body) |

Positive controls go where no defect could hide. On the caliper, the control over the slot sat right above the defect (a ray only reports the first thing it hits), so a check that looked green could never have caught it. Every key and rule for these tests is in `checks-reference.md`.
