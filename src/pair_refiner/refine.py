"""Seam 3: refining one sentence (BUILD.md, "Picking the winner"; docs/adr/0002)."""

import hashlib
import json
import random
from dataclasses import dataclass, field
from string import ascii_uppercase

import sacrebleu

from pair_refiner import persian
from pair_refiner.connection import GOOGLE_TRANSLATE, Connection, Task
from pair_refiner.dataset import Row


@dataclass(frozen=True)
class RefineSettings:
    source_lang: str
    target_lang: str
    register: str
    translators: list[str]
    judges: list[str]
    top_judge: str
    shortlist_size: int = 3
    back_translation: bool = True
    chrf_threshold: float = 40.0


@dataclass
class Candidate:
    text: str
    authors: tuple[str, ...]
    scores: dict[str, tuple[int, int]] = field(default_factory=dict)  # judge -> (meaning, naturalness), kept votes
    own_scores: dict[str, tuple[int, int]] = field(default_factory=dict)  # votes by its own authors, discarded

    @property
    def scored_only_by_authors(self) -> bool:
        return not self.scores and bool(self.own_scores)

    @property
    def panel_score(self) -> tuple[float, float]:
        """(mean meaning, mean naturalness) over the kept votes. When every judge wrote it, its authors' own votes
        are used (docs/adr/0002); with no votes at all, (0, 0)."""
        votes = list((self.own_scores if self.scored_only_by_authors else self.scores).values())
        if not votes:
            return (0.0, 0.0)
        return (sum(m for m, _ in votes) / len(votes), sum(n for _, n in votes) / len(votes))


@dataclass
class Result:
    candidates: list[Candidate]
    shortlist: list[Candidate]  # best first by panel score
    winner: Candidate
    top_judge_reason: str | None
    flags: list[str]
    cost: float
    replaced: bool = False  # the dataset's own translation (origin "unknown") lost
    back_translation: str | None = None  # the winner translated back into the source language
    chrf: float | None = None  # 0-100: how closely the back-translation matches the source
    notes: list[str] = field(default_factory=list)  # worth knowing, not a warning


DATASET = "dataset"  # the author of a dataset's own translation


def refine(row: Row, settings: RefineSettings, connection: Connection) -> Result:
    calls = _Calls(connection)
    task = Task(row.source, settings.source_lang, settings.target_lang, settings.register, row.context)
    candidates, reference = _candidates(row, settings, task, calls)
    _panel(candidates, settings, task, calls)
    shortlist = sorted(candidates, key=lambda c: c.panel_score, reverse=True)[: settings.shortlist_size]

    reason = None
    if row.origin == "native":  # the reference is always the output; no top judge (docs/adr/0002)
        winner = reference
        best = max((c for c in candidates if c is not reference), key=lambda c: c.panel_score, default=reference)
        if best.panel_score[0] - reference.panel_score[0] >= 1:
            calls.flags.append("beats the native reference")
    else:
        winner, reason = _top_judge(shortlist, settings, task, calls)
    meanings = [m for m, _ in winner.scores.values()]
    if meanings and max(meanings) - min(meanings) >= 2:  # docs/adr/0002
        calls.flags.append("panel disagreement")
    replaced = reference is not None and winner is not reference
    back, chrf = _back_translate(winner, row, settings, calls) if settings.back_translation else (None, None)
    return Result(candidates, shortlist, winner, reason, calls.flags, calls.cost, replaced, back, chrf, calls.notes)


class _Calls:
    """The connection, with the running cost and the flags raised so far."""

    def __init__(self, connection: Connection):
        self.connection, self.cost, self.flags, self.notes = connection, 0.0, [], []

    def __call__(self, kind: str, *args) -> str:
        answer = getattr(self.connection, kind)(*args)
        self.cost += answer.cost
        return answer.text


def _candidates(row: Row, settings: RefineSettings, task: Task, calls: _Calls) -> tuple[list[Candidate], Candidate | None]:
    """Each translator's version, and the dataset's own translation if it has one (returned again as the
    reference). Identical texts merge into one candidate with all their authors."""
    by_text: dict[str, Candidate] = {}

    def add(text: str, author: str) -> Candidate:
        if text in by_text:
            by_text[text].authors += (author,)
        else:
            by_text[text] = Candidate(text, (author,))
        return by_text[text]

    for model in settings.translators:
        text = persian.tidy_if_persian(calls("translate", model, task), settings.target_lang)
        if text:
            add(text, model)
        else:  # a silent refusal: carry on without it (docs/adr/0002)
            calls.notes.append(f"no answer from {model}")
    reference = add(row.existing, DATASET) if row.existing else None
    return list(by_text.values()), reference


