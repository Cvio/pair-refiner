"""Seam 6: a run's output files (BUILD.md, "Outputs"; docs/adr/0003). The CSVs are UTF-8 with a BOM, so Excel
reads them correctly."""

import csv
import dataclasses
import json
from pathlib import Path

from pair_refiner.dataset import DatasetSettings
from pair_refiner.refine import Candidate


def write(folder: Path, report, dataset: DatasetSettings, settings, times: dict) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    _pairs(folder / "pairs.jsonl", report, dataset)
    _candidates(folder / "candidates.csv", report, settings.judges)
    _flags(folder / "flags.csv", report)
    _run_json(folder / "run.json", report, dataset, settings, times)


def _pairs(path: Path, report, dataset: DatasetSettings) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for s in report.sentences:
            pair = {"source": s.result.source or s.row.source, "target": s.result.winner.text, "source_lang": dataset.source_lang,
                    "target_lang": dataset.target_lang, "register": s.register,
                    "author": list(s.result.winner.authors), "id": s.row.id}
            f.write(json.dumps(pair, ensure_ascii=False) + "\n")


def _candidates(path: Path, report, judges: list[str]) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        out = csv.writer(f)
        out.writerow(["id", "register", "source", "original source", "candidate", "authors",
                      *(f"{judge} {score}" for judge in judges for score in ("meaning", "naturalness")),
                      "panel meaning", "panel naturalness", "shortlisted", "winner", "top judge reason",
                      "back-translation", "chrF", "replaced", "notes", "sentence cost"])
        for s in report.sentences:
            r = s.result
            for c in sorted(r.candidates, key=lambda c: c.panel_score, reverse=True):
                won = c is r.winner
                meaning, naturalness = c.panel_score
                sentence = [r.top_judge_reason or "", r.back_translation or "",
                            "" if r.chrf is None else f"{r.chrf:.1f}",
                            "" if not _had_dataset_translation(r) else ("yes" if r.replaced else "no"),
                            "; ".join(r.notes), f"{r.cost:.6f}"] if won else [""] * 6
                out.writerow([s.row.id, s.register or "", s.result.source or s.row.source, _original(s), c.text, " + ".join(c.authors),
                              *_votes(c, judges), f"{meaning:.2f}", f"{naturalness:.2f}",
                              "yes" if c in r.shortlist else "", "yes" if won else "", *sentence])


def _votes(candidate: Candidate, judges: list[str]) -> list[str]:
    """Each judge's meaning and naturalness; a discarded vote for its own model's candidate marked "(own)"."""
    cells = []
    for judge in judges:
        if judge in candidate.scores:
            cells += [str(score) for score in candidate.scores[judge]]
        elif judge in candidate.own_scores:
            cells += [f"{score} (own)" for score in candidate.own_scores[judge]]
        else:  # no vote: the judge's answer was malformed
            cells += ["", ""]
    return cells


def _had_dataset_translation(result) -> bool:
    return any("dataset" in c.authors for c in result.candidates)


def _flags(path: Path, report) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        out = csv.writer(f)
        out.writerow(["id", "register", "source", "winner", "flag"])
        for s in report.sentences:
            for flag in s.result.flags:
                out.writerow([s.row.id, s.register or "", s.result.source or s.row.source, s.result.winner.text, flag])


def _run_json(path: Path, report, dataset: DatasetSettings, settings, times: dict) -> None:
    record = {
        "status": report.status,
        "dataset": dataclasses.asdict(dataset),
        "settings": dataclasses.asdict(settings),
        "totals": {"sentences": len(report.sentences), "pairs": len(report.sentences),
                   "flagged": sum(bool(s.result.flags) for s in report.sentences),
                   "replaced": sum(s.result.replaced for s in report.sentences)},
        "cost": round(report.cost, 6),
        **times,
    }
    path.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")


def _original(sentence) -> str:
    """The source as the dataset wrote it, when the tidy-up changed it (docs/adr/0006); empty otherwise."""
    tidied = sentence.result.source
    return sentence.row.source if tidied and tidied != sentence.row.source else ""
