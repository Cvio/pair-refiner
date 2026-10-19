"""Run a dataset from the command line (the dashboard comes in M7).

    uv run python -m pair_refiner.cli DATASET_SETTINGS --name NAME [--sentences N] [--limit USD]
                                      [--register written|spoken|both] [--estimate]

The run's files go to runs\\NAME. Running the same name again resumes it: answers already paid for come from the
cache, and the spending limit counts what the run spent before. The top judge and chrF threshold are placeholders
until the M6 test run sets their defaults."""

import argparse
import sys
import tomllib
from pathlib import Path

from pair_refiner import estimate
from pair_refiner.cache import CachedConnection
from pair_refiner.connection import OpenRouter
from pair_refiner.dataset import read_dataset, read_settings
from pair_refiner.live import LiveConnection, load_keys
from pair_refiner.run import RunSettings, run

REPO = Path(__file__).parents[2]
CACHE = REPO / "cache" / "answers.sqlite"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="pair-refiner")
    parser.add_argument("dataset", type=Path, help="the dataset's settings file (.toml)")
    parser.add_argument("--name", required=True, help="the run's name; its files go to runs\\NAME")
    parser.add_argument("--sentences", type=int, help="only the first N sentences")
    parser.add_argument("--limit", type=float, help="spending limit in USD")
    parser.add_argument("--register", help="written, spoken or both (Persian only)")
    parser.add_argument("--estimate", action="store_true", help="only estimate the cost; spend nothing")
    args = parser.parse_args()

    with open(REPO / "defaults.toml", "rb") as f:
        models = tomllib.load(f)["models"]
    path, dataset = read_settings(args.dataset)
    rows = read_dataset(path, dataset)
    settings = RunSettings(translators=models["translators"], judges=models["judges"],
                           top_judge="anthropic/claude-opus-5.5", register=args.register or dataset.register,
                           sentence_limit=args.sentences, spending_limit=args.limit)
    estimator = estimate.from_cache(OpenRouter().list_models(), CACHE)
    folder = REPO / "runs" / args.name

    if args.estimate:
        report = run(rows, dataset, settings, None, folder, estimator, dry_run=True)
        basis = "measured answer lengths" if estimator.measured else "a rough guess (no run has measured yet)"
        count = min(len(rows), args.sentences or len(rows))
        print(f"Estimate for {count} sentences: ${report.estimate:.2f}, from today's prices and {basis}. "
              "Answers already in the cache will cost nothing, so a resumed run costs less.")
        return

    connection = CachedConnection(LiveConnection(load_keys(REPO / "keys.toml")), CACHE)
    report = run(rows, dataset, settings, connection, folder, estimator)
    print(f"{report.status}: {len(report.sentences)} sentences, ${report.cost:.4f} spent by this run so far.")
    print(f"Files: {folder}")


if __name__ == "__main__":
    main()
