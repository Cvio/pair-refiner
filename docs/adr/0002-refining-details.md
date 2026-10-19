# 2. Details of refining one sentence

Date: 2026-10-18. Decided with the user at the start of M3. BUILD.md left these open.

- **Panel disagreement.** A row is flagged when the judges' kept meaning scores for the winner
  differ by 2 points or more (for example, 5 and 3).
- **Native reference.** It is always the output, so the top judge is skipped (its pick could change
  nothing). The panel still scores every candidate, for the "beats the native reference" flag, and
  back-translation still runs.
- **Back-translation** is done by the first AI model in the translator list that isn't one of the
  winner's authors. Never Google Translate. When every AI model wrote the winner (found in the M4 live
  check: short sentences often come out identical), the check is skipped and the row gets the note
  "double-check skipped: every AI model wrote it". It's a note, not a flag: that agreement is
  itself the check.
- **A candidate written by every judge** (common for short sentences): no outside judge is left, so
  its authors' own votes are used for it, and the row is flagged "scored only by its authors".
  Added during M3.
- **A top judge whose answer is malformed twice:** the panel's highest-scored candidate wins, and
  the row is flagged for malformed judge answers.
