"""Мелкие текстовые помощники для экранов (screens.py). Без обращений к Telegram API."""

from html import escape
from uuid import UUID

from muallim.presentation.telegram import texts

MAX_ERRORS_SHOWN = 3  # исправлять несколько мест, а не все сразу (ADR-0031)


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
