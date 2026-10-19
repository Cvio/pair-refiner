"""Seam 5: the test run. Sentences with professional (reference) translations give each translator's chrF, each
judge's accuracy, the ensemble against the best single translator, and the recommended top judge and
back-translation threshold (docs/adr/0004). The connection is the stand-in, behind a real cache."""

import pytest
from conftest import StandIn

from pair_refiner.cache import CachedConnection
from pair_refiner.dataset import DatasetSettings, Row
from pair_refiner.evaluation import Reference, evaluate
from pair_refiner.run import RunSettings

EN_FA = DatasetSettings(source_lang="en", target_lang="fa")
REFS = ["کتاب روی میز است.",  # کتاب روی میز است.
        "شب بخیر.",  # شب بخیر.
        "سلام دوست من.",  # سلام دوست من.
        "هوا سرد است."]  # هوا سرد است.
SOURCES = ["The book is on the table.", "Good night.", "Hello my friend.", "The weather is cold."]
JUNK = [f"zzz {'q' * n}" for n in range(1, 5)]  # no letter in common with any reference


def items(n: int = 4) -> list[Reference]:
    return [Reference(Row(id=str(i), source=s, existing=None, origin=None), r)
            for i, (s, r) in enumerate(zip(SOURCES[:n], REFS[:n]), 1)]


def test_translators_chrf_and_judges_accuracy_give_the_recommended_top_judge(tmp_path):
    standin = StandIn(
        translations={"m/a": dict(zip(SOURCES, REFS)), "m/b": dict(zip(SOURCES, JUNK))},
        panel={
            "m/b": {**{r: (2, 2) for r in REFS}, **{j: (5, 5) for j in JUNK}},  # prefers its own junk: 0 of 4
            "m/c": {**{r: (5, 5) for r in REFS}, **{j: (1, 1) for j in JUNK}},  # always right: 4 of 4
            "m/d": {REFS[0]: (5, 5), REFS[1]: (5, 5), JUNK[0]: (1, 1), JUNK[1]: (1, 1),  # right twice: 2 of 4
                    REFS[2]: (1, 1), REFS[3]: (1, 1), JUNK[2]: (5, 5), JUNK[3]: (5, 5)},
        },
        top_pick=set(REFS),
    )
    settings = RunSettings(translators=["m/a", "m/b"], judges=["m/b", "m/c", "m/d"], top_judge="m/b",
                           back_translation=False)

    report = evaluate(items(), EN_FA, settings, CachedConnection(standin, tmp_path / "c.sqlite"))

    assert report.translator_chrf == {"m/a": pytest.approx(100.0), "m/b": pytest.approx(0.0)}
    assert report.judge_accuracy == {"m/b": 0.0, "m/c": 1.0, "m/d": 0.5}
    assert report.top_judge == "m/c"


def test_the_ensemble_with_the_recommended_top_judge_is_compared_with_the_best_single_translator(tmp_path):
    half = {"m/a": REFS[:2] + JUNK[2:], "m/b": JUNK[:2] + REFS[2:]}  # each right on two sentences only
    standin = StandIn(
        translations={model: dict(zip(SOURCES, texts)) for model, texts in half.items()},
        panel={"m/c": {**{r: (5, 5) for r in REFS}, **{j: (1, 1) for j in JUNK}},
               "m/d": {**{r: (1, 1) for r in REFS}, **{j: (5, 5) for j in JUNK}}},
        top_pick=set(REFS),
    )
    settings = RunSettings(translators=["m/a", "m/b"], judges=["m/c", "m/d"], top_judge="m/d",
                           back_translation=False)

    report = evaluate(items(), EN_FA, settings, CachedConnection(standin, tmp_path / "c.sqlite"))

    assert report.top_judge == "m/c"
    assert report.ensemble_chrf == pytest.approx(100.0)  # every winner is the reference
    assert report.best_translator in ("m/a", "m/b") and report.best_translator_chrf < 100.0
    assert report.ensemble_beats_best is True
    # The second pass asked only the recommended top judge; translations and the panel came from the cache.
    assert [k for k in standin.kinds() if k == ("top_judge", "m/c")] == [("top_judge", "m/c")] * 4
    assert len([k for k in standin.kinds() if k[0] in ("translate", "judge")]) == 4 * 2 + 4 * 2


def test_persian_digits_score_the_same_as_the_references_western_digits(tmp_path):
    reference = "موش‌های 4 ماهه"  # موش‌های 4 ماهه, as FLORES+ writes
    translation = "موش‌های ۴ ماهه"  # موش‌های ۴ ماهه
    standin = StandIn(translations={"m/a": translation}, panel={"m/c": {translation: (5, 5)}}, top_pick=translation)
    item = Reference(Row(id="1", source="4-month-old mice", existing=None, origin=None), reference)
    settings = RunSettings(translators=["m/a"], judges=["m/c"], top_judge="m/c", back_translation=False)

    report = evaluate([item], EN_FA, settings, CachedConnection(standin, tmp_path / "c.sqlite"))

    assert report.translator_chrf == {"m/a": pytest.approx(100.0)}


def test_the_recommended_threshold_best_separates_the_truly_bad_winners(tmp_path):
    standin = StandIn(
        translations={"m/a": dict(zip(SOURCES, REFS)), "m/b": dict(zip(SOURCES, JUNK))},
        panel={"m/c": {**{r: (5, 5) for r in REFS}, **{j: (1, 1) for j in JUNK}}},
        top_pick={REFS[0], REFS[1], REFS[2], JUNK[3]},  # sentence 4's winner is junk: the truly bad one
        back={"m/b": dict(zip(REFS[:3], SOURCES[:3])),  # good winners come back exactly: chrF 100
              "m/a": {JUNK[3]: "zzz"}},  # the junk comes back as nonsense: chrF 0
    )
    settings = RunSettings(translators=["m/a", "m/b"], judges=["m/c"], top_judge="m/c", back_translation=True)

    report = evaluate(items(), EN_FA, settings, CachedConnection(standin, tmp_path / "c.sqlite"))

    assert report.threshold == pytest.approx(50.0)  # the midpoint between 0 and 100
    assert report.flag_share == pytest.approx(0.25)  # it flags sentence 4 only
