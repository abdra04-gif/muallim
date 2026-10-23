"""Картинки урока читаются на телефоне (FR-48, автор 2026-10-20, UX-обход).

Холст не шире 900 px, текст не теряется в пустых полях: Telegram сжимает картинку до ширины
сообщения (~360 pt), и чем шире холст, тем мельче буквы и огласовки на экране.
Чернила — пиксели цвета ``render.INK``; рамку отрезаем полями по 40 px.
"""

import io
from collections.abc import Callable

import pytest
from PIL import Image

from muallim.presentation.telegram import render, texts

needs_raqm = pytest.mark.skipif(not render.available(), reason="нет libraqm (brew install fribidi)")

MAX_WIDTH = 900  # px, FR-48
PHONE_WIDTH = 360  # pt — ширина сообщения в Telegram на телефоне
FRAME_MARGIN = 40  # px — рамка и уголки по краям картинки
INK_TOLERANCE = 40  # сумма |ΔR|+|ΔG|+|ΔB| — сглаживание краёв букв

# Строки из curriculum/course.ru.yaml
ISTI_ADHA = "أَعُوذُ بِٱللَّهِ مِنَ ٱلشَّيْطَانِ ٱلرَّجِيمِ"  # L001-02
BASMALA = "بِسْمِ ٱللَّهِ ٱلرَّحْمَـٰنِ ٱلرَّحِيمِ"  # L001-03
AHAD = "أَحَدٌ"  # L086-05, Коран 112:1
SIX_SYLLABLES = "صُمْ صِفْ فَصْ صَرَفَ صَبَرَ بَصَرَ"  # урок буквы ص


def _image(png: bytes) -> Image.Image:
    return Image.open(io.BytesIO(png)).convert("RGB")


def _ink_box(
    png: bytes, color: tuple[int, int, int] = render.INK
) -> tuple[Image.Image, tuple[int, int, int, int]]:
    """Картинка и рамка вокруг букв цвета ``color`` (без декоративной рамки и точек-шагов)."""
    img = _image(png)
    w, h = img.size
    px = img.load()
    assert px is not None
    xs, ys = [], []
    for y in range(FRAME_MARGIN, h - FRAME_MARGIN):
        for x in range(FRAME_MARGIN, w - FRAME_MARGIN):
            pixel = px[x, y]
            assert isinstance(pixel, tuple)  # RGB
            r, g, b = pixel[:3]
            ir, ig, ib = color
            if abs(r - ir) + abs(g - ig) + abs(b - ib) < INK_TOLERANCE:
                xs.append(x)
                ys.append(y)
    assert xs, f"на картинке нет текста цвета {color}"
    return img, (min(xs), min(ys), max(xs), max(ys))


LESSON_IMAGES: dict[str, Callable[[], bytes]] = {
    "card_isti_adha": lambda: render.card(ISTI_ADHA, (), (1, 3)),
    "card_one_syllable": lambda: render.card("مَ", (), (0, 3)),
    "card_basmala": lambda: render.card(BASMALA, set(), (2, 3)),
    "rule": lambda: render.rule("بَ بِ بُ"),
    "letters": lambda: render.letters("ا ب ت ث ج ح خ"),
    "letter_forms": lambda: render.letter_forms(
        "م", "مَ مِ مُ", texts.LETTER_FORMS, [("горло", False), ("язык", False), ("губы", True)]
    ),
    "result": lambda: render.result("صُمْ صِفْ", {0}, 70),
    "result_words": lambda: render.result_words(
        SIX_SYLLABLES,
        [render.WordState.OK] * 5 + [render.WordState.WRONG],
        83,
        texts.RESULT_WORDS.format(ok=5, total=6),
    ),
    "opening": lambda: render.opening([ISTI_ADHA, BASMALA]),
    "alphabet": lambda: render.alphabet([[("ا", render.Mark.DONE), ("ب", render.Mark.CURRENT)]]),
    "signs": render.signs,
    "postcard": lambda: render.postcard("م", texts.POSTCARD_TITLE, "6. Мим · с. 14", (True,) * 7),
    "book_progress": lambda: render.book_progress(
        [("1. Знакомство", 1, 1), ("2. Буквы и огласовки", 3, 28)],
        (True, False, True, True, False, False, True),
        texts.WEEKDAYS,
    ),
}


