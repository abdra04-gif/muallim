"""Настройки ученика и состояние его экрана (FR-51, TD-FN-90, ADR-0061). Только правила.

Одна запись на ученика: выбор ученика (как показывать «Как читается», автозвук, начало занятия,
крупный шрифт, блок исследования, напоминание) и состояние экрана (что открыто, идёт ли начало
занятия) — чтобы перезапуск бота ничего не терял. Умолчания — как бот работал до настроек.

«Сегодня» для ученика — его местная дата: постоянное смещение от UTC в минутах (Россия без
летнего времени с 2014 г., Казахстан — единый UTC+5 с 2024 г.). До ответа «который у тебя час?» —
UTC+3 (решение автора 2026-10-21, В3).
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from typing import Final

DEFAULT_UTC_OFFSET_MIN: Final = 180  # UTC+3 — до ответа ученика (В3)
MIN_UTC_OFFSET_MIN: Final = -720  # UTC−12
MAX_UTC_OFFSET_MIN: Final = 840  # UTC+14
MINUTES_PER_DAY: Final = 24 * 60
REMINDER_CATCH_UP_MIN: Final = 3 * 60  # бот был выключен — напомнит не позже 3 ч (В4)
REMINDER_PAUSE_AFTER_DAYS: Final = 14  # молчит дольше — напоминания на паузе (В2)

OPENING_ITEMS: Final = ("L001-02", "L001-03")  # истиаза, басмала (ADR-0050)
FIRST_LESSON: Final = "L001"


class HowToRead(StrEnum):
    """Подсказка «🔤 Как читается» на карточке (ADR-0029)."""

    SPOILER = "spoiler"  # «Закрыта» — под спойлером (по умолчанию)
    SHOWN = "shown"  # «Видна сразу»
    HIDDEN = "hidden"  # «Не показывать»


@dataclass(frozen=True, slots=True)
class LearnerSettings:
    # выбор ученика
    how_to_read: HowToRead = HowToRead.SPOILER
    auto_reference: bool = False  # В5: автозвук выключен
    daily_opening: bool = True  # ADR-0050: начало занятия предлагается
    large_font: bool = False
    research_block: bool = False  # ADR-0057: блок исследования — по умолчанию выкл.
    reminder_minute: int | None = None  # минута местных суток; None — напоминание выключено
    utc_offset_min: int = DEFAULT_UTC_OFFSET_MIN
    # состояние экрана и начала занятия (TD-FN-90)
    screen_item_id: str | None = None  # None — на экране меню, не карточка
    screen_opening: bool = False  # карточка открыта как шаг начала занятия
    opening_resume_item: str | None = None  # куда вернуться после басмалы
    opening_day: date | None = None  # местная дата начала занятия: вчерашнее не действует
    opening_skipped_on: date | None = None  # «Пропустить» — местная дата
    reminder_sent_on: date | None = None  # местная дата последнего напоминания


def local_date(now: datetime, utc_offset_min: int) -> date:
    """Местная дата ученика в момент ``now`` (время с часовым поясом)."""
    return (now.astimezone(UTC) + timedelta(minutes=utc_offset_min)).date()


def _local_minute(now: datetime, utc_offset_min: int) -> int:
    local = now.astimezone(UTC) + timedelta(minutes=utc_offset_min)
    return local.hour * 60 + local.minute


def needs_opening(
    settings: LearnerSettings,
    *,
    today: date,
    first_lesson_done: bool,
    practiced_today: bool,
    cursor_item: str | None,
) -> bool:
    """Предложить начало занятия: включено, урок 1 пройден, сегодня не занимался и не пропускал.

    Новичку урока 1 не предлагается: урок и так с них начинается. Курсор на истиазе или басмале
    (вернулся повторить) — не предлагать: иначе «Продолжить» после басмалы открывает начало
    занятия по кругу (TD-FN-90 п. 5).
    """
    if not settings.daily_opening or not first_lesson_done or practiced_today:
        return False
    if cursor_item in OPENING_ITEMS:
        return False
    return settings.opening_skipped_on != today


def reminder_due(now: datetime, settings: LearnerSettings, last_practiced: date | None) -> bool:
    """Пора ли напомнить о занятии (В2, В4).

    Раз в местный день, с выбранной минуты и не позже окна догоняния (окно не переходит через
    местную полночь); не если сегодня уже занимался; после 14 дней молчания — пауза (на 15-й день
    уже нет). Ни разу не занимался, но включил напоминание — напоминать.
    """
    if settings.reminder_minute is None:
        return False
    today = local_date(now, settings.utc_offset_min)
    if settings.reminder_sent_on == today:
        return False
    if last_practiced is not None:
        if last_practiced >= today:
            return False
        if (today - last_practiced).days > REMINDER_PAUSE_AFTER_DAYS:
            return False
    late = _local_minute(now, settings.utc_offset_min) - settings.reminder_minute
    return 0 <= late < REMINDER_CATCH_UP_MIN
