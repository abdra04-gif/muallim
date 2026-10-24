"""Формулы метрик пилота (FR-55, docs/research/metrics-gqm.md): G4 — путь новичка и продвижение
по книге, G3 — повтор после объяснения (разведка E-7), G5 — время ответа по дням."""

from datetime import UTC, date, datetime, timedelta

import pytest

from muallim.research.pilot import (
    ALL,
    WITH_REFERENCE,
    WITHOUT_REFERENCE,
    DayTiming,
    FirstSuccess,
    LessonEffort,
    RetryEffect,
    Try,
    attempts_to_pass,
    drop_off,
    first_success,
    response_by_day,
    retries,
    weekly_new_lines,
)

MON = datetime(2026, 10, 19, 9, 0, tzinfo=UTC)  # понедельник


def _try(
    learner: str,
    item: str,
    at: datetime,
    score: int,
    *,
    passed: bool | None = None,
    lesson: int | None = 1,
    reference: str = "صَ",
    errors: frozenset[tuple[int, str]] = frozenset(),
) -> Try:
    return Try(
        learner=learner, item_id=item, lesson=lesson, at=at, score=score,
        passed=score >= 80 if passed is None else passed, reference=reference, errors=errors,
    )  # fmt: skip


# ---------- Q4.4 главная метрика ----------
def test_line_counts_once_in_week_of_first_pass() -> None:
    """Строка засчитана в неделю первого зачёта; повторные зачёты и незачёты не считаются."""
    tries = [
        _try("A", "L01-1", MON, 50),
        _try("A", "L01-1", MON + timedelta(days=1), 90),  # первый зачёт — неделя 19.10
        _try("A", "L01-1", MON + timedelta(days=8), 95),  # повторный зачёт — не в счёт
        _try("A", "L01-2", MON + timedelta(days=7), 85),  # неделя 26.10
        _try("B", "L01-1", MON + timedelta(days=6, hours=14), 80),  # вс 23:00 UTC — ещё 19.10
        _try("B", "L01-3", MON, 10),  # не засчитана — не в счёт
    ]
    rows = weekly_new_lines(tries)
    assert [(r.week, r.lines, r.learners) for r in rows] == [
        (date(2026, 10, 19), 2, 2),
        (date(2026, 10, 26), 1, 1),
    ]


def test_passed_comes_from_stored_verdict_not_from_score() -> None:
    """Зачёт — по вердикту бота с порогами той попытки (attempts.policy), а не по нынешнему 80."""
    rows = weekly_new_lines([_try("A", "L01-1", MON, 75, passed=True)])
    assert [(r.lines) for r in rows] == [1]
    assert weekly_new_lines([_try("A", "L01-1", MON, 85, passed=False)]) == []


def test_weekly_new_lines_empty() -> None:
    assert weekly_new_lines([]) == []


# ---------- Q4.1 первый успех ----------
def test_first_success_same_day_and_median_minutes() -> None:
    registered = {"A": MON, "B": MON, "C": MON, "D": MON}
    tries = [
        _try("A", "L01-1", MON + timedelta(minutes=10), 90),  # в день регистрации, 10 мин
        _try("B", "L01-1", MON + timedelta(minutes=5), 40),
        _try("B", "L01-1", MON + timedelta(days=2), 90),  # через 2 дня = 2880 мин
        _try("C", "L01-1", MON + timedelta(minutes=3), 30),  # так и не засчитано
        # D — ни одной попытки
    ]
    s = first_success(registered, tries)
    assert s == FirstSuccess(learners=4, passed_ever=2, passed_same_day=1, median_minutes=1445.0)
    assert s.same_day_share == pytest.approx(0.25)


def test_first_success_without_learners() -> None:
    s = first_success({}, [])
    assert s == FirstSuccess(0, 0, 0, None) and s.same_day_share is None


# ---------- Q4.3 где бросают ----------
def test_drop_off_counts_lesson_of_last_attempt_of_idle_learners() -> None:
    today = date(2026, 11, 2)
    tries = [
        _try("A", "L01-1", MON, 90, lesson=1),
        _try("A", "L02-1", MON + timedelta(days=1), 40, lesson=2),  # A ушёл на уроке 2
        _try("B", "L01-1", MON, 90, lesson=1),  # B ушёл на уроке 1
        _try(
            "C", "L03-1", datetime(2026, 10, 27, tzinfo=UTC), 90, lesson=3
        ),  # ровно 6 дней — активен
        _try("D", "L03-1", datetime(2026, 10, 26, tzinfo=UTC), 90, lesson=3),  # ровно 7 дней — ушёл
        _try("E", "X-1", MON, 90, lesson=None),  # урок неизвестен (нет снимка программы)
    ]
    assert drop_off(tries, today) == {1: 1, 2: 1, 3: 1, None: 1}


