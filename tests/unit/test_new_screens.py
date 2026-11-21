"""Экраны из макетов (ADR-0050): формы буквы, разбор по словам, открытка, прогресс.

Экран «начало занятия» убран (автор 2026-11-21: истиазы в книге нет)."""

from datetime import date
from typing import Any
from uuid import UUID

import pytest
from aiogram.types import InlineKeyboardMarkup

from muallim.application.feedback import Explanation
from muallim.application.use_cases.progress import LessonProgress, Progress
from muallim.application.use_cases.recitation import RecitationResult
from muallim.domain.assessment import assess
from muallim.domain.attempt import Attempt
from muallim.domain.curriculum import Curriculum, ItemKind, Lesson
from muallim.domain.phonetics import Zone, articulation_zone
from muallim.domain.policy import GradingPolicy
from muallim.presentation.telegram import callbacks as cb
from muallim.presentation.telegram import render, screens, texts
from tests.fakes import FixedClock

PNG = b"\x89PNG"
TODAY = date(2026, 10, 18)
needs_raqm = pytest.mark.skipif(not render.available(), reason="нет libraqm (brew install fribidi)")


def _buttons(kb: InlineKeyboardMarkup) -> list[tuple[str, Any]]:
    return [(b.text, b.callback_data) for row in kb.inline_keyboard for b in row]


def _progress(
    c: Curriculum, done: frozenset[str] = frozenset(), today_attempts: int = 0
) -> Progress:
    lessons = tuple(
        LessonProgress(les, len(les.practice_items) if les.id in done else 0, ())
        for les in c.lessons
    )
    week = (True, False, True, True, False, True, today_attempts > 0)
    return Progress(
        lessons, 9, streak_days=2, today_attempts=today_attempts,
        continue_item=c.first_item(), today=TODAY, week=week,
    )  # fmt: skip


def _letter_lesson(c: Curriculum, letter: str) -> Lesson:
    return next(les for les in c.lessons if les.section == "letter" and letter in les.title)


# ---------- зоны звука (SRC-059) ----------
@pytest.mark.parametrize(
    ("letter", "zone"),
    [
        ("ء", Zone.THROAT), ("أ", Zone.THROAT), ("ه", Zone.THROAT), ("ع", Zone.THROAT),
        ("ح", Zone.THROAT), ("غ", Zone.THROAT), ("خ", Zone.THROAT),
        ("ب", Zone.LIPS), ("م", Zone.LIPS), ("و", Zone.LIPS), ("ف", Zone.LIPS),
        ("ر", Zone.TONGUE), ("ق", Zone.TONGUE), ("ص", Zone.TONGUE), ("ي", Zone.TONGUE),
        ("ا", None), ("x", None),
    ],
)  # fmt: skip
def test_articulation_zone(letter: str, zone: Zone | None) -> None:
    assert articulation_zone(letter) is zone


# ---------- неделя в прогрессе ----------
def test_progress_week_is_seven_days_ending_today(curriculum: Curriculum) -> None:
    p = _progress(curriculum, today_attempts=1)
    assert len(p.week) == 7 and p.week[-1] is True


# ---------- разбор по словам ----------
def test_word_states_mark_wrong_and_unread_words() -> None:
    text = "صُمْ صِفْ فَصْ"
    letters = render.clusters(text)
    first_word = {n for n, c in enumerate(letters) if c.start < 4}
    last_word = {n for n, c in enumerate(letters) if c.start >= text.rindex(" ")}
    states = render.word_states(text, wrong=first_word, unread=last_word)
    assert states == [render.WordState.WRONG, render.WordState.OK, render.WordState.UNREAD]


@needs_raqm
def test_result_image_is_words(curriculum: Curriculum) -> None:
    item = next(
        i for les in curriculum.lessons for i in les.items
        if i.kind is ItemKind.LINE and len(i.text.split()) > 3
    )  # fmt: skip
    a = assess(item.text, item.text[:-2])
    attempt = Attempt(
        UUID(int=1), UUID(int=2), item.id, "v", "stub", a, GradingPolicy().verdict(a),
        None, None, 1, FixedClock().now(),
    )  # fmt: skip
    r = RecitationResult(item, attempt, (Explanation("x"),), "", None)
    s = screens.result(curriculum, r, has_audio=False)
    assert s.image is not None and s.image.startswith(PNG)


# ---------- урок пройден — без открытки (автор 2026-11-21) ----------
def _done_result(c: Curriculum) -> RecitationResult:
    lesson = _letter_lesson(c, "Мим")
    item = lesson.practice_items[-1]
    a = assess(item.text, item.text)
    attempt = Attempt(
        UUID(int=1), UUID(int=2), item.id, "v", "stub", a, GradingPolicy().verdict(a),
        None, None, 1, FixedClock().now(),
    )  # fmt: skip
    return RecitationResult(item, attempt, (), "", c.next_item(item.id), lesson_completed=True)


def test_completed_lesson_does_not_distract(curriculum: Curriculum) -> None:
    """Автор 2026-11-21: «Урок пройден!», открытка и «Поделиться» убраны — не отвлекать ученика.
    Урок по-прежнему засчитывается (прогресс), просто без поздравления."""
    r = _done_result(curriculum)
    s = screens.result(curriculum, r, has_audio=False)
    shown = s.caption + " ".join(t for t, _ in _buttons(s.keyboard))
    assert "Урок пройден" not in shown and "Поделиться" not in shown
    assert not [d for _, d in _buttons(s.keyboard) if d.startswith(cb.ShareLesson.__prefix__)]
    assert not hasattr(texts, "LESSON_DONE") and not hasattr(texts, "SHARE_BUTTON")


# ---------- прогресс ----------
@needs_raqm
def test_progress_image_is_book_parts_not_alphabet(curriculum: Curriculum) -> None:
    p = _progress(curriculum)
    assert screens.progress(curriculum, p).image != screens.home(curriculum, p).image


# ---------- карточка буквы ----------
@needs_raqm
def test_letter_card_shows_forms(curriculum: Curriculum) -> None:
    lesson = _letter_lesson(curriculum, "Мим")
    item = next(i for i in lesson.items if i.kind is ItemKind.LETTER)
    s = screens.card(curriculum, item, has_audio=False, is_teacher=False)
    assert s.image is not None and s.image != render.card(item.text, lesson.accent, (0, 1))
