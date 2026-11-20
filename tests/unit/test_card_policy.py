"""Пороги «вариантов карточки», «прочитай ещё раз» и освоение по вердикту (FR-70 п. 3, 4, 6, 8;
ADR-0087 п. 4, ADR-0088 п. 4, 6, 7). Значения порогов утвердил автор 2026-11-19."""

import pytest

from muallim.domain.curriculum import Curriculum
from muallim.domain.policy import CardPolicy, GradingPolicy, Verdict, is_mastered_verdict


def test_default_thresholds_are_the_approved_strict_ones() -> None:
    policy = CardPolicy()
    assert policy.pass_margin == 0.0
    assert policy.error_margin == -4.0
    assert policy.other_again == -3.0
    assert policy.other_error == -6.0


@pytest.mark.parametrize(
    "kwargs",
    [
        {"error_margin": 1.0},  # ошибка выше «засчитано»
        {"other_again": 1.0},  # «ещё раз» по другому слогу выше нуля
        {"other_error": -2.0},  # ошибка по другому слогу выше «ещё раз»
    ],
)
def test_thresholds_out_of_order_are_rejected(kwargs: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        CardPolicy(**kwargs)


@pytest.mark.parametrize(("lesson", "expected"), [(2, False), (3, True), (30, True), (31, False)])
def test_long_vowel_counts_as_short_on_lessons_3_to_30(lesson: int, expected: bool) -> None:
    assert CardPolicy().long_is_short(lesson) is expected


def test_again_is_a_separate_verdict() -> None:
    assert Verdict.AGAIN.value == "again"


def test_first_again_on_a_card_stays_again() -> None:
    policy = CardPolicy()
    for previous in (None, Verdict.PASSED, Verdict.FAILED, Verdict.EXCELLENT):
        assert policy.after_repeat(previous, Verdict.AGAIN) == (Verdict.AGAIN, False)


def test_second_again_in_a_row_is_passed_and_goes_to_the_teacher() -> None:
    assert CardPolicy().after_repeat(Verdict.AGAIN, Verdict.AGAIN) == (Verdict.PASSED, True)


@pytest.mark.parametrize("current", [Verdict.PASSED, Verdict.FAILED, Verdict.EXCELLENT])
@pytest.mark.parametrize("previous", [None, Verdict.AGAIN, Verdict.PASSED])
def test_passed_and_error_are_not_changed_by_repeat(
    previous: Verdict | None, current: Verdict
) -> None:
    assert CardPolicy().after_repeat(previous, current) == (current, False)


@pytest.mark.parametrize(
    ("verdict", "mastered"),
    [
        (Verdict.EXCELLENT, True),
        (Verdict.PASSED, True),
        (Verdict.AGAIN, False),
        (Verdict.FAILED, False),
    ],
)
def test_card_is_mastered_by_verdict_not_by_score(verdict: Verdict, mastered: bool) -> None:
    assert is_mastered_verdict(verdict) is mastered


def test_score_mastery_is_unchanged() -> None:
    assert GradingPolicy().is_mastered(80) and not GradingPolicy().is_mastered(79)


# [утвердить] ERROR_RULES_DRAFT: какие ошибки ищем на каком уроке — черновик
# `docs/research/ERROR_RULES_DRAFT.md` («Which rules on which lessons»), автор утвердит.
BASE = frozenset({"vowel", "lookalike", "no_vowel"})


@pytest.mark.parametrize(
    ("lesson", "rules"),
    [
        (3, BASE),
        (30, BASE),
        (31, BASE | {"short_madd"}),
        (37, BASE | {"short_madd"}),
        (38, BASE | {"short_madd", "no_shadda"}),
        (41, BASE | {"short_madd", "no_shadda"}),
        (42, BASE | {"short_madd", "no_shadda"}),
        (70, BASE | {"short_madd", "no_shadda"}),
    ],
)
def test_rules_checked_on_each_lesson(lesson: int, rules: frozenset[str]) -> None:
    assert CardPolicy().rules_for(lesson) == rules


def test_short_madd_and_missing_shadda_are_always_soft() -> None:
    """ADR-0086 п. 3: шадда и мадд — только мягкая подсказка, не «ошибка» и не «ещё раз»."""
    assert CardPolicy().soft_kinds == frozenset({"short_madd", "no_shadda"})


def test_new_check_covers_every_lesson_of_the_book_by_default(curriculum: Curriculum) -> None:
    """Решение автора 2026-11-19 (ADR-0088): MostafaMaroof — сразу на всю книгу и суры, Muaalem не
    нужна. Каждый урок программы идёт через «варианты карточки»."""
    lessons = CardPolicy().maroof_lessons
    assert all(lesson.number in lessons for lesson in curriculum.lessons)
