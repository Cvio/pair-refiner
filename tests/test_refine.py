"""Seam 3: refining one sentence. A row, the settings and a connection give candidates, scores, a winner,
flags and the cost. The connection is the stand-in (conftest.py)."""

import pytest
from conftest import StandIn

from pair_refiner.cache import CachedConnection
from pair_refiner.dataset import Row
from pair_refiner.refine import RefineSettings, refine

BOOK = Row(id="1", source="The book is on the table.", existing=None, origin=None)
ON_TABLE = "کتاب روی میز است."  # کتاب روی میز است.
OVER_TABLE = "کتاب بالای میز است."  # کتاب بالای میز است.


def settings(**changes) -> RefineSettings:
    base = dict(source_lang="en", target_lang="fa", register="written",
                translators=["m/a", "m/b"], judges=["m/c", "m/d"], top_judge="m/c",
                shortlist_size=3, back_translation=False, chrf_threshold=40.0)
    return RefineSettings(**(base | changes))


def test_the_top_judges_pick_from_the_panels_shortlist_wins(tmp_path):
    standin = StandIn(
        translations={"m/a": ON_TABLE, "m/b": OVER_TABLE},
        panel={"m/c": {ON_TABLE: (5, 5), OVER_TABLE: (3, 4)}, "m/d": {ON_TABLE: (5, 4), OVER_TABLE: (2, 4)}},
        top_pick=ON_TABLE,
    )

    result = refine(BOOK, settings(), standin)

    assert result.winner.text == ON_TABLE
    assert result.winner.authors == ("m/a",)
    assert result.top_judge_reason == "It reads best."
    assert result.flags == []
    assert result.cost == pytest.approx(0.042)  # 2 translations at 0.001, 2 judges at 0.01, top judge 0.02


def test_a_judges_score_for_its_own_models_translation_is_discarded():
    standin = StandIn(
        translations={"m/a": OVER_TABLE, "m/b": ON_TABLE},
        panel={
            "m/a": {OVER_TABLE: (5, 5), ON_TABLE: (3, 3)},  # its own OVER_TABLE: discarded
            "m/b": {OVER_TABLE: (3, 3), ON_TABLE: (3, 3)},  # its own ON_TABLE: discarded
            "m/c": {OVER_TABLE: (3, 3), ON_TABLE: (4, 4)},
        },
        top_pick=ON_TABLE,
    )

    result = refine(BOOK, settings(judges=["m/a", "m/b", "m/c"], shortlist_size=1), standin)

    # All votes: OVER 11/3 = 3.67, ON 10/3 = 3.33. Kept votes: OVER (3+3)/2 = 3.0, ON (3+4)/2 = 3.5.
    by_text = {c.text: c for c in result.candidates}
    assert by_text[OVER_TABLE].scores == {"m/b": (3, 3), "m/c": (3, 3)}
    assert by_text[ON_TABLE].scores == {"m/a": (3, 3), "m/c": (4, 4)}
    assert result.winner.text == ON_TABLE


def test_the_shortlist_is_the_top_three_by_meaning_with_naturalness_breaking_ties():
    one, two, three, four = "یک", "دو", "سه", "چهار"  # یک دو سه چهار
    standin = StandIn(
        translations={"m/1": one, "m/2": two, "m/3": three, "m/4": four},
        panel={"m/z": {one: (5, 3), two: (4, 5), three: (5, 4), four: (4, 4)}},
        top_pick=two,
    )

    result = refine(BOOK, settings(translators=["m/1", "m/2", "m/3", "m/4"], judges=["m/z"], top_judge="m/z"), standin)

    assert [c.text for c in result.shortlist] == [three, one, two]
    [(_, _, _, shown)] = [call for call in standin.calls if call[0] == "top_judge"]
    assert sorted(shown.values()) == sorted([three, one, two])
    assert result.winner.text == two


