"""Shared test helpers: the stand-in for the model connection (seam 2), the only stand-in in the tests."""

import json
from dataclasses import dataclass, field

from pair_refiner.connection import Answer, Task

PRICES = {"translate": 0.001, "judge": 0.01, "top_judge": 0.02, "back_translate": 0.001}


@dataclass
class StandIn:
    """Replays prepared answers. Judges' scores are prepared per candidate *text*, so a test never needs to
    know which blind label a candidate got. Every call is recorded in `calls`; each costs PRICES[kind]."""

    translations: dict[str, str | dict[str, str]] = field(default_factory=dict)  # model -> text, or source -> text
    panel: dict[str, dict[str, tuple[int, int]]] = field(default_factory=dict)  # judge -> text -> (meaning, naturalness)
    top_pick: str | set[str] | None = None  # the text the top judge picks (whichever of the set is shown)
    back: dict[str, str | dict[str, str]] = field(default_factory=dict)  # model -> text, or winner text -> text
    garbled: dict[str, list[str]] = field(default_factory=dict)  # model -> raw answers it gives before a good one
    calls: list[tuple] = field(default_factory=list)  # answered calls only
    fingerprint: str = "standin"
    fingerprints: dict[str, str] = field(default_factory=dict)  # per kind of request; overrides `fingerprint`

    def fingerprint_for(self, kind: str) -> str:
        return self.fingerprints.get(kind, self.fingerprint)
    fail_after: int | None = None  # the connection is lost once this many calls have been answered
    balance_left: float | None = 10.0  # the OpenRouter balance; None: no management key
    models: list = field(default_factory=list)  # what list_models returns

    def balance(self) -> float:
        if self.balance_left is None:
            raise LookupError("no management key")
        return self.balance_left

    def list_models(self) -> list:
        return self.models

    def _check(self) -> None:
        if self.fail_after is not None and len(self.calls) >= self.fail_after:
            raise ConnectionError("the connection was lost")

    def _answer(self, kind: str, model: str, good: str) -> Answer:
        queue = self.garbled.get(model, [])
        return Answer(queue.pop(0) if queue else good, PRICES[kind])

    def translate(self, model: str, task: Task) -> Answer:
        self._check()
        self.calls.append(("translate", model, task))
        prepared = self.translations[model]
        return self._answer("translate", model, prepared if isinstance(prepared, str) else prepared[task.text])

    def judge(self, model: str, task: Task, candidates: dict[str, str], attempt: int = 1) -> Answer:
        self._check()
        self.calls.append(("judge", model, task, dict(candidates)))
        scores = {label: self.panel[model][text] for label, text in candidates.items()}
        good = json.dumps({
            "scores": {label: {"meaning": m, "naturalness": n} for label, (m, n) in scores.items()},
            "ranking": sorted(scores, key=lambda label: scores[label], reverse=True),
            "reason": f"{model} scored them.",
        })
        return self._answer("judge", model, good)

    def top_judge(self, model: str, task: Task, candidates: dict[str, str], attempt: int = 1) -> Answer:
        self._check()
        self.calls.append(("top_judge", model, task, dict(candidates)))
        picks = {self.top_pick} if isinstance(self.top_pick, str) else self.top_pick
        winner = next(label for label, text in candidates.items() if text in picks)
        return self._answer("top_judge", model, json.dumps({"winner": winner, "reason": "It reads best."}))

    def back_translate(self, model: str, text: str, source_lang: str, target_lang: str) -> Answer:
        self._check()
        self.calls.append(("back_translate", model, text))
        prepared = self.back[model]
        return Answer(prepared if isinstance(prepared, str) else prepared[text], PRICES["back_translate"])

    def kinds(self) -> list[tuple[str, str]]:
        return [(call[0], call[1]) for call in self.calls]
