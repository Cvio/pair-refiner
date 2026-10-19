"""Seam 4: a whole run. Rows, settings and a connection (the stand-in, behind a real cache) give every
sentence's result, stopping at the spending limit and resuming without repeating a call."""

import pytest
from conftest import StandIn

from pair_refiner.cache import CachedConnection
from pair_refiner.dataset import DatasetSettings, Row
from pair_refiner.estimate import Estimator
from pair_refiner.run import RunSettings, run

EN_FA = DatasetSettings(source_lang="en", target_lang="fa")
ON_TABLE = "کتاب روی میز است."  # کتاب روی میز است.
OVER_TABLE = "کتاب بالای میز است."  # کتاب بالای میز است.
ROWS = [Row(id=str(n), source=f"Sentence {n}.", existing=None, origin=None) for n in (1, 2, 3)]


def standin() -> StandIn:
    return StandIn(
        translations={"m/a": ON_TABLE, "m/b": OVER_TABLE},
        panel={judge: {ON_TABLE: (5, 5), OVER_TABLE: (3, 3)} for judge in ("m/c", "m/d")},
        top_pick=ON_TABLE,
        back={"m/b": "Sentence 1."},
    )


def settings(**changes) -> RunSettings:
    base = dict(translators=["m/a", "m/b"], judges=["m/c", "m/d"], top_judge="m/c", back_translation=False)
    return RunSettings(**(base | changes))


def test_a_run_refines_every_sentence_up_to_the_sentence_limit(tmp_path):
    connection = standin()

    report = run(ROWS, EN_FA, settings(sentence_limit=2), CachedConnection(connection, tmp_path / "c.sqlite"),
                 tmp_path / "run")

    assert report.status == "finished"
    assert [(s.row.id, s.result.winner.text) for s in report.sentences] == [("1", ON_TABLE), ("2", ON_TABLE)]
    assert report.cost == pytest.approx(0.084)  # per sentence: 2 translations 0.002, 2 judges 0.02, top 0.02


FIVE_CENTS = Estimator(  # every call: 5,000 tokens in and out at $1 per million = $0.01; 5 calls a sentence
    prices={model: (1.0, 1.0) for model in ("m/a", "m/b", "m/c", "m/d")},
    lengths={(kind, model): (5000, 5000) for kind in ("translate", "judge", "top_judge", "back_translate")
             for model in ("m/a", "m/b", "m/c", "m/d")},
)


def test_a_run_stops_cleanly_before_a_sentence_that_would_pass_the_spending_limit(tmp_path):
    connection = standin()

    report = run(ROWS, EN_FA, settings(spending_limit=0.10), CachedConnection(connection, tmp_path / "c.sqlite"),
                 tmp_path / "run", estimator=FIVE_CENTS)

    # Sentence 1: 0 + 0.05 fits; spent 0.042. Sentence 2: 0.042 + 0.05 = 0.092 fits; spent 0.084.
    # Sentence 3: 0.084 + 0.05 = 0.134 would pass 0.10: stop.
    assert report.status == "stopped at the spending limit"
    assert [s.row.id for s in report.sentences] == ["1", "2"]
    assert report.cost == pytest.approx(0.084)
    assert "Sentence 3." not in {call[2].text for call in connection.calls if call[0] == "translate"}


def test_a_crashed_run_resumes_without_repeating_any_call_and_counts_what_it_spent_before(tmp_path):
    connection = standin()
    connection.fail_after = 7  # sentence 1 takes 5 calls; the connection is lost during sentence 2
    with pytest.raises(ConnectionError):
        run(ROWS, EN_FA, settings(), CachedConnection(connection, tmp_path / "c.sqlite"), tmp_path / "run")

    connection.fail_after = None
    report = run(ROWS, EN_FA, settings(), CachedConnection(connection, tmp_path / "c.sqlite"), tmp_path / "run")

    assert report.status == "finished"
    assert len(report.sentences) == 3
    assert len(connection.calls) == 15  # 3 sentences x 5 calls, none asked twice
    assert report.cost == pytest.approx(0.126)  # 3 x 0.042, including what the crashed attempt spent


@pytest.mark.parametrize("change, new_calls", [
    # Only the double-check is new. All three winners are the same text, so it is asked once and cached.
    (dict(back_translation=True), [("back_translate", "m/b")]),
    (dict(top_judge="m/d"), [("top_judge", "m/d")] * 3),  # only the new top judge's picks are new
])
def test_changing_a_setting_reruns_only_the_parts_it_affects(tmp_path, change, new_calls):
    connection = standin()
    connection.back = {"m/b": "Sentence."}
    run(ROWS, EN_FA, settings(), CachedConnection(connection, tmp_path / "c.sqlite"), tmp_path / "run1")
    assert len(connection.calls) == 15

    run(ROWS, EN_FA, settings(**change), CachedConnection(connection, tmp_path / "c.sqlite"), tmp_path / "run2")

    assert connection.kinds()[15:] == new_calls


def test_a_dry_run_estimates_the_cost_and_makes_no_calls(tmp_path):
    connection = standin()

    report = run(ROWS, EN_FA, settings(register="both", sentence_limit=2),
                 CachedConnection(connection, tmp_path / "c.sqlite"), tmp_path / "run",
                 estimator=FIVE_CENTS, dry_run=True)

    assert connection.calls == []
    assert report.status == "estimate"
    assert report.estimate == pytest.approx(0.20)  # 2 sentences x 2 registers x $0.05
    assert report.cost == 0


def test_register_both_picks_a_written_and_a_spoken_version_of_each_sentence(tmp_path):
    connection = standin()

    report = run(ROWS[:2], EN_FA, settings(register="both"), CachedConnection(connection, tmp_path / "c.sqlite"),
                 tmp_path / "run")

    assert [(s.row.id, s.register) for s in report.sentences] == [
        ("1", "written"), ("1", "spoken"), ("2", "written"), ("2", "spoken")]
    asked = {(call[2].text, call[2].register) for call in connection.calls if call[0] == "translate"}
    assert asked == {("Sentence 1.", "written"), ("Sentence 1.", "spoken"),
                     ("Sentence 2.", "written"), ("Sentence 2.", "spoken")}
