# pair-refiner

pair-refiner makes **training pairs for a translation LoRA**, English ↔ Persian. It takes a dataset
of sentences, has several AI models translate each one, has the models judge each other's
translations without knowing who wrote what, and keeps the best one.

> **Status (19 October 2026): milestones M0–M4 of 8 are done.** The tool can read datasets, pick
> the best translation of a sentence with real models, and run a 20-sentence pilot. It **can't yet**
> run a whole dataset, stop at a spending limit, write the final output files (`pairs.jsonl` etc.),
> or show a dashboard. Those come in M5–M7, and the full guide in M8. The plan is in
> [BUILD.md](BUILD.md).

---

## How it picks the best translation

Think of a cooking contest, held separately for every sentence.

1. **The cooks.** Each model translates the sentence: Claude Opus 5.5, GPT-6.1 Sol, Gemini 4 Argon,
   DeepSeek V4 Pro, Meta Muse Wonder, and Google Translate. If the dataset already has a
   translation, it joins in too. Identical translations are merged, keeping all their authors.
2. **Hidden labels.** The translations are shuffled and labelled A, B, C… The order comes from the
   sentence itself, so the same sentence always gets the same order.
3. **The panel.** Every AI model scores every translation from 1 to 5 for **meaning** and
   **naturalness**. A judge's scores for its own translation are thrown away. Google Translate
   translates but doesn't judge.
4. **The shortlist.** The top 3, by meaning first and naturalness to break ties.
5. **The head judge** picks the winner from the shortlist, with fresh hidden labels, and gives a
   one-sentence reason.
6. **The double-check.** Another AI model, one that didn't write the winner, translates it back
   into the original language. A score called **chrF** (0–100: how many small groups of letters
   match the original) shows whether the meaning survived.

The dataset's own translation is handled by where it came from:

- **`native`** (a native speaker or professional): it's judged like the rest, but it **always wins**.
  The head judge is skipped. If a model's translation scores a full point higher on meaning, the
  row is flagged, because that usually means a typo or a mismatched row.
- **`unknown`**: an ordinary candidate. If it loses, the row is marked **replaced**.

A row is **flagged** (marked for you to look at) when:

| Flag | Why |
|---|---|
| panel disagreement | judges' meaning scores for the winner are 2 or more points apart |
| top judge chose its own | the head judge picked its own model's translation when the panel didn't rank it first |
| meaning may have changed | the double-check's chrF is below the threshold |
| beats the native reference | a model beat a native translation by a point or more |
| malformed judge answer | a judge answered twice in an unusable form, so its vote was dropped |
| scored only by its authors | every judge wrote that translation, so their own votes were used |

The reasons for these rules are in [docs/adr](docs/adr) (short decision notes).

**Persian tidy-up.** Every Persian text going in or coming out is cleaned up. Arabic look-alike
letters become Persian ones (ي → ی, ك → ک), and Arabic-Indic digits become Persian digits. The
half-space is put back where a space was written (می روم → می‌روم, کتاب ها → کتاب‌ها). The old
spelling ـائی becomes ـایی (یادداشت‌هائی → یادداشت‌هایی), and invisible text-direction marks are
removed.

**Never paying twice.** Every answer from a model is saved the moment it arrives, in
`cache\answers.sqlite`. Asking the same thing again, even after a crash or on another day, reads the
saved answer and costs nothing. Asking anything different, even by one letter, is a new question and
is paid for once.

---

## Setting up (once)

