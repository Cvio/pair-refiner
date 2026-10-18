# pair-refiner

The full spec is `BUILD.md`. Read it before working. Its **Decisions** are settled: don't revisit
them. If one turns out to be impossible, stop and say why.

## How to work

- **Test-driven, with the `tdd` skill** (`/mattpocock-skills:tdd`). One failing test, then just
  enough code to pass it, then the next. Never all tests first.
- **Tests only at the agreed seams** (BUILD.md, "Seams", approved by the user on 2026-10-18).
  Three behaviours with no seam of their own are tested here:
  - the dry-run estimate → seam 4 (a whole run); it makes zero calls on the stand-in;
  - the Persian tidy-up of model answers → seam 3 (refining one sentence);
  - "changing a setting re-runs only the parts it affects" → seam 4.
- **The only stand-in (mock) is the model connection, seam 2.** Nothing else is mocked; the cache
  is a real one in a temporary folder.
- **Expected values come from worked examples written into the test**, never recomputed the way
  the code computes them.
- **No test spends money or needs the internet**, except the live check (seam 8), which is marked
  `live` and skipped unless run by hand with `uv run pytest -m live`.
- **Milestones** (BUILD.md, M0–M8). After each: show its check passing, commit, and stop for the
  user to say go on. Git stays local.
- **Talking to the user:** PowerShell commands, **one command per step**. Plain words; explain any
  term the first time it's used.
- **Other repos are read-only:** volis, volis-rust, model-converter, model-bench. Reading
  model-converter's FLORES+ files is fine.
- **Keys** (`keys.toml`, git-ignored) are never printed, logged, committed, or sent anywhere except
  their own service.

## Commands

- Run the tests: `uv run pytest`
- Run the live check (costs a few cents): `uv run pytest -m live`
