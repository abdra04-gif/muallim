"""Методические пороги оценки. Значения выбирает человек (CLAUDE.md, раздел «Только человек»)."""

from dataclasses import dataclass
from enum import StrEnum

from muallim.domain.assessment import Assessment


class Verdict(StrEnum):
    EXCELLENT = "excellent"  # верно, без замечаний
    PASSED = "passed"  # засчитано, есть мелкие неточности
    FAILED = "failed"  # нужно повторить


@dataclass(frozen=True, slots=True)
class GradingPolicy:
    pass_threshold: int = 80
    excellent_threshold: int = 90

    def __post_init__(self) -> None:
        if not 0 <= self.pass_threshold <= self.excellent_threshold <= 100:
            raise ValueError("Нужно 0 <= pass_threshold <= excellent_threshold <= 100")

    def verdict(self, assessment: Assessment) -> Verdict:
        if assessment.score >= self.excellent_threshold and not assessment.errors:
            return Verdict.EXCELLENT
        if assessment.score >= self.pass_threshold:
            return Verdict.PASSED
        return Verdict.FAILED

    def is_mastered(self, best_score: int) -> bool:
        return best_score >= self.pass_threshold
