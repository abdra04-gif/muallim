"""«🔁 Повторение» 1·3·7 дней из истории попыток (FR-52 (б), ADR-0062 п. 4 и «Решения автора
2026-10-21»): чистые функции домена ``muallim.domain.review``.

Правила (решение автора): строка входит в повторение, только если не засчитана и со второй попытки
подряд; срок — следующий местный день; засчитана в срок или позже — следующая ступень (+3, затем
+7 дней), после третьей — выходит; не засчитана на повторении — сначала (+1); засчитана раньше
срока — ничего не меняется; просрочка не наказывается. На день — не больше 10 строк, сначала самые
просроченные, затем по книге; свободные места — строки пройденных уроков с 1–2 буквами, в которых
ученик чаще всего ошибается.
"""

from collections.abc import Sequence
from datetime import date, timedelta
from itertools import pairwise

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from muallim.domain import review
from muallim.domain.assessment import assess
from muallim.domain.curriculum import Curriculum, ItemKind, Lesson, LessonItem

settings.register_profile("project", max_examples=300, deadline=None)
settings.load_profile("project")

D0 = date(2026, 10, 17)
LINE = "L01-14"


def day(n: int) -> date:
    return D0 + timedelta(days=n)


def fail(n: int, item_id: str = LINE) -> review.Outcome:
    return review.Outcome(item_id, day(n), passed=False)


def ok(n: int, item_id: str = LINE) -> review.Outcome:
    return review.Outcome(item_id, day(n), passed=True)


def state(outcomes: Sequence[review.Outcome], item_id: str = LINE) -> tuple[int, date] | None:
    """(ступень, срок) строки или None — строки нет в повторении."""
    found = review.schedule(outcomes).get(item_id)
    return None if found is None else (found.stage, found.due)


# ---------- константы методики (M-18) ----------
def test_review_intervals_are_one_three_and_seven_days() -> None:
    assert review.REVIEW_INTERVALS == (1, 3, 7)


def test_review_daily_limit_is_ten_lines() -> None:
    assert review.REVIEW_DAILY_LIMIT == 10


# ---------- когда строка входит в повторение (В1) ----------
def test_line_failed_once_is_not_in_review() -> None:
    assert state([fail(0)]) is None


def test_line_failed_once_then_passed_is_not_in_review() -> None:
    assert state([fail(0), ok(0)]) is None


def test_line_failed_twice_in_a_row_enters_review_due_next_local_day() -> None:
    assert state([fail(0), fail(0)]) == (1, day(1))


def test_second_failure_on_a_later_day_makes_line_due_the_day_after_it() -> None:
    assert state([fail(0), fail(2)]) == (1, day(3))


def test_failures_separated_by_a_pass_do_not_enter_review() -> None:
    assert state([fail(0), ok(0), fail(1)]) is None


def test_failures_of_different_lines_are_not_counted_together() -> None:
    """Две неудачи подряд — по одной строке, а не две любые попытки ученика подряд."""
    other = "L01-15"
    result = review.schedule([fail(0, LINE), fail(0, other), ok(0, LINE), fail(0, other)])
    assert set(result) == {other}


def test_schedule_returns_state_with_item_stage_and_due() -> None:
    assert review.schedule([fail(0), fail(0)]) == {LINE: review.ReviewState(LINE, 1, day(1))}


# ---------- ступени 1 · 3 · 7 ----------
def test_passed_on_due_day_moves_line_to_second_stage_three_days_later() -> None:
    assert state([fail(0), fail(0), ok(1)]) == (2, day(4))


def test_passed_second_stage_moves_line_to_third_stage_seven_days_later() -> None:
    assert state([fail(0), fail(0), ok(1), ok(4)]) == (3, day(11))


def test_line_leaves_review_after_third_stage_is_passed() -> None:
    assert state([fail(0), fail(0), ok(1), ok(4), ok(11)]) is None


def test_passed_before_due_changes_nothing() -> None:
    assert state([fail(0), fail(0), ok(0)]) == (1, day(1))
    assert state([fail(0), fail(0), ok(1), ok(2)]) == (2, day(4))


def test_overdue_line_waits_without_penalty() -> None:
    """Пропущенный срок не наказывается: строка остаётся на своей ступени и ждёт."""
    assert state([fail(0), fail(0)]) == (1, day(1))
    assert state([fail(0), fail(0), ok(1), ok(20)]) == (3, day(27))


