"""FR-61 (ADR-0077 п. 6): карточка шага урока «Суры» рисуется по слогам, если разбор есть.

``screens.card(..., syllables=...)`` — как ``videos=`` (ADR-0074). Для ``lesson.section == "sura"``
и пункта с ``quran``: библиотека знает текст — ``render.ayah(words, number, position, scale)``,
иначе — прежняя ``render.card``. Номер — ``ayah_number`` (басмала перед сурой — без номера).
«Как читается» под спойлером остаётся; «Крупный шрифт» — ``render.LARGE_SCALE`` и свой ключ экрана.

Разбор — фейк порта ``AyahSyllables`` (каждое слово — одна клетка); рисование подменено шпионами,
пиксели не проверяются. Тексты — из curriculum/course.ru.yaml.
"""

from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

import pytest

from muallim.application.use_cases.reading import CardReading
from muallim.domain.curriculum import Curriculum
from muallim.domain.settings import LearnerSettings
from muallim.presentation.telegram import render, screens

# модулей ещё нет до реализации FR-61 — во время выполнения не импортируются
if TYPE_CHECKING:
    from muallim.application.ports.reading import AyahSyllables
if TYPE_CHECKING:
    from muallim.domain.syllables import SyllableCell

Ayah = tuple[tuple["SyllableCell", ...], ...]

FATIHA_BASMALA = "L097-02"  # 1:1 в аль-Фатихе — номер 1, шаг 2 из 8
FATIHA_RULE = "L097-01"  # правило «سُورَة» — без quran
BAQARA_BASMALA = "L098-01"  # 1:1 перед аль-Бакарой — без номера
BAQARA_5 = "L098-06"  # 2:5
AHAD = "L086-05"  # أَحَدٌ (112:1) — урок «остановка», не «sura»


class FakeSyllables:
    """Фейк порта ``AyahSyllables``: знает только переданные тексты, слово — одна клетка."""

    def __init__(self, texts: Iterable[str]) -> None:
        from muallim.domain.syllables import SyllableCell  # noqa: PLC0415

        self.words: dict[str, Ayah] = {
            t: tuple((SyllableCell(w, "звук"),) for w in t.split(" ")) for t in texts
        }

    def for_text(self, text: str) -> Ayah | None:
        return self.words.get(text)


def _port(texts: Iterable[str]) -> "AyahSyllables":
    """Фейк, проверенный mypy на совместимость с портом ``AyahSyllables``."""
    return FakeSyllables(texts)


class Spy:
    def __init__(self) -> None:
        self.ayah: list[dict[str, Any]] = []
        self.card: list[str] = []


@pytest.fixture
def drawn(monkeypatch: pytest.MonkeyPatch) -> Spy:
    spy = Spy()

    def ayah(
        words: Any, number: int | None, position: tuple[int, int], scale: float = 1.0
    ) -> bytes:
        spy.ayah.append({"words": words, "number": number, "position": position, "scale": scale})
        return b"ayah-png"

    def card(text: str, accent: Any, position: tuple[int, int], scale: float = 1.0) -> bytes:
        spy.card.append(text)
        return b"card-png"

    monkeypatch.setattr(render, "available", lambda: True)
    monkeypatch.setattr(render, "ayah", ayah)
    monkeypatch.setattr(render, "card", card)
    # шаг-правило рисуется render.rule: подменяем, чтобы тест не зависел от libraqm
    monkeypatch.setattr(render, "rule", lambda text, scale=1.0: b"rule-png")
    return spy


def _all_sura_texts(c: Curriculum) -> "AyahSyllables":
    return _port(
        {i.text for les in c.lessons if les.section == "sura" for i in les.items if i.quran}
    )


def _card(c: Curriculum, item_id: str, **kw: Any) -> screens.Screen:
    return screens.card(c, c.item(item_id), False, False, **kw)


def test_sura_step_with_syllables_is_drawn_as_ayah(curriculum: Curriculum, drawn: Spy) -> None:
    library = _all_sura_texts(curriculum)
    text = curriculum.item(FATIHA_BASMALA).text
    s = _card(curriculum, FATIHA_BASMALA, syllables=library)
    assert s.image == b"ayah-png"
    assert drawn.card == []
    [call] = drawn.ayah
    assert call == {
        "words": library.for_text(text), "number": 1, "position": (1, 8), "scale": 1.0,
    }  # fmt: skip


def test_basmala_before_sura_is_drawn_without_number(curriculum: Curriculum, drawn: Spy) -> None:
    _card(curriculum, BAQARA_BASMALA, syllables=_all_sura_texts(curriculum))
    [call] = drawn.ayah
    assert call["number"] is None and call["position"] == (0, 6)


def test_ayah_number_is_taken_from_quran_reference(curriculum: Curriculum, drawn: Spy) -> None:
    _card(curriculum, BAQARA_5, syllables=_all_sura_texts(curriculum))
    [call] = drawn.ayah
    assert call["number"] == 5


def test_large_font_draws_ayah_larger_with_its_own_screen_key(
    curriculum: Curriculum, drawn: Spy
) -> None:
    library = _all_sura_texts(curriculum)
    normal = _card(curriculum, BAQARA_5, syllables=library)
    large = _card(curriculum, BAQARA_5, syllables=library, view=LearnerSettings(large_font=True))
    assert [c["scale"] for c in drawn.ayah] == [1.0, render.LARGE_SCALE]
    assert normal.image_key != large.image_key


def test_sura_step_without_syllables_keeps_old_card(curriculum: Curriculum, drawn: Spy) -> None:
    text = curriculum.item(BAQARA_5).text
    s = _card(curriculum, BAQARA_5, syllables=_port(()))
    assert s.image == b"card-png" and drawn.card == [text] and drawn.ayah == []


def test_card_without_syllables_argument_keeps_old_card(curriculum: Curriculum, drawn: Spy) -> None:
    _card(curriculum, BAQARA_5)
    assert drawn.ayah == [] and len(drawn.card) == 1


def test_ayah_outside_sura_lessons_keeps_old_card(curriculum: Curriculum, drawn: Spy) -> None:
    """أَحَدٌ (112:1) в уроке остановки: разбор есть, но урок не «sura» — прежняя карточка."""
    text = curriculum.item(AHAD).text
    _card(curriculum, AHAD, syllables=_port((text,)))
    assert drawn.ayah == [] and drawn.card == [text]


def test_rule_step_of_sura_lesson_is_not_an_ayah(curriculum: Curriculum, drawn: Spy) -> None:
    """Правило «سُورَة» (без quran) — не аят, даже если текст знаком библиотеке."""
    text = curriculum.item(FATIHA_RULE).text
    _card(curriculum, FATIHA_RULE, syllables=_port((text,)))
    assert drawn.ayah == []


def test_how_to_read_spoiler_stays_on_syllable_card(curriculum: Curriculum, drawn: Spy) -> None:
    """Решение автора 2026-10-30: «Как читается» под спойлером на карточке суры остаётся."""
    reading = CardReading((("бисми", False), ("ллаахи", False)), ())
    library = _all_sura_texts(curriculum)
    with_ayah = _card(curriculum, FATIHA_BASMALA, reading=reading, syllables=library)
    before = _card(curriculum, FATIHA_BASMALA, reading=reading, syllables=_port(()))
    assert drawn.ayah, "карточка нарисована по слогам"
    assert "<tg-spoiler>" in with_ayah.caption
    assert with_ayah.caption == before.caption
