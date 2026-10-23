"""Картинки урока читаются на телефоне (FR-48, автор 2026-10-20, UX-обход).

Холст не шире 900 px, текст не теряется в пустых полях: Telegram сжимает картинку до ширины
сообщения (~360 pt), и чем шире холст, тем мельче буквы и огласовки на экране.
Чернила — пиксели цвета ``render.INK``; рамку отрезаем полями по 40 px.
FR-54: картинка разбора группами ``render.result_marks`` — та же ширина, красная только буква.
"""

import io
from collections.abc import Callable
from dataclasses import replace
from typing import Any

import pytest
from PIL import Image, ImageChops

from muallim.domain.assessment import assess
from muallim.infrastructure.curriculum.yaml_loader import load_lexicon
from muallim.presentation.telegram import render, texts
from tests.conftest import CURRICULUM_DIR

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


def _review(text: str, heard: str, letter: str | None = None) -> Any:
    """FR-54: разбор группами по оценке ``assess`` (эталон — текст строки)."""
    from muallim.application.breakdown import build_breakdown  # noqa: PLC0415

    lexicon = load_lexicon(CURRICULUM_DIR / "lexicon.ru.yaml")
    return build_breakdown(assess(text, heard), text, lexicon, lesson_letter=letter)


def _marks(text: str, heard: str, letter: str | None = None) -> bytes:
    """Картинка разбора группами (``render.result_marks``)."""
    review = _review(text, heard, letter)
    return render.result_marks(text, review, "Верно 1 слово из 2")


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
        "Верно 5 слов из 6",
    ),
    "result_marks": lambda: _marks(SIX_SYLLABLES, "سُمْ صِفْ فَصْ صَلَفَ صَبَرَ مَصَرَ"),
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
    png = render.result_words("صُمْ صِفْ", states, 85, "Верно 2 слова из 2")
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


# ---------- FR-54: картинка разбора группами ----------
L020_06 = SIX_SYLLABLES
ONE_SWAP = "سُمْ صِفْ فَصْ صَرَفَ صَبَرَ بَصَرَ"  # ص→س один раз
SWAP_THREE = "سُمْ صِفْ فَصْ سَرَفَ صَبَرَ بَسَرَ"  # одна группа ص→س, три места
TWO_KINDS = "سُمْ صِفْ فَصْ صَلَفَ صَبَرَ بَصَرَ"  # ص→س, ر→ل
THREE_KINDS = "سُمْ صِفْ فَصْ صَلَفَ صَبَرَ مَصَرَ"  # ص→س, ر→ل, ب→م
WORD = "اِسْتَحْسَنَ"  # слово строки L024-09 (урок ح)