def test_failed_on_review_starts_over_due_next_day() -> None:
    assert state([fail(0), fail(0), ok(1), fail(4)]) == (1, day(5))
    assert state([fail(0), fail(0), ok(1), ok(4), fail(11)]) == (1, day(12))


def test_line_that_left_review_returns_after_two_new_failures_in_a_row() -> None:
    history = [fail(0), fail(0), ok(1), ok(4), ok(11)]
    assert state([*history, fail(30)]) is None
    assert state([*history, fail(30), fail(30)]) == (1, day(31))


# ---------- свойства (Hypothesis) ----------
histories = st.lists(
    st.tuples(st.integers(min_value=0, max_value=8), st.booleans()), max_size=25
)  # (сколько дней прошло с прошлой попытки, засчитана ли)


def _outcomes(steps: Sequence[tuple[int, bool]]) -> list[review.Outcome]:
    out: list[review.Outcome] = []
    n = 0
    for gap, passed in steps:
        n += gap
        out.append(review.Outcome(LINE, day(n), passed))
    return out


def _stage(outcomes: Sequence[review.Outcome]) -> int:
    found = review.schedule(outcomes).get(LINE)
    return 0 if found is None else found.stage


@given(st.lists(st.integers(min_value=0, max_value=8), max_size=25))
def test_line_without_failures_is_never_in_review(gaps: list[int]) -> None:
    assert review.schedule(_outcomes([(g, True) for g in gaps])) == {}


@given(histories)
def test_line_without_two_failures_in_a_row_is_never_in_review(
    steps: list[tuple[int, bool]],
) -> None:
    passed = [p for _, p in steps]
    if any(not a and not b for a, b in pairwise(passed)):
        return
    assert review.schedule(_outcomes(steps)) == {}


@given(histories)
def test_line_never_moves_more_than_one_stage_a_day(steps: list[tuple[int, bool]]) -> None:
    """За один местный день строка поднимается не больше чем на одну ступень (и выходит только
    с третьей); вниз — только сброс на первую."""
    outcomes = _outcomes(steps)
    days = sorted({o.day for o in outcomes})
    before = 0
    for d in days:
        after = _stage([o for o in outcomes if o.day <= d])
        if after == 0:
            assert before in (0, 3), (before, d)
        else:
            assert 1 <= after <= before + 1, (before, after, d)
        before = after


@given(histories)
def test_due_is_always_after_the_last_attempt_of_the_line(steps: list[tuple[int, bool]]) -> None:
    outcomes = _outcomes(steps)
    found = review.schedule(outcomes).get(LINE)
    if found is not None:
        assert found.due > outcomes[-1].day
        assert found.stage in (1, 2, 3)


# ---------- буквы, в которых ученик ошибается ----------
def test_error_letters_count_expected_consonants() -> None:
    errors = [*assess("صَ", "سَ").errors, *assess("صَ", "سَ").errors]
    assert review.error_letters(errors) == {"ص": 2}


def test_vowel_errors_do_not_count_as_letter_errors() -> None:
    errors = assess("بَ", "بِ").errors
    assert errors and review.error_letters(errors) == {}


# ---------- отбор на сегодня (В2) ----------
LETTERS = "أبتثجحخدذرزسشصضطظعغفقكلمنوهي"  # L01-14 — صَ


@pytest.fixture(scope="module")
def course(curriculum: Curriculum) -> Curriculum:
    letters = tuple(
        LessonItem(f"L01-{i:02}", f"{c}َ", ItemKind.LETTER, "x", name="x")
        for i, c in enumerate(LETTERS, start=1)
    )
    lines = tuple(
        LessonItem(f"L02-{i:02}", text, ItemKind.LINE, "")
        for i, text in enumerate(["رَرْ رِرْ", "أَزْ إِزْ", "مَرْمَرُ"], start=1)
    )
    return Curriculum(
        "test", "test-1", "Тест",
        (Lesson("L01", 1, "Буквы", letters), Lesson("L02", 2, "Строки", lines)),
        curriculum.lexicon,
    )  # fmt: skip


def _states(*items: tuple[str, date]) -> dict[str, review.ReviewState]:
    return {item_id: review.ReviewState(item_id, 1, due) for item_id, due in items}


