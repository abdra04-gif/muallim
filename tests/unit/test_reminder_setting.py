"""Значения напоминания из кнопки (FR-51, ADR-0061, круг 4): минута суток и смещение от UTC.

Границы — те же, что CHECK в `learner_settings` (ADR-0055): минута 0…1439, смещение −720…840.
Кнопка от другой версии экрана или подделанная — ``ValueError`` (бот отвечает «устарела»).
"""

import pytest

from muallim.application.use_cases.settings import parse
from muallim.domain.settings import MAX_UTC_OFFSET_MIN, MIN_UTC_OFFSET_MIN, MINUTES_PER_DAY


@pytest.mark.parametrize("minute", [0, 7 * 60, 19 * 60, 23 * 60])
def test_reminder_minute_is_parsed_as_minute_of_local_day(minute: int) -> None:
    assert parse("reminder_minute", str(minute)) == minute


@pytest.mark.parametrize("offset", [2 * 60, 3 * 60, 5 * 60, 12 * 60])
def test_utc_offset_is_parsed_as_minutes(offset: int) -> None:
    assert parse("utc_offset_min", str(offset)) == offset


@pytest.mark.parametrize("value", [str(MINUTES_PER_DAY), "-1", "abc", "", "7.5", "19:00"])
def test_reminder_minute_outside_check_is_rejected(value: str) -> None:
    with pytest.raises(ValueError, match="reminder_minute"):
        parse("reminder_minute", value)


@pytest.mark.parametrize(
    "value", [str(MAX_UTC_OFFSET_MIN + 1), str(MIN_UTC_OFFSET_MIN - 1), "x", "", "true"]
)
def test_utc_offset_outside_check_is_rejected(value: str) -> None:
    with pytest.raises(ValueError, match="utc_offset_min"):
        parse("utc_offset_min", value)


def test_screen_state_is_not_a_setting_a_button_may_change() -> None:
    """Белый список: кнопкой — только настройки, не состояние экрана и не дата напоминания."""
    for name in ("reminder_sent_on", "screen_item_id", "opening_day"):
        with pytest.raises(ValueError, match=name):
            parse(name, "1")
