"""Seam 7: the dashboard's server. Each page and action through Flask's test client, with the stand-in connection
behind a real cache, and real runs in a temporary folder."""

import json
import time

import pytest
from conftest import StandIn

from pair_refiner.cache import CachedConnection
from pair_refiner.connection import Model
from pair_refiner.dashboard import create_app
from pair_refiner.dataset import DatasetSettings, Row
from pair_refiner.run import RunSettings, run

ON_TABLE = "کتاب روی میز است."  # کتاب روی میز است.
OVER_TABLE = "کتاب بالای میز است."  # کتاب بالای میز است.


def standin() -> StandIn:
    return StandIn(translations={"m/a": ON_TABLE, "m/b": OVER_TABLE},
                   panel={judge: {ON_TABLE: (5, 5), OVER_TABLE: (3, 3)} for judge in ("m/c", "m/d")},
                   top_pick=ON_TABLE)


@pytest.fixture
def root(tmp_path):
    (tmp_path / "datasets").mkdir()
    (tmp_path / "defaults.toml").write_text(
        '[directions.en-fa]\ntranslators = ["m/a", "m/b"]\njudges = ["m/c", "m/d"]\ntop_judge = "m/c"\n'
        "back_translation = false\n", encoding="utf-8")
    return tmp_path


def client(root, connection):
    return create_app(root, connection, root / "cache" / "answers.sqlite").test_client()


def test_the_front_page_goes_to_the_runs(root):
    page = client(root, standin()).get("/")

    assert page.status_code == 302 and page.headers["Location"].endswith("/runs")


def test_the_runs_page_lists_past_runs_with_their_status_and_cost(root):
    connection = standin()
    run([Row(id="1", source="The book is on the table.", existing=None, origin=None)],
        DatasetSettings(source_lang="en", target_lang="fa"),
        RunSettings(translators=["m/a", "m/b"], judges=["m/c", "m/d"], top_judge="m/c", back_translation=False),
        CachedConnection(connection, root / "cache" / "answers.sqlite"), root / "runs" / "first-run")

    page = client(root, connection).get("/runs")

    assert page.status_code == 200
    text = page.get_data(as_text=True)
    assert "first-run" in text and "finished" in text
    assert "$0.0420" in text  # 2 translations 0.002, 2 judges 0.02, top judge 0.02


def test_the_models_page_shows_each_directions_models_prices_and_test_run_scores(root):
    connection = standin()
    connection.models = [Model("m/a", "Maker: A", "m", 0, 2.0, 10.0, True, "low"),
                         Model("m/c", "Maker: C", "m", 0, 0.5, 1.5, False, None)]
    (root / "runs" / "test-run").mkdir(parents=True)
    (root / "runs" / "test-run" / "scores.json").write_text(json.dumps({"en-fa": {
        "translator_chrf": {"m/a": 58.1, "m/b": 51.4}, "judge_accuracy": {"m/c": 0.25, "m/d": 0.2},
        "top_judge": "m/c", "ensemble_chrf": 53.1, "threshold": 49.9, "flag_share": 0.06}}), encoding="utf-8")

    text = client(root, connection).get("/models").get_data(as_text=True)

    assert "en-fa" in text
    assert "$2.00" in text and "$10.00" in text  # m/a's prices per million tokens
    assert "58.1" in text  # m/a's chrF in the test run
    assert "25%" in text  # m/c's accuracy as a judge


def dataset(root, name="three"):
    (root / "datasets" / f"{name}.csv").write_text(
        "source\nThe book is on the table.\nGood night.\nWhere is the station?\n", encoding="utf-8")
    (root / "datasets" / f"{name}.toml").write_text(
        f'file = "{name}.csv"\nsource_lang = "en"\ntarget_lang = "fa"\n', encoding="utf-8")


def priced(connection: StandIn) -> StandIn:
    connection.models = [Model(m, m, "m", 0, 1.0, 1.0, True, None) for m in ("m/a", "m/b", "m/c", "m/d")]
    return connection


