"""Закрепление: вопросы по начатым буквам (ADR-0025; с ADR-0066 — ``next_pick`` и
``build_question`` вместо случайного ``make_question``). Здесь — инварианты, которые были и раньше:
четыре разных варианта с одним верным, варианты из начатых букв, урок открытия (FR-49).
"""

from datetime import date

import pytest

from muallim.domain.curriculum import Curriculum, ItemKind, Lesson
from muallim.domain.quiz import (
    Pick,
    PickReason,
    QuizError,
    build_question,
    first_quiz_lesson,
    next_pick,
)


def _letters(c: Curriculum) -> list[Lesson]:
    return [les for les in c.lessons if les.section == "letter"]


def _heads(lessons: list[Lesson]) -> list[str]:
    return [i.id for les in lessons for i in les.items if i.kind is ItemKind.LETTER and i.sound]


def _pick(c: Curriculum, started: list[str]) -> Pick:
    return next_pick(
        c, started=started, history=(), round_len=0, today=date(2026, 10, 22), reading_errors={}
    )


def _all_questions(c: Curriculum, started: list[str], step: int):  # type: ignore[no-untyped-def]
    for letter in started:
        for vowel in range(3):
            yield build_question(c, Pick(letter, step, vowel, PickReason.OLD), started)


@pytest.mark.parametrize("step", [1, 2])
def test_question_has_four_distinct_options_with_one_answer(
    curriculum: Curriculum, step: int
) -> None:
    started = _heads(_letters(curriculum)[:6])
    for q in _all_questions(curriculum, started, step):
        assert len(q.options) == 4 and len(set(q.options)) == 4, q
        syllable = curriculum.item(q.item_id)
        right = syllable.sound if step == 1 else syllable.text
        assert q.options[q.answer] == right


def test_needs_at_least_two_letters(curriculum: Curriculum) -> None:
    with pytest.raises(QuizError):
        _pick(curriculum, _heads(_letters(curriculum)[:1]))


# ---------- на каком уроке откроется закрепление (FR-49) ----------
def test_first_quiz_lesson_is_where_questions_become_possible(curriculum: Curriculum) -> None:
    """Правило «откроется на уроке …» живёт в домене, рядом с правилом вопроса."""
    opens = first_quiz_lesson(curriculum)
    assert opens is not None and opens.section == "letter"
    letters = _letters(curriculum)
    k = letters.index(opens)
    _pick(curriculum, _heads(letters[: k + 1]))  # с этим уроком — вопрос есть
    with pytest.raises(QuizError):
        _pick(curriculum, _heads(letters[:k]))  # без него — ещё нет


def test_first_quiz_lesson_is_none_without_letter_lessons(curriculum: Curriculum) -> None:
    only_start = Curriculum("test", "t-1", "Тест", curriculum.lessons[:2], curriculum.lexicon)
    assert first_quiz_lesson(only_start) is None


# ---------- отвлекающие варианты — из начатых букв (FR-49, решение автора 2026-10-20) ----------
def _started_sounds(c: Curriculum, started: list[str]) -> set[str]:
    return {s for h in started for s in c.item(h).sound.split(" · ")}


def test_options_come_only_from_started_letters(curriculum: Curriculum) -> None:
    """Начаты ء, ر, ز — вариантов хватает на 4, поэтому чужих букв в ответах нет."""
    started = _heads(_letters(curriculum)[:3])
    allowed = _started_sounds(curriculum, started)
    for q in _all_questions(curriculum, started, 1):
        assert set(q.options) <= allowed, q.options


def test_two_started_letters_still_give_four_options(curriculum: Curriculum) -> None:
    started = _heads(_letters(curriculum)[:2])
    for step in (1, 2):
        for q in _all_questions(curriculum, started, step):
            assert len(set(q.options)) == 4, q.options


def test_hear_options_come_only_from_started_letters(curriculum: Curriculum) -> None:
    started = _heads(_letters(curriculum)[:3])
    allowed = {
        s.text
        for h in started
        for s in curriculum.locate(h)[0].items
        if s.kind is ItemKind.SYLLABLE
    }
    for q in _all_questions(curriculum, started, 2):
        assert set(q.options) <= allowed, q.options
        assert q.prompt == curriculum.item(q.item_id).text
