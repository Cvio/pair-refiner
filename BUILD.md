# pair-refiner: build instructions

For Claude Code. Build a new tool, **pair-refiner**, in `D:\AI_Data\projects\pair-refiner\`. It takes
a dataset of sentences, has several AI models translate each one, has them judge each other's
translations blind, and keeps the best. The result is a set of sentence pairs good enough to
train a translation LoRA on.

Read this whole file before writing anything. Everything under **Decisions** was settled with the
user in a long design discussion. Don't revisit those decisions; if one turns out to be
impossible, stop and say why.

---

## How to work

- **Test-driven, with the `tdd` skill** (`/mattpocock-skills:tdd`). Load it before the first test,
  and follow it:
  - one failing test, then just enough code to pass it, then the next test. Not all tests first;
  - tests only at the agreed seams (below). **Start by showing the user the seam list and getting
    a yes**, as the skill requires;
  - the only stand-in (mock) is the model connection, seam 2. Nothing else is mocked;
  - expected values come from worked examples written into the test, never recomputed the way the
    code computes them.
- **Milestones.** Each ends with a check. After each one: show the check passing, commit, and stop
  for the user to say go on. Git stays local; the user creates the GitHub repo later.
- **The user:** give PowerShell commands, **one command per step**, never several at once. Use
  plain words, and explain any term the first time you use it. The README is written for someone
  who has never used the tool, step by step.
- **Other repos are read-only.** Don't change volis, volis-rust, model-converter or model-bench.
  Reading model-converter's FLORES+ files (see M6) is fine.
- **Keys are never printed, logged, committed or sent anywhere except their own service.**

## Decisions

**Purpose.** Translate sentence datasets English ↔ Persian (both directions), choose the best
translation of each by blind judging, and produce training pairs. No dialects yet; the design
must not block adding them later (a dialect is just another target-language setting).

**Separate from volis.** Its own repo and its own environment. It shares nothing with volis except
the output format, which is the `source`/`target` JSONL that volis's `notebooks\train-a-lora.ipynb`
and model-converter's pairs job read.

**The models.** All through **OpenRouter** (one key), except **Google Translate**, which goes
through Google Cloud Translation directly. The user wants Opus 5.5, GPT-6, Gemini, DeepSeek and
Meta, plus Google Translate. The exact model of each maker is the user's choice from the list M1
produces; the default is each maker's newest top model. The user can change the selection for any
run in the dashboard.

**What each model does.**
- Every enabled model translates, Google Translate included.
- The AI models also judge. Google Translate can't judge.

**Picking the winner, for one sentence:**
1. **Candidates:** each translator's version. If the dataset already has a translation, it's a
   candidate too (see "Existing translations"). Identical candidates are merged into one, keeping
   all their authors.
2. **Blind labels:** the candidates are labelled A, B, C… in an order shuffled per sentence. The
   shuffle is seeded from the sentence, so a re-run gives the same order and hits the cache.
   Judges never see who wrote what.
3. **The panel:** every judge scores every candidate (structured answer, below). Then a judge's
   scores for **its own model's candidate are discarded**.
4. **Shortlist:** the top 3 by panel score (meaning first, naturalness to break ties). The number
   is a setting.
5. **The top judge** picks the winner from the shortlist, again blind and with fresh labels, and
   gives a one-sentence reason. The top judge is a setting, and its default is whichever model wins
   the test run (M6). Flag the row if the top judge picks its own model's candidate when the panel
   didn't rank it first.
6. **Back-translation:** a model that didn't write the winner translates it back into the source
   language. The chrF between that and the original source (0–100: how many small groups of
   letters match) is recorded. Below a threshold, the row is flagged "meaning may have changed".
   The default threshold comes from the test run (M6). Back-translation can be turned off.

**Judges' answers** are structured JSON, never free text: for each candidate label, `meaning`
(1–5) and `naturalness` (1–5), a `ranking` of all labels, and a one-sentence `reason`. The top
judge returns `winner` and `reason`. A malformed answer is asked for once more, then counted as no
vote and noted on the row.

**Existing translations.** Each dataset says where its existing translations came from:
- `origin = "native"` (a native speaker or professional): the translation is the **reference**. It
  goes into judging blind, like any candidate, but it is always the output. If the panel's best
  candidate beats it by 1 point or more on meaning, the row is flagged; that usually means a typo
  or a misaligned row.
- `origin = "unknown"`: it's an ordinary candidate. If it loses, the row is marked `replaced`.
- No existing translations: all candidates come from the models.

**Register (Persian only).** A setting per run: `written` (default), `spoken`, or `both`. "Both"
produces two Persian versions per sentence, each picked separately. Written is formal Persian;
spoken is everyday colloquial speech (می‌رم خونه, not می‌روم به خانه). The translation and
judging prompts say which one is wanted.

**Neighbouring sentences.** A dataset can be marked as a conversation, with an optional column
naming which conversation each line belongs to. Then each sentence is sent with the **previous two
original sentences** of the same conversation (never their translations), and the judges see them
too. It's off unless the dataset is marked.

**Persian text tidy-up**, on every Persian text going in or coming out: Arabic ي → Persian ی,
Arabic ك → ک, Arabic-Indic digits → Persian digits, and the half-space (ZWNJ, U+200C) put back
after the prefix می/نمی and before the suffixes ها/های/ام/ای/اید/اند where a plain space was
written. Copy the rules into this repo from volis's `volis\persian.py` (read it there); don't
import volis.

**Money.**
- **Dry run:** before every run, an estimate of the cost, spending nothing. It's based on
  OpenRouter's published prices and the measured average length of answers, which the first run
  establishes; before then, a stated rough estimate.
- **Spending limit per run,** set in the dashboard. The tool counts **real** cost as it goes: the
  cost OpenRouter reports for each call, and characters × price for Google. It stops cleanly
  before starting a sentence whose estimated cost would pass the limit.
- **Backstop:** the OpenRouter key used for calls has its own spending limit set on OpenRouter's
  site. The README tells the user how to set it.
- **Balance:** the dashboard shows the OpenRouter balance, from the credits endpoint
  (`GET https://openrouter.ai/api/v1/credits`: `total_credits` − `total_usage`). That endpoint only
  answers to a **management key**, a second key kept only for this. Google has no balance to
  query; show its spend for this month as counted by the tool, at $20 per million characters,
  without assuming the free monthly allowance.
