# pair-refiner

pair-refiner makes **training pairs for a translation LoRA**, English ↔ Persian. You give it a file
of sentences. It has AI models translate each one, checks the translations, and writes out the best
one for each sentence as a pair you can train on. A LoRA is a small add-on that teaches a translation
model to translate more like your examples.

This guide takes you from nothing to training pairs, step by step. Run each command in
**PowerShell**, one at a time, and wait for it to finish before the next.

**Contents**

1. [What you need](#1-what-you-need)
2. [Install](#2-install)
3. [Your keys, and a spending limit](#3-your-keys-and-a-spending-limit)
4. [Check that it works](#4-check-that-it-works)
5. [Prepare a dataset](#5-prepare-a-dataset)
6. [Run a dataset from the dashboard](#6-run-a-dataset-from-the-dashboard)
7. [Find the outputs](#7-find-the-outputs)
8. [Train a LoRA with the pairs, in volis](#8-train-a-lora-with-the-pairs-in-volis)
9. [The test run (optional)](#9-the-test-run-optional)
10. [How it picks a translation](#10-how-it-picks-a-translation)
11. [When something goes wrong](#11-when-something-goes-wrong)
12. [Where things are](#12-where-things-are)

---

## 1. What you need

- **A Windows computer** with this folder: `D:\AI_Data\projects\pair-refiner`.
- **[uv](https://docs.astral.sh/uv/)**, which installs Python and everything else the tool uses.
  **[git](https://git-scm.com/)** too, if you want to keep track of changes.
- **An [OpenRouter](https://openrouter.ai) account with some credit.** OpenRouter is one account
  that reaches many AI models (Claude, GPT, Gemini, DeepSeek…). You pay it per use.
- **A [Google Cloud](https://console.cloud.google.com) account with billing turned on**, for Google
  Translate. The first 500,000 characters each month are free, then it's $20 per million characters.
- **Only for the test run (section 9):** a [Hugging Face](https://huggingface.co) account that has
  accepted the terms of the [FLORES+ dataset](https://huggingface.co/datasets/openlanguagedata/flores_plus).

## 2. Install

**Go to the tool's folder:**

```bash
cd D:\AI_Data\projects\pair-refiner
```

**Install everything** (Python 3.12 and the libraries, into a `.venv` folder here):

```bash
uv sync
```

## 3. Your keys, and a spending limit

The tool needs keys: passwords that let it use your accounts. They go in a file called `keys.toml`
that never leaves your computer (git ignores it). **Never paste a key into a chat, an email or a
document.**

**Make your keys file** from the example:

```bash
Copy-Item keys.example.toml keys.toml
```

**Get an OpenRouter key, and give it a spending limit.** In your web browser:

1. Go to **openrouter.ai**, sign in, and open **Settings → API Keys** (openrouter.ai/settings/keys).
2. Click **Create Key** and name it `pair-refiner`.
3. Set its **credit limit** to a dollar amount, for example **10**. This is your safety net:
   OpenRouter refuses this key once it has spent that much, whatever the tool does. You can raise
   it later on the same page.
4. Copy the key (it starts with `sk-or-v1-`). OpenRouter shows it only once.

**Get an OpenRouter management key** (optional: it only lets the dashboard show your balance):

1. Open OpenRouter's [Management API Keys](https://openrouter.ai/settings/management-keys) page.
2. Click **Create New Key**, name it `pair-refiner-balance`, and copy it.

It can't run models or spend credits.

**Get a Google Cloud Translation key.** In your web browser:

1. Go to **console.cloud.google.com** and pick or create a project with billing turned on.
2. Search for **Cloud Translation API** and click **Enable**.
3. Go to **APIs & Services → Credentials → Create credentials → API key**.
4. Open the new key. Under **API restrictions**, choose **Restrict key → Cloud Translation API**
   and save, so the key can't be used for anything else.
5. Copy the key.

**Put the keys in the file.** This opens it in Notepad:

```bash
notepad keys.toml
```

Paste each key on its line (`api_key`, `management_key`, `translate_api_key`), keeping the quotes,
and save.

## 4. Check that it works

**The tests** are free and need no internet:

```bash
uv run pytest
```

The output should end with `passed` and a few `deselected`. The deselected ones are the live
checks, which talk to the real services.

**The live check** sends 3 short sentences through every model for real (about 3 cents). It confirms
that your keys work and the answers come back as expected:

```bash
uv run pytest -m live
```

## 5. Prepare a dataset

A dataset is two files in the `datasets` folder:

- **the sentences:** a CSV file (it opens in Excel), a TSV file, or a JSONL file;
- **its settings:** a small text file ending in `.toml`, with one `name = value` per line.

There's a ready example to copy: [datasets/example.csv](datasets/example.csv), with 10 sentences, and
its settings, [datasets/example.toml](datasets/example.toml):

```toml
file = "example.csv"        # the sentences: next to this file, or a full path like 'D:\data\my.csv'
source_lang = "en"          # the language of the sentences: "en" or "fa"
target_lang = "fa"          # the language to translate them into
register = "written"        # Persian only: "written", "spoken" or "both"
# origin = "native"         # only if the file has its own translations: "native" or "unknown"
conversation = false        # true if the lines are a conversation
```

**The sentences file.** Columns are found by name (capital letters don't matter):

- the sentences: `source`, or the language's code (`en` or `fa`);
- **optional,** translations you already have: `target`, `translation`, or the other language's
  code. Then the settings must say where they came from:
  - `origin = "native"`: a native speaker or a professional. Their translation is always kept, and a
    row where a model does clearly better is flagged for you to look at, since that usually means a
    typo or a mismatched row.
  - `origin = "unknown"`: anyone else, or not sure. It competes with the models' translations, and
    the best one wins.
- **optional,** an `id` column. Without it, a sentence's id is its line number.

If no column matches, the tool stops and lists the names it accepts.

**The settings.**

- `register`: for Persian only. `written` is formal Persian (می‌روم به خانه); `spoken` is everyday
  speech (می‌رم خونه); `both` makes one of each per sentence.
- `conversation = true`: each line is sent with the two lines before it, so the models understand it
  in context. If the file holds several conversations, add a column saying which conversation each
  line belongs to, and name it in the settings: `conversation_column = "chat"`.
- `tidy_source = true`: for untidy datasets, such as text split into sentences by a program. Before
  translating, an AI model fixes **only punctuation and capitals**. It removes stray quote marks
  (`' 'I hate to do this to you, Dorothy` → `I hate to do this to you, Dorothy`) and puts headings into
  normal case (`SAME SPECIES, DIFFERENT WORLDS` → `Same species, different worlds`), keeping names and
  acronyms. The tidied sentence is used only if its words are exactly the same as before; otherwise the
  original is kept. `pairs.jsonl` gets the tidied sentence, and `candidates.csv` shows the original
  alongside. It costs about $0.0006 a sentence, and it's off unless you add this line.

**What the tool does when reading:** it skips empty rows and keeps only the first copy of a repeated
sentence. It also tidies all Persian text: Arabic look-alike letters become Persian ones (ي → ی,
ك → ک), Arabic-Indic digits become Persian digits, the half-space goes back where a space was written
(می روم → می‌روم), the old spelling ـائی becomes ـایی, and invisible text-direction marks are removed.
Files saved by Excel work as they are.

## 6. Run a dataset from the dashboard

**Start the dashboard.** This opens it in your browser:

```bash
uv run pair-refiner
```

It runs on your computer only (`http://127.0.0.1:8765`), and nothing is reachable from other
machines. Keep the PowerShell window open while you use it. Closing it stops the dashboard, and any
run that's working.

**Then, in the browser:**

1. Click **New run** and choose your **dataset first**. Choosing one reloads the form with the models
   and checks for its direction already ticked (see [section 10](#10-how-it-picks-a-translation) for
   why these), and it resets the run name.
2. Fill in the rest. Leaving every ticked box as it is gives the tested defaults:

   | Field | What it means |
   |---|---|
   | **Dataset** | which sentences to translate (the files in `datasets\`) |
   | **Run name** | the folder the results go in, `runs\<name>`: letters, numbers, `.`, `-` and `_` only. Reusing a name resumes that run |
   | **Register** | Persian only: `written` (formal), `spoken` (everyday) or `both` (one of each) |
   | **Translators** | which models translate each sentence |
   | **Judges** | which models score the translations, when there's more than one to choose between. More judges cost more, and the test run found they don't help |
   | **Top judge** | the model that makes the final pick from the shortlist |
   | **Shortlist size** | how many of the best-scored translations go to the final pick. With 2–3 translations per sentence it makes no difference |
   | **Double-check** | translates the winner back and flags the sentence if it drifted from the original. The threshold is the score (0–100) below which it flags |
   | **Sentence limit** | only the first N sentences; empty means all of them |
   | **Spending limit** | the most the run may spend, in dollars (required) |

3. Click **Estimate**. It shows what the run should cost and spends nothing.
4. Click **Start**. The run's page shows its progress, what it has spent against the limit, and any
   flags, and it refreshes itself.
5. Click any sentence to see every translation, the judges' scores and their reasons.

**The spending limit:** before each sentence, the tool estimates its cost. If that would go over the
limit, it stops cleanly and keeps what it has done.

**Stopped runs pick up where they left off.** A run stopped by the limit, by closing the window, or
by a crash continues if you start a new run with **the same name** (with a higher limit, if it hit
the limit). Nothing is paid for twice: every answer from a model is saved the moment it arrives, in
`cache\answers.sqlite`, and asking the same thing again reads the saved answer for free.

At the top of every page are your **OpenRouter balance** and **Google's spend this month**. Google
has no balance to ask for, so the tool counts its own Google spend.

**Without the dashboard,** the same run from PowerShell:

```bash
uv run python -m pair_refiner.cli datasets\example.toml --name example-1 --estimate
```

```bash
uv run python -m pair_refiner.cli datasets\example.toml --name example-1 --limit 1
```

The first command only estimates. The second runs, with a $1 limit. Add `--sentences 20` for just
the first 20 sentences, or `--register spoken` to override the dataset's register.

## 7. Find the outputs

Each run writes to `runs\<run name>\`:

| File | What's in it |
|---|---|
| `pairs.jsonl` | **the training pairs**, one line per sentence: `source`, `target`, the two languages, `register`, `author` (every model that wrote the winning text; `dataset` means your file's own translation) and `id` |
| `candidates.csv` | every translation considered, best first, with every judge's scores, the winner, the head judge's reason, the double-check and its score, whether your file's translation was replaced, the cost, and (with `tidy_source`) the sentence as your file had it before tidying |
| `flags.csv` | the sentences worth a look, and why |
| `run.json` | the settings, totals, cost and time taken |

The CSV files open in Excel. Each pair records its author, so you can later decide what each
provider's terms allow you to train on. The tool enforces nothing about that.

## 8. Train a LoRA with the pairs, in volis

volis's notebook `notebooks\train-a-lora.ipynb` reads `pairs.jsonl` directly. Open it as it
explains, and in **Part 2: your choices** set:

```python
DATA_FILE  = r"D:\AI_Data\projects\pair-refiner\runs\<run name>\pairs.jsonl"
SOURCE     = "en"      # the run's source language
TARGET     = "fa"      # the run's target language
RUN_NAME   = "<a name for this training run>"
```

Then run the notebook from Part 3, as it describes. Two tips:

- **Use one register per training run.** A run with register `both` has a written and a spoken
  Persian version of every sentence. Train on written or spoken, not both mixed: make the run with
  `written` or `spoken`.
- **Use enough pairs.** The notebook needs at least 20, and a LoRA learns little from fewer than a
  few hundred.

## 9. The test run (optional)

The test run measures how good each model is, on 200 sentences that come with professional
translations (FLORES+, in both directions). It decided the defaults below. Run it again if you want
to re-check them, for example after adding a model. It costs about **$13** the first time. Answers
are cached, so running it again costs nothing.

**Get FLORES+.** It's a dataset you have to accept the terms for first, on its
[Hugging Face page](https://huggingface.co/datasets/openlanguagedata/flores_plus). Log in once:

```bash
uvx --from huggingface_hub hf auth login
```

Then download the Persian and English sentences into this folder's `inputs\` (git ignores it, and
FLORES+ must not be shared):

```bash
uvx --from huggingface_hub hf download openlanguagedata/flores_plus devtest/pes_Arab.jsonl devtest/eng_Latn.jsonl --repo-type dataset --local-dir inputs\flores_plus
```

**Run it** (with its own $20 limit):

```bash
uv run python -m pair_refiner.flores_run
```

It takes about an hour, and writes `runs\test-run\report.md`, along with a CSV per direction. The
dashboard's **Models** page shows its scores.

## 10. How it picks a translation

**What the test run found, and the defaults.** On FLORES+, no panel of several models beat the best
single model, in either direction. So the defaults are small:

| Direction | Translators | Checked by |
|---|---|---|
| English → Persian | **Google Translate** (the closest to the professional translations) and **Gemini 4 Argon** (the best AI model, and it follows written or spoken) | GPT-6.1 Sol picks between them with the register in mind; double-check on |
| Persian → English | **Claude Opus 5.5** (the closest to the professional translations) | GPT-6.1 Sol, only when there's a second translation to choose between (your file's own, for example); double-check off |

Why two for English → Persian: Google Translate can't be told written or spoken, so on its own it
gives a mix. The judge is told which register you asked for, and a translation in the wrong one
loses. A sentence costs about half a cent this way. With only one translation to consider, no judge
is asked, and a sentence costs well under a cent. The settings are in [defaults.toml](defaults.toml),
and the numbers and reasons are in [docs/adr/0005](docs/adr/0005-test-run-results-and-defaults.md).
In the dashboard you can tick more translators and judges for any run.

**The full process,** with several translators and judges. Steps with nothing to decide are skipped.

1. **Translations.** Each chosen model translates the sentence, and your file's translation (if any)
   joins in. Identical translations are merged, keeping all their authors.
2. **Hidden labels.** The translations are shuffled and labelled A, B, C…, so judges never know who
   wrote what. The order comes from the sentence itself, so asking again gives the same order.
3. **The panel.** Every judge scores every translation from 1 to 5, for **meaning** and for
   **naturalness**. A judge's scores for its own model's translation are thrown away.
4. **The shortlist.** The top 3 by meaning, with naturalness breaking ties.
5. **The head judge** picks the winner from the shortlist, with fresh hidden labels, and gives a
   one-sentence reason in English.
6. **The double-check.** A model that didn't write the winner translates it back. A score called
   **chrF** (0–100: how many small groups of letters match the original) shows whether the meaning
   survived.

**Flags** mark sentences worth a look:

| Flag | Why |
|---|---|
| meaning may have changed | the double-check's chrF (compared without capitals or punctuation) is below the threshold. On short or literary lines this often just means the same meaning in other words ("The time went by" → "Time passed"): read the original and the double-check, both in the source language |
| panel disagreement | the judges' meaning scores for the winner are 2 or more points apart |
| top judge chose its own | the head judge picked its own model's translation when the panel didn't rank it first |
| beats the native reference | a model beat your `native` translation by a point or more on meaning |
| malformed judge answer | a judge answered twice in an unusable form, so its vote was dropped |
| scored only by its authors | every judge wrote that translation, so their own votes were used |

**Notes** are worth knowing, but not warnings. For example, "no answer from…" means a model
silently refused a sentence, and the others carried on without it. The reasons for every rule are in
[docs/adr](docs/adr).

## 11. When something goes wrong

- **"keys.toml not found":** do [section 3](#3-your-keys-and-a-spending-limit).
- **The balance says "add a management key":** that key is optional (section 3). Everything else
  works without it.
- **A run stopped:** start it again with the same name (section 6). Nothing is paid for twice.
- **"Rate limit" or a slow run:** new OpenRouter accounts may send 20 requests a minute per model.
  The tool waits and carries on.
- **Meta's models are switched off.** During the test run, Meta blocked this account for "repeated
  policy violations": its filter silently refused medical sentences, which were then asked again.
  The tool now never repeats a refused request. Ask OpenRouter's support before switching Meta back
  on in `defaults.toml`.

## 12. Where things are

| Path | What it is |
|---|---|
| `datasets\` | your datasets and their settings |
| `runs\` | each run's outputs (never committed) |
| `keys.toml` | your keys (yours only, never committed) |
| `defaults.toml` | the models and checks used by default |
| `cache\` | every model answer so far, so nothing is paid twice (never committed) |
| `inputs\` | downloaded test data (never committed) |
| `docs\adr\` | short notes on why things were decided |
| `src\pair_refiner\` | the tool's code |
| `tests\` | the tests (`uv run pytest`) |
| `tools\` | the dashboard's browser check |
| `BUILD.md` | the original plan |

**Older tools from the build,** kept for reference: `uv run python -m pair_refiner.models_report`
lists every maker's models and prices. `uv run python -m pair_refiner.pilot` re-runs the first
20-sentence pilot with the full panel.