# ---------- Q4.5 попыток до зачёта ----------
def test_attempts_to_first_pass_by_lesson() -> None:
    tries = [
        _try("A", "L01-1", MON, 90),  # 1 попытка
        _try("B", "L01-1", MON, 10),
        _try("B", "L01-1", MON + timedelta(minutes=1), 20),
        _try("B", "L01-1", MON + timedelta(minutes=2), 85),  # 3 попытки
        _try("B", "L01-1", MON + timedelta(minutes=3), 30),  # после зачёта — не в счёт
        _try("A", "L01-2", MON, 10),  # не засчитана
        _try("A", "L02-1", MON, 10, lesson=2),
        _try("A", "L02-1", MON + timedelta(minutes=1), 95, lesson=2),  # 2 попытки
    ]
    assert attempts_to_pass(tries) == {
        1: LessonEffort(passed=2, median_attempts=2.0, not_passed=1),
        2: LessonEffort(passed=1, median_attempts=2.0, not_passed=0),
    }


def test_attempts_are_ordered_by_time_not_by_input_order() -> None:
    tries = [_try("A", "L01-1", MON + timedelta(minutes=1), 90), _try("A", "L01-1", MON, 10)]
    assert attempts_to_pass(tries)[1].median_attempts == 2.0


# ---------- Q3.1–Q3.3 повтор после объяснения ----------
def test_retry_after_failed_attempt_delta_and_fixed_errors() -> None:
    """Пара — незасчитанная попытка и следующая попытка того же ученика по той же строке."""
    e = frozenset({(0, "ص"), (1, "َ")})
    tries = [
        _try("A", "L01-1", MON, 40, errors=e),
        _try("A", "L01-1", MON + timedelta(minutes=1), 70, errors=frozenset({(1, "َ")})),
        _try("A", "L01-1", MON + timedelta(minutes=2), 90),  # пара 2: 70 → 90, исправлено 1
        _try("A", "L01-1", MON + timedelta(minutes=3), 50),  # после зачёта — не пара
        _try("B", "L01-1", MON, 60, errors=frozenset({(0, "ص")})),
        _try("B", "L01-2", MON + timedelta(minutes=1), 90),  # другая строка — не пара
    ]
    effect = retries(tries, {})[ALL]
    assert effect == RetryEffect(pairs=2, mean_delta=25.0, improved=2, named=3, fixed=2)
    assert effect.improved_share == pytest.approx(1.0)
    assert effect.fixed_share == pytest.approx(2 / 3)


def test_named_errors_are_compared_only_with_the_same_reference() -> None:
    """Другой вариант эталона — позиции не совпадают; Δ балла есть, исправления не считаются."""
    tries = [
        _try("A", "L01-1", MON, 40, reference="صَ", errors=frozenset({(0, "ص")})),
        _try("A", "L01-1", MON + timedelta(minutes=1), 60, reference="صَا"),
    ]
    effect = retries(tries, {})[ALL]
    assert (effect.pairs, effect.named, effect.fixed) == (1, 0, 0)
    assert effect.fixed_share is None


def test_retry_split_by_reference_played_between_attempts() -> None:
    """Q3.3: эталон 🔊 той же строки прослушан после попытки n и до попытки n + 1."""
    tries = [
        _try("A", "L01-1", MON, 40),
        _try("A", "L01-1", MON + timedelta(minutes=5), 90),  # между ними — эталон
        _try("B", "L01-1", MON, 40),
        _try("B", "L01-1", MON + timedelta(minutes=5), 50),
    ]
    played = {
        ("A", "L01-1"): [MON + timedelta(minutes=2)],
        ("B", "L01-1"): [MON - timedelta(minutes=1)],  # до первой попытки — не между
        ("B", "L01-2"): [MON + timedelta(minutes=2)],  # другая строка — не в счёт
    }
    by = retries(tries, played)
    assert by[ALL].pairs == 2
    assert (by[WITH_REFERENCE].pairs, by[WITH_REFERENCE].mean_delta) == (1, 50.0)
    assert (by[WITHOUT_REFERENCE].pairs, by[WITHOUT_REFERENCE].mean_delta) == (1, 10.0)


def test_retries_without_pairs() -> None:
    effect = retries([_try("A", "L01-1", MON, 90)], {})[ALL]
    assert effect == RetryEffect(0, None, 0, 0, 0) and effect.improved_share is None


# ---------- Q5.1 время ответа по дням ----------
def test_response_time_by_day() -> None:
    rows = [(MON, 1000), (MON + timedelta(hours=1), 3000), (MON + timedelta(days=1), 2000)]
    assert response_by_day(rows) == [
        DayTiming(date(2026, 10, 19), attempts=2, p50_ms=1000, p90_ms=3000, max_ms=3000),
        DayTiming(date(2026, 10, 20), attempts=1, p50_ms=2000, p90_ms=2000, max_ms=2000),
    ]