def test_labels_are_shuffled_per_sentence_and_the_same_sentence_gets_the_same_labels():
    texts = ["یک", "دو", "سه", "چهار"]
    translators = ["m/1", "m/2", "m/3", "m/4"]

    def labels_seen(source):
        standin = StandIn(translations=dict(zip(translators, texts)),
                          panel={"m/z": {t: (5, 5) for t in texts}}, top_pick=texts[0])
        refine(Row(id="1", source=source, existing=None, origin=None),
               settings(translators=translators, judges=["m/z"], top_judge="m/z"), standin)
        [panel_labels] = [call[3] for call in standin.calls if call[0] == "judge"]
        [top_labels] = [call[3] for call in standin.calls if call[0] == "top_judge"]
        return panel_labels, top_labels

    sentences = [f"Sentence number {n}." for n in range(10)]
    first = [labels_seen(s) for s in sentences]

    assert [labels_seen(s) for s in sentences] == first  # a re-run sends the very same labels
    in_writing_order = dict(zip("ABCD", texts))
    assert any(panel != in_writing_order for panel, _ in first)  # the panel's order is shuffled
    assert any(list(top.values()) != list(panel.values())[:3] for panel, top in first)  # fresh labels


def test_identical_translations_are_merged_and_keep_all_their_authors():
    standin = StandIn(
        translations={"m/a": ON_TABLE, "m/b": OVER_TABLE, "m/c": ON_TABLE},
        panel={"m/a": {ON_TABLE: (5, 5), OVER_TABLE: (2, 2)},
               "m/b": {ON_TABLE: (4, 4), OVER_TABLE: (5, 5)},
               "m/z": {ON_TABLE: (5, 4), OVER_TABLE: (3, 3)}},
        top_pick=ON_TABLE,
    )

    result = refine(BOOK, settings(translators=["m/a", "m/b", "m/c"], judges=["m/a", "m/b", "m/z"]), standin)

    assert [(c.text, c.authors) for c in result.candidates] == [(ON_TABLE, ("m/a", "m/c")), (OVER_TABLE, ("m/b",))]
    assert {c.text: c.scores for c in result.candidates}[ON_TABLE] == {"m/b": (4, 4), "m/z": (5, 4)}
    assert all(len(call[3]) == 2 for call in standin.calls if call[0] == "judge")
    assert result.winner.authors == ("m/a", "m/c")


def test_persian_answers_are_tidied_before_they_are_compared():
    on_table_arabic_letters = "كتاب روي ميز است."  # كتاب روي ميز است.
    standin = StandIn(
        translations={"m/a": ON_TABLE, "m/b": on_table_arabic_letters},
        panel={"m/z": {ON_TABLE: (5, 5)}},
        top_pick=ON_TABLE,
    )

    result = refine(BOOK, settings(judges=["m/z"], top_judge="m/z"), standin)

    assert [(c.text, c.authors) for c in result.candidates] == [(ON_TABLE, ("m/a", "m/b"))]


@pytest.mark.parametrize("panel_scores_for_own, flags", [
    ((3, 3), ["top judge chose its own"]),  # the panel ranked OVER_TABLE (4) first
    ((5, 5), []),  # the panel ranked the top judge's own ON_TABLE first too
])
def test_a_top_judge_picking_its_own_models_translation_is_flagged_unless_the_panel_agreed(panel_scores_for_own, flags):
    standin = StandIn(
        translations={"m/a": ON_TABLE, "m/b": OVER_TABLE},
        panel={"m/c": {ON_TABLE: panel_scores_for_own, OVER_TABLE: (4, 4)},
               "m/d": {ON_TABLE: panel_scores_for_own, OVER_TABLE: (4, 4)}},
        top_pick=ON_TABLE,
    )

    result = refine(BOOK, settings(top_judge="m/a"), standin)

    assert result.winner.text == ON_TABLE
    assert result.flags == flags


def test_a_malformed_judge_answer_is_asked_for_again_then_counted_as_no_vote():
    standin = StandIn(
        translations={"m/a": ON_TABLE, "m/b": OVER_TABLE},
        panel={"m/c": {ON_TABLE: (5, 5), OVER_TABLE: (3, 3)}, "m/d": {ON_TABLE: (4, 4), OVER_TABLE: (2, 2)}},
        top_pick=ON_TABLE,
        garbled={
            "m/c": ["I think A is the best one."],  # once: the second answer is used
            "m/d": ['{"scores": {"A": {"meaning": 9, "naturalness": 4}}}', "Sorry."],  # twice: no vote
        },
    )

    result = refine(BOOK, settings(), standin)

    assert {c.text: c.scores for c in result.candidates} == {ON_TABLE: {"m/c": (5, 5)}, OVER_TABLE: {"m/c": (3, 3)}}
    assert [k for k in standin.kinds() if k[0] == "judge"] == [("judge", "m/c")] * 2 + [("judge", "m/d")] * 2
    assert result.flags == ["malformed judge answer: m/d"]
    assert result.cost == pytest.approx(0.062)  # 2 translations at 0.001, 4 judge calls at 0.01, top judge 0.02


