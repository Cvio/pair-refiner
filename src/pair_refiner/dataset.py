"""Seam 1: reading a dataset. A CSV, TSV or JSONL file plus its settings becomes clean rows."""

import csv
import json
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Literal

from pair_refiner import persian

Origin = Literal["native", "unknown"]
Register = Literal["written", "spoken", "both"]


class DatasetError(Exception):
    """The dataset can't be read as it is; the message says what to change."""


@dataclass(frozen=True)
class DatasetSettings:
    source_lang: str
    target_lang: str
    register: Register = "written"  # the default for runs on this dataset (Persian only)
    origin: Origin | None = None  # where the dataset's own translations came from
    conversation: bool = False  # lines are sent with the previous two lines of their conversation
    conversation_column: str | None = None  # names each line's conversation; without it, one conversation


@dataclass(frozen=True)
class Row:
    id: str
    source: str
    existing: str | None  # the dataset's own translation, if it has one
    origin: Origin | None  # set only when there is an existing translation
    context: tuple[str, ...] = ()  # the previous two original sentences of the same conversation


def read_settings(settings_file: Path) -> tuple[Path, DatasetSettings]:
    """A dataset's settings file (TOML): `file` (relative to the settings file) and the settings."""
    with open(settings_file, "rb") as f:
        values = tomllib.load(f)
    file = values.pop("file", None)
    known = {field.name for field in fields(DatasetSettings)}
    if file is None or values.keys() - known:
        unknown = ", ".join(sorted(values.keys() - known)) or "none"
        raise DatasetError(f"{settings_file.name}: needs `file` and accepts only {', '.join(sorted(known))} "
                           f"(unknown: {unknown}).")
    return settings_file.parent / file, DatasetSettings(**values)


def read_dataset(path: Path, settings: DatasetSettings) -> list[Row]:
    header, records = _records(path)
    source_col, target_col = _columns(path, header, settings)
    if target_col and settings.origin not in ("native", "unknown"):
        raise DatasetError(
            f"{path.name} has existing translations, so its settings must say where they came from: "
            'origin = "native" (a native speaker or professional) or origin = "unknown".'
        )
    conversation_col = (settings.conversation_column or "").strip().lower()
    if settings.conversation and conversation_col and conversation_col not in header:
        raise DatasetError(f"{path.name} has no conversation column '{conversation_col}'; "
                           f"it has: {', '.join(header)}.")
    rows, seen = [], set()
    earlier: dict[str, list[str]] = {}  # each conversation's sentences so far, duplicates included
    for n, record in records:
        source = persian.tidy_if_persian(record.get(source_col, ""), settings.source_lang)
        if not source:
            continue
        existing = persian.tidy_if_persian(record.get(target_col, ""), settings.target_lang) or None
        context = ()
        if settings.conversation:
            before = earlier.setdefault(record.get(conversation_col, "").strip(), [])
            context = tuple(before[-2:])
            before.append(source)
        # A repeated line is a duplicate only if its neighbours are the same too.
        if (source, context) not in seen:
            seen.add((source, context))
            rows.append(Row(id=record.get("id", "").strip() or str(n), source=source, existing=existing,
                            origin=settings.origin if existing else None, context=context))
    return rows


def _records(path: Path) -> tuple[list[str], list[tuple[int, dict[str, str]]]]:
    """The column names (lower case) and each record with its line number (after any header)."""
    # utf-8-sig drops the byte-order mark Excel writes at the start of a file.
    with open(path, encoding="utf-8-sig", newline="") as f:
        if path.suffix.lower() == ".jsonl":
            records = [(n, _jsonl_record(path, n, line)) for n, line in enumerate(f, 1)]
            header = list(dict.fromkeys(name for _, record in records for name in record))
            return header, records
        if path.suffix.lower() == ".tsv":
            reader = csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE)
        elif path.suffix.lower() == ".csv":
            reader = csv.reader(f)
        else:
            raise DatasetError(f"{path.name}: a dataset must be a .csv, .tsv or .jsonl file.")
        header, *lines = reader
    header = [name.strip().lower() for name in header]
    # csv.reader keeps blank lines (as []), so n is the record's line number after the header.
    return header, [(n, dict(zip(header, line))) for n, line in enumerate(lines, 1)]


def _jsonl_record(path: Path, n: int, line: str) -> dict[str, str]:
    if not line.strip():
        return {}
    try:
        record = json.loads(line)
    except json.JSONDecodeError as e:
        raise DatasetError(f"{path.name}, line {n}: not valid JSON ({e.msg}).") from None
    return {key.strip().lower(): "" if value is None else str(value) for key, value in record.items()}


def _columns(path: Path, header: list[str], settings: DatasetSettings) -> tuple[str, str | None]:
    """The sentence column and the existing-translation column (or None), found by name."""
    source_names = ["source", settings.source_lang]
    target_names = ["target", "translation", settings.target_lang]
    source = next((name for name in source_names if name in header), None)
    if source is None:
        accepted = " or ".join(f"'{name}'" for name in source_names)
        raise DatasetError(f"{path.name} has no sentence column. Name it {accepted}; it has: {', '.join(header)}.")
    return source, next((name for name in target_names if name in header), None)
