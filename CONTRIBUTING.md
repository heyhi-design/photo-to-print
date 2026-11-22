# Contributing to photo-to-print

Thanks for considering a contribution. Issues and pull requests are both welcome. A quick read of `SKILL.md` and `references/intake-interview.md` first will save you time: the interview is the core of this project, and changes that shorten it or soften its gate will be asked to make the case.

## Development setup

```
git clone https://github.com/heyhi-design/photo-to-print.git
cd photo-to-print
python3 -m pip install --user -r requirements.txt -r requirements-dev.txt
python3 -m pytest tests/ -v
python3 scripts/kit.py selftest
```

The unit tests need only Pillow and numpy (they cover `spec.py`, so a new `checks.json` rule gets a unit test). `selftest` needs Blender; run it before opening any PR that touches `print_check.py`, `views.py`, `partlib.py`, `spec.py` or `selftest_part.py`.

## Ways to contribute

**Report a bug.** Use the bug report template. Include the command, what you expected, what happened, your OS and Blender version.

**Add a Blender rule.** If something cost you real time, add it to `references/blender-gotchas.md` with the version it happened on. Mark it **(kit)** only if a script in this repo enforces it.

**Add a question to the interview.** `references/intake-interview.md` and `templates/CLARITY.md` grow from real misses. Say in the PR which project the question would have saved, and what it would have caught.

**Add a check.** A new check type is a function added to `CHECKS` in `print_check.py`, its keys validated in `spec.py` and documented in `references/checks-reference.md`, and a pair of cases in `kit.py`'s `SELFTEST_CASES`: one it must pass and one it must fail. A check without a negative control isn't proven to catch anything.

**Add a printer process.** Add it to `scripts/presets.json` with every key, and mirror it in `references/print-limits.md` (a unit test compares the two).

**Share a worked example.** A short `references/worked-example-<part>.md` with what went wrong and what the checks caught is one of the most useful contributions there is. Leave out anything you wouldn't want public, including trademarked marks on the part.

## Pull request expectations

- `python3 -m pytest tests/ -v` passes
- `python3 scripts/kit.py selftest` passes if you touched a Blender-side script
- Commits are signed off (see DCO, below)
- The PR description says what changed and why

## Developer Certificate of Origin (DCO)

This project uses the DCO instead of a CLA. Every commit must include a `Signed-off-by` trailer certifying you wrote it (or otherwise have the right to submit it under this project's license):

```
git commit -s -m "your commit message"
```

If you forgot, `git commit --amend -s` fixes the most recent commit.

## Response time

This is a small project. Expect a first response on issues and pull requests within 5 business days.