You need [uv](https://docs.astral.sh/uv/), which installs Python and everything else the tool uses,
and [git](https://git-scm.com/). Run each command below in **PowerShell**, one at a time.

**1. Go to the tool's folder:**

```bash
cd D:\AI_Data\projects\pair-refiner
```

**2. Install everything** (Python 3.12 and the libraries, into a `.venv` folder here):

```bash
uv sync
```

**3. Check that it works.** This runs the tests. They're free and need no internet:

```bash
uv run pytest
```

It should end with something like `45 passed, 2 deselected`. The 2 deselected are the live checks,
which cost money, so they only run when you ask.

### Your keys

The tool needs two keys: one for **OpenRouter** (all the AI models, through one account) and one
for **Google Cloud Translation**. They go in a file called `keys.toml` that never leaves your
computer: git ignores it. **Never paste a key into a chat, email or document.**

**4. Make your keys file** from the example:

```bash
Copy-Item keys.example.toml keys.toml
```

**5. Get an OpenRouter key**, in your web browser:

1. Go to **openrouter.ai**, sign in, and open **Settings → API Keys** (openrouter.ai/settings/keys).
2. Click **Create Key** and name it `pair-refiner`.
3. In **Credit limit**, enter a dollar amount, for example **10**. This is your safety net:
   OpenRouter refuses the key once it has spent that much, whatever the tool does. You can raise it
   later on the same page.
4. Copy the key (it starts with `sk-or-v1-`). OpenRouter shows it only once.

**6. Get a Google Cloud Translation key**, in your web browser:

1. Go to **console.cloud.google.com** and pick or create a project. It needs billing turned on. The
   first 500,000 characters each month are free, then it's $20 per million characters.
2. Search for **Cloud Translation API** and click **Enable**.
3. Go to **APIs & Services → Credentials → Create credentials → API key**.
4. Open the new key. Under **API restrictions**, choose **Restrict key → Cloud Translation API**
   and save. Then the key can't be used for anything else.
5. Copy the key.

**7. Put both keys in the file.** This opens it in Notepad:

```bash
notepad keys.toml
```

Paste the OpenRouter key on the `api_key =` line and the Google key on the `translate_api_key =`
line, keeping the quotes. Leave `management_key` as it is: it's only needed for showing your
balance in the dashboard, which comes later. Save the file.

---

## What you can do so far

### See the models and their prices

This reads OpenRouter's price list. It's free and needs no key:

```bash
uv run python -m pair_refiner.models_report
```

It shows each maker's newest models, their prices per million tokens (a token is a few letters of
text), and a rough cost per 1,000 sentences. The models the tool uses are listed in
[defaults.toml](defaults.toml).

### Run the live check (about $0.07)

This sends 3 short sentences through every model for real, and checks that real answers have the
shape the tool expects:

```bash
uv run pytest -m live
```

### Run the 20-sentence pilot (about $1.70 the first time)

This takes the first 20 sentences of the MIZAN sample, English→Persian, and the same 20 reversed,
Persian→English:

```bash
uv run python -m pair_refiner.pilot
```

It prints each sentence's winner and flags, and how much it spent this time. Because answers are
cached, running it again costs nothing, unless something changed what the models are asked: a
reworded prompt, a different model, or a change to the tidy-up that alters a sentence. Then only
the changed questions are paid for. It writes to `runs\pilot-m4\`:

- `pilot-en-fa.csv` and `pilot-fa-en.csv`: one row per candidate translation, best first, with the
  panel's scores, the winner marked, the head judge's reason, the back-translation, its chrF, the
  flags and the cost. They open in Excel.
- `answer-lengths.json`: how long each model's answers really are, for estimating costs.

In the pilot, the head judge (Opus 5.5) and the double-check threshold (chrF 40) are
**placeholders**. Milestone M6 measures which head judge and threshold work best. At 40 the
"meaning may have changed" flag fires too often, so ignore it for now.

---

## Datasets

A dataset is a **CSV**, **TSV** or **JSONL** file of sentences, plus a small **settings file** that
describes it. The settings file uses TOML, a simple `name = value` format. Example:
[datasets/mizan-sample-2000.toml](datasets/mizan-sample-2000.toml):

```toml
file = 'D:\AI_Data\projects\datasets\farsi\mizan\mizan-sample-2000.csv'
source_lang = "en"          # the language of the sentences: "en" or "fa"
target_lang = "fa"          # the language to translate into
register = "written"        # Persian only: "written", "spoken" or "both"
origin = "unknown"          # where the file's own translations came from: "native" or "unknown"
conversation = false        # true if the lines are a conversation (see below)
```

`file` can also be a path relative to the settings file.

**Columns are found by name** (capital letters don't matter):

- the sentences: `source`, or the language code (`en` or `fa`);
- an existing translation, if any: `target`, `translation`, or the other language's code. If there
  is one, `origin` must be set, or the tool stops and asks;
- an optional `id`. Without it, a sentence's id is its line number.

If no column matches, the tool stops and lists the names it accepts.

**When reading, the tool:**

- skips empty rows;
- keeps only the first copy of a repeated sentence. In a conversation, a repeat counts only if its
  two previous lines are the same too;
- tidies all Persian text (see above);
- for a **conversation** (`conversation = true`), sends each line with the two lines before it, so
  the models understand it in context. If the file has several conversations, name the column that
  says which line belongs to which: `conversation_column = "chat"`.

Files saved by Excel (UTF-8 with a BOM) work as they are.

---

## Where things are

| Path | What it is |
|---|---|
| `src\pair_refiner\` | the tool's code |
| `tests\` | the tests (`uv run pytest`) |
| `datasets\` | dataset settings files |
| `defaults.toml` | the models used by default |
| `keys.toml` | your keys (yours only, never committed) |
| `cache\` | every model answer so far (never committed) |
| `runs\` | what runs and pilots write (never committed) |
| `docs\adr\` | short notes on why things were decided |
| `BUILD.md` | the full plan |

## Still to come

- **M5:** whole runs with a spending limit, picking up after an interruption without paying again,
  a cost estimate before every run, and the output files: `pairs.jsonl` (the training pairs),
  `candidates.csv`, `flags.csv` and `run.json`.
- **M6:** a test run on FLORES+ (sentences with professional translations) to choose the head judge
  and the double-check threshold, and to measure whether the whole panel beats the single best
  model.
- **M7:** a dashboard in your web browser to set up, start and watch runs.
- **M8:** the complete step-by-step guide, including using `pairs.jsonl` with volis's
  `notebooks\train-a-lora.ipynb`.
