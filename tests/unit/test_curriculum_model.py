import pytest

from muallim.domain.curriculum import Curriculum, ItemKind, Lesson, LessonItem, Lexicon

LEX = Lexicon({}, {}, {}, {})
ALPHA = ItemKind.ALPHABET


def _item(i: str, kind: ItemKind = ItemKind.LINE) -> LessonItem:
    return LessonItem(id=i, text="بَ", kind=kind, sound="")


def _course() -> Curriculum:
    return Curriculum(
        "c", "1", "t",
        (
            Lesson("L01", 1, "a", (_item("L01-01", ALPHA), _item("L01-02", ALPHA))),
            Lesson("L02", 2, "b", (_item("L02-01", ItemKind.LETTER), _item("L02-02"))),
        ),
        LEX,
    )  # fmt: skip


def test_next_item_crosses_lesson_border() -> None:
    c = _course()
    assert c.next_item("L01-02") == c.item("L02-01")  # «Дальше» на последней карточке — новый урок
    assert c.next_item("L02-01") == c.item("L02-02")
    assert c.next_item("L02-02") is None  # конец программы


def test_previous_item_crosses_lesson_border() -> None:
    c = _course()
    assert c.previous_item("L02-01") == c.item("L01-02")
    assert c.previous_item("L01-01") is None


def test_alphabet_items_are_not_practice() -> None:
    c = _course()
    assert not c.item("L01-01").is_practice and c.item("L02-01").is_practice
    assert [i.id for i in c.lesson("L02").practice_items] == ["L02-01", "L02-02"]
    assert c.lesson("L01").practice_items == ()


def test_rule_items_are_not_practice() -> None:
    rule = LessonItem("L01-03", "بَ", ItemKind.RULE, "", name="Огласовки", tip="...")
    assert not rule.is_practice


def test_parts_keep_book_order() -> None:
    a = Lesson("L01", 1, "a", (_item("L01-01"),), part="1. Знакомство", section="start")
    b = Lesson("L02", 2, "b", (_item("L02-01"),), part="2. Буквы", section="letter")
    c = Lesson("L03", 3, "c", (_item("L03-01"),), part="2. Буквы", section="letter")
    course = Curriculum("c", "1", "t", (a, b, c), LEX)
    assert course.parts() == [("1. Знакомство", [a]), ("2. Буквы", [b, c])]


def test_next_lesson() -> None:
    c = _course()
    assert c.next_lesson("L01") == c.lesson("L02")
    assert c.next_lesson("L02") is None


def test_previous_lesson() -> None:
    c = _course()
    assert c.previous_lesson("L02") == c.lesson("L01")
    assert c.previous_lesson("L01") is None


def test_duplicate_item_ids_rejected() -> None:
    lesson = Lesson("L01", 1, "x", (_item("L01-01"), _item("L01-01")))
    with pytest.raises(ValueError, match="Повторяющийся"):
        Curriculum("c", "1", "t", (lesson,), LEX)


def test_unknown_lesson_raises(curriculum: Curriculum) -> None:
    with pytest.raises(KeyError):
        curriculum.lesson("L99")


# ---------- FR-54: буква урока — одна функция домена ----------
@pytest.mark.parametrize(
    ("lesson_id", "letter"),
    [("L003", "ء"), ("L004", "ر"), ("L020", "ص"), ("L024", "ح"), ("L031", None)],
    ids=["hamza", "ra", "sad", "ha", "madd_lesson"],
)
def test_lesson_letter_of_letter_lessons(
    curriculum: Curriculum, lesson_id: str, letter: str | None
) -> None:
    """Буква урока — первая буква головной карточки урока буквы; опоры хамзы — ء (с. 10 книги);
    у уроков не про букву (мадд, ташдид…) — None. Её используют сценарий и экран (FR-54)."""
    from muallim.domain.curriculum import lesson_letter  # noqa: PLC0415

    assert lesson_letter(curriculum.lesson(lesson_id)) == letter
