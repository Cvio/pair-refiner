# 3. Output files

Date: 2026-10-19. Decided with the user during M5. BUILD.md's "Outputs" gives the files; these are the
details it left open. The exact formats are pinned by tests/expected/.

- **`pairs.jsonl`:** BUILD.md's keys in BUILD.md's order. `author` is a **list** of every author of the
  winning text: a pair can be kept if any one author's licence allows it (user's choice). `register` is
  **null** when the target isn't Persian, since only Persian has registers (user's choice). The dataset's
  own translation has the author `"dataset"`.
- **`candidates.csv`:** one row per candidate, best first. A meaning and a naturalness column for every
  judge, in the run's judge order. A discarded vote for the judge's own model's candidate is still shown,
  marked like `5 (own)`; an empty cell is no vote (a malformed answer). The sentence-level columns (top
  judge reason, back-translation, chrF, replaced, notes, sentence cost) are filled on the winner's row only,
  so the cost column adds up to the run's total. `replaced` is empty when the sentence had no dataset
  translation.
- **`flags.csv`:** one row per flag: id, register, source, winner, flag.
- **`run.json`:** status, the dataset and run settings, totals (sentences, pairs, flagged, replaced), the
  cost (earlier stopped attempts included), and the start, end and seconds taken.
- CSVs are UTF-8 with a BOM and `\r\n` line endings, so Excel opens them correctly.
- **Spending is ledgered per run:** each paid answer's cost is appended to the run folder's
  `spending.log` the moment it arrives, so a resumed run's spending limit counts what was spent before it
  stopped.
