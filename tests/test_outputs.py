"""Seam 6: the output files. A run's pairs.jsonl, candidates.csv, flags.csv and run.json, checked byte for byte
against expected files written out by hand (tests/expected/), and run.json field by field."""

import json
from pathlib import Path

from conftest import StandIn

from pair_refiner.cache import CachedConnection
from pair_refiner.dataset import DatasetSettings, Row
from pair_refiner.run import RunSettings, run

EXPECTED = Path(__file__).parent / "expected" / "two-sentences"
ON, OVER = "کتاب روی میز است.", \
           "کتاب بالای میز است."
KHOSH, BEKHEIR = "شب خوش.", "شب بخیر."  # شب خوش. / شب بخیر.
DATASET = DatasetSettings(source_lang="en", target_lang="fa", origin="unknown")
SETTINGS = RunSettings(translators=["m/a", "m/b"], judges=["m/a", "m/c"], top_judge="m/c", back_translation=True)


def run_two_sentences(folder: Path) -> None:
    rows = [Row(id="1", source="The book is on the table.", existing=None, origin=None),
            Row(id="2", source="Good night.", existing=BEKHEIR, origin="unknown")]
    standin = StandIn(
        translations={"m/a": {"The book is on the table.": ON, "Good night.": KHOSH},
                      "m/b": {"The book is on the table.": OVER, "Good night.": BEKHEIR}},
        panel={"m/a": {ON: (5, 5), OVER: (3, 4), KHOSH: (5, 5), BEKHEIR: (3, 4)},
               "m/c": {ON: (5, 4), OVER: (2, 3), KHOSH: (3, 3), BEKHEIR: (5, 5)}},
        top_pick={ON, BEKHEIR},
        back={"m/b": "The book is on the table.", "m/a": "Good night."},
    )
    run(rows, DATASET, SETTINGS, CachedConnection(standin, folder.parent / "c.sqlite"), folder)


def test_pairs_candidates_and_flags_match_the_expected_files_byte_for_byte(tmp_path):
    run_two_sentences(tmp_path / "run")

    for name in ("pairs.jsonl", "candidates.csv", "flags.csv"):
        assert (tmp_path / "run" / name).read_bytes() == (EXPECTED / name).read_bytes(), name


def test_run_json_records_the_settings_totals_cost_and_time(tmp_path):
    run_two_sentences(tmp_path / "run")

    record = json.loads((tmp_path / "run" / "run.json").read_text(encoding="utf-8"))

    assert {key: record.pop(key) is not None for key in ("started", "finished", "seconds")} == \
        {"started": True, "finished": True, "seconds": True}
    assert record == {
        "status": "finished",
        "dataset": {"source_lang": "en", "target_lang": "fa", "register": "written", "origin": "unknown",
                    "conversation": False, "conversation_column": None},
        "settings": {"translators": ["m/a", "m/b"], "judges": ["m/a", "m/c"], "top_judge": "m/c",
                     "shortlist_size": 3, "back_translation": True, "chrf_threshold": 40.0, "register": "written",
                     "sentence_limit": None, "spending_limit": None},
        "totals": {"sentences": 2, "pairs": 2, "flagged": 1, "replaced": 0},
        "cost": 0.086,  # per sentence: 2 translations 0.002, 2 judges 0.02, top judge 0.02, double-check 0.001
    }
