"""The instructions the models receive. Changing anything here changes the connection's fingerprint, so the
cache asks again instead of reusing answers to the old wording."""

import hashlib
import inspect
import sys

from pair_refiner.connection import Task

LANGUAGES = {"en": "English", "fa": "Persian"}

REGISTERS = {
    "written": "Write standard, formal written Persian, as in a published book.",
    "spoken": "Write everyday colloquial spoken Persian, as people actually talk "
              "(for example می‌رم خونه, not "
              "به خانه می‌روم).",
}

PERSIAN_SPELLING = "Use standard Persian spelling, with the half-space (ZWNJ) where it belongs."

RETRY = "Your previous answer was not valid JSON in the required format. Answer again with only that JSON."


def _language_notes(task: Task) -> str:
    notes = []
    if task.target_lang == "fa":
        notes += [REGISTERS[task.register], PERSIAN_SPELLING]
    if task.context:
        lines = "\n".join(f"- {line}" for line in task.context)
        notes.append("The sentence comes from a conversation. The lines just before it were (for context "
                     f"only; don't translate them):\n{lines}")
    return "\n".join(notes)


def translate(task: Task) -> tuple[str, str]:
    """(system, user) messages for a translation."""
    source, target = LANGUAGES[task.source_lang], LANGUAGES[task.target_lang]
    system = (f"You are a professional {source}-to-{target} translator. Translate the sentence the user gives "
              f"into {target}, keeping its exact meaning and tone. {_language_notes(task)}\n"
              "Reply with the translation only: no quotation marks, notes or explanations.")
    return system, task.text


def judge(task: Task, candidates: dict[str, str], attempt: int) -> tuple[str, str]:
    """(system, user) messages for a panel judge."""
    source, target = LANGUAGES[task.source_lang], LANGUAGES[task.target_lang]
    system = (f"You are an expert judge of {source}-to-{target} translation. You will see a {source} sentence and "
              f"several candidate {target} translations labelled with letters. {_language_notes(task)}\n"
              "Score every candidate:\n"
              "- meaning, 1 to 5: 5 = exactly the meaning of the source, nothing added, lost or changed;\n"
              f"- naturalness, 1 to 5: 5 = exactly what a fluent native speaker would write.\n"
              "Then rank all the labels, best first, and give a one-sentence reason for your ranking, "
              "written in English.\n"
              'Answer only with JSON: {"scores": {"A": {"meaning": 5, "naturalness": 4}, ...}, '
              '"ranking": ["A", ...], "reason": "..."}')
    return system, _candidates_message(task, candidates, attempt)


def top_judge(task: Task, candidates: dict[str, str], attempt: int) -> tuple[str, str]:
    """(system, user) messages for the top judge."""
    source, target = LANGUAGES[task.source_lang], LANGUAGES[task.target_lang]
    system = (f"You are the final judge of {source}-to-{target} translation. You will see a {source} sentence "
              f"and a shortlist of candidate {target} translations labelled with letters. "
              f"{_language_notes(task)}\n"
              "Pick the single best translation: first exact meaning, then naturalness. Give a one-sentence reason, "
              "written in English.\n"
              'Answer only with JSON: {"winner": "A", "reason": "..."}')
    return system, _candidates_message(task, candidates, attempt)


def back_translate(text: str, source_lang: str, target_lang: str) -> tuple[str, str]:
    """(system, user) messages for a back-translation: literal, so a changed meaning shows."""
    source, target = LANGUAGES[source_lang], LANGUAGES[target_lang]
    system = (f"Translate the user's {source} sentence into {target} as literally as reads naturally, keeping "
              "every detail of its meaning. Reply with the translation only.")
    return system, text


def _candidates_message(task: Task, candidates: dict[str, str], attempt: int) -> str:
    lines = [f"{LANGUAGES[task.source_lang]} sentence: {task.text}", "", "Candidates:"]
    lines += [f"{label}: {text}" for label, text in candidates.items()]
    if attempt > 1:
        lines += ["", RETRY]
    return "\n".join(lines)


def judge_schema(labels: list[str]) -> dict:
    """The exact JSON shape a panel judge must answer in."""
    score = {"type": "object", "additionalProperties": False, "required": ["meaning", "naturalness"],
             "properties": {"meaning": {"type": "integer", "minimum": 1, "maximum": 5},
                            "naturalness": {"type": "integer", "minimum": 1, "maximum": 5}}}
    return {"type": "object", "additionalProperties": False, "required": ["scores", "ranking", "reason"],
            "properties": {
                "scores": {"type": "object", "additionalProperties": False, "required": labels,
                           "properties": {label: score for label in labels}},
                "ranking": {"type": "array", "items": {"type": "string", "enum": labels}},
                "reason": {"type": "string"}}}


def top_judge_schema(labels: list[str]) -> dict:
    return {"type": "object", "additionalProperties": False, "required": ["winner", "reason"],
            "properties": {"winner": {"type": "string", "enum": labels}, "reason": {"type": "string"}}}


# Every word of this file counts: any change gives a new fingerprint.
FINGERPRINT = hashlib.sha256(inspect.getsource(sys.modules[__name__]).encode()).hexdigest()[:16]
