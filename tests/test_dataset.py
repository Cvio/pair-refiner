"""Seam 1: reading a dataset. A file plus its settings becomes clean rows."""

import pytest

from pair_refiner.dataset import DatasetError, DatasetSettings, read_dataset, read_settings

EN_FA = DatasetSettings(source_lang="en", target_lang="fa")


def write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_csv_with_a_source_column_reads_one_row_per_sentence(tmp_path):
    path = write(tmp_path, "data.csv", "source\nHello there.\nWhere is the station?\n")

    rows = read_dataset(path, EN_FA)

    assert [(r.id, r.source, r.existing) for r in rows] == [
        ("1", "Hello there.", None),
        ("2", "Where is the station?", None),
    ]


def test_empty_rows_are_skipped_and_ids_keep_their_line_numbers(tmp_path):
    path = write(tmp_path, "data.csv", "source\n  Hello there.  \n   \n\nGood night.\n")

    rows = read_dataset(path, EN_FA)

    assert [(r.id, r.source) for r in rows] == [("1", "Hello there."), ("4", "Good night.")]


def test_a_repeated_sentence_keeps_only_its_first_copy(tmp_path):
    path = write(tmp_path, "data.csv", "source\nHello.\nGood night.\n Hello. \nHello.\n")

    rows = read_dataset(path, EN_FA)

    assert [(r.id, r.source) for r in rows] == [("1", "Hello."), ("2", "Good night.")]


def test_existing_translations_are_read_with_their_origin(tmp_path):
    path = write(tmp_path, "data.csv", "source,target\nThank you.,ممنونم.\nGood night.,\n")

    rows = read_dataset(path, DatasetSettings(source_lang="en", target_lang="fa", origin="native"))

    assert [(r.source, r.existing, r.origin) for r in rows] == [
        ("Thank you.", "ممنونم.", "native"),
        ("Good night.", None, None),
    ]


def test_existing_translations_without_an_origin_stop_with_a_clear_message(tmp_path):
    path = write(tmp_path, "data.csv", "source,target\nThank you.,ممنونم.\n")

    with pytest.raises(DatasetError, match="origin"):
        read_dataset(path, EN_FA)


def test_columns_are_found_by_language_code_and_an_id_column_is_used(tmp_path):
    path = write(tmp_path, "data.csv", "ID,FA,En\nq7,ممنونم.,Thank you.\n")

    rows = read_dataset(path, DatasetSettings(source_lang="en", target_lang="fa", origin="unknown"))

    assert [(r.id, r.source, r.existing) for r in rows] == [("q7", "Thank you.", "ممنونم.")]


def test_a_file_with_no_sentence_column_names_the_ones_it_accepts(tmp_path):
    path = write(tmp_path, "data.csv", "text,notes\nHello.,greeting\n")

    with pytest.raises(DatasetError, match="'source' or 'en'"):
        read_dataset(path, EN_FA)


@pytest.mark.parametrize("name, text", [
    ("data.tsv", "id\tsource\na1\tHello, friend.\n\na3\tGood night.\n"),
    ("data.jsonl", '{"id": "a1", "source": "Hello, friend."}\n\n{"id": "a3", "source": "Good night."}\n'),
    ("excel.csv", '﻿id,source\na1,"Hello, friend."\n,\na3,Good night.\n'),
])
def test_tsv_jsonl_and_excel_csv_files_read_the_same_way(tmp_path, name, text):
    path = write(tmp_path, name, text)

    rows = read_dataset(path, EN_FA)

    assert [(r.id, r.source) for r in rows] == [("a1", "Hello, friend."), ("a3", "Good night.")]


def test_a_conversation_gives_each_line_its_previous_two_sentences(tmp_path):
    path = write(tmp_path, "chat.csv", 'source\nHi.\nHow are you?\n\n"Fine, thanks."\nAnd you?\n')

    rows = read_dataset(path, DatasetSettings(source_lang="en", target_lang="fa", conversation=True))

    assert [(r.source, r.context) for r in rows] == [
        ("Hi.", ()),
        ("How are you?", ("Hi.",)),
        ("Fine, thanks.", ("Hi.", "How are you?")),
        ("And you?", ("How are you?", "Fine, thanks.")),
    ]


def test_a_conversation_column_keeps_each_conversations_neighbours_apart(tmp_path):
    path = write(tmp_path, "chat.csv", (
        "chat,source\n"
        "1,Is it raining?\n"
        "2,Shall we go?\n"
        "1,Yes.\n"
        "2,OK.\n"
        "1,OK.\n"     # same words as line 4, but other neighbours: kept
        "3,Shall we go?\n"
        "3,OK.\n"     # same words and same neighbours as line 4: a duplicate
    ))
    settings = DatasetSettings(source_lang="en", target_lang="fa", conversation=True, conversation_column="chat")

    rows = read_dataset(path, settings)

    assert [(r.id, r.source, r.context) for r in rows] == [
        ("1", "Is it raining?", ()),
        ("2", "Shall we go?", ()),
        ("3", "Yes.", ("Is it raining?",)),
        ("4", "OK.", ("Shall we go?",)),
        ("5", "OK.", ("Is it raining?", "Yes.")),
    ]