- Verify each endpoint and field against OpenRouter's and Google's current documentation before
  coding it. Don't rely on these instructions for exact field names.

**Never pay twice.** Every model answer is stored, keyed by model, exact prompt and settings,
the moment it arrives, in a cache shared across runs. A stopped or crashed run resumes where it
stopped. Changing a setting re-runs only the parts it affects. Temperature 0 for every call.

**Outputs, per run, in the run's folder:**
- `pairs.jsonl`: the chosen pairs. One line each:
  `{"source": ..., "target": ..., "source_lang": "en", "target_lang": "fa", "register": "written", "author": "<model id>", "id": ...}`.
- `candidates.csv`: one row per candidate, with every score from every judge, the top judge's
  pick and reason, the back-translation and its chrF, the author, and the cost. It opens in Excel:
  write UTF-8 with a BOM.
- `flags.csv`: the flagged rows and why (panel disagreement, top judge chose its own, meaning may
  have changed, beats the native reference, malformed judge answers).
- `run.json`: the settings, the totals, the cost and the time taken.

Each output row records its author, so the user can later decide what each provider's license
allows. The tool itself enforces nothing about licenses.

**Dashboard.** A page in the user's web browser, served by the tool itself while it runs, on
`127.0.0.1` only (nothing is reachable from other machines). One command starts it and opens the
browser. No JavaScript build tools (no Node, no npm); a Python web framework with server-made pages
and at most a little plain JavaScript. Pages:
- **Runs:** each past run, its status, cost and result.
- **New run:** dataset, languages, register, models on/off, judges, top judge, shortlist size,
  back-translation on/off, sentence limit, spending limit, then **estimate** and **start**.
- **One run:** live progress, cost so far against the limit, and the flags; click a sentence to see
  all its candidates, scores and reasons.
- **Models:** the selected models, their prices, and the test run's scores for each.
- The **OpenRouter balance** and this month's **Google spend**, always visible.