def _ids(entries: Sequence[review.ReviewEntry]) -> list[str]:
    return [e.item_id for e in entries]


def test_only_lines_due_today_or_earlier_are_selected(course: Curriculum) -> None:
    states = _states(("L01-03", day(5)), ("L01-02", day(6)), ("L01-01", day(7)))
    got = review.due_today(states, day(6), course)
    assert _ids(got) == ["L01-03", "L01-02"]
    assert {e.reason for e in got} == {review.ReviewReason.DUE}


def test_most_overdue_first_then_book_order(course: Curriculum) -> None:
    states = _states(("L02-01", day(3)), ("L01-09", day(5)), ("L01-02", day(5)), ("L02-03", day(1)))
    got = review.due_today(states, day(6), course)
    assert _ids(got) == ["L02-03", "L02-01", "L01-02", "L01-09"]


def test_no_more_than_ten_lines_a_day_most_overdue_kept(course: Curriculum) -> None:
    states = _states(*((f"L01-{i:02}", day(i)) for i in range(1, 13)))
    got = review.due_today(states, day(20), course)
    assert _ids(got) == [f"L01-{i:02}" for i in range(1, 11)]


def test_line_removed_from_program_is_skipped(course: Curriculum) -> None:
    """Программа сменилась, а в истории — строка, которой больше нет: показать её нельзя."""
    states = _states(("L09-01", day(1)), ("L01-01", day(1)))
    assert _ids(review.due_today(states, day(6), course)) == ["L01-01"]


def test_free_places_go_to_passed_lines_with_two_most_frequent_error_letters(
    course: Curriculum,
) -> None:
    states = _states(("L01-05", day(1)))
    got = review.due_today(
        states, day(6), course, passed_lessons=["L02"], letter_errors={"ز": 4, "م": 2, "ر": 1}
    )
    assert got == (
        review.ReviewEntry("L01-05", review.ReviewReason.DUE),
        review.ReviewEntry("L02-02", review.ReviewReason.FREQUENT_LETTER),  # أَزْ إِزْ — ز
        review.ReviewEntry("L02-03", review.ReviewReason.FREQUENT_LETTER),  # مَرْمَرُ — م
    )


def test_single_error_letter_is_enough(course: Curriculum) -> None:
    got = review.due_today({}, day(6), course, passed_lessons=["L02"], letter_errors={"ر": 3})
    assert got == (
        review.ReviewEntry("L02-01", review.ReviewReason.FREQUENT_LETTER),
        review.ReviewEntry("L02-03", review.ReviewReason.FREQUENT_LETTER),
    )


def test_frequent_letter_lines_come_only_from_passed_lessons(course: Curriculum) -> None:
    states = _states(("L01-05", day(1)))
    got = review.due_today(states, day(6), course, passed_lessons=[], letter_errors={"ر": 3})
    assert _ids(got) == ["L01-05"]


def test_without_letter_errors_only_due_lines(course: Curriculum) -> None:
    states = _states(("L01-05", day(1)))
    got = review.due_today(states, day(6), course, passed_lessons=["L02"], letter_errors={})
    assert _ids(got) == ["L01-05"]


def test_due_line_is_not_repeated_as_frequent_letter_line(course: Curriculum) -> None:
    states = _states(("L02-02", day(1)))
    got = review.due_today(states, day(6), course, passed_lessons=["L02"], letter_errors={"ز": 5})
    assert got == (review.ReviewEntry("L02-02", review.ReviewReason.DUE),)


def test_frequent_letter_lines_only_fill_places_left_under_the_limit(course: Curriculum) -> None:
    nine = _states(*((f"L01-{i:02}", day(1)) for i in range(1, 10)))
    got = review.due_today(nine, day(6), course, passed_lessons=["L02"], letter_errors={"ر": 3})
    assert len(got) == review.REVIEW_DAILY_LIMIT
    assert got[-1] == review.ReviewEntry("L02-01", review.ReviewReason.FREQUENT_LETTER)

    ten = _states(*((f"L01-{i:02}", day(1)) for i in range(1, 11)))
    got = review.due_today(ten, day(6), course, passed_lessons=["L02"], letter_errors={"ر": 3})
    assert {e.reason for e in got} == {review.ReviewReason.DUE}
    assert len(got) == review.REVIEW_DAILY_LIMIT