def test_a_top_judge_malformed_twice_leaves_the_panels_favourite_as_winner():
    standin = StandIn(
        translations={"m/a": ON_TABLE, "m/b": OVER_TABLE},
        panel={"m/c": {ON_TABLE: (3, 3), OVER_TABLE: (5, 5)}, "m/d": {ON_TABLE: (3, 3), OVER_TABLE: (4, 4)}},
        top_pick=ON_TABLE,
        garbled={"m/e": ['{"winner": "Z", "reason": "Z is best."}', "B"]},  # no label Z; not JSON
    )

    result = refine(BOOK, settings(top_judge="m/e"), standin)

    assert result.winner.text == OVER_TABLE
    assert result.top_judge_reason is None
    assert result.flags == ["malformed judge answer: m/e"]
    assert [k for k in standin.kinds() if k[0] == "top_judge"] == [("top_judge", "m/e")] * 2


ON_TOP_OF = "کتاب بر روی میز است."  # کتاب بر روی میز است.


@pytest.mark.parametrize("reference_scores, flags", [
    (((4, 4), (3, 3)), ["beats the native reference"]),  # best model 4.5 vs reference 3.5: 1 point
    (((4, 4), (4, 4)), []),  # best model 4.5 vs reference 4.0: half a point
])
def test_a_native_reference_is_always_the_output_and_flagged_when_beaten_by_a_point(reference_scores, flags):
    row = Row(id="1", source="The book is on the table.", existing=ON_TOP_OF, origin="native")
    standin = StandIn(
        translations={"m/a": ON_TABLE, "m/b": OVER_TABLE},
        panel={"m/c": {ON_TABLE: (5, 5), OVER_TABLE: (2, 2), ON_TOP_OF: reference_scores[0]},
               "m/d": {ON_TABLE: (4, 4), OVER_TABLE: (2, 2), ON_TOP_OF: reference_scores[1]}},
    )

    result = refine(row, settings(), standin)

    assert result.winner.text == ON_TOP_OF
    assert result.winner.authors == ("dataset",)
    assert all(len(call[3]) == 3 for call in standin.calls if call[0] == "judge")  # judged blind with the others
    assert "top_judge" not in [k for k, _ in standin.kinds()]
    assert result.flags == flags


@pytest.mark.parametrize("top_pick, replaced", [(ON_TABLE, True), (ON_TOP_OF, False)])
def test_an_unknown_origin_translation_is_an_ordinary_candidate_marked_replaced_when_it_loses(top_pick, replaced):
    row = Row(id="1", source="The book is on the table.", existing=ON_TOP_OF, origin="unknown")
    standin = StandIn(
        translations={"m/a": ON_TABLE, "m/b": OVER_TABLE},
        panel={judge: {ON_TABLE: (5, 5), OVER_TABLE: (2, 2), ON_TOP_OF: (5, 4)} for judge in ("m/c", "m/d")},
        top_pick=top_pick,
    )

    result = refine(row, settings(), standin)

    assert result.winner.text == top_pick
    assert result.replaced is replaced


@pytest.mark.parametrize("back, chrf, flags", [
    ("The book is on the table.", 100.0, []),
    ("Zzz qqq", 0.0, ["meaning may have changed"]),  # no letter in common with the source
])
def test_the_winner_is_back_translated_by_the_first_ai_model_that_didnt_write_it(back, chrf, flags):
    standin = StandIn(
        translations={"google-translate": OVER_TABLE, "m/a": ON_TABLE, "m/b": ON_TOP_OF},
        panel={judge: {ON_TABLE: (5, 5), OVER_TABLE: (3, 3), ON_TOP_OF: (4, 4)} for judge in ("m/c", "m/d")},
        top_pick=ON_TABLE,
        back={"m/b": back},
    )

    result = refine(BOOK, settings(translators=["google-translate", "m/a", "m/b"], back_translation=True), standin)

    assert [call for call in standin.calls if call[0] == "back_translate"] == [("back_translate", "m/b", ON_TABLE)]
    assert result.back_translation == back
    assert result.chrf == pytest.approx(chrf)
    assert result.flags == flags


