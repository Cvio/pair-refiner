"""Never pay twice: every model answer is stored the moment it arrives, keyed by the model, the exact request and
the connection's fingerprint, in a cache shared across runs (BUILD.md, "Never pay twice")."""

import dataclasses
import hashlib
import json
import sqlite3
from pathlib import Path

from pair_refiner.connection import Answer, Connection, Task


class CachedConnection:
    """A connection that answers from the cache when it can, and stores every new answer before returning it.
    A cached answer costs nothing this time."""

    def __init__(self, connection: Connection, path: Path):
        self.connection = connection
        self.fingerprint = connection.fingerprint
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute("""CREATE TABLE IF NOT EXISTS answers (
            key TEXT PRIMARY KEY, kind TEXT, model TEXT, text TEXT, cost REAL,
            input_tokens INTEGER, output_tokens INTEGER, stored TEXT DEFAULT CURRENT_TIMESTAMP)""")

    def translate(self, model: str, task: Task) -> Answer:
        return self._ask("translate", model, task)

    def judge(self, model: str, task: Task, candidates: dict[str, str], attempt: int = 1) -> Answer:
        return self._ask("judge", model, task, candidates, attempt)

    def top_judge(self, model: str, task: Task, candidates: dict[str, str], attempt: int = 1) -> Answer:
        return self._ask("top_judge", model, task, candidates, attempt)

    def back_translate(self, model: str, text: str, source_lang: str, target_lang: str) -> Answer:
        return self._ask("back_translate", model, text, source_lang, target_lang)

    def _ask(self, kind: str, model: str, *args) -> Answer:
        request = [self.connection.fingerprint, kind, model,
                   *(dataclasses.asdict(a) if isinstance(a, Task) else a for a in args)]
        key = hashlib.sha256(json.dumps(request, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        row = self.db.execute("SELECT text, input_tokens, output_tokens FROM answers WHERE key = ?", (key,)).fetchone()
        if row:
            return Answer(row[0], 0.0, row[1], row[2])
        answer = getattr(self.connection, kind)(model, *args)
        with self.db:  # committed at once, so a crash right after loses nothing paid for
            self.db.execute("INSERT INTO answers (key, kind, model, text, cost, input_tokens, output_tokens) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (key, kind, model, answer.text, answer.cost, answer.input_tokens, answer.output_tokens))
        return answer
