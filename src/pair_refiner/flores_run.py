"""M6: the test run on FLORES+ devtest (200 sentences, both directions, register written; docs/adr/0004).

Run with: uv run python -m pair_refiner.flores_run
Writes runs\\test-run\\report.md and one detail CSV per direction. Stops every call once LIMIT is spent; running
it again picks up from the cache."""

import csv
import json
import sys
import threading
import tomllib
from pathlib import Path

import sacrebleu

from pair_refiner import estimate, persian
from pair_refiner.cache import CachedConnection
from pair_refiner.connection import OpenRouter
from pair_refiner.dataset import DatasetSettings, Row
from pair_refiner.evaluation import EvaluationReport, Reference, evaluate
from pair_refiner.live import LiveConnection, load_keys
from pair_refiner.run import RunSettings, refine_settings

REPO = Path(__file__).parents[2]
# English: this repo's own copy if it has one, else model-converter's (read only, never written to).
ENGLISH = next((p for p in [REPO / "inputs" / "flores_plus" / "devtest" / "eng_Latn.jsonl",
                            Path(r"D:\AI_Data\projects\model-converter\inputs\data\flores_plus\devtest\eng_Latn.jsonl")]
                if p.exists()), REPO / "inputs" / "flores_plus" / "devtest" / "eng_Latn.jsonl")
PERSIAN = REPO / "inputs" / "flores_plus" / "devtest" / "pes_Arab.jsonl"
OUT = REPO / "runs" / "test-run"
CACHE = REPO / "cache" / "answers.sqlite"
SENTENCES, LIMIT, WORKERS = 200, 20.0, 3  # 3 at a time stays under 20 requests a minute per model


class Budget:
    """The live connection, refusing every call once LIMIT has been spent by this test run."""

    def __init__(self, connection, limit: float):
        self.connection, self.limit, self.spent = connection, limit, 0.0
        self.fingerprint_for = connection.fingerprint_for
        self.lock = threading.Lock()

    def __getattr__(self, kind):
        def call(*args):
            with self.lock:
                if self.spent >= self.limit:
                    raise RuntimeError(f"the ${self.limit:.2f} limit is spent; run again with a higher one")
            answer = getattr(self.connection, kind)(*args)
            with self.lock:
                self.spent += answer.cost
            return answer
        return call


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    english = [json.loads(line) for line in open(ENGLISH, encoding="utf-8")][:SENTENCES]
    persian_ = [json.loads(line) for line in open(PERSIAN, encoding="utf-8")][:SENTENCES]
    assert [e["id"] for e in english] == [p["id"] for p in persian_], "FLORES+ ids don't line up"
    with open(REPO / "defaults.toml", "rb") as f:
        models = tomllib.load(f)["panel"]
    settings = RunSettings(translators=models["translators"], judges=models["judges"], top_judge=models["judges"][0],
                           back_translation=True)
    directions = {
        ("en", "fa"): [Reference(Row(str(e["id"]), e["text"].strip(), None, None), persian.tidy(p["text"]))
                       for e, p in zip(english, persian_)],
        ("fa", "en"): [Reference(Row(str(e["id"]), persian.tidy(p["text"]), None, None), e["text"].strip())
                       for e, p in zip(english, persian_)],
    }

    estimator = estimate.from_cache(OpenRouter().list_models(), CACHE)
    guess = sum(estimator.sentence_cost(item.row, refine_settings(DatasetSettings(s, t), settings, "written"))
                for (s, t), items in directions.items() for item in items)
    print(f"Estimate: ${guess:.2f} (limit ${LIMIT:.2f}). Answers already cached cost nothing.")
    if guess > LIMIT:
        sys.exit("The estimate is over the limit; nothing was spent.")

    budget = Budget(LiveConnection(load_keys(REPO / "keys.toml")), LIMIT)
    connection = CachedConnection(budget, CACHE)
    OUT.mkdir(parents=True, exist_ok=True)
    reports = {}
    for (source, target), items in directions.items():
        print(f"{source}->{target}: {len(items)} sentences ...", flush=True)
        reports[(source, target)] = evaluate(items, DatasetSettings(source, target), settings, connection, WORKERS)
        _details(OUT / f"details-{source}-{target}.csv", reports[(source, target)], target)
        print(f"  done; spent so far ${budget.spent:.2f}", flush=True)
    (OUT / "report.md").write_text(_report(reports, budget.spent), encoding="utf-8")
    scores = {f"{s}-{t}": {"translator_chrf": r.translator_chrf, "judge_accuracy": r.judge_accuracy,
                           "top_judge": r.top_judge, "ensemble_chrf": r.ensemble_chrf, "threshold": r.threshold,
                           "flag_share": r.flag_share} for (s, t), r in reports.items()}
    (OUT / "scores.json").write_text(json.dumps(scores, indent=1), encoding="utf-8")  # for the dashboard
    print(f"Report: {OUT / 'report.md'}")


def _details(path: Path, report: EvaluationReport, target: str) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        out = csv.writer(f)
        out.writerow(["id", "source", "reference", "winner", "authors", "winner chrF vs reference",
                      "back-translation", "back chrF", "flags"])
        for item, r in report.details:
            closeness = sacrebleu.sentence_chrf(r.winner.text, [item.reference]).score
            out.writerow([item.row.id, item.row.source, item.reference, r.winner.text, " + ".join(r.winner.authors),
                          f"{closeness:.1f}", r.back_translation or "", "" if r.chrf is None else f"{r.chrf:.1f}",
                          "; ".join(r.flags)])


def _report(reports: dict, spent: float) -> str:
    lines = ["# Test run: FLORES+ devtest, 200 sentences each way, register written", ""]
    for (source, target), r in reports.items():
        lines += [f"## {source} → {target}", "", "| Translator | chrF |", "|---|---|"]
        lines += [f"| {m} | {c:.1f} |" for m, c in sorted(r.translator_chrf.items(), key=lambda x: -x[1])]
        lines += ["", "| Judge | Accuracy |", "|---|---|"]
        lines += [f"| {j} | {a:.0%} |" for j, a in sorted(r.judge_accuracy.items(), key=lambda x: -x[1])]
        verdict = "beats" if r.ensemble_beats_best else "does NOT beat"
        lines += ["", f"- Recommended top judge: **{r.top_judge}**",
                  f"- Ensemble chrF **{r.ensemble_chrf:.1f}** {verdict} the best single translator "
                  f"({r.best_translator}, {r.best_translator_chrf:.1f})",
                  f"- Recommended back-translation threshold: **{r.threshold:.1f}**, flagging "
                  f"{r.flag_share:.0%} of sentences" if r.threshold is not None else "- No threshold (no spread)",
                  ""]
    lines += [f"Total spent by this test run: **${spent:.2f}**", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
