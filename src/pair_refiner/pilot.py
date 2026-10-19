"""M4: the 20-sentence pilot. MIZAN's first 20 rows English->Persian, and the same rows reversed. Writes one
Excel-ready CSV per direction and the measured answer lengths (for M5's dry-run estimate) to runs\\pilot-m4.

Run with: uv run python -m pair_refiner.pilot
The top judge and chrF threshold here are placeholders until the M6 test run sets their defaults."""

import csv
import json
import sqlite3
import sys
import tomllib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pair_refiner import persian
from pair_refiner.cache import CachedConnection
from pair_refiner.dataset import Row, read_dataset, read_settings
from pair_refiner.live import LiveConnection, load_keys
from pair_refiner.refine import RefineSettings, Result, refine

REPO = Path(__file__).parents[2]
OUT = REPO / "runs" / "pilot-m4"
CACHE = REPO / "cache" / "answers.sqlite"
SENTENCES = 20


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    with open(REPO / "defaults.toml", "rb") as f:
        models = tomllib.load(f)["models"]
    path, dataset = read_settings(REPO / "datasets" / "mizan-sample-2000.toml")
    en_fa = read_dataset(path, dataset)[:SENTENCES]
    fa_en = [Row(r.id, persian.tidy(r.existing), r.source, "unknown") for r in en_fa]
    live = LiveConnection(load_keys(REPO / "keys.toml"))
    OUT.mkdir(parents=True, exist_ok=True)

    total = 0.0
    for source_lang, target_lang, rows in (("en", "fa", en_fa), ("fa", "en", fa_en)):
        settings = RefineSettings(source_lang=source_lang, target_lang=target_lang, register="written",
                                  translators=models["translators"], judges=models["judges"],
                                  top_judge="anthropic/claude-opus-5.5", back_translation=True, chrf_threshold=40.0)

        def one(row: Row) -> Result:
            return refine(row, settings, CachedConnection(live, CACHE))  # one cache handle per thread

        with ThreadPoolExecutor(max_workers=5) as pool:
            results = list(pool.map(one, rows))
        cost = sum(r.cost for r in results)
        total += cost
        _write(OUT / f"pilot-{source_lang}-{target_lang}.csv", rows, results)
        print(f"{source_lang}->{target_lang}: {len(rows)} sentences, ${cost:.4f} spent this time")
        for row, result in zip(rows, results):
            print(f"  {row.id:>3} {', '.join(result.winner.authors):60} {'; '.join(result.flags + result.notes)}")
    _answer_lengths(OUT / "answer-lengths.json")
    print(f"total spent this time: ${total:.4f}")


def _write(path: Path, rows: list[Row], results: list[Result]) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as f:  # the BOM makes Excel read it as UTF-8
        out = csv.writer(f)
        out.writerow(["id", "source", "candidate", "authors", "panel meaning", "panel naturalness", "winner",
                      "top judge reason", "back-translation", "chrF", "flags", "notes", "sentence cost"])
        for row, result in zip(rows, results):
            for c in sorted(result.candidates, key=lambda c: c.panel_score, reverse=True):
                meaning, naturalness = c.panel_score
                won = c is result.winner
                out.writerow([row.id, row.source, c.text, " + ".join(c.authors), f"{meaning:.2f}",
                              f"{naturalness:.2f}", "WINNER" if won else "",
                              result.top_judge_reason or "" if won else "",
                              result.back_translation or "" if won else "",
                              f"{result.chrf:.1f}" if won and result.chrf is not None else "",
                              "; ".join(result.flags) if won else "", "; ".join(result.notes) if won else "",
                              f"{result.cost:.5f}" if won else ""])


def _answer_lengths(path: Path) -> None:
    """Average tokens per call kind and model, from every answer in the cache (M5's dry run uses these)."""
    db = sqlite3.connect(CACHE)
    rows = db.execute("SELECT kind, model, COUNT(*), AVG(input_tokens), AVG(output_tokens), AVG(cost) "
                      "FROM answers GROUP BY kind, model ORDER BY kind, model").fetchall()
    lengths = [{"kind": k, "model": m, "calls": n, "input_tokens": round(i), "output_tokens": round(o),
                "cost": round(c, 6)} for k, m, n, i, o, c in rows]
    path.write_text(json.dumps(lengths, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