**Not now:** a speaker check of a sample (later it will use the same `review.csv` format as
model-converter's pairs job, an `ok` column marked y/n), dialects, and any link to volis.

## Seams

Confirm these with the user before the first test.

1. **Reading a dataset:** a CSV, TSV or JSONL file plus its settings → clean rows. Covers column
   detection, empty rows, duplicates, `origin`, conversation grouping, and the Persian tidy-up.
2. **The model connection:** the only code that talks to OpenRouter or Google: `translate`,
   `judge`, `top_judge`, `back_translate`, `list_models` (with prices), `balance`. Each returns the
   answer and its cost. In tests, a stand-in that replays prepared answers and costs replaces it.
   **No test spends money or needs the internet**, except seam 8.
3. **Refining one sentence:** a row, the settings and a connection → candidates, scores, winner,
   flags and cost. All the rules under "Picking the winner" and "Existing translations" are tested
   here.
4. **A whole run:** stops at the spending limit; resumes after an interruption without repeating
   any call (the stand-in counts calls).
5. **The test run:** sentences with human references → each translator's chrF, each judge's
   accuracy, the ensemble's chrF against the best single translator, and a recommended top judge
   and back-translation threshold.
6. **The output files:** exact formats as above, checked against written-out expected files.
7. **The dashboard's server:** each page and action through an HTTP test client, with the stand-in
   connection.
8. **The live check, run only by hand** (marked so the normal test run skips it): 3 real sentences
   through the real models, a few cents, checking that real answers and costs have the shape the
   stand-in assumes.

## Setup

- Python 3.12, managed with **uv**, with the environment (`.venv\`) inside the repo folder, as the
  user's other repos do. `pytest` for tests.
- Keys in `keys.toml` in the repo folder, **git-ignored**, with a committed `keys.example.toml`
  showing the three entries: the OpenRouter key for calls, the OpenRouter management key, and the
  Google Cloud Translation API key. Explain in the README, step by step, how to get each one and
  how to set the spending limit on the OpenRouter key.
- Git-ignore `keys.toml`, `runs\`, `cache\` and `.venv\`.
- A short `CLAUDE.md` for this repo restating the rules under "How to work".

## Milestones

**M0: start.** Load the `tdd` skill. Show the user the seam list and wait for a yes. Create the
repo, the uv project, pytest, `CLAUDE.md`, `.gitignore`, `keys.example.toml`. Copy this file in as
`BUILD.md`.
Check: `uv run pytest` runs (no tests yet) and git has its first commit.

**M1: the models and their prices.** Seam 2's `list_models`. OpenRouter's model list is free to
read. Print, for each maker the user named (Anthropic, OpenAI, Google, DeepSeek, Meta), its
current top models with input and output prices, and an estimated cost per 1,000 sentences for
this pipeline. Add Google Translate's price.
Check: the list, shown to the user. **Stop for the user to choose the models.** Save the choice as
the default selection.

**M2: reading datasets.** Seam 1.
Check: the seam's tests pass, and a small sample CSV, written into the tests, reads correctly.

**M3: refining one sentence.** Seam 3, with the stand-in.
Check: the seam's tests pass, including worked examples for: own-vote discarded, shortlist,
top judge choosing its own, native reference kept but flagged, unknown origin replaced, identical
candidates merged, malformed judge answer retried and then dropped, back-translation flag.

**M4: the live check, and a 20-sentence pilot.** Seam 8, then 20 real sentences in each direction
(the user provides them, or use 20 FLORES+ dev sentences). Print the real cost.
Check: the user sees the candidates, the winners and the cost, and says whether the answers look
sane. Fix the stand-in if real answers differed from what it assumed.

**M5: whole runs and the output files.** Seams 4 and 6, and the dry-run estimate, which now uses
the answer lengths measured in M4.
Check: an interrupted run (stopped by hand) resumes with no repeated calls; a run stops at a low
spending limit; the files match the expected formats.

**M6: the test run.** Seam 5. FLORES+ (gated: the user has already accepted its terms). English is
`eng_Latn` and Persian is `pes_Arab`. model-converter keeps FLORES+ under
`D:\AI_Data\projects\model-converter\inputs\data\flores_plus\<split>\<code>.jsonl`. It has
English there but not yet Persian, so download `pes_Arab` (dev and devtest) into this repo's own
`inputs\` folder, giving the user the one command if a login is needed. Read the English from
model-converter's copy, or download it too; never write into model-converter. Use `devtest`, 200 sentences, both directions, register `written`.
Check: a report. A table with each translator's chrF, each judge's agreement with the
references, and the ensemble against the single best translator, plus a recommended top judge and
back-translation threshold, and the total cost. **Stop for the user to accept them as the
defaults.** If the ensemble doesn't beat the best single translator, say so plainly; that decides
whether the extra cost is worth it.

**M7: the dashboard.** Seam 7.
Check: start the tool with one command, and open the browser. A new run can be estimated, started,
watched and opened, with the balance and Google spend showing. Use a browser check (Playwright)
to load each page, and send the user a screenshot of each.

**M8: the README.** Step by step for a first-time user: install, get the keys, set the spending
limit, prepare a dataset (with an example file), run the test run, run a dataset, find the
outputs, and use `pairs.jsonl` with volis's `notebooks\train-a-lora.ipynb`.
Check: the user follows it.

After M8, the user's first real run is a **200-sentence pilot** of their own dataset, before any
large run.
