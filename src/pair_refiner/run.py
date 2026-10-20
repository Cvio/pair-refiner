"""Seam 4: a whole run. Every sentence of a dataset refined, within a spending limit, resumable."""

import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from pair_refiner import outputs
from pair_refiner.connection import Answer, Connection
from pair_refiner.dataset import DatasetSettings, Row
from pair_refiner.estimate import Estimator
from pair_refiner.refine import RefineSettings, Result, refine


PROGRESS_EVERY = 2.0  # seconds between updates of a running run's files


@dataclass(frozen=True)
class RunSettings:
    translators: list[str]
    judges: list[str]
    top_judge: str
    shortlist_size: int = 3
    back_translation: bool = True
    chrf_threshold: float = 40.0
    register: str = "written"  # "written", "spoken" or "both" (Persian only)
    sentence_limit: int | None = None
    spending_limit: float | None = None  # USD


@dataclass
class Sentence:
    row: Row
    register: str
    result: Result


@dataclass
class RunReport:
    status: str  # "running", "finished", "stopped at the spending limit", or "estimate" (a dry run)
    sentences: list[Sentence] = field(default_factory=list)
    cost: float = 0.0  # USD actually spent by this run, earlier stopped attempts included
    estimate: float | None = None  # USD, a dry run's estimate


def run(rows: list[Row], dataset: DatasetSettings, settings: RunSettings, connection: Connection,
        folder: Path, estimator: Estimator | None = None, dry_run: bool = False) -> RunReport:
    if (dry_run or settings.spending_limit is not None) and estimator is None:
        raise ValueError("a dry run or a spending limit needs an estimator")
    if dry_run:  # spends nothing: no call is made
        estimate = sum(estimator.sentence_cost(row, refine_settings(dataset, settings, register))
                       for row in rows[: settings.sentence_limit] for register in _registers(dataset, settings))
        return RunReport("estimate", estimate=estimate)
    started, clock = datetime.now().astimezone(), time.monotonic()
    ledger = _Ledger(connection, folder / "spending.log")
    planned = len(rows[: settings.sentence_limit]) * len(_registers(dataset, settings))
    report = RunReport("running")
    last_write = -1e9

    def write(final: bool = False) -> None:
        """The output files, kept up to date while the run works (so its page shows progress), and at the end."""
        nonlocal last_write
        if final or time.monotonic() - last_write >= PROGRESS_EVERY:
            report.cost = ledger.spent
            outputs.write(folder, report, dataset, settings, {
                "planned": planned,
                "started": started.isoformat(timespec="seconds"),
                "finished": datetime.now().astimezone().isoformat(timespec="seconds") if final else None,
                "seconds": round(time.monotonic() - clock, 1)})
            last_write = time.monotonic()

    write()
    for row in rows[: settings.sentence_limit]:
        for register in _registers(dataset, settings):
            this = refine_settings(dataset, settings, register)
            if settings.spending_limit is not None and \
                    ledger.spent + estimator.sentence_cost(row, this) > settings.spending_limit:
                report.status = "stopped at the spending limit"
                break
            result = refine(row, this, ledger)
            report.sentences.append(Sentence(row, register, result))
            write()
        else:
            continue
        break
    if report.status == "running":
        report.status = "finished"
    write(final=True)
    return report


class _Ledger:
    """The connection, with every paid answer's cost written to the run's spending.log the moment it arrives, so
    a resumed run knows what was spent before it stopped. Cached answers cost nothing and aren't written."""

    def __init__(self, connection: Connection, path: Path):
        self.connection, self.fingerprint, self.path = connection, connection.fingerprint, path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.spent = sum(float(line) for line in path.read_text().split()) if path.exists() else 0.0

    def __getattr__(self, kind: str):
        def call(*args) -> Answer:
            answer = getattr(self.connection, kind)(*args)
            if answer.cost:
                with open(self.path, "a") as f:
                    f.write(f"{answer.cost!r}\n")
                self.spent += answer.cost
            return answer
        return call


def _registers(dataset: DatasetSettings, settings: RunSettings) -> list[str | None]:
    """The registers each sentence is translated in. Only Persian has them; other targets get None."""
    if dataset.target_lang != "fa":
        return [None]
    return ["written", "spoken"] if settings.register == "both" else [settings.register]


def refine_settings(dataset: DatasetSettings, settings: RunSettings, register: str | None) -> RefineSettings:
    return RefineSettings(
        source_lang=dataset.source_lang, target_lang=dataset.target_lang, register=register or "written",
        translators=settings.translators, judges=settings.judges, top_judge=settings.top_judge,
        shortlist_size=settings.shortlist_size, back_translation=settings.back_translation,
        chrf_threshold=settings.chrf_threshold)