NEW_RUN = {"dataset": "three", "name": "my-run", "register": "written", "translators": ["m/a", "m/b"],
           "judges": ["m/c", "m/d"], "top_judge": "m/c", "shortlist_size": "3", "chrf_threshold": "40",
           "sentence_limit": "", "spending_limit": "1.00"}


def test_the_new_run_page_offers_the_datasets_with_their_directions_defaults_ticked(root):
    dataset(root)

    text = client(root, priced(standin())).get("/new?dataset=three").get_data(as_text=True)

    assert '<option value="three" selected>' in text
    assert 'name="translators" value="m/a" checked' in text
    assert 'name="judges" value="m/d" checked' in text


def test_estimate_shows_the_cost_and_makes_no_calls(root):
    dataset(root)
    connection = priced(standin())

    text = client(root, connection).post("/new", data={**NEW_RUN, "action": "estimate"}).get_data(as_text=True)

    assert connection.calls == []
    # Rough guess (nothing measured yet), $1 per million tokens: 2 translations x 530 tokens, 2 judges x 1,200,
    # the top judge 800: $0.00426 a sentence, x 3 sentences.
    assert "$0.0128" in text


def wait_for(browser, url: str, text: str, seconds: float = 10.0) -> str:
    """The page at `url` once it contains `text` (a run works in the background)."""
    deadline = time.monotonic() + seconds
    while True:
        page = browser.get(url).get_data(as_text=True)
        if text in page or time.monotonic() > deadline:
            return page
        time.sleep(0.05)


def test_start_runs_in_the_background_and_its_page_shows_progress_cost_and_limit(root):
    dataset(root)
    browser = client(root, priced(standin()))

    started = browser.post("/new", data={**NEW_RUN, "action": "start"})
    text = wait_for(browser, "/runs/my-run", "finished")

    assert started.status_code == 303 and started.headers["Location"].endswith("/runs/my-run")
    assert "finished" in text
    assert "3 of 3 sentences" in text
    assert "$0.1260 of $1.00" in text  # 3 sentences x $0.042
    assert "No flags" in text


def test_a_sentence_page_shows_every_candidate_every_judges_scores_and_the_reasons(root):
    dataset(root)
    connection = priced(standin())
    connection.panel["m/d"] = {ON_TABLE: (3, 3), OVER_TABLE: (2, 2)}  # 5 and 3 on the winner: panel disagreement
    browser = client(root, connection)
    browser.post("/new", data={**NEW_RUN, "action": "start", "sentence_limit": "1"})
    run_page = wait_for(browser, "/runs/my-run", "finished")

    text = browser.get("/runs/my-run/sentences/0").get_data(as_text=True)

    assert "panel disagreement" in run_page
    assert "The book is on the table." in text
    assert ON_TABLE in text and OVER_TABLE in text
    assert "m/c meaning" in text and "m/d naturalness" in text
    assert "It reads best." in text  # the top judge's reason
    assert "panel disagreement" in text


@pytest.mark.parametrize("balance, shown", [(12.34, "$12.34"), (None, "add a management key")])
def test_every_page_shows_the_openrouter_balance_and_this_months_google_spend(root, balance, shown):
    connection = standin()
    connection.translations["google-translate"] = OVER_TABLE
    connection.balance_left = balance  # None: no management key
    run([Row(id="1", source="The book is on the table.", existing=None, origin=None)],
        DatasetSettings(source_lang="en", target_lang="fa"),
        RunSettings(translators=["google-translate", "m/a"], judges=["m/c"], top_judge="m/c", back_translation=False),
        CachedConnection(connection, root / "cache" / "answers.sqlite"), root / "runs" / "with-google")

    text = client(root, connection).get("/runs").get_data(as_text=True)

    assert shown in text
    assert "Google this month: <b>$0.0010</b>" in text  # one Google translation at the stand-in's 0.001
