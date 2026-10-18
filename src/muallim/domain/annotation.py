"""Разметка попыток человеком: метки, проверка фонем, коды разметчиков и приглашения.

Одни и те же правила для пакета Excel (``research/annotation.py``) и разметки в Telegram (FR-17):
руководство — docs/data/annotation-guide.md. Разметчик видит ответ бота: ``agree`` — бот прав,
``fix`` — записать, что прозвучало на самом деле (решение автора 2026-10-18, ADR-0040).
"""

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Final
from uuid import UUID

from muallim.domain.phonetics import CONSONANTS, SPECIAL, VOWELS

# Версия docs/data/annotation-guide.md — пишется в каждую метку (это проверяет тест).
GUIDE_VERSION: Final = "2.0"


class AnnotationStatus(StrEnum):
    AGREE = "agree"  # бот услышал верно: actual = что услышал бот
    FIX = "fix"  # бот ошибся: в actual — что прозвучало на самом деле
    AUDIO_UNUSABLE = "audio_unusable"  # шум, тишина, обрезано, несколько голосов
    OFF_TASK = "off_task"  # прочитано не то, что на карточке


USABLE: Final = frozenset({AnnotationStatus.AGREE, AnnotationStatus.FIX})  # попытку можно оценить


class AnnotationSource(StrEnum):
    EXCEL = "excel"  # пакет tasks.csv
    TELEGRAM = "telegram"  # кнопки в боте


PHONEME_ALPHABET: Final = CONSONANTS | VOWELS | SPECIAL
# Частые описки при наборе арабского текста вместо фонетической записи (SRC-002).
_HINTS: Final = {
    **dict.fromkeys("أإآؤئ", "хамза пишется одним знаком «ء»"),
    "ّ": "удвоение пишется двумя одинаковыми буквами, без шадды",
    "ْ": "сукун не пишется: согласная без огласовки",
    **dict.fromkeys("ًٌٍ", "танвин пишется огласовкой и «ن»"),
}
# Невидимые знаки, которые добавляют Excel, редакторы и Telegram (направление письма, BOM).
_INVISIBLE: Final = str.maketrans(
    dict.fromkeys("\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069\ufeff", None)
)
_ANNOTATOR_CODE: Final = re.compile(r"[A-Za-z0-9_-]{1,64}")

INVITE_TTL: Final = timedelta(hours=24)  # приглашение действует сутки и один раз
MAX_INVITE_FAILURES: Final = 5  # неверных кодов подряд — и вход закрыт…
INVITE_LOCK: Final = timedelta(hours=1)  # …на час: подбирать код бессмысленно


class LabelError(ValueError):
    """Метка противоречит правилам руководства; текст — что исправить, для разметчика."""


def clean_phonemes(text: str) -> str:
    """Без пробелов и невидимых знаков."""
    return "".join(text.translate(_INVISIBLE).split())


def check_phonemes(text: str) -> None:
    """Запись — только символами фонетического алфавита модели; иначе — подсказка, что не так."""
    if not text:
        raise LabelError("пустое поле «что прозвучало»")
    for ch in text:
        if ch not in PHONEME_ALPHABET:
            hint = _HINTS.get(ch, "в записи только буквы и огласовки фонетического алфавита")
            raise LabelError(f"символ «{ch}» не фонема — {hint}")


def check_label(status: AnnotationStatus, actual: str | None, bot_heard: str) -> None:
    """«agree» — фонемы бота без правок, «fix» — с правками: иначе метка противоречит записи."""
    if status is AnnotationStatus.AGREE and actual != bot_heard:
        raise LabelError(
            "стоит «agree», но «что прозвучало» отличается от того, что услышал бот. "
            "Бот ошибся — поставьте «fix»; согласны — верните его вариант."
        )
    if status is AnnotationStatus.FIX and actual == bot_heard:
        raise LabelError("стоит «fix», но ничего не исправлено. Если бот прав — поставьте «agree».")


def valid_annotator_code(code: str) -> bool:
    """Код разметчика (A1, A2…): латиница, цифры, «-» и «_», до 64 символов. Имени — нет."""
    return bool(_ANNOTATOR_CODE.fullmatch(code))


def invite_digest(code: str) -> str:
    """Отпечаток кода приглашения: в БД хранится он, а не сам код (утечка БД не даёт войти)."""
    normal = "".join(code.split()).replace("-", "").upper()
    return hashlib.sha256(normal.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class AnnotationTask:
    """Попытка в очереди разметчика: что читал ученик и что ответил бот. Кто ученик — не видно."""

    attempt_id: UUID
    item_id: str
    item_text: str
    page: int | None
    line: int | None
    bot_passed: bool
    bot_errors: tuple[tuple[str, str], ...]  # (нужно, услышано); "" — звука нет
    reference_phonemes: str
    bot_heard: str
    learner_says: str | None  # причина «бот ошибся» от ученика (ReportReason) или None
    audio_sha256: str


@dataclass(frozen=True, slots=True)
class Label:
    attempt_id: UUID
    annotator: str
    status: AnnotationStatus
    actual: str | None  # что прозвучало; None — оценить нельзя (audio_unusable, off_task)
    comment: str
    source: AnnotationSource
    seconds_spent: int | None  # от показа записи до ответа (только Telegram)
    created_at: datetime
