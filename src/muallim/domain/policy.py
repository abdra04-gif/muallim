"""Методические пороги оценки. Значения выбирает человек (CLAUDE.md, раздел «Только человек»)."""

import difflib
from dataclasses import dataclass
from enum import StrEnum

from muallim.domain.assessment import Assessment
from muallim.domain.phonetics import CONSONANTS


class Verdict(StrEnum):
    EXCELLENT = "excellent"  # верно, без замечаний
    PASSED = "passed"  # засчитано, есть мелкие неточности
    FAILED = "failed"  # нужно повторить


@dataclass(frozen=True, slots=True)
class GradingPolicy:
    pass_threshold: int = 80
    excellent_threshold: int = 90
    # Согласных совпало меньше (%) — «похоже, прочитана другая строка» (автор, 2026-11-08)
    other_line_threshold: int = 20

    def __post_init__(self) -> None:
        if not 0 <= self.pass_threshold <= self.excellent_threshold <= 100:
            raise ValueError("Нужно 0 <= pass_threshold <= excellent_threshold <= 100")

    def verdict(self, assessment: Assessment) -> Verdict:
        if assessment.score >= self.excellent_threshold and not assessment.errors:
            return Verdict.EXCELLENT
        if assessment.score >= self.pass_threshold:
            return Verdict.PASSED
        return Verdict.FAILED

    def is_other_line(self, assessment: Assessment) -> bool:
        """Совпало меньше порога согласных (%): гласные есть почти в любой строке и завышают
        сходство — чужая строка набирает по всем фонемам 20–30 %, а по согласным около 0."""
        ref, heard = (
            "".join(ch for ch in s if ch in CONSONANTS)
            for s in (assessment.reference, assessment.heard)
        )
        same = difflib.SequenceMatcher(None, ref, heard, autojunk=False).ratio()
        return round(100 * same) < self.other_line_threshold

    def is_mastered(self, best_score: int) -> bool:
        return best_score >= self.pass_threshold
