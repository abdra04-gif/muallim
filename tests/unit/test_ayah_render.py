"""FR-61 (ADR-0077 п. 5): картинка аята по слогам ``render.ayah(words, number, position, scale)``.

Холст 900 px (FR-48) в обычном масштабе и в «Крупном шрифте» (``render.LARGE_SCALE``, ADR-0061);
без номера (басмала перед сурой) — тоже рисуется. Пиксели номера и клеток не проверяются.
Разбор — из curriculum/syllables/ayat.yaml (кусочки и подписи — как в файле).

Раскладка — ``render.ayah_layout(words, number, scale) -> AyahLayout`` (``rows`` — строки, строка —
индексы слов по порядку; ``row_widths`` — ширина каждой строки в px; ``scale`` — масштаб, которым
нарисовано): каждое слово ровно в одной строке, порядок слов сохранён, строка не шире
``render.TEXT_WIDTH``; одно слово шире строки — масштаб уменьшен (слово не ломается).

Рисование одного аята ≈ 0,1 с, все 168 текстов × 2 масштаба не укладываются в 10 с (NFR-MNT-04),
поэтому берутся самые трудные для вёрстки: самые длинные аяты, аяты с самым длинным словом,
самый короткий (الٓمٓ) и басмала.
"""

import io
from pathlib import Path
from typing import Any

import pytest
import yaml
from PIL import Image

from muallim.domain.curriculum import Curriculum
from muallim.presentation.telegram import render

ROOT = Path(__file__).resolve().parents[2]
AYAT = ROOT / "curriculum" / "syllables" / "ayat.yaml"
MAX_WIDTH = 900  # px, FR-48
HARDEST = 3  # сколько самых длинных аятов и аятов с самым длинным словом

needs_raqm = pytest.mark.skipif(not render.available(), reason="нет libraqm (brew install fribidi)")


def _words(row: dict[str, Any]) -> tuple[tuple[Any, ...], ...]:
    from muallim.domain.syllables import SyllableCell  # noqa: PLC0415

    return tuple(tuple(SyllableCell(str(t), str(s)) for t, s in word) for word in row["words"])


def _rows() -> list[dict[str, Any]]:
    assert AYAT.is_file(), "нет curriculum/syllables/ayat.yaml — make syllables"
    return list(yaml.safe_load(AYAT.read_text(encoding="utf-8"))["ayat"])


def _basmala() -> dict[str, Any]:
    return next(r for r in _rows() if r["text"].startswith("بِسْمِ"))


def _hardest() -> list[dict[str, Any]]:
    rows = _rows()
    longest = sorted(rows, key=lambda r: len(r["text"]), reverse=True)[:HARDEST]
    widest = sorted(rows, key=lambda r: max(map(len, r["text"].split())), reverse=True)[:HARDEST]
    shortest = min(rows, key=lambda r: len(r["text"]))
    picked = {r["text"]: r for r in [*longest, *widest, shortest, _basmala()]}
    return list(picked.values())


def _size(png: bytes) -> tuple[int, int]:
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    return Image.open(io.BytesIO(png)).size


@needs_raqm
@pytest.mark.parametrize("scale", [1.0, render.LARGE_SCALE], ids=["normal", "large"])
def test_ayah_card_is_900_px_wide_for_hardest_ayat(scale: float) -> None:
    for row in _hardest():
        width, height = _size(render.ayah(_words(row), 1, (1, 8), scale))
        assert width == MAX_WIDTH, row["text"]
        assert height > 0


@needs_raqm
@pytest.mark.parametrize("scale", [1.0, render.LARGE_SCALE], ids=["normal", "large"])
def test_ayah_card_without_number_is_drawn(scale: float) -> None:
    """Басмала перед сурой — без номера (``number=None``)."""
    width, _ = _size(render.ayah(_words(_basmala()), None, (0, 8), scale))
    assert width == MAX_WIDTH


@needs_raqm
def test_large_font_ayah_is_taller() -> None:
    """«Крупный шрифт»: ширина та же, буквы крупнее, слова переносятся на больше строк — выше."""
    row = max(_rows(), key=lambda r: len(r["text"]))
    _, normal = _size(render.ayah(_words(row), 5, (5, 8), 1.0))
    _, large = _size(render.ayah(_words(row), 5, (5, 8), render.LARGE_SCALE))
    assert large > normal


