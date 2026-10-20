"""Seam 8: the live check. Talks to the real services; run by hand with `uv run pytest -m live`.
The refining check costs about $0.20."""

import tomllib
from pathlib import Path

import pytest

from pair_refiner.cache import CachedConnection
from pair_refiner.connection import GOOGLE_TRANSLATE, OpenRouter
from pair_refiner.dataset import Row
from pair_refiner.live import LiveConnection, load_keys
from pair_refiner.refine import RefineSettings, refine

pytestmark = pytest.mark.live
REPO = Path(__file__).parent.parent


class Recording:
    """Passes calls to the live connection and keeps every answer, to check its shape."""

    def __init__(self, connection):
        self.connection, self.fingerprint, self.answers = connection, connection.fingerprint, []

    def __getattr__(self, kind):
        def call(model, *args):
            answer = getattr(self.connection, kind)(model, *args)
            self.answers.append((kind, model, answer))
            return answer
        return call


def test_three_real_sentences_have_the_shape_the_standin_assumes(tmp_path):
    with open(REPO / "defaults.toml", "rb") as f:
        models = tomllib.load(f)["panel"]
    live = Recording(LiveConnection(load_keys(REPO / "keys.toml")))
    connection = CachedConnection(live, tmp_path / "answers.sqlite")  # empty: every answer is fresh
    settings = RefineSettings(source_lang="en", target_lang="fa", register="written",
                              translators=models["translators"], judges=models["judges"],
                              top_judge=models["judges"][0], back_translation=True)
    sentences = ["The book is on the table.", "Where is the train station?", "I'll call you tomorrow."]

    results = [refine(Row(id=str(n), source=s, existing=None, origin=None), settings, connection)
               for n, s in enumerate(sentences, 1)]

    for result in results:
        assert result.winner.text
        assert not [f for f in result.flags if f.startswith("malformed")], result.flags
        assert result.chrf is not None or result.notes == ["double-check skipped: every AI model wrote it"]
    for kind, model, answer in live.answers:
        assert answer.text, (kind, model)
        assert answer.cost > 0, (kind, model)
        if model != GOOGLE_TRANSLATE:
            assert answer.input_tokens > 0 and answer.output_tokens > 0, (kind, model)
    print(f"\nlive check: {len(live.answers)} calls, ${sum(r.cost for r in results):.4f}")


def test_balance_reads_the_openrouter_credits_with_the_management_key():
    balance = LiveConnection(load_keys(REPO / "keys.toml")).balance()

    assert isinstance(balance, float) and balance >= 0


def test_list_models_reads_openrouter_prices_and_settings():
    models = {m.id: m for m in OpenRouter().list_models()}

    # As seen on OpenRouter on 2026-10-18 (docs/adr/0001).
    opus = models["anthropic/claude-opus-5.5"]
    assert opus.maker == "anthropic"
    assert opus.name == "Anthropic: Claude Opus 5.5"
    assert opus.input_price > 0 and opus.output_price > opus.input_price  # USD per million tokens
    assert opus.accepts_temperature is False
    assert opus.lowest_effort == "low"

    assert models["deepseek/deepseek-v4.1-flash-1017"].accepts_temperature is True
    assert models["deepseek/deepseek-v4.1-flash-1017"].lowest_effort == "none"
    assert models["meta/muse-spark-1.3"].lowest_effort == "minimal"
    assert models["meta-llama/llama-4-maverick"].lowest_effort is None
    assert models["meta-llama/llama-4-maverick"].maker == "meta"

    # Batch variants and image makers aren't usable for this pipeline.
    assert "anthropic/claude-opus-5.5:batch" not in models
    assert "google/gemini-nano-banana-2.1" not in models
