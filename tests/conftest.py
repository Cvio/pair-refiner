"""Shared test helpers: the stand-in for the model connection (seam 2), the only stand-in in the tests."""

import json
from dataclasses import dataclass, field

from pair_refiner.connection import Answer, Task

PRICES = {"translate": 0.001, "judge": 0.01, "top_judge": 0.02, "back_translate": 0.001}


@dataclass
class StandIn:
    """Replays prepared answers. Judges' scores are prepared per candidate *text*, so a test never needs to
    know which blind label a candidate got. Every call is recorded in `calls`; each costs PRICES[kind]."""

    translations: dict[str, str] = field(default_factory=dict)  # model -> its translation
    panel: dict[str, dict[str, tuple[int, int]]] = field(default_factory=dict)  # judge -> text -> (meaning, naturalness)
    top_pick: str | None = None  # the text the top judge picks
    back: dict[str, str] = field(default_factory=dict)  # model -> its back-translation
    garbled: dict[str, list[str]] = field(default_factory=dict)  # model -> raw answers it gives before a good one
    calls: list[tuple] = field(default_factory=list)

    def _answer(self, kind: str, model: str, good: str) -> Answer:
        queue = self.garbled.get(model, [])
        return Answer(queue.pop(0) if queue else good, PRICES[kind])

    def translate(self, model: str, task: Task) -> Answer:
        self.calls.append(("translate", model, task))
        return self._answer("translate", model, self.translations[model])

    def judge(self, model: str, task: Task, candidates: dict[str, str]) -> Answer:
        self.calls.append(("judge", model, task, dict(candidates)))
        scores = {label: self.panel[model][text] for label, text in candidates.items()}
        good = json.dumps({
            "scores": {label: {"meaning": m, "naturalness": n} for label, (m, n) in scores.items()},
            "ranking": sorted(scores, key=lambda label: scores[label], reverse=True),
            "reason": f"{model} scored them.",
        })
        return self._answer("judge", model, good)

    def top_judge(self, model: str, task: Task, candidates: dict[str, str]) -> Answer:
        self.calls.append(("top_judge", model, task, dict(candidates)))
        winner = next(label for label, text in candidates.items() if text == self.top_pick)
        return self._answer("top_judge", model, json.dumps({"winner": winner, "reason": "It reads best."}))

    def back_translate(self, model: str, text: str, source_lang: str, target_lang: str) -> Answer:
        self.calls.append(("back_translate", model, text))
        return Answer(self.back[model], PRICES["back_translate"])

    def kinds(self) -> list[tuple[str, str]]:
        return [(call[0], call[1]) for call in self.calls]
