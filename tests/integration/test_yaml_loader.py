from pathlib import Path

import pytest

from muallim.domain.curriculum import ItemKind
from muallim.infrastructure.curriculum.yaml_loader import load_curriculum, load_lexicon


def test_non_mapping_yaml_rejected(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("- just\n- a list\n", encoding="utf-8")
    with pytest.raises(ValueError, match="словарь"):
        load_lexicon(path)


def test_item_kind_and_note_override_lesson(tmp_path: Path) -> None:
    course = tmp_path / "course.yaml"
    course.write_text(
        """\
id: c
version: "1"
title: t
lessons:
- id: L01
  number: 1
  title: t
  kind: line
  source: {source_id: SRC-040, page: 11}
  items:
  - {id: L01-01, kind: letter, text: "رَ رِ رُ", sound: ро, name: Ро}
  - {id: L01-02, text: "رَرْ", note: пары, source: {source_id: SRC-040, page: 11, line: 2}}
""",
        encoding="utf-8",
    )
    lexicon = Path(__file__).resolve().parents[2] / "curriculum" / "lexicon.ru.yaml"
    head, line = load_curriculum(course, lexicon).lessons[0].items
    assert (head.kind, line.kind) == (ItemKind.LETTER, ItemKind.LINE)
    assert (line.note, line.sound) == ("пары", "")
    assert head.source is not None and head.source.page == 11 and head.source.line is None
    assert line.source is not None and line.source.line == 2


LEXICON_RU = Path(__file__).resolve().parents[2] / "curriculum" / "lexicon.ru.yaml"
SMALL_LEXICON = """\
consonants:
  ح: {name: Хэ, translit: х}
  ص: {name: Сад, translit: с}
vowels: {}
letter_tips: {}
pair_tips: []
"""


def test_lexicon_reads_optional_sounds_section(tmp_path: Path) -> None:
    """FR-54: подписи звуков кириллицей — раздел ``sounds:`` (say, note); note необязателен."""
    path = tmp_path / "lexicon.yaml"
    sounds = "sounds:\n  ح: {say: ха, note: горлом}\n  ص: {say: со}\n"
    path.write_text(SMALL_LEXICON + sounds, encoding="utf-8")
    assert dict(load_lexicon(path).sounds) == {"ح": ("ха", "горлом"), "ص": ("со", "")}


def test_lexicon_without_sounds_section_loads(tmp_path: Path) -> None:
    path = tmp_path / "lexicon.yaml"
    path.write_text(SMALL_LEXICON, encoding="utf-8")
    assert load_lexicon(path).sounds == {}


def test_russian_lexicon_tells_throat_sounds_apart_by_word() -> None:
    """Проверяет КОНТЕНТ автора (решение 2026-10-23, черновик в lexicon.ru.yaml — утвердить
    автору): ح «ха» горлом, ه «ха» легко (Р8, 2026-10-24: не «выдохом») — звук один, подпись
    разная."""
    sounds = load_lexicon(LEXICON_RU).sounds
    assert sounds["ح"][0] == sounds["ه"][0] == "ха"
    assert sounds["ح"][1] != sounds["ه"][1]
    assert sounds["ه"][1] != "выдохом" and "легко" in sounds["ه"][1]


def test_lexicon_reads_optional_syllables_of_a_sound(tmp_path: Path) -> None:
    """Слоги огласовки как в карточках (со · сы · су) — ``sounds.<буква>.syllables``,
    необязательно; в ``Lexicon.syllables`` — (фатха, кясра, дамма)."""
    path = tmp_path / "lexicon.yaml"
    sounds = "sounds:\n  ص: {say: со, syllables: [со, сы, су]}\n  ح: {say: ха, note: горлом}\n"
    path.write_text(SMALL_LEXICON + sounds, encoding="utf-8")
    lexicon = load_lexicon(path)
    assert dict(lexicon.syllables) == {"ص": ("со", "сы", "су")}
    assert lexicon.sounds["ص"] == ("со", "")
