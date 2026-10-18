"""Пять экранов из макетов (ADR-0050): формы буквы, разбор по словам, открытка, прогресс, начало."""

from datetime import date, timedelta
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
from muallim.presentation.telegram.opening import OPENING_ITEMS, needs_opening
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


# ---------- открытка ----------
def _done_result(c: Curriculum) -> RecitationResult:
    lesson = _letter_lesson(c, "Мим")
    item = lesson.practice_items[-1]
    a = assess(item.text, item.text)
    attempt = Attempt(
        UUID(int=1), UUID(int=2), item.id, "v", "stub", a, GradingPolicy().verdict(a),
        None, None, 1, FixedClock().now(),
    )  # fmt: skip
    return RecitationResult(item, attempt, (), "", c.next_item(item.id), lesson_completed=True)


def test_completed_lesson_offers_share(curriculum: Curriculum) -> None:
    r = _done_result(curriculum)
    s = screens.result(curriculum, r, has_audio=False)
    lesson, _ = curriculum.locate(r.item.id)
    assert (texts.SHARE_BUTTON, cb.ShareLesson(lesson=lesson.id).pack()) in _buttons(s.keyboard)


def test_share_postcard_has_no_personal_data(curriculum: Curriculum) -> None:
    lesson = _letter_lesson(curriculum, "Мим")
    s = screens.postcard(curriculum, lesson, _progress(curriculum), bot_username="muallim_bot")
    assert "t.me/muallim_bot" in s.caption
    assert "L-" not in s.caption  # без псевдонима
    if render.available():
        assert s.image is not None and s.image.startswith(PNG)


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


# ---------- начало занятия (истиаза и басмала, SRC-110) ----------
def test_opening_items_are_isti_adha_then_basmala(curriculum: Curriculum) -> None:
    first, second = (curriculum.item(i) for i in OPENING_ITEMS)
    assert first.text.startswith("أَعُوذُ") and second.quran == "1:1"


def test_opening_needed_once_a_day_after_lesson_one(curriculum: Curriculum) -> None:
    beginner = _progress(curriculum)
    assert not needs_opening(beginner, skipped_on=None), "урок 1 и так начинается с них"
    after_one = _progress(curriculum, done=frozenset({"L001"}))
    assert needs_opening(after_one, skipped_on=None)
    assert not needs_opening(after_one, skipped_on=TODAY), "пропустил сегодня — не спрашивать"
    assert needs_opening(after_one, skipped_on=TODAY - timedelta(days=1))
    read_today = _progress(curriculum, done=frozenset({"L001"}), today_attempts=1)
    assert not needs_opening(read_today, skipped_on=None), "сегодня уже занимался"


def test_opening_screen_offers_read_and_skip(curriculum: Curriculum) -> None:
    s = screens.opening(curriculum)
    data = [d for _, d in _buttons(s.keyboard)]
    assert cb.Opening(act="start").pack() in data and cb.Opening(act="skip").pack() in data
    if render.available():
        assert s.image is not None and s.image.startswith(PNG)


def test_result_of_basmala_in_opening_continues_session(curriculum: Curriculum) -> None:
    basmala = curriculum.item(OPENING_ITEMS[1])
    resume = _letter_lesson(curriculum, "Мим").items[0]
    a = assess(basmala.text, basmala.text)
    attempt = Attempt(
        UUID(int=1), UUID(int=2), basmala.id, "v", "stub", a, GradingPolicy().verdict(a),
        None, None, 1, FixedClock().now(),
    )  # fmt: skip
    r = RecitationResult(basmala, attempt, (), "", curriculum.next_item(basmala.id))
    s = screens.result(curriculum, r, has_audio=False, resume=resume)
    assert cb.GoItem(item_id=resume.id).pack() in [d for _, d in _buttons(s.keyboard)]
