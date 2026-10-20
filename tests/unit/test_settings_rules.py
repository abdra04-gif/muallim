"""Правила настроек ученика: местная дата, начало занятия, напоминание (FR-51, TD-FN-90, ADR-0061).

Чистые правила `domain/settings.py` (stdlib). Решения автора 2026-10-21: смещение от UTC хранится
в минутах, до ответа «который у тебя час?» — UTC+3; напоминание раз в местный день в выбранную
минуту, не если сегодня уже занимался, окно догоняния 3 ч, после 14 дней молчания — пауза.
Ученики — Россия и Казахстан: смещения UTC+2…UTC+12 (Hypothesis, SRC-080).
"""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from hypothesis import given
from hypothesis import settings as hsettings
from hypothesis import strategies as st

from muallim.domain.settings import (
    HowToRead,
    LearnerSettings,
    local_date,
    needs_opening,
    reminder_due,
)

ISTI_ADHA, BASMALA = "L001-02", "L001-03"  # карточки начала занятия (ADR-0050)
offsets = st.integers(min_value=2, max_value=12).map(lambda h: h * 60)  # UTC+2…UTC+12, минуты
days = st.dates(min_value=date(2026, 1, 1), max_value=date(2030, 12, 31))


def _utc(day: date, minute: int, offset_min: int) -> datetime:
    """Момент UTC, когда у ученика со смещением offset_min идёт минута minute местного дня day."""
    midnight = datetime(day.year, day.month, day.day, tzinfo=UTC)
    return midnight + timedelta(minutes=minute - offset_min)


# ---------- умолчания: как бот работает сейчас + решения автора ----------
def test_defaults_match_current_bot_and_author_decisions() -> None:
    s = LearnerSettings()
    assert s.how_to_read is HowToRead.SPOILER  # «Закрыта» (ADR-0029)
    assert s.auto_reference is False  # В5
    assert s.daily_opening is True  # ADR-0050
    assert s.large_font is False
    assert s.research_block is False  # ADR-0057: по умолчанию выкл.
    assert s.reminder_minute is None  # напоминание выключено
    assert s.utc_offset_min == 180  # В3: до ответа — UTC+3
    assert s.screen_item_id is None and s.screen_opening is False  # на экране меню
    assert s.opening_resume_item is None and s.opening_day is None
    assert s.opening_skipped_on is None and s.reminder_sent_on is None


def test_how_to_read_values_are_the_db_values() -> None:
    assert {str(v) for v in HowToRead} == {"spoiler", "shown", "hidden"}


# ---------- местная дата ----------
def test_evening_utc_is_already_tomorrow_in_almaty() -> None:
    """UTC+5: 20:30 UTC — 01:30 следующего дня."""
    now = datetime(2026, 10, 21, 20, 30, tzinfo=UTC)
    assert local_date(now, 300) == date(2026, 10, 22)
    assert local_date(now, 180) == date(2026, 10, 21)  # Москва: 23:30 того же дня


@hsettings(max_examples=200, deadline=None)
@given(days, offsets)
def test_local_date_changes_exactly_at_local_midnight(day: date, offset: int) -> None:
    midnight = _utc(day, 0, offset)
    assert local_date(midnight, offset) == day
    assert local_date(midnight - timedelta(minutes=1), offset) == day - timedelta(days=1)
    assert local_date(midnight + timedelta(hours=23, minutes=59), offset) == day


# ---------- начало занятия (перенесено из presentation/telegram/opening.py) ----------
TODAY = date(2026, 10, 21)


def _opening(
    settings: LearnerSettings | None = None,
    *,
    first_lesson_done: bool = True,
    practiced_today: bool = False,
    cursor_item: str | None = "L006-01",
) -> bool:
    result: bool = needs_opening(
        settings or LearnerSettings(),
        today=TODAY,
        first_lesson_done=first_lesson_done,
        practiced_today=practiced_today,
        cursor_item=cursor_item,
    )
    return result


def test_opening_offered_when_lesson_one_done_and_not_practiced_today() -> None:
    assert _opening() is True


@pytest.mark.parametrize(
    "overrides",
    [
        {"first_lesson_done": False},  # новичку урока 1 не предлагается
        {"practiced_today": True},
        {"settings": LearnerSettings(opening_skipped_on=TODAY)},
        {"settings": LearnerSettings(daily_opening=False)},  # выключено в настройках
        {"cursor_item": ISTI_ADHA},  # вернулся повторить — без круга (TD-FN-90 п. 5)
        {"cursor_item": BASMALA},
    ],
    ids=["lesson_one_not_done", "practiced_today", "skipped_today", "turned_off",
         "cursor_on_isti_adha", "cursor_on_basmala"],
)  # fmt: skip
def test_opening_not_offered(overrides: dict[str, Any]) -> None:
    assert _opening(**overrides) is False