def _panel(candidates: list[Candidate], settings: RefineSettings, task: Task, calls: _Calls) -> None:
    """Every judge scores every candidate, blind. Its votes for its own model's candidate are discarded."""
    labelled = _blind(candidates, task, "panel")
    shown = {label: c.text for label, c in labelled.items()}
    for judge in settings.judges:
        vote, refused = _ask_twice(lambda attempt: calls("judge", judge, task, shown, attempt),
                                   lambda raw: _panel_vote(raw, shown))
        if vote is None:
            _no_vote(judge, refused, calls)
            continue
        for label, score in vote.items():
            candidate = labelled[label]
            (candidate.own_scores if judge in candidate.authors else candidate.scores)[judge] = score
    if any(c.scored_only_by_authors for c in candidates):
        calls.flags.append("scored only by its authors")


def _top_judge(shortlist: list[Candidate], settings: RefineSettings, task: Task,
               calls: _Calls) -> tuple[Candidate, str | None]:
    """The top judge's pick from the shortlist, blind with fresh labels, and its reason."""
    blind = _blind(shortlist, task, "top")
    shown = {label: c.text for label, c in blind.items()}
    pick, refused = _ask_twice(lambda attempt: calls("top_judge", settings.top_judge, task, shown, attempt),
                               lambda raw: _top_pick(raw, shown))
    if pick is None:  # the panel's favourite wins (docs/adr/0002)
        _no_vote(settings.top_judge, refused, calls)
        return shortlist[0], None
    winner = blind[pick[0]]
    if settings.top_judge in winner.authors and winner is not shortlist[0]:
        calls.flags.append("top judge chose its own")
    return winner, pick[1]


def _back_translate(winner: Candidate, row: Row, settings: RefineSettings,
                    calls: _Calls) -> tuple[str | None, float | None]:
    """The winner translated back by the first AI translator that didn't write it (docs/adr/0002), and its chrF
    against the source. Flags the row when the chrF is below the threshold."""
    checkers = [m for m in settings.translators if m != GOOGLE_TRANSLATE and m not in winner.authors]
    if not checkers:  # every AI model wrote it: that agreement is the check (docs/adr/0002)
        calls.notes.append("double-check skipped: every AI model wrote it")
        return None, None
    for model in checkers:
        back = persian.tidy_if_persian(
            calls("back_translate", model, winner.text, settings.target_lang, settings.source_lang),
            settings.source_lang)
        if back:
            break
        calls.notes.append(f"no answer from {model}")  # a silent refusal: the next AI model checks instead
    else:
        return None, None
    chrf = sacrebleu.sentence_chrf(back, [row.source]).score
    if chrf < settings.chrf_threshold:
        calls.flags.append("meaning may have changed")
    return back, chrf


def _ask_twice(ask, parse):
    """A malformed answer is asked for once more. Returns (parsed or None, whether both answers were empty)."""
    empty = True
    for attempt in (1, 2):
        raw = ask(attempt)
        parsed = parse(raw)
        if parsed is not None:
            return parsed, False
        empty = empty and not raw.strip()
    return None, empty


def _no_vote(judge: str, refused: bool, calls: _Calls) -> None:
    """A judge with no usable answer: a note if it silently refused (docs/adr/0002), a flag if it was malformed."""
    if refused:
        calls.notes.append(f"no answer from {judge}")
    else:
        calls.flags.append(f"malformed judge answer: {judge}")


def _top_pick(raw: str, shown: dict[str, str]) -> tuple[str, str] | None:
    """The top judge's (winner label, reason), or None if the answer isn't the agreed JSON."""
    try:
        answer = json.loads(raw)
        pick = (answer["winner"], answer["reason"])
    except (ValueError, TypeError, KeyError):
        return None
    return pick if pick[0] in shown and isinstance(pick[1], str) else None


def _panel_vote(raw: str, shown: dict[str, str]) -> dict[str, tuple[int, int]] | None:
    """A panel judge's {label: (meaning, naturalness)}, or None if the answer isn't the agreed JSON: a score from
    1 to 5 for every label shown and no other, a ranking of exactly those labels, and a reason."""
    try:
        answer = json.loads(raw)
        scores = answer["scores"]
        vote = {label: (scores[label]["meaning"], scores[label]["naturalness"]) for label in shown}
        valid = (set(scores) == set(shown) and sorted(answer["ranking"]) == sorted(shown)
                 and isinstance(answer["reason"], str)
                 and all(type(s) is int and 1 <= s <= 5 for pair in vote.values() for s in pair))
    except (ValueError, TypeError, KeyError):
        return None
    return vote if valid else None


def _blind(candidates: list[Candidate], task: Task, stage: str) -> dict[str, Candidate]:
    """The candidates under labels A, B, C... in an order shuffled per sentence. The shuffle is seeded from the
    sentence, so a re-run sends the same prompt and hits the cache."""
    seed = hashlib.sha256("\n".join([stage, task.text, task.target_lang, task.register]).encode()).digest()
    order = list(candidates)
    random.Random(seed).shuffle(order)
    return dict(zip(ascii_uppercase, order))
