"""Кнопки карточки и результата (автор 2026-11-08): «◀️ Назад · 🏠 · ▶️ Дальше» одним рядом на
любом шаге, 🏠 по центру, без длинных «Предыдущий/Следующий урок: …»; 🔊 и 🎬 — оба, если есть.

Заменяет прежние раскладки FR-50/ADR-0082 (назад отдельной строкой, ролик вместо 🔊).
"""

from pathlib import Path
from typing import Any

import pytest
from aiogram.types import InlineKeyboardMarkup

from muallim.application.feedback import FeedbackRenderer
from muallim.domain.curriculum import Curriculum
from muallim.presentation.telegram import callbacks as cb
from muallim.presentation.telegram import render, screens, texts
from tests.fakes import InMemoryVideos
from tests.unit.test_screens import _result, _with_errors

NAV = [texts.BACK_BUTTON, texts.HOME_BUTTON, texts.NEXT_BUTTON]


@pytest.fixture(autouse=True)
def captions_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(render, "available", lambda: False)


def _rows(kb: InlineKeyboardMarkup) -> list[list[tuple[str, Any]]]:
    return [[(b.text, b.callback_data) for b in row] for row in kb.inline_keyboard]


def _nav_row(kb: InlineKeyboardMarkup) -> list[tuple[str, Any]]:
    (row,) = [r for r in _rows(kb) if (texts.HOME_BUTTON, cb.Home().pack()) in r]
    return row


def _labels(kb: InlineKeyboardMarkup) -> list[str]:
    return [t for row in _rows(kb) for t, _ in row]


def _edges(c: Curriculum) -> list[str]:
    """Первый и последний шаг урока в середине книги и средний шаг."""
    lesson = c.lessons[10]
    return [lesson.items[0].id, lesson.items[1].id, lesson.items[-1].id]


@pytest.mark.parametrize("step", [0, 1, 2])
def test_card_nav_is_one_row_back_home_next(curriculum: Curriculum, step: int) -> None:
    item = curriculum.item(_edges(curriculum)[step])
    kb = screens.card(curriculum, item, has_audio=True, is_teacher=False).keyboard
    prev, nxt = curriculum.previous_item(item.id), curriculum.next_item(item.id)
    assert prev is not None and nxt is not None
    assert _nav_row(kb) == [
        (texts.BACK_BUTTON, cb.GoItem(item_id=prev.id).pack()),
        (texts.HOME_BUTTON, cb.Home().pack()),
        (texts.NEXT_BUTTON, cb.GoItem(item_id=nxt.id).pack()),
    ]


def test_no_long_lesson_buttons_anywhere(curriculum: Curriculum) -> None:
    for item_id in _edges(curriculum):
        labels = _labels(
            screens.card(
                curriculum, curriculum.item(item_id), has_audio=True, is_teacher=False
            ).keyboard
        )
        assert not [x for x in labels if "урок:" in x], labels


def test_first_card_of_book_has_no_back(curriculum: Curriculum) -> None:
    item = curriculum.lessons[0].items[0]
    kb = screens.card(curriculum, item, has_audio=False, is_teacher=False).keyboard
    assert [t for t, _ in _nav_row(kb)] == [texts.HOME_BUTTON, texts.NEXT_BUTTON]


def test_card_with_video_and_audio_has_both(curriculum: Curriculum) -> None:
    item = curriculum.item("L004-02")
    videos = InMemoryVideos({item.text: "ra"})
    kb = screens.card(curriculum, item, has_audio=True, is_teacher=False, videos=videos).keyboard
    first = [t for t, _ in _rows(kb)[0]]
    assert first[:2] == [texts.LISTEN_BUTTON, texts.VIDEO_BUTTON]