@pytest.mark.parametrize("second_judges_meaning, flags", [(3, ["panel disagreement"]), (4, [])])
def test_judges_two_points_apart_on_the_winners_meaning_are_flagged(second_judges_meaning, flags):
    standin = StandIn(
        translations={"m/a": ON_TABLE, "m/b": OVER_TABLE},
        panel={"m/c": {ON_TABLE: (5, 5), OVER_TABLE: (2, 2)},
               "m/d": {ON_TABLE: (second_judges_meaning, 5), OVER_TABLE: (2, 2)}},
        top_pick=ON_TABLE,
    )

    assert refine(BOOK, settings(), standin).flags == flags


def test_a_translation_written_by_every_judge_is_scored_by_their_own_votes_and_flagged():
    standin = StandIn(
        translations={"google-translate": OVER_TABLE, "m/a": ON_TABLE, "m/b": ON_TABLE},
        panel={"m/a": {ON_TABLE: (5, 5), OVER_TABLE: (3, 3)}, "m/b": {ON_TABLE: (4, 4), OVER_TABLE: (3, 3)}},
        top_pick=ON_TABLE,
    )

    result = refine(BOOK, settings(translators=["google-translate", "m/a", "m/b"], judges=["m/a", "m/b"],
                                   top_judge="m/a"), standin)

    assert [c.text for c in result.shortlist] == [ON_TABLE, OVER_TABLE]  # own votes 4.5 against 3.0
    assert result.flags == ["scored only by its authors"]


def test_translators_and_judges_all_see_the_previous_two_sentences_of_a_conversation():
    row = Row(id="3", source="It's on the table.", existing=None, origin=None,
              context=("Where is my book?", "Which one?"))
    standin = StandIn(translations={"m/a": ON_TABLE, "m/b": OVER_TABLE},
                      panel={judge: {ON_TABLE: (5, 5), OVER_TABLE: (3, 3)} for judge in ("m/c", "m/d")},
                      top_pick=ON_TABLE)

    refine(row, settings(), standin)

    tasks = [call[2] for call in standin.calls if call[0] in ("translate", "judge", "top_judge")]
    assert len(tasks) == 5 and all(t.context == ("Where is my book?", "Which one?") for t in tasks)


def test_refining_again_through_the_cache_makes_no_calls_and_costs_nothing(tmp_path):
    standin = StandIn(
        translations={"m/a": ON_TABLE, "m/b": OVER_TABLE},
        panel={judge: {ON_TABLE: (5, 5), OVER_TABLE: (3, 3)} for judge in ("m/c", "m/d")},
        top_pick=ON_TABLE,
        back={"m/b": "The book is on the table."},
        garbled={"m/d": ["Not JSON."]},  # m/d's first answer is malformed; its second is fine
    )
    cache_file = tmp_path / "answers.sqlite"

    first = refine(BOOK, settings(back_translation=True), CachedConnection(standin, cache_file))
    calls_made = len(standin.calls)
    again = refine(BOOK, settings(back_translation=True), CachedConnection(standin, cache_file))  # as if restarted

    assert len(standin.calls) == calls_made == 7  # 2 translations, 3 judge calls, top judge, back-translation
    assert first.cost == pytest.approx(0.053)  # 0.002 + 0.03 + 0.02 + 0.001
    assert again.cost == 0
    assert (again.winner.text, again.flags, again.chrf) == (first.winner.text, first.flags, first.chrf)
    assert {c.text: c.scores for c in again.candidates} == {c.text: c.scores for c in first.candidates}


def test_changing_how_a_model_is_asked_misses_the_cache(tmp_path):
    standin = StandIn(translations={"m/a": ON_TABLE, "m/b": OVER_TABLE},
                      panel={judge: {ON_TABLE: (5, 5), OVER_TABLE: (3, 3)} for judge in ("m/c", "m/d")},
                      top_pick=ON_TABLE)
    cache_file = tmp_path / "answers.sqlite"
    refine(BOOK, settings(), CachedConnection(standin, cache_file))

    standin.fingerprint = "prompts v2"  # e.g. a translation prompt was reworded
    refine(BOOK, settings(), CachedConnection(standin, cache_file))

    assert len(standin.calls) == 2 * 5


def test_a_winner_written_by_every_ai_model_skips_the_double_check_with_a_note():
    standin = StandIn(translations={"google-translate": ON_TABLE, "m/a": ON_TABLE, "m/b": ON_TABLE},
                      panel={"m/a": {ON_TABLE: (5, 5)}, "m/b": {ON_TABLE: (5, 5)}}, top_pick=ON_TABLE)

    result = refine(BOOK, settings(translators=["google-translate", "m/a", "m/b"], judges=["m/a", "m/b"],
                                   top_judge="m/a", back_translation=True), standin)

    assert "back_translate" not in [k for k, _ in standin.kinds()]
    assert result.notes == ["double-check skipped: every AI model wrote it"]
    assert "meaning may have changed" not in result.flags