@needs_raqm
@pytest.mark.parametrize("name", sorted(LESSON_IMAGES))
def test_lesson_image_is_at_most_900_px_wide(name: str) -> None:
    width, _ = _image(LESSON_IMAGES[name]()).size
    assert width <= MAX_WIDTH, f"{name}: {width} px"


@needs_raqm
@pytest.mark.parametrize(
    ("text", "position"), [(AHAD, (3, 8)), ("مَ", (0, 3))], ids=["ahad", "one_syllable"]
)
def test_short_line_letters_are_large_on_a_phone_screen(
    text: str, position: tuple[int, int]
) -> None:
    """Буквы с огласовками на экране 360 pt — не меньше 65 pt по высоте (сейчас ≈ 53 pt)."""
    img, (_, top, _, bottom) = _ink_box(render.card(text, (), position))
    on_phone = (bottom - top) * PHONE_WIDTH / img.width
    assert on_phone >= 65, f"{text}: {on_phone:.0f} pt"


@needs_raqm
def test_short_word_is_not_lost_in_empty_side_margins() -> None:
    """«أَحَدٌ» занимает не меньше 22% ширины картинки (на холсте 1280 px — 18%)."""
    img, (left, _, right, _) = _ink_box(render.card(AHAD, (), (3, 8)))
    assert (right - left) / img.width >= 0.22


@needs_raqm
def test_long_line_fills_most_of_the_width() -> None:
    """Строка из шести слогов — не меньше 55% ширины: узкий холст не должен мельчить текст.

    Сейчас 76%; на холсте 900 px с переносом на две строки — около 64%.
    """
    img, (left, _, right, _) = _ink_box(render.card(SIX_SYLLABLES, (), (1, 5)))
    assert (right - left) / img.width >= 0.55


def _on_phone(png: bytes, color: tuple[int, int, int] = render.INK) -> float:
    img, (_, top, _, bottom) = _ink_box(png, color)
    return (bottom - top) * PHONE_WIDTH / img.width


@needs_raqm
def test_result_words_are_large_on_a_phone_screen() -> None:
    """Слова разбора (зелёные) на экране 360 pt — не меньше 38 pt (сейчас ≈ 32, при 900 px ≈ 45).

    Балл 85 — полоса оценки жёлтая и не попадает в замер зелёных букв.
    """
    states = [render.WordState.OK] * 2
    png = render.result_words("صُمْ صِفْ", states, 85, texts.RESULT_WORDS.format(ok=2, total=2))
    assert _on_phone(png, render.OK) >= 38


@needs_raqm
def test_opening_line_is_large_on_a_phone_screen() -> None:
    """Строка истиазы в начале занятия — не меньше 50 pt (сейчас ≈ 45, при 900 px ≈ 54)."""
    assert _on_phone(render.opening([ISTI_ADHA])) >= 50


@needs_raqm
def test_longest_word_fits_inside_frame_with_large_font() -> None:
    """Самое длинное слово программы (L079-03) с крупным шрифтом не залезает на рамку."""
    png = render.card("فَٱنۢبَجَسَتْ", (), (0, 1), scale=render.LARGE_SCALE)
    img, (left, _, right, _) = _ink_box(png)
    assert left > FRAME_MARGIN + 5, "слово вылезло влево за поле"
    assert right < img.width - FRAME_MARGIN - 5, "слово вылезло вправо за поле"


@needs_raqm
@pytest.mark.parametrize(("letter", "vowels"), [("أ", "أَ إِ أُ"), ("ل", "لَ لِ لُ"), ("ي", "يَ يِ يُ")])
def test_vowel_row_of_letter_card_stays_between_line_and_zones(letter: str, vowels: str) -> None:
    """Аудит 2026-10-23: дамма над «أُ» (самая высокая связка) наезжала на черту под формами.

    Черта — y = 352, плашки зон начинаются с y = 590 (render.letter_forms).
    """
    png = render.letter_forms(letter, vowels, texts.LETTER_FORMS, [])
    _, (_, top, _, bottom) = _ink_box(png)
    assert top > 352 + 6, f"огласовки наехали на черту: верх {top}"
    assert bottom < 590 - 6, f"огласовки наехали на плашки зон: низ {bottom}"
