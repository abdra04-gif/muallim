"""Мелкие текстовые помощники для экранов (screens.py). Без обращений к Telegram API."""

from html import escape
from uuid import UUID

from muallim.presentation.telegram import texts

MAX_ERRORS_SHOWN = 2  # в тексте — не больше двух пунктов, остальные на картинке (FR-54, ADR-0031)


def plural(n: int, forms: tuple[str, str, str]) -> str:
    """Склонение после числа: (1 «день», 2 «дня», 5 «дней») — 1/21 → первая форма, 2–4/22 →
    вторая, 5–20/11 → третья."""
    one, few, many = forms
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def times(n: int) -> str:
    """«(2 раза)» — сколько раз та же ошибка; одно место — ничего (FR-54)."""
    if n == 1:
        return ""
    return texts.GROUP_TIMES.format(n=n, word=plural(n, texts.TIMES_FORMS))


def bar(percent: int) -> str:
    n = round(percent / 10)
    return "▰" * n + "▱" * (10 - n)


def privacy(research_consent: bool) -> str:
    status = texts.CONSENT_ON if research_consent else texts.CONSENT_OFF
    return texts.PRIVACY_STATUS.format(status=status)


def attempt_code(attempt_id: UUID) -> str:
    """Короткий номер попытки для ученика и для поиска в БД (начало UUID)."""
    return attempt_id.hex[:8].upper()


def me(pseudonym: str) -> str:
    return texts.ME_TEXT.format(pseudonym=escape(pseudonym))
