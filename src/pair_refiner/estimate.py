"""What a sentence will cost, before spending anything (BUILD.md, "Money"): model prices times the measured
average answer lengths. Before any run has measured them, a stated rough guess."""

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from pair_refiner.connection import GOOGLE_TRANSLATE, Model
from pair_refiner.dataset import Row
from pair_refiner.live import GOOGLE_PRICE_PER_CHARACTER
from pair_refiner.refine import RefineSettings

# The rough guess, as (input tokens, output tokens with thinking), used until the cache has measured a call.
ROUGH_TOKENS = {"translate": (250, 280), "judge": (700, 500), "top_judge": (500, 300), "back_translate": (150, 260)}


@dataclass
class Estimator:
    prices: dict[str, tuple[float, float]]  # model -> (input, output) USD per million tokens
    lengths: dict[tuple[str, str], tuple[int, int]] = field(default_factory=dict)  # (kind, model) -> tokens

    def sentence_cost(self, row: Row, settings: RefineSettings) -> float:
        """One sentence in one register: every translation, every judge, the top judge and the double-check."""
        cost = 0.0
        for model in settings.translators:
            if model == GOOGLE_TRANSLATE:
                cost += len(row.source) * GOOGLE_PRICE_PER_CHARACTER
            else:
                cost += self._call("translate", model)
        if len(settings.translators) + bool(row.existing) > 1:  # one candidate: nothing to judge (docs/adr/0005)
            cost += sum(self._call("judge", judge) for judge in settings.judges)
            if row.origin != "native":
                cost += self._call("top_judge", settings.top_judge)
        if settings.back_translation:  # who checks depends on who wins; the first AI translator or judge is the guess
            checker = next((m for m in settings.translators + settings.judges if m != GOOGLE_TRANSLATE), None)
            cost += self._call("back_translate", checker) if checker else 0.0
        return cost

    def _call(self, kind: str, model: str) -> float:
        input_tokens, output_tokens = self.lengths.get((kind, model), ROUGH_TOKENS[kind])
        input_price, output_price = self.prices[model]
        return (input_tokens * input_price + output_tokens * output_price) / 1_000_000

    @property
    def measured(self) -> bool:
        return bool(self.lengths)


def from_cache(models: list[Model], cache: Path) -> Estimator:
    """Today's OpenRouter prices and the average answer lengths of every call stored in the cache."""
    lengths = {}
    if cache.exists():
        db = sqlite3.connect(cache)
        rows = db.execute("SELECT kind, model, AVG(input_tokens), AVG(output_tokens) FROM answers "
                          "WHERE model != ? GROUP BY kind, model", (GOOGLE_TRANSLATE,)).fetchall()
        lengths = {(kind, model): (round(i), round(o)) for kind, model, i, o in rows}
    return Estimator({m.id: (m.input_price, m.output_price) for m in models}, lengths)
