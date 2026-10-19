"""Seam 2, for real: the only code that calls OpenRouter's chat models and Google Cloud Translation.
Checked only by the live check (tests/test_live.py, run by hand). Keys are never printed or logged."""

import hashlib
import json
import time
import tomllib
from pathlib import Path

import httpx

from pair_refiner import prompts
from pair_refiner.connection import GOOGLE_TRANSLATE, OPENROUTER_API, Answer, Model, OpenRouter, Task

GOOGLE_API = "https://translation.googleapis.com/language/translate/v2"
GOOGLE_PRICE_PER_CHARACTER = 20 / 1_000_000  # USD (cloud.google.com/products/translate/pricing)
MAX_OUTPUT_TOKENS = 4000  # thinking included; a sentence never needs more
RETRY_WAITS = (2, 10, 30)  # seconds to wait after a server error or a dropped connection, before giving up
RATE_LIMIT_TRIES = 6  # times to wait out a speed limit (429) before giving up


def _retry_after(response: httpx.Response) -> float:
    """Seconds to wait after a 429: the Retry-After header, else OpenRouter's X-RateLimit-Reset (a time in
    milliseconds, in the header or in the body's metadata), else a minute. At least 1 second, at most 2 minutes."""
    try:
        if "retry-after" in response.headers:
            return min(max(float(response.headers["retry-after"]), 1), 120)
        reset = response.headers.get("x-ratelimit-reset") or \
            response.json()["error"]["metadata"]["headers"]["X-RateLimit-Reset"]
        return min(max(float(reset) / 1000 - time.time(), 1), 120)
    except (ValueError, KeyError, TypeError):
        return 60.0


class LiveError(Exception):
    """A service failed or answered in a way the tool can't use. The message never contains a key."""


def load_keys(path: Path) -> dict:
    if not path.exists():
        raise LiveError(f"{path.name} not found. Copy keys.example.toml to keys.toml and put your keys in it "
                        "(see the README).")
    with open(path, "rb") as f:
        return tomllib.load(f)


