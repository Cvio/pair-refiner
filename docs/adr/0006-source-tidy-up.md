# 6. Tidying a source's punctuation and capitals

Date: 2026-10-23. Asked for by the user after the 200-sentence MIZAN pilot; the details are Claude's judgement,
at the user's request.

## Why

MIZAN's automatic sentence-splitting left lines with stray quote marks (`' 'I hate to do this to you, Dorothy`,
`her John' to go away`) and headings in CAPITALS or Title Case (`SAME SPECIES, DIFFERENT WORLDS`, `SO boy!`,
`Unlocking Your Inner Genius`). They go into the training pairs, and a LoRA learns to copy them. Casing can't be
fixed by rule (`SO` → `So`, but `CSR` stays), so a model does it.

Common practice keeps natural casing in training data (no lowercasing or truecasing), and repairs or filters
abnormal lines.

## Decision

- **A dataset setting, `tidy_source = true`**, off by default: only noisy datasets need the extra call. MIZAN has
  it on.
- **The model** is set in `defaults.toml` (`[tidy] model`): **GPT-6.1 Sol**, which got all 7 of MIZAN's untidy
  examples right in a live check (DeepSeek kept an unpaired opening quote; Gemini capitalised a fragment). About
  $0.0006 a sentence.
- **It only fixes punctuation and capitals:** unpaired quote marks, ALL CAPS or Title Case to sentence case
  (keeping names, places, acronyms, "I"), spacing. No full stop added to fragments.
- **The safety net:** the tidied sentence is used only if its words are exactly the original's, compared without
  capitals or punctuation. Otherwise the original is kept with the note "tidy-up rejected: it changed words". A
  refusal also keeps the original.
- **Headings are repaired, not dropped:** "Same species, different worlds" is still a good phrase to train on, and
  dropping needs a guess at what a heading is.
- **Only the source is tidied.** The dataset's own translations rarely win (6 of 200 in the pilot); the models'
  translations come out well-formed.
- **Outputs:** `pairs.jsonl` has the tidied sentence; `candidates.csv` has an `original source` column, filled when
  the tidy-up changed the sentence; the row gets the note "source tidied".
- **Related (same day):** the double-check now compares without capitals or punctuation, which removed 13 false
  alarms from the pilot.