def test_yesterdays_skip_does_not_count_today() -> None:
    assert _opening(settings=LearnerSettings(opening_skipped_on=TODAY - timedelta(days=1)))


# ---------- напоминание ----------
NINE = 9 * 60  # 09:00 местного


def _on(minute: int = NINE, offset: int = 180, **kw: Any) -> LearnerSettings:
    return replace(LearnerSettings(), reminder_minute=minute, utc_offset_min=offset, **kw)


AT_NINE_MSK = datetime(2026, 10, 21, 6, 0, tzinfo=UTC)  # 09:00 по Москве
LOCAL_TODAY = date(2026, 10, 21)
YESTERDAY = LOCAL_TODAY - timedelta(days=1)


def test_reminder_due_at_chosen_local_minute() -> None:
    assert reminder_due(AT_NINE_MSK, _on(), YESTERDAY) is True


def test_reminder_not_due_when_turned_off() -> None:
    assert reminder_due(AT_NINE_MSK, LearnerSettings(), YESTERDAY) is False


def test_reminder_not_due_if_already_practiced_today() -> None:
    assert reminder_due(AT_NINE_MSK, _on(), LOCAL_TODAY) is False


def test_reminder_not_sent_twice_a_day() -> None:
    assert reminder_due(AT_NINE_MSK, _on(reminder_sent_on=LOCAL_TODAY), YESTERDAY) is False
    assert reminder_due(AT_NINE_MSK, _on(reminder_sent_on=YESTERDAY), YESTERDAY) is True


def test_reminder_uses_local_time_not_utc() -> None:
    """09:00 в Алматы (UTC+5) — это 04:00 UTC; в 06:00 UTC там 11:00 — ещё в окне."""
    assert reminder_due(datetime(2026, 10, 21, 4, 0, tzinfo=UTC), _on(offset=300), YESTERDAY)
    assert not reminder_due(datetime(2026, 10, 21, 3, 59, tzinfo=UTC), _on(offset=300), YESTERDAY)


def test_reminder_catch_up_window_is_three_hours() -> None:
    """Бот был выключен в 09:00 — напомнит до 11:59, в 12:00 уже нет (В4)."""
    assert reminder_due(AT_NINE_MSK + timedelta(hours=2, minutes=59), _on(), YESTERDAY)
    assert not reminder_due(AT_NINE_MSK + timedelta(hours=3), _on(), YESTERDAY)


def test_reminder_pauses_after_fourteen_days_of_silence() -> None:
    assert reminder_due(AT_NINE_MSK, _on(), LOCAL_TODAY - timedelta(days=14)) is True
    assert reminder_due(AT_NINE_MSK, _on(), LOCAL_TODAY - timedelta(days=15)) is False


@hsettings(max_examples=200, deadline=None)
@given(days, offsets, st.integers(min_value=0, max_value=1439 - 180))
def test_reminder_window_starts_at_chosen_minute_and_lasts_three_hours(
    day: date, offset: int, minute: int
) -> None:
    start = _utc(day, minute, offset)
    s, last = _on(minute, offset), day - timedelta(days=1)
    assert not reminder_due(start - timedelta(minutes=1), s, last)
    assert reminder_due(start, s, last)
    assert reminder_due(start + timedelta(minutes=179), s, last)
    assert not reminder_due(start + timedelta(minutes=180), s, last)


@hsettings(max_examples=25, deadline=None)
@given(days, offsets, st.integers(min_value=0, max_value=1439))
def test_silent_learner_gets_exactly_one_reminder_per_local_day(
    day: date, offset: int, minute: int
) -> None:
    """Тик раз в минуту двое суток; бот ставит reminder_sent_on (местная дата) при отправке."""
    s = _on(minute, offset)
    last = day - timedelta(days=1)  # вчера занимался, сегодня и завтра молчит
    sent: list[date] = []
    now = _utc(day, 0, offset)
    for _ in range(2 * 24 * 60):
        if reminder_due(now, s, last):
            today = local_date(now, offset)
            sent.append(today)
            s = replace(s, reminder_sent_on=today)
        now += timedelta(minutes=1)
    assert sent == [day, day + timedelta(days=1)]
