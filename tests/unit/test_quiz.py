"""Закрепление: вопросы «как читается слог» из пройденных букв (ADR-0025)."""

import pytest

from muallim.domain.curriculum import Curriculum, ItemKind
from muallim.domain.quiz import QuizError, make_question, question_from


def _letters(c: Curriculum) -> list:  # type: ignore[type-arg]
    return [les for les in c.lessons if les.section == "letter"]


def test_question_has_four_distinct_options_with_one_answer(curriculum: Curriculum) -> None:
    for seed in range(30):
        q = make_question(curriculum, _letters(curriculum)[:6], seed)
        assert len(q.options) == 4 and len(set(q.options)) == 4
        head = curriculum.item(q.item_id)
        assert q.prompt == head.text.split()[q.vowel]
        assert q.options[q.answer] == head.sound.split(" · ")[q.vowel]


def test_question_is_reproducible_from_callback_data(curriculum: Curriculum) -> None:
    q = make_question(curriculum, _letters(curriculum)[:6], seed=42)
    assert question_from(curriculum, q.item_id, q.vowel, q.seed) == q


def test_questions_only_from_given_lessons(curriculum: Curriculum) -> None:
    allowed = _letters(curriculum)[:3]
    ids = {i.id for les in allowed for i in les.items}
    assert all(make_question(curriculum, allowed, s).item_id in ids for s in range(20))


def test_needs_at_least_two_letters(curriculum: Curriculum) -> None:
    with pytest.raises(QuizError):
        make_question(curriculum, _letters(curriculum)[:1], seed=1)


# ---------- на каком уроке откроется закрепление (FR-49) ----------
def test_first_quiz_lesson_is_where_questions_become_possible(curriculum: Curriculum) -> None:
    """Правило «откроется на уроке …» живёт в домене, рядом с правилом вопроса."""
    from muallim.domain.quiz import first_quiz_lesson  # noqa: PLC0415 — новая функция

    opens = first_quiz_lesson(curriculum)
    assert opens is not None and opens.section == "letter"
    letters = _letters(curriculum)
    k = letters.index(opens)
    make_question(curriculum, letters[: k + 1], seed=0)  # с этим уроком — вопрос есть
    with pytest.raises(QuizError):
        make_question(curriculum, letters[:k], seed=0)  # без него — ещё нет


def test_first_quiz_lesson_is_none_without_letter_lessons(curriculum: Curriculum) -> None:
    from muallim.domain.quiz import first_quiz_lesson  # noqa: PLC0415

    only_start = Curriculum("test", "t-1", "Тест", curriculum.lessons[:2], curriculum.lexicon)
    assert first_quiz_lesson(only_start) is None


# ---------- отвлекающие варианты — из начатых букв (FR-49, решение автора 2026-10-20) ----------
def _started_sounds(lessons: list) -> set[str]:  # type: ignore[type-arg]
    return {
        s
        for les in lessons
        for i in les.items
        if i.kind is ItemKind.LETTER and i.sound
        for s in i.sound.split(" · ")
    }


def test_options_come_only_from_started_letters(curriculum: Curriculum) -> None:
    """Начаты ء, ر, ز — вариантов хватает на 4, поэтому чужих букв в ответах нет."""
    started = _letters(curriculum)[:3]
    allowed = _started_sounds(started)
    for seed in range(50):
        q = make_question(curriculum, started, seed)
        assert len(set(q.options)) == 4
        assert set(q.options) <= allowed, (seed, q.options)


def test_two_started_letters_still_give_four_options(curriculum: Curriculum) -> None:
    started = _letters(curriculum)[:2]
    for seed in range(30):
        assert len(set(make_question(curriculum, started, seed).options)) == 4
