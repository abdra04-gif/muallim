"""Деление попыток на учёбу и тест (предрегистрация 0.7, ADR-0090, TD-FN-174). Только правило.

≈ 30 % попыток — в тест. Часть попытки — хеш её номера с солью: решение принимается при сохранении,
не меняется и повторяется без хранения списка. Соль выбирается один раз и до первого обучения
фиксируется отпечатком (SHA-256) в журнале исследования; где она лежит — забота infrastructure.
"""

import hashlib
from enum import StrEnum
from typing import Final
from uuid import UUID

TEST_SHARE: Final = 0.30  # решение автора 2026-11-21, предрегистрация 0.7
_SCALE: Final = 2**64


class Part(StrEnum):
    """Значения уходят в БД и выгрузки — не менять."""

    TRAIN = "train"
    TEST = "test"


def part_of(attempt_id: UUID, salt: bytes) -> Part:
    """Часть попытки: первые 8 байт SHA-256(соль + номер) как число в [0, 1) против доли теста."""
    digest = hashlib.sha256(salt + attempt_id.bytes).digest()
    share = int.from_bytes(digest[:8], "big") / _SCALE
    return Part.TEST if share < TEST_SHARE else Part.TRAIN
