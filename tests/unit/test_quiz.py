"""Закрепление: вопросы «как читается слог» из пройденных букв (ADR-0025)."""

import pytest

from muallim.domain.curriculum import Curriculum
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
