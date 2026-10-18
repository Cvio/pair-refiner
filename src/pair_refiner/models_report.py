"""M1: print each maker's current top models, their prices, and a rough cost per 1,000 sentences.

Run with: uv run python -m pair_refiner.models_report
"""

from pair_refiner.connection import Model, OpenRouter

MAKERS = ["anthropic", "openai", "google", "deepseek", "meta"]
SHOWN_PER_MAKER = 6

GOOGLE_TRANSLATE_PRICE = 20.0  # USD per million characters (cloud.google.com/products/translate/pricing)
ROUGH_SENTENCE_CHARS = 100

# A stated rough estimate, used until the first run measures real answer lengths (BUILD.md, "Money").
# Tokens for one call about one sentence, as (input tokens, output tokens).
# "translate": the translation prompt and the translation it returns.
# "judge": a panel judge's prompt (the sentence plus about 6 candidates) and its JSON scores.
# THINKING_TOKENS: extra output tokens a model spends thinking at its lowest effort,
# for models whose lowest effort isn't "none" (docs/adr/0001).
ROUGH_TOKENS = {
    "translate": (250, 80),
    "judge": (700, 300),
}
THINKING_TOKENS = 200


def cost_per_1000_sentences(model: Model) -> float:
    """What one model costs per 1,000 sentences as a translator and a panel judge."""
    thinking = 0 if model.lowest_effort in (None, "none") else THINKING_TOKENS
    usd = 0.0
    for call in ("translate", "judge"):
        input_tokens, output_tokens = ROUGH_TOKENS[call]
        usd += input_tokens * model.input_price + (output_tokens + thinking) * model.output_price
    return usd * 1000 / 1_000_000


def main() -> None:
    models = OpenRouter().list_models()
    print("Prices in USD per million tokens. Cost: rough, per 1,000 sentences, one direction.\n")
    for maker in MAKERS:
        newest = sorted((m for m in models if m.maker == maker), key=lambda m: -m.created)
        print(maker)
        for m in newest[:SHOWN_PER_MAKER]:
            temperature = "temp 0" if m.accepts_temperature else "no temp"
            print(
                f"  {m.id:40} in {m.input_price:6.2f}  out {m.output_price:6.2f}"
                f"  ~${cost_per_1000_sentences(m):6.2f}  {temperature:7}  effort {m.lowest_effort}"
            )
        print()
    google = GOOGLE_TRANSLATE_PRICE * ROUGH_SENTENCE_CHARS * 1000 / 1_000_000
    print(f"google-translate  ${GOOGLE_TRANSLATE_PRICE:.2f} per million characters  ~${google:.2f}")


if __name__ == "__main__":
    main()
