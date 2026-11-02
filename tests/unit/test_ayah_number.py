"""FR-61 (ADR-0077 п. 2): клетка-слог аята и номер аята на карточке суры — правило домена.

Номер — не в файле разбора (басмала одна на 28 сур), а правилом: сура пункта не совпадает с сурой
остальных пунктов урока (басмала перед сурой) — номера нет; иначе номер — из ``quran``. У аль-Фатихи
басмала — первый аят (1:1 в L097). Настоящая программа из curriculum/course.ru.yaml.
"""

import dataclasses

import pytest

from muallim.domain.curriculum import Curriculum, Lesson


def _number(curriculum: Curriculum, item_id: str) -> int | None:
    from muallim.domain.syllables import ayah_number  # noqa: PLC0415

    lesson, _ = curriculum.locate(item_id)
    return ayah_number(lesson, curriculum.item(item_id))


def test_syllable_cell_keeps_text_and_sound() -> None:
    from muallim.domain.syllables import SyllableCell  # noqa: PLC0415

    cell = SyllableCell("مِ", "ми")  # кусочек басмалы (L097-02)
    assert (cell.text, cell.sound) == ("مِ", "ми")
    assert cell == SyllableCell(text="مِ", sound="ми")


def test_syllable_cell_is_immutable() -> None:
    from muallim.domain.syllables import SyllableCell  # noqa: PLC0415

    cell = SyllableCell("مِ", "ми")
    with pytest.raises(dataclasses.FrozenInstanceError):
        cell.sound = "му"  # type: ignore[misc]


def test_basmala_before_sura_has_no_number(curriculum: Curriculum) -> None:
    assert curriculum.item("L098-01").quran == "1:1"  # басмала перед аль-Бакарой
    assert _number(curriculum, "L098-01") is None


def test_basmala_of_al_fatiha_is_ayah_one(curriculum: Curriculum) -> None:
    assert curriculum.item("L097-02").quran == "1:1"
    assert _number(curriculum, "L097-02") == 1


@pytest.mark.parametrize(("item_id", "number"), [("L098-06", 5), ("L098-02", 1), ("L097-08", 7)])
def test_ayah_number_comes_from_quran_reference(
    curriculum: Curriculum, item_id: str, number: int
) -> None:
    assert _number(curriculum, item_id) == number


def test_item_without_quran_has_no_number(curriculum: Curriculum) -> None:
    assert curriculum.item("L097-01").quran == ""  # правило «سُورَة»
    assert _number(curriculum, "L097-01") is None


def test_every_basmala_before_a_sura_has_no_number(curriculum: Curriculum) -> None:
    """28 сур после аль-Фатихи: у басмалы номера нет, у остальных аятов — есть."""
    from muallim.domain.syllables import ayah_number  # noqa: PLC0415

    suras = [les for les in curriculum.lessons if les.section == "sura"]
    assert suras[0].id == "L097"
    for lesson in suras[1:]:
        for item in lesson.items:
            if not item.quran:
                continue
            expected = None if item.quran == "1:1" else int(item.quran.split(":")[1])
            assert ayah_number(lesson, item) == expected, item.id


def test_number_rule_depends_only_on_the_lesson_items(curriculum: Curriculum) -> None:
    """Маленький урок из настоящих пунктов: басмала перед сурой 2 — без номера; урок только из
    аятов аль-Фатихи — басмала с номером 1."""
    from muallim.domain.syllables import ayah_number  # noqa: PLC0415

    baqara = tuple(curriculum.item(i) for i in ("L098-01", "L098-02", "L098-06"))
    lesson = Lesson("X", 1, "сура", baqara, section="sura")
    assert [ayah_number(lesson, i) for i in lesson.items] == [None, 1, 5]
    fatiha = tuple(curriculum.item(i) for i in ("L097-02", "L097-03"))
    lesson = Lesson("Y", 2, "сура", fatiha, section="sura")
    assert [ayah_number(lesson, i) for i in lesson.items] == [1, 2]
