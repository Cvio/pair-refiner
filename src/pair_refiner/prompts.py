"""The instructions the models receive. Each kind of request has its own fingerprint, made from exactly the
wording it uses: rewording the judges' instructions re-asks the judges, not the translators."""

import hashlib
import inspect

from pair_refiner.connection import Task

LANGUAGES = {"en": "English", "fa": "Persian"}

REGISTERS = {
    "written": "Write standard, formal written Persian, as in a published book.",
    "spoken": "Write everyday colloquial spoken Persian, as people actually talk "
              "(for example می‌رم خونه, not "
              "به خانه می‌روم).",
}

# What the judges are told about the register: which one is wanted, and that the wrong one loses.
JUDGE_REGISTERS = {
    "written": "The translation must be standard, formal written Persian, as in a published book. A candidate in "
               "colloquial spoken Persian (for example می‌رم خونه instead of "
               "به خانه می‌روم) is in the wrong register: "
               "give it a naturalness score of 2 at most.",
    "spoken": "The translation must be everyday colloquial spoken Persian, as people actually talk (for example "
              "می‌رم خونه, not "
              "به خانه می‌روم). A candidate in formal "
              "written Persian is in the wrong register: give it a naturalness score of 2 at most.",
}

PERSIAN_SPELLING = "Use standard Persian spelling, with the half-space (ZWNJ) where it belongs."

RETRY = "Your previous answer was not valid JSON in the required format. Answer again with only that JSON."


def _context_note(task: Task) -> list[str]:
    if not task.context:
        return []
    lines = "\n".join(f"- {line}" for line in task.context)
    return ["The sentence comes from a conversation. The lines just before it were (for context only; don't "
            f"translate them):\n{lines}"]


def _translation_notes(task: Task) -> str:
    notes = [REGISTERS[task.register], PERSIAN_SPELLING] if task.target_lang == "fa" else []
    return "\n".join(notes + _context_note(task))


def _judging_notes(task: Task) -> str:
    notes = [JUDGE_REGISTERS[task.register]] if task.target_lang == "fa" else []
    return "\n".join(notes + _context_note(task))


def translate(task: Task) -> tuple[str, str]:
    """(system, user) messages for a translation."""
    source, target = LANGUAGES[task.source_lang], LANGUAGES[task.target_lang]
    system = (f"You are a professional {source}-to-{target} translator. Translate the sentence the user gives "
              f"into {target}, keeping its exact meaning and tone. {_translation_notes(task)}\n"
              "Reply with the translation only: no quotation marks, notes or explanations.")
    return system, task.text


def judge(task: Task, candidates: dict[str, str], attempt: int) -> tuple[str, str]:
    """(system, user) messages for a panel judge."""
    source, target = LANGUAGES[task.source_lang], LANGUAGES[task.target_lang]
    system = (f"You are an expert judge of {source}-to-{target} translation. You will see a {source} sentence and "
              f"several candidate {target} translations labelled with letters. {_judging_notes(task)}\n"
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
              f"{_judging_notes(task)}\n"
              "Pick the single best translation: first exact meaning, then naturalness. A candidate in the wrong "
              "register should not win unless every candidate is in the wrong register. Give a one-sentence "
              "reason, written in English.\n"
              'Answer only with JSON: {"winner": "A", "reason": "..."}')
    return system, _candidates_message(task, candidates, attempt)


def back_translate(text: str, source_lang: str, target_lang: str) -> tuple[str, str]:
    """(system, user) messages for a back-translation: literal, so a changed meaning shows."""
    source, target = LANGUAGES[source_lang], LANGUAGES[target_lang]
    system = (f"Translate the user's {source} sentence into {target} as literally as reads naturally, keeping "
              "every detail of its meaning. Reply with the translation only.")
    return system, text


def tidy(text: str, lang: str) -> tuple[str, str]:
    """(system, user) messages for tidying a source sentence's punctuation and capitals (docs/adr/0006)."""
    system = (f"You fix the punctuation and capital letters of one {LANGUAGES[lang]} sentence taken from a book, "
              "which automatic sentence-splitting may have left untidy. Only:\n"
              "- remove every quotation mark whose partner is not in this same sentence: an opening quote with no "
              "closing quote, a closing quote with no opening quote, or a stray ' or \" after a word. Keep "
              "apostrophes inside words (don't, John's) and quotation marks that open and close in the sentence;\n"
              "- write a line in ALL CAPITALS or Title Case in normal sentence case, keeping capitals on names, "
              "places, acronyms and the word 'I';\n"
              "- fix spacing around punctuation.\n"
              "Never change, add, remove or reorder a word. Don't add a full stop to a fragment. If nothing needs "
              "fixing, reply with the sentence exactly as it is. Reply with the sentence only.")
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


def _fingerprint(*parts) -> str:
    """A short hash of exactly these functions' code and these constants' values."""
    text = "\n".join(inspect.getsource(p) if callable(p) else repr(p) for p in parts)
    return hashlib.sha256(text.encode()).hexdigest()[:16]


_JUDGING = (_judging_notes, _context_note, JUDGE_REGISTERS, LANGUAGES, _candidates_message, RETRY)
FINGERPRINTS = {
    "translate": _fingerprint(translate, _translation_notes, _context_note, REGISTERS, PERSIAN_SPELLING, LANGUAGES),
    "judge": _fingerprint(judge, judge_schema, *_JUDGING),
    "top_judge": _fingerprint(top_judge, top_judge_schema, *_JUDGING),
    "back_translate": _fingerprint(back_translate, LANGUAGES),
    "tidy": _fingerprint(tidy, LANGUAGES),
}
