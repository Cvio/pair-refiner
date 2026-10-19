"""Seam 2: the model connection. The only code that talks to OpenRouter or Google."""

from dataclasses import dataclass
from typing import Protocol

import httpx

OPENROUTER_API = "https://openrouter.ai/api/v1"

# Cheapest first (docs/adr/0001).
EFFORTS = ["none", "minimal", "low", "medium", "high", "xhigh", "max"]

# OpenRouter's maker prefixes, mapped to the maker names the tool uses.
MAKERS = {"meta-llama": "meta"}


@dataclass(frozen=True)
class Model:
    id: str
    name: str
    maker: str
    created: int
    input_price: float  # USD per million tokens
    output_price: float  # USD per million tokens
    accepts_temperature: bool
    lowest_effort: str | None  # None: the model takes no reasoning setting


GOOGLE_TRANSLATE = "google-translate"  # translates, can't judge


@dataclass(frozen=True)
class Answer:
    text: str  # a translation, or a judge's JSON exactly as it came back
    cost: float  # USD, as the service reported it


@dataclass(frozen=True)
class Task:
    """What every call is about: one sentence and how it is to be translated."""
    text: str
    source_lang: str
    target_lang: str
    register: str  # "written" or "spoken"; only Persian uses it
    context: tuple[str, ...] = ()  # the previous two original sentences of its conversation


class Connection(Protocol):
    """Seam 2. Judges answer in JSON:
    judge:     {"scores": {"A": {"meaning": 1-5, "naturalness": 1-5}, ...}, "ranking": ["A", ...], "reason": "..."}
    top_judge: {"winner": "A", "reason": "..."}
    """

    def translate(self, model: str, task: Task) -> Answer: ...

    def judge(self, model: str, task: Task, candidates: dict[str, str]) -> Answer: ...

    def top_judge(self, model: str, task: Task, candidates: dict[str, str]) -> Answer: ...

    def back_translate(self, model: str, text: str, source_lang: str, target_lang: str) -> Answer: ...


class OpenRouter:
    def list_models(self) -> list[Model]:
        response = httpx.get(f"{OPENROUTER_API}/models", timeout=30)
        response.raise_for_status()
        return [
            _model(entry)
            for entry in response.json()["data"]
            if ":" not in entry["id"] and entry["architecture"]["output_modalities"] == ["text"]
        ]


def _model(entry: dict) -> Model:
    prefix = entry["id"].split("/")[0]
    efforts = (entry.get("reasoning") or {}).get("supported_efforts") or []
    return Model(
        id=entry["id"],
        name=entry["name"],
        maker=MAKERS.get(prefix, prefix),
        created=entry["created"],
        input_price=float(entry["pricing"]["prompt"]) * 1_000_000,
        output_price=float(entry["pricing"]["completion"]) * 1_000_000,
        accepts_temperature="temperature" in entry["supported_parameters"],
        lowest_effort=next((e for e in EFFORTS if e in efforts), None),
    )