class LiveConnection:
    """OpenRouter for every AI model, Google Cloud Translation for google-translate. Temperature 0 where a model
    accepts it, and each model's lowest reasoning effort (docs/adr/0001)."""

    def __init__(self, keys: dict):
        self._openrouter_key = keys["openrouter"]["api_key"]
        self._google_key = keys["google"]["translate_api_key"]
        self._models: dict[str, Model] = {m.id: m for m in OpenRouter().list_models()}
        settings = {"temperature_when_accepted": 0, "effort": "lowest", "max_tokens": MAX_OUTPUT_TOKENS}
        self.fingerprint = hashlib.sha256(
            json.dumps([prompts.FINGERPRINT, settings, "google-nmt-v2"]).encode()).hexdigest()[:16]
        self._http = httpx.Client(timeout=120)

    def translate(self, model: str, task: Task) -> Answer:
        if model == GOOGLE_TRANSLATE:
            return self._google(task.text, task.source_lang, task.target_lang)
        return self._chat(model, *prompts.translate(task))

    def judge(self, model: str, task: Task, candidates: dict[str, str], attempt: int = 1) -> Answer:
        return self._chat(model, *prompts.judge(task, candidates, attempt),
                          schema=("judgement", prompts.judge_schema(list(candidates))))

    def top_judge(self, model: str, task: Task, candidates: dict[str, str], attempt: int = 1) -> Answer:
        return self._chat(model, *prompts.top_judge(task, candidates, attempt),
                          schema=("pick", prompts.top_judge_schema(list(candidates))))

    def back_translate(self, model: str, text: str, source_lang: str, target_lang: str) -> Answer:
        if model == GOOGLE_TRANSLATE:
            return self._google(text, source_lang, target_lang)
        return self._chat(model, *prompts.back_translate(text, source_lang, target_lang))

    def _chat(self, model: str, system: str, user: str, schema: tuple[str, dict] | None = None) -> Answer:
        info = self._models.get(model)
        if info is None:
            raise LiveError(f"{model} is not in OpenRouter's model list.")
        body: dict = {"model": model, "max_completion_tokens": MAX_OUTPUT_TOKENS,
                      "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if info.accepts_temperature:
            body["temperature"] = 0
        if info.lowest_effort:
            body["reasoning"] = {"effort": info.lowest_effort}
        if schema:
            name, json_schema = schema
            body["response_format"] = {"type": "json_schema",
                                       "json_schema": {"name": name, "strict": True, "schema": json_schema}}
            body["provider"] = {"require_parameters": True}
        headers = {"Authorization": f"Bearer {self._openrouter_key}", "X-Title": "pair-refiner"}
        for wait in (*RETRY_WAITS, None):
            reply = self._post(f"{OPENROUTER_API}/chat/completions", model, json=body, headers=headers)
            if "error" not in reply and reply.get("choices"):
                break
            # An error delivered as an answer: nothing was produced, so asking again pays only once.
            if wait is None:
                raise LiveError(f"{model}: OpenRouter answered with an error: {str(reply.get('error'))[:300]}")
            time.sleep(wait)
        usage = reply.get("usage") or {}
        cost = usage.get("cost")
        text = (reply["choices"][0].get("message") or {}).get("content") or ""
        if cost is None and not text.strip():
            # A silent refusal (seen in M6: Muse Wonder on medical sentences): no text, no usage, nothing charged.
            # Refining carries on without it (docs/adr/0002).
            return Answer("", 0.0)
        if cost is None:  # text but no cost: look the cost up by the answer's id rather than ask (and pay) again
            cost = self._generation_cost(model, reply.get("id"), headers)
        return Answer(text.strip(), float(cost), int(usage.get("prompt_tokens") or 0),
                      int(usage.get("completion_tokens") or 0))

    def _generation_cost(self, model: str, generation_id: str | None, headers: dict) -> float:
        """An answer's cost from OpenRouter's generation lookup, which can lag the answer by a few seconds."""
        if generation_id:
            for wait in (1, 3, 10, 30):
                time.sleep(wait)
                response = self._http.get(f"{OPENROUTER_API}/generation", params={"id": generation_id},
                                          headers=headers)
                cost = (response.json().get("data") or {}).get("total_cost") if response.is_success else None
                if cost is not None:
                    return cost
        raise LiveError(f"{model}: OpenRouter's answer had no cost, and its generation lookup found none.")

    def _google(self, text: str, source_lang: str, target_lang: str) -> Answer:
        reply = self._post(GOOGLE_API, GOOGLE_TRANSLATE, headers={"X-Goog-Api-Key": self._google_key},
                           json={"q": text, "source": source_lang, "target": target_lang, "format": "text"})
        translated = reply["data"]["translations"][0]["translatedText"]
        return Answer(translated.strip(), len(text) * GOOGLE_PRICE_PER_CHARACTER)

    def _post(self, url: str, who: str, **request) -> dict:
        rate_limited = 0
        waits = iter((*RETRY_WAITS, None))
        while True:
            try:
                response = self._http.post(url, **request)
            except httpx.TransportError as e:
                status, detail = None, type(e).__name__
            else:
                if response.is_success:
                    return response.json()
                status, detail = response.status_code, response.text[:300]
                if status == 429 and rate_limited < RATE_LIMIT_TRIES:
                    # A speed limit (new accounts: 20 requests a minute per model): wait as long as asked.
                    rate_limited += 1
                    time.sleep(_retry_after(response))
                    continue
                if status not in (408, 429) and status < 500:
                    break
            wait = next(waits)
            if wait is None:
                break
            time.sleep(wait)
        # The message names the service and status only: never the request, which holds a key.
        raise LiveError(f"{who}: the call failed ({status or 'no connection'}): {detail}")