def test_a_conversation_column_the_file_lacks_stops_with_a_clear_message(tmp_path):
    path = write(tmp_path, "chat.csv", "source\nHi.\n")
    settings = DatasetSettings(source_lang="en", target_lang="fa", conversation=True, conversation_column="chat")

    with pytest.raises(DatasetError, match="'chat'"):
        read_dataset(path, settings)


def test_a_dataset_not_marked_as_a_conversation_has_no_neighbours(tmp_path):
    path = write(tmp_path, "data.csv", "source\nHi.\nHow are you?\n")

    assert [r.context for r in read_dataset(path, EN_FA)] == [(), ()]


def test_persian_sentences_are_tidied_and_then_compared_for_duplicates(tmp_path):
    path = write(tmp_path, "fa.csv", (
        "source\n"
        "علي ٣ كتاب ها دارد\n"  # Arabic ي, ك, ٣; ها written apart
        "من مي روم\n"  # می written apart from its verb
        "خسته ام\n"  # ام written apart after ه
        "من می‌روم\n"  # line 2 already tidy: a duplicate
    ))

    rows = read_dataset(path, DatasetSettings(source_lang="fa", target_lang="en"))

    assert [r.source for r in rows] == [
        "علی ۳ کتاب‌ها دارد",  # علی ۳ کتاب‌ها دارد
        "من می‌روم",  # من می‌روم
        "خسته‌ام",  # خسته‌ام
    ]


def test_m2_sample_csv_reads_correctly(tmp_path):
    # As Excel saves it: a byte-order mark, quoted commas, a blank row, a repeat, Arabic ي in a translation.
    path = write(tmp_path, "sample.csv", (
        "﻿ID,Dialogue,EN,FA\n"
        "s1,d1,\"Hello, Sara.\",\"سلام سارا.\"\n"
        "s2,d1,How are you?,\n"
        ",,,\n"
        "s4,d1,I am tired.,من خسته ام.\n"
        "s5,d2,Where is the bus?,اتوبوس كجاست؟\n"
        "s6,d2,Where is the bus?,\n"
    ))
    settings = DatasetSettings(source_lang="en", target_lang="fa", origin="native",
                               conversation=True, conversation_column="Dialogue")

    rows = read_dataset(path, settings)

    assert [(r.id, r.source, r.existing, r.origin, r.context) for r in rows] == [
        ("s1", "Hello, Sara.", "سلام سارا.", "native", ()),
        ("s2", "How are you?", None, None, ("Hello, Sara.",)),
        ("s4", "I am tired.", "من خسته‌ام.", "native",
         ("Hello, Sara.", "How are you?")),  # من خسته‌ام.
        ("s5", "Where is the bus?", "اتوبوس کجاست؟", "native",
         ()),  # اتوبوس کجاست؟
        ("s6", "Where is the bus?", None, None, ("Where is the bus?",)),
    ]


def test_the_older_spelling_of_haii_and_aii_becomes_the_modern_one(tmp_path):
    path = write(tmp_path, "fa.csv", (
        "source\n"
        "یادداشت‌هائی نوشت.\n"  # یادداشت‌هائی نوشت.
        "یادداشت هائی دیگر\n"  # یادداشت هائی دیگر (written apart)
        "جدائی سخت است\n"  # جدائی سخت است
        "اسرائیل و اخر\n"  # اسرائیل و اخر: not a word ending, no madda added
    ))

    rows = read_dataset(path, DatasetSettings(source_lang="fa", target_lang="en"))

    assert [r.source for r in rows] == [
        "یادداشت‌هایی نوشت.",  # یادداشت‌هایی نوشت.
        "یادداشت‌هایی دیگر",  # یادداشت‌هایی دیگر
        "جدایی سخت است",  # جدایی سخت است
        "اسرائیل و اخر",  # unchanged
    ]


def test_a_settings_file_names_the_dataset_and_its_settings(tmp_path):
    write(tmp_path, "data.csv", "source,target\nThank you.,ممنونم.\n")
    settings_file = write(tmp_path, "data.toml", (
        'file = "data.csv"\n'  # next to the settings file
        'source_lang = "en"\n'
        'target_lang = "fa"\n'
        'register = "written"\n'
        'origin = "unknown"\n'
        "conversation = false\n"
    ))

    path, settings = read_settings(settings_file)

    assert path == tmp_path / "data.csv"
    assert settings == DatasetSettings(source_lang="en", target_lang="fa", register="written", origin="unknown")
    assert [(r.source, r.origin) for r in read_dataset(path, settings)] == [("Thank you.", "unknown")]


def test_a_settings_file_with_an_unknown_setting_stops_with_a_clear_message(tmp_path):
    settings_file = write(tmp_path, "data.toml", 'file = "data.csv"\nsource_lang = "en"\ntarget_lang = "fa"\norgin = "native"\n')

    with pytest.raises(DatasetError, match="orgin"):
        read_settings(settings_file)


def test_an_existing_persian_translation_is_tidied_but_english_is_left_alone(tmp_path):
    path = write(tmp_path, "en.csv", "source,fa\nI have 3 books.,من ٣ كتاب دارم.\n")

    rows = read_dataset(path, DatasetSettings(source_lang="en", target_lang="fa", origin="unknown"))

    assert [(r.source, r.existing) for r in rows] == [
        ("I have 3 books.", "من ۳ کتاب دارم."),  # من ۳ کتاب دارم.
    ]