def test_a_translator_that_answers_with_nothing_is_left_out_with_a_note():
    standin = StandIn(translations={"m/a": ON_TABLE, "m/b": ""},  # m/b refuses silently
                      panel={judge: {ON_TABLE: (5, 5)} for judge in ("m/c", "m/d")}, top_pick=ON_TABLE)

    result = refine(BOOK, settings(), standin)

    assert [(c.text, c.authors) for c in result.candidates] == [(ON_TABLE, ("m/a",))]
    assert result.notes == ["no answer from m/b"]
    assert result.flags == []


def test_a_judge_that_answers_with_nothing_is_not_asked_again_and_has_no_vote_and_a_note():
    # A refusal is never repeated: in M6, repeated refused requests got the account blocked by Meta.
    standin = StandIn(translations={"m/a": ON_TABLE, "m/b": OVER_TABLE},
                      panel={judge: {ON_TABLE: (5, 5), OVER_TABLE: (3, 3)} for judge in ("m/c", "m/d")},
                      top_pick=ON_TABLE, garbled={"m/d": [""]})

    result = refine(BOOK, settings(), standin)

    assert [k for k in standin.kinds() if k == ("judge", "m/d")] == [("judge", "m/d")]  # asked once only
    assert {c.text: c.scores for c in result.candidates} == {ON_TABLE: {"m/c": (5, 5)}, OVER_TABLE: {"m/c": (3, 3)}}
    assert result.notes == ["no answer from m/d"]
    assert result.flags == []


def test_a_top_judge_that_answers_with_nothing_leaves_the_panels_favourite_with_a_note():
    standin = StandIn(translations={"m/a": ON_TABLE, "m/b": OVER_TABLE},
                      panel={judge: {ON_TABLE: (3, 3), OVER_TABLE: (5, 5)} for judge in ("m/c", "m/d")},
                      top_pick=ON_TABLE, garbled={"m/e": [""]})

    result = refine(BOOK, settings(top_judge="m/e"), standin)

    assert [k for k in standin.kinds() if k[0] == "top_judge"] == [("top_judge", "m/e")]  # asked once only
    assert result.winner.text == OVER_TABLE
    assert result.notes == ["no answer from m/e"]
    assert result.flags == []


def test_a_double_check_model_that_answers_with_nothing_passes_to_the_next_ai_model():
    standin = StandIn(translations={"m/a": ON_TABLE, "m/b": OVER_TABLE, "m/x": OVER_TABLE},
                      panel={judge: {ON_TABLE: (5, 5), OVER_TABLE: (3, 3)} for judge in ("m/c", "m/d")},
                      top_pick=ON_TABLE, back={"m/b": "", "m/x": "The book is on the table."})

    result = refine(BOOK, settings(translators=["m/a", "m/b", "m/x"], back_translation=True), standin)

    assert [k for k in standin.kinds() if k[0] == "back_translate"] == [("back_translate", "m/b"),
                                                                       ("back_translate", "m/x")]
    assert (result.back_translation, result.chrf) == ("The book is on the table.", pytest.approx(100.0))
    assert result.notes == ["no answer from m/b"]


def test_a_single_candidate_wins_without_asking_any_judge():
    standin = StandIn(translations={"google-translate": ON_TABLE}, panel={}, back={})

    result = refine(BOOK, settings(translators=["google-translate"], judges=["m/c"], top_judge="m/c"), standin)

    assert standin.kinds() == [("translate", "google-translate")]
    assert result.winner.text == ON_TABLE
    assert result.flags == []


def test_with_no_other_ai_translator_the_first_judge_that_didnt_write_it_double_checks():
    standin = StandIn(translations={"google-translate": ON_TABLE}, panel={},
                      back={"m/c": "The book is on the table."})

    result = refine(BOOK, settings(translators=["google-translate"], judges=["m/c"], top_judge="m/c",
                                   back_translation=True), standin)

    assert standin.kinds() == [("translate", "google-translate"), ("back_translate", "m/c")]
    assert result.chrf == pytest.approx(100.0)
    assert result.notes == []


