"""Жалоба ученика на проверку: «бот ошибся» (FR-23, ADR-0020)."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class ReportReason(StrEnum):
    READ_CORRECTLY = "read_correctly"  # «я прочитал правильно»
    WRONG_ERROR = "wrong_error"  # «ошибка указана не та»
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class LearnerReport:
    attempt_id: UUID
    learner_id: UUID
    reason: ReportReason
    at: datetime
