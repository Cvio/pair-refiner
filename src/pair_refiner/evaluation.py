"""Seam 5: the test run (BUILD.md, M6; docs/adr/0004). Sentences with reference translations measure each
translator, each judge and the ensemble, and recommend the top judge and the back-translation threshold."""

import math
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace

import sacrebleu

from pair_refiner import persian
from pair_refiner.connection import Connection
from pair_refiner.dataset import DatasetSettings, Row
from pair_refiner.refine import Candidate, RefineSettings, Result, refine
from pair_refiner.run import RunSettings, refine_settings

# For scoring only: Persian and Arabic-Indic digits count as Western ones.
_DIGITS = str.maketrans({**{chr(0x06F0 + n): str(n) for n in range(10)}, **{chr(0x0660 + n): str(n) for n in range(10)}})


@dataclass(frozen=True)
class Reference:
    row: Row
    reference: str  # the professional translation


@dataclass
class EvaluationReport:
    translator_chrf: dict[str, float]  # corpus chrF against the references
    judge_accuracy: dict[str, float]  # share of sentences whose closest candidate was the judge's first choice
    top_judge: str  # recommended
    ensemble_chrf: float  # the winners' corpus chrF, with the recommended top judge
    best_translator: str
    best_translator_chrf: float
    ensemble_beats_best: bool
    threshold: float | None  # recommended back-translation chrF threshold
    flag_share: float | None  # share of sentences that threshold flags
    cost: float = 0.0
    details: list[tuple[Reference, Result]] = field(default_factory=list)


def evaluate(items: list[Reference], dataset: DatasetSettings, settings: RunSettings,
             connection: Connection, workers: int = 1) -> EvaluationReport:
    target = dataset.target_lang

    def refine_all(chosen: RefineSettings) -> list[tuple[Reference, Result]]:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            return list(zip(items, pool.map(lambda item: refine(item.row, chosen, connection), items)))

    # First pass: the translations and the panel. Its top judge is a stand-in for the one being chosen, so no
    # back-translations are paid for its winners.
    first = refine_all(refine_settings(dataset, replace(settings, back_translation=False), "written"))
    references = [_scoring(item.reference, target) for item in items]

    translator_chrf = {}
    for model in settings.translators:
        texts = [_scoring(next(c.text for c in result.candidates if model in c.authors), target) for _, result in first]
        translator_chrf[model] = sacrebleu.corpus_chrf(texts, [references]).score

    judge_accuracy = {judge: sum(_judge_was_right(judge, item, result, target) for item, result in first) / len(first)
                      for judge in settings.judges}
    top_judge = max(settings.judges, key=lambda judge: judge_accuracy[judge])  # list order breaks a tie

    # The ensemble: refined again with the recommended top judge. Translations and the panel come from the cache.
    final = refine_all(refine_settings(dataset, replace(settings, top_judge=top_judge), "written"))
    ensemble_chrf = sacrebleu.corpus_chrf([_scoring(r.winner.text, target) for _, r in final], [references]).score
    best = max(settings.translators, key=lambda model: translator_chrf[model])

    threshold, flag_share = _threshold(final, target)
    return EvaluationReport(
        translator_chrf, judge_accuracy, top_judge, ensemble_chrf, best, translator_chrf[best],
        ensemble_chrf > translator_chrf[best], threshold, flag_share,
        cost=sum(r.cost for _, r in first + final), details=final)


def _threshold(final: list[tuple[Reference, Result]], lang: str) -> tuple[float | None, float | None]:
    """The back-translation chrF threshold that best catches the truly bad winners (the worst tenth against the
    reference, at least one) while flagging few good ones: the highest F1, the lower threshold on a tie. Also the
    share of sentences it flags. (None, None) without back-translations to compare."""
    checked = [(r.chrf, _sentence_chrf(r.winner.text, item.reference, lang)) for item, r in final if r.chrf is not None]
    values = sorted({back for back, _ in checked})
    if len(values) < 2:
        return None, None
    worst_first = sorted(range(len(checked)), key=lambda i: checked[i][1])
    bad = set(worst_first[: max(1, math.ceil(len(checked) / 10))])
    best_f1, best = -1.0, None
    for low, high in zip(values, values[1:]):
        threshold = (low + high) / 2
        flagged = {i for i, (back, _) in enumerate(checked) if back < threshold}
        caught = len(flagged & bad)
        f1 = 2 * caught / (len(flagged) + len(bad))
        if f1 > best_f1:
            best_f1, best = f1, (threshold, len(flagged) / len(checked))
    return best


def _scoring(text: str, lang: str) -> str:
    return persian.tidy_if_persian(text, lang).translate(_DIGITS)


def _sentence_chrf(text: str, reference: str, lang: str) -> float:
    return sacrebleu.sentence_chrf(_scoring(text, lang), [_scoring(reference, lang)]).score


def _judge_was_right(judge: str, item: Reference, result: Result, lang: str) -> bool:
    """Whether the judge's first choice (its highest score, own candidate included) was the candidate closest to
    the reference. Ties on either side count as right if they overlap; no vote counts as wrong."""
    votes = {id(c): _vote(c, judge) for c in result.candidates}
    if not any(votes.values()):
        return False
    best_vote = max(v for v in votes.values() if v)
    chosen = {id(c) for c in result.candidates if votes[id(c)] == best_vote}
    closeness = {id(c): _sentence_chrf(c.text, item.reference, lang) for c in result.candidates}
    closest = {key for key, value in closeness.items() if value == max(closeness.values())}
    return bool(chosen & closest)


def _vote(candidate: Candidate, judge: str) -> tuple[int, int] | None:
    return candidate.scores.get(judge) or candidate.own_scores.get(judge)