def test_result_nav_matches_card(curriculum: Curriculum, renderer: FeedbackRenderer) -> None:
    r = _with_errors(curriculum, renderer)
    kb = screens.result(curriculum, r, has_audio=True).keyboard
    assert [t for t, _ in _nav_row(kb)] == NAV
    assert [t for t, _ in _rows(kb)[0]] == [texts.LISTEN_BUTTON, texts.DEEP_BUTTON]
    assert [texts.AGAIN_BUTTON, texts.DISPUTE_BUTTON] in [[t for t, _ in r] for r in _rows(kb)]


def test_result_of_last_step_goes_to_next_lesson(curriculum: Curriculum) -> None:
    last = curriculum.lessons[10].items[-1]
    r = _result(curriculum, last.id, last.text, completed=True)
    kb = screens.result(curriculum, r, has_audio=False).keyboard
    nxt = curriculum.next_item(last.id)
    assert nxt is not None
    assert (texts.NEXT_BUTTON, cb.GoItem(item_id=nxt.id).pack()) in _nav_row(kb)
    assert texts.SHARE_BUTTON in _labels(kb)


def test_deep_offers_book_page_and_home(curriculum: Curriculum) -> None:
    """Автор 2026-11-08: из «Подробнее» — картинка этой страницы книги; 🏠 рядом с «К уроку»."""
    item = curriculum.item("L045-03")
    assert item.source is not None and item.source.page == 35
    kb = screens.deep(curriculum, item, book_page=True).keyboard
    rows = _rows(kb)
    assert rows[0] == [(texts.BOOK_PAGE_BUTTON, cb.BookPage(page=35, item_id=item.id).pack())]
    assert [t for t, _ in rows[-1]] == [texts.DEEP_BACK_BUTTON, texts.HOME_BUTTON]


def test_book_page_screen_has_picture_and_way_back(curriculum: Curriculum) -> None:
    item = curriculum.item("L045-03")
    s = screens.book_page(item, 35, b"jpg")
    assert s.image == b"jpg" and "35" in s.caption
    assert (texts.DEEP_BACK_BUTTON, cb.GoItem(item_id=item.id).pack()) in _rows(s.keyboard)[0]


async def test_dir_book_pages_reads_only_existing(tmp_path: Path) -> None:
    from muallim.infrastructure.curriculum.book_pages import DirBookPages  # noqa: PLC0415

    (tmp_path / "035.jpg").write_bytes(b"x")
    pages = DirBookPages(tmp_path)
    assert pages.has(35) and not pages.has(36)
    assert await pages.get(35) == b"x" and await pages.get(36) is None


# ---------- урок = страница книги (автор 2026-11-08) ----------
def test_pages_cover_the_whole_book_in_order(curriculum: Curriculum) -> None:
    pages = curriculum.pages()
    assert [p.number for p in pages] == list(range(10, 86))
    assert sum(len(p.items) for p in pages) == sum(len(les.items) for les in curriculum.lessons)
    assert curriculum.page(46).items == ()  # только правило изхара


def test_page_intro_shows_scan_title_and_start(curriculum: Curriculum) -> None:
    page = curriculum.page(11)
    s = screens.page_intro(curriculum, page, b"jpg")
    assert s.image == b"jpg" and "Страница 11" in s.caption and "ر ز م" in s.caption
    rows = _rows(s.keyboard)
    assert rows[0] == [(texts.PAGE_START, cb.GoItem(item_id=page.items[0].id).pack())]
    assert [t for t, _ in rows[-1]] == NAV


def test_rule_only_page_has_no_start_but_goes_on(curriculum: Curriculum) -> None:
    s = screens.page_intro(curriculum, curriculum.page(46), None)
    assert texts.PAGE_RULE_ONLY in s.caption
    assert (texts.NEXT_BUTTON, cb.PageOpen(n=47).pack()) in _rows(s.keyboard)[-1]


def test_last_step_of_page_leads_to_next_page_intro(curriculum: Curriculum) -> None:
    last = curriculum.page(11).items[-1]
    kb = screens.card(curriculum, last, has_audio=False, is_teacher=False).keyboard
    assert (texts.NEXT_BUTTON, cb.PageOpen(n=12).pack()) in _nav_row(kb)