def test_rewording_one_kind_of_request_re_asks_only_that_kind(tmp_path):
    standin = StandIn(translations={"m/a": ON_TABLE, "m/b": OVER_TABLE},
                      panel={judge: {ON_TABLE: (5, 5), OVER_TABLE: (3, 3)} for judge in ("m/c", "m/d")},
                      top_pick=ON_TABLE)
    standin.fingerprints = {"translate": "t1", "judge": "j1", "top_judge": "tj1", "back_translate": "b1"}
    cache_file = tmp_path / "answers.sqlite"
    refine(BOOK, settings(), CachedConnection(standin, cache_file))

    standin.fingerprints["judge"] = "j2"  # the panel judges' instructions were reworded
    refine(BOOK, settings(), CachedConnection(standin, cache_file))

    assert standin.kinds()[5:] == [("judge", "m/c"), ("judge", "m/d")]


def test_the_double_check_ignores_capitals_and_punctuation():
    # MIZAN's heading: same words, but in capitals and without the full stop. Case-sensitive chrF gave it 1.2.
    row = Row(id="1", source="SAME SPECIES, DIFFERENT WORLDS", existing=None, origin=None)
    standin = StandIn(translations={"m/a": ON_TABLE, "m/b": OVER_TABLE},
                      panel={judge: {ON_TABLE: (5, 5), OVER_TABLE: (3, 3)} for judge in ("m/c", "m/d")},
                      top_pick=ON_TABLE, back={"m/b": "Same species, different worlds."})

    result = refine(row, settings(back_translation=True), standin)

    assert result.chrf == pytest.approx(100.0)
    assert result.flags == []


@pytest.mark.parametrize("source, tidied", [
    ("SAME SPECIES, DIFFERENT WORLDS", "Same species, different worlds"),  # a heading in capitals
    ("' 'I hate to do this to you, Dorothy", "I hate to do this to you, Dorothy"),  # stray quote marks
])
def test_a_tidied_source_is_what_gets_translated_judged_and_kept(source, tidied):
    standin = StandIn(translations={"m/a": ON_TABLE, "m/b": OVER_TABLE},
                      panel={judge: {ON_TABLE: (5, 5), OVER_TABLE: (3, 3)} for judge in ("m/c", "m/d")},
                      top_pick=ON_TABLE, tidied={source: tidied})

    result = refine(Row(id="1", source=source, existing=None, origin=None), settings(tidy_model="m/t"), standin)

    assert standin.kinds()[0] == ("tidy", "m/t")
    assert {call[2].text for call in standin.calls if call[0] in ("translate", "judge", "top_judge")} == {tidied}
    assert result.source == tidied
    assert result.notes == ["source tidied"]


def test_a_tidy_up_that_changes_a_word_is_rejected_and_the_original_kept():
    source = "he squeaked."
    standin = StandIn(translations={"m/a": ON_TABLE, "m/b": OVER_TABLE},
                      panel={judge: {ON_TABLE: (5, 5), OVER_TABLE: (3, 3)} for judge in ("m/c", "m/d")},
                      top_pick=ON_TABLE, tidied={source: "He squealed."})  # "squeaked" became "squealed"

    result = refine(Row(id="1", source=source, existing=None, origin=None), settings(tidy_model="m/t"), standin)

    assert result.source == source
    assert {call[2].text for call in standin.calls if call[0] == "translate"} == {source}
    assert result.notes == ["tidy-up rejected: it changed words"]


def test_without_a_tidy_model_no_tidy_up_is_asked():
    standin = StandIn(translations={"m/a": ON_TABLE, "m/b": OVER_TABLE},
                      panel={judge: {ON_TABLE: (5, 5), OVER_TABLE: (3, 3)} for judge in ("m/c", "m/d")},
                      top_pick=ON_TABLE)

    result = refine(BOOK, settings(), standin)

    assert "tidy" not in [k for k, _ in standin.kinds()]
    assert result.source == BOOK.source


def test_back_translation_can_be_turned_off():
    standin = StandIn(translations={"m/a": ON_TABLE, "m/b": OVER_TABLE},
                      panel={judge: {ON_TABLE: (5, 5), OVER_TABLE: (3, 3)} for judge in ("m/c", "m/d")},
                      top_pick=ON_TABLE)

    result = refine(BOOK, settings(back_translation=False), standin)

    assert "back_translate" not in [k for k, _ in standin.kinds()]
    assert (result.back_translation, result.chrf) == (None, None)