@needs_raqm
def test_single_step_lesson_ayah_is_drawn() -> None:
    """Точек «шаг k из n» нет при одном шаге — картинка всё равно есть."""
    row = min(_rows(), key=lambda r: len(r["text"]))
    assert _size(render.ayah(_words(row), 1, (0, 1), 1.0))[0] == MAX_WIDTH


@needs_raqm
def test_ayah_card_draws_any_cells_without_the_data_file(curriculum: Curriculum) -> None:
    """Не зависит от ayat.yaml: аят 2:2 (L098-03), каждое слово — одна клетка."""
    from muallim.domain.syllables import SyllableCell  # noqa: PLC0415

    text = curriculum.item("L098-03").text
    words = tuple((SyllableCell(w, "звук"),) for w in text.split(" "))
    assert _size(render.ayah(words, 2, (2, 8), 1.0))[0] == MAX_WIDTH


# ---------- номер аята ----------
@needs_raqm
def test_number_changes_the_picture(curriculum: Curriculum) -> None:
    """Номер рисуется только при ``number``; разные номера — разные картинки (без пикселей)."""
    from muallim.domain.syllables import SyllableCell  # noqa: PLC0415

    text = curriculum.item("L097-03").text  # 1:2, каждое слово — одна клетка
    words = tuple((SyllableCell(w, "звук"),) for w in text.split(" "))
    without = render.ayah(words, None, (2, 8), 1.0)
    one = render.ayah(words, 1, (2, 8), 1.0)
    seven = render.ayah(words, 7, (2, 8), 1.0)
    assert without != one
    assert one != seven


# ---------- раскладка: слово переносится только целиком ----------
def _check_layout(words: tuple[tuple[Any, ...], ...], scale: float) -> Any:
    layout = render.ayah_layout(words, 1, scale)
    flat = [i for row in layout.rows for i in row]
    assert flat == list(range(len(words))), "каждое слово ровно в одной строке, по порядку"
    assert all(layout.rows), "пустых строк нет"
    assert len(layout.row_widths) == len(layout.rows)
    assert all(0 < w <= render.TEXT_WIDTH for w in layout.row_widths), layout.row_widths
    assert 0 < layout.scale <= scale
    return layout


@needs_raqm
@pytest.mark.parametrize("scale", [1.0, render.LARGE_SCALE], ids=["normal", "large"])
def test_hardest_ayat_are_laid_out_by_whole_words(scale: float) -> None:
    for row in _hardest():
        _check_layout(_words(row), scale)


@needs_raqm
@pytest.mark.parametrize("scale", [1.0, render.LARGE_SCALE], ids=["normal", "large"])
def test_word_wider_than_a_line_shrinks_the_card_instead_of_breaking(
    curriculum: Curriculum, scale: float
) -> None:
    """Синтетика: одно слово из 40 клеток «بَ» (L010-02) — шире строки; масштаб уменьшен."""
    from muallim.domain.syllables import SyllableCell  # noqa: PLC0415

    ba = curriculum.item("L010-02").text
    word = tuple(SyllableCell(ba, "ба") for _ in range(40))
    layout = _check_layout((word,), scale)
    assert [list(r) for r in layout.rows] == [[0]]
    assert layout.scale < scale


@needs_raqm
def test_long_ayah_takes_more_lines_in_large_font() -> None:
    row = max(_rows(), key=lambda r: len(r["text"]))
    normal = _check_layout(_words(row), 1.0)
    large = _check_layout(_words(row), render.LARGE_SCALE)
    assert len(large.rows) > len(normal.rows)


def test_small_waw_and_yaa_are_not_joining_letters() -> None:
    """ۦ ۥ — маленькие знаки после буквы, а не буквы: «إِۦ» не соединяется со следующей (106:2)."""
    assert render._joins("إِۦ") is False
    assert render._joins("هُۥ") is True  # ه соединяется — знак ۥ этого не меняет
    assert render._joins("بِ") is True
    assert render._joins("دَا") is False
