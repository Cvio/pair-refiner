"""Seam 8: the live check. Talks to the real services; run by hand with `uv run pytest -m live`."""

import pytest

from pair_refiner.connection import OpenRouter

pytestmark = pytest.mark.live


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
