# 5. Test run results, and one model per direction

Date: 2026-10-19. The M6 test run (FLORES+ devtest, the first 200 sentences each way, register written;
measured as in docs/adr/0004), and the defaults the user chose from it.

## Results

Translators: Claude Opus 5.5, GPT-6.1 Sol, Gemini 4 Argon, DeepSeek V4 Pro, Google Translate. Judges: the four
AI models. (Meta's Muse Wonder was dropped part-way: Meta blocked the account, see ADR 0002.)

| | English → Persian | Persian → English |
|---|---|---|
| Best single translator (chrF) | Google Translate 58.1 | Claude Opus 5.5 75.0 |
| Others | Gemini 53.4, DeepSeek 52.7, GPT 52.5, Opus 51.4 | Gemini 71.9, Google 67.8, DeepSeek 67.7, GPT 67.3 |
| The panel's winners | 53.1 | 69.1 |
| The panel's favourite, without the top judge | 53.4 | 69.1 |
| Best possible pick from the candidates | 60.5 | 78.3 |
| Judge accuracy: chance / best (GPT-6.1 Sol) / others | 21% / 25% / 20–22% | 24% / 50% / 29–50% |
| Recommended threshold | 49.9, flagging 6% | 58.8, flagging 53% (unusable) |

**The panel did not beat the best single translator in either direction.** English→Persian, the judges were
no better than chance at picking the candidate closest to the reference. Cost: $14.39 for the test run.

Caveat: chrF rewards closeness to one reference wording, and Persian allows many correct wordings, so the
judges may value what chrF can't see. A human check needs a Persian reader; the user doesn't read Persian, so
the user decided on the numbers.

## Decision (user's)

- **One translator per direction:** Google Translate English→Persian, Claude Opus 5.5 Persian→English.
- **One judge, only when needed:** GPT-6.1 Sol (the best measured) judges only when there are two different
  candidates, e.g. a dataset's own translation. A single candidate wins without any judge being asked.
- **Double-check:** on for English→Persian, threshold 49.9, done by GPT-6.1 Sol (when no other AI translator is
  available, the first judge that didn't write the winner checks it). Off for Persian→English.
- **Amended 2026-10-20 (M8):** Google Translate can't be told written or spoken: the example dataset's
  "Could you speak a little more slowly, please?", asked for in written Persian, came back colloquial.
  So English→Persian now has **two translators, Google Translate and Gemini 4 Argon** (the best AI model on
  FLORES+, 53.4), and GPT-6.1 Sol judges between them, told which register is wanted and that a candidate in
  the wrong one scores 2 at most for naturalness (user's choice). A live check confirms the judge prefers
  the asked-for register both ways. About $0.004 a sentence on the example. Prompts now have one
  fingerprint per kind of request, so rewording the judges' instructions re-asks only the judges.
- The panel stays in `defaults.toml` as `[panel]`, so the test run can be repeated, e.g. once Meta's block is
  lifted, or by a Persian reader with the spot-check page (runs\spot-check\).