def _mask(png: bytes, color: tuple[int, int, int]) -> Image.Image:
    """Пиксели цвета ``color`` (белым) внутри рамки — каждый канал ближе INK_TOLERANCE/3."""
    img = _image(png)
    w, h = img.size
    region = img.crop((FRAME_MARGIN, FRAME_MARGIN, w - FRAME_MARGIN, h - FRAME_MARGIN))
    diff = ImageChops.difference(region, Image.new("RGB", region.size, color))
    near = [ch.point(lambda v: 255 if v < INK_TOLERANCE // 3 else 0) for ch in diff.split()]
    return ImageChops.multiply(ImageChops.multiply(near[0], near[1]), near[2])


def _rows(mask: Image.Image) -> list[int]:
    data, w = mask.tobytes(), mask.width
    return [data[y * w : (y + 1) * w].count(255) for y in range(mask.height)]


def _text_band(png: bytes) -> tuple[int, int]:
    """Полоса строки арабского текста: самый «зелёный» непрерывный ряд строк (верные буквы
    зелёные; у крупного арабского шрифта зелени больше, чем у любой подписи легенды)."""
    rows = _rows(_mask(png, render.OK))
    runs: list[tuple[int, int, int]] = []  # (сумма, начало, конец)
    start = None
    for y, n in enumerate([*rows, 0]):
        if n and start is None:
            start = y
        elif not n and start is not None:
            runs.append((sum(rows[start:y]), start, y))
            start = None
    assert runs, "на картинке нет зелёных букв"
    _, top, bottom = max(runs)
    return top, bottom


def _columns(mask: Image.Image, top: int, bottom: int) -> list[int]:
    band = mask.crop((0, top, mask.width, bottom))
    data, w = band.tobytes(), band.width
    return [x for x in range(w) if any(data[y * w + x] for y in range(band.height))]


@needs_raqm
def test_result_marks_letters_are_large_on_a_phone_screen() -> None:
    """Одна строка арабского текста (зелёные верные буквы) — не меньше 38 pt на экране 360 pt;
    легенда и полоса балла в замер не попадают."""
    png = _marks("صُمْ صِفْ", "سُمْ صِفْ")
    top, bottom = _text_band(png)
    assert (bottom - top) * PHONE_WIDTH / _image(png).width >= 38


@needs_raqm
def test_result_marks_paints_only_the_wrong_letter_red() -> None:
    """Красная — сама буква ح, а не всё слово «اِسْتَحْسَنَ»: в полосе строки красное занимает
    меньше половины ширины слова (номер над буквой и легенда не в счёт)."""
    png = _marks(WORD, "اِسْتَهْسَنَ")
    top, bottom = _text_band(png)
    red = _columns(_mask(png, render.ACCENT), top, bottom)
    word = _columns(_mask(png, render.OK), top, bottom) + red
    assert red, "в строке нет красной буквы"
    assert max(red) - min(red) < (max(word) - min(word)) / 2


def test_legend_has_a_row_for_every_group_not_for_every_place() -> None:
    """Легенда — строка на ГРУППУ (номер, нужно, у тебя): три замены — три строки; одна группа
    в трёх местах — одна строка (баг 3: раньше показывалась только первая замена)."""
    three = _review(L020_06, THREE_KINDS)
    rows = render.legend_rows(three)
    assert [n for n, *_ in rows] == [1, 2, 3]
    assert [(need, heard) for _, need, heard in rows] == [
        (g.need_label, g.heard_label) for g in three.groups
    ]
    assert len(render.legend_rows(_review(L020_06, SWAP_THREE))) == 1


def test_number_over_letter_is_the_group_number() -> None:
    """Номер над буквой = номер группы (= номер пункта в тексте); у всех мест группы — один."""
    same = render.group_numbers(_review(L020_06, SWAP_THREE))
    assert same == {0: 1, 6: 1, 13: 1}
    kinds = render.group_numbers(_review(L020_06, THREE_KINDS))
    # ص в «صُمْ» — 0, ر в «صَرَفَ» — 7, ب в «بَصَرَ» — 12
    assert kinds == {0: 1, 7: 2, 12: 3}


@needs_raqm
def test_result_marks_height_grows_with_groups_not_places() -> None:
    """Высота картинки: 1 < 2 < 3 группы; одна группа в трёх местах — как одна замена."""
    one = _image(_marks(L020_06, ONE_SWAP))
    same = _image(_marks(L020_06, SWAP_THREE))
    two = _image(_marks(L020_06, TWO_KINDS))
    three = _image(_marks(L020_06, THREE_KINDS))
    assert one.height == same.height < two.height < three.height
    assert max(one.width, two.width, three.width) <= MAX_WIDTH


def _diff_box(a: bytes, b: bytes) -> tuple[int, int, int, int]:
    box = (
        ImageChops.difference(_image(a), _image(b))
        .convert("L")
        .point(lambda v: 255 if v > 40 else 0)
        .getbbox()
    )
    assert box, "картинки не отличаются"
    return box


@needs_raqm
def test_legend_arabic_letter_is_large() -> None:
    """Буква в легенде («у тебя ه …») крупная — не меньше 30 pt на экране 360 pt. Меряем разницу
    двух картинок, где отличается только прозвучавшая буква группы (ه → ق)."""
    review = _review(WORD, "اِسْتَهْسَنَ")
    (g,) = review.groups
    other = replace(g, heard="ق", heard_label=g.heard_label.replace("ه", "ق"))
    a = render.result_marks(WORD, review)
    b = render.result_marks(WORD, replace(review, groups=(other,)))
    _, top, _, bottom = _diff_box(a, b)
    assert (bottom - top) * PHONE_WIDTH / _image(a).width >= 30


# ---------- раунд 2 (ревью 2026-10-24): длинная строка, номера на картинке ----------
L107_09 = "جَزَآؤُهُمْ عِندَ رَبِّهِمْ جَنَّـٰتُ عَدْنٍۢ تَجْرِى مِن تَحْتِهَا ٱلْأَنْهَـٰرُ خَـٰلِدِينَ فِيهَآ"
L107_09_PHONEMES = (  # quran-transcript, MOSHAF_PARAMS бота (без модели)
    "جَزَااااءُهُمعِںںںدَرَببِهِمجَننننَااتُعَدڇنِںںںتَجڇرِۦۦمِںںںتَحتِهَلءَنهَاارُخَاالِدِۦۦنَفِۦۦهَاا"
)
L040_01 = "ذُكِّرَ عُلِّمَ كُمِّلَ شُمِّرَ صُنِّفَ صُوِّرَ غُيِّرَ"
L040_01_PHONEMES = "ذُككِرَعُللِمَكُممممِلَشُممممِرَصُننننِفَصُووِرَغُييِر"
TELEGRAM_PHOTO_SIDES = 10000  # ширина + высота фото в Telegram, не больше


def _breakdown(text: str, reference: str, heard: str) -> Any:
    from muallim.application.breakdown import build_breakdown  # noqa: PLC0415

    lexicon = load_lexicon(CURRICULUM_DIR / "lexicon.ru.yaml")
    return build_breakdown(assess(reference, heard), text, lexicon)


@pytest.mark.parametrize("heard", ["", "جَ"], ids=["nothing", "one_syllable"])
def test_long_line_with_many_groups_keeps_the_legend_short(heard: str) -> None:
    """B2: L107-09 почти не прочитана — групп много; в легенде не больше
    ``render.LEGEND_MAX_ROWS`` строк (дальше — «ещё K» из texts.py)."""
    b = _breakdown(L107_09, L107_09_PHONEMES, heard)
    assert len(b.groups) > render.LEGEND_MAX_ROWS
    assert len(render.legend_rows(b)) <= render.LEGEND_MAX_ROWS


@needs_raqm
@pytest.mark.parametrize("heard", ["", "جَ"], ids=["nothing", "one_syllable"])
def test_long_line_image_fits_telegram_limits(heard: str) -> None:
    """B2: картинку с длинной строкой и многими ошибками Telegram примет: ширина ≤ 900,
    ширина + высота ≤ 10000."""
    img = _image(render.result_marks(L107_09, _breakdown(L107_09, L107_09_PHONEMES, heard)))
    assert img.width <= MAX_WIDTH
    assert img.width + img.height <= TELEGRAM_PHOTO_SIDES


@pytest.mark.parametrize(
    ("text", "reference", "heard"),
    [
        (SIX_SYLLABLES, SIX_SYLLABLES, THREE_KINDS),
        (L040_01, L040_01_PHONEMES, L040_01_PHONEMES.replace("ُ", "َ")),
        (L107_09, L107_09_PHONEMES, "جَ"),
    ],
    ids=["three_kinds", "one_sign_many_letters", "long_line"],
)
def test_every_legend_number_has_a_badge(text: str, reference: str, heard: str) -> None:
    """I4: каждый номер легенды 1..N стоит хотя бы над одной буквой; бейджей с номером без
    строки легенды нет (``render.badges`` — то, что рисуется: (кластер, номер))."""
    b = _breakdown(text, reference, heard)
    rows = render.legend_rows(b)
    numbers = {n for _, n in render.badges(b)}
    assert {n for n, *_ in rows} <= numbers
    assert numbers <= set(range(1, len(b.groups) + 1))


@needs_raqm
@pytest.mark.parametrize(
    ("text", "reference", "heard"),
    [
        (L040_01, L040_01_PHONEMES, L040_01_PHONEMES.replace("ُ", "َ")),
        (L107_09, L107_09_PHONEMES, "جَ"),
    ],
    ids=["one_sign_many_letters", "long_line"],
)
def test_badges_do_not_overlap(text: str, reference: str, heard: str) -> None:
    """I4: номера над соседними буквами не налезают друг на друга (раскладка —
    ``render.badge_boxes(text, breakdown)`` → [(номер, (x0, y0, x1, y1))])."""
    boxes = [box for _, box in render.badge_boxes(text, _breakdown(text, reference, heard))]
    assert boxes
    for i, (ax0, ay0, ax1, ay1) in enumerate(boxes):
        for bx0, by0, bx1, by1 in boxes[i + 1 :]:
            assert ax1 <= bx0 or bx1 <= ax0 or ay1 <= by0 or by1 <= ay0, (i, boxes)
