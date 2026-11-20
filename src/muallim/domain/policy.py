"""Методические пороги оценки. Значения выбирает человек (CLAUDE.md, раздел «Только человек»)."""

import difflib
import sys
from dataclasses import dataclass
from enum import StrEnum

from muallim.domain.assessment import Assessment
from muallim.domain.phonetics import CONSONANTS


class Verdict(StrEnum):
    EXCELLENT = "excellent"  # верно, без замечаний
    PASSED = "passed"  # засчитано, есть мелкие неточности
    FAILED = "failed"  # нужно повторить
    AGAIN = "again"  # «прочитай ещё раз»: модель не уверена (ADR-0088 п. 6)


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


def is_mastered_verdict(verdict: Verdict) -> bool:
    """Карточка освоена по вердикту, а не по баллу (ADR-0088 п. 7): «ошибка» с баллом 85 — не
    освоена, «ещё раз» — тоже."""
    return verdict in (Verdict.EXCELLENT, Verdict.PASSED)


# Виды ошибок способа «варианты карточки» (docs/research/ERROR_RULES_DRAFT.md, утвердил автор
# 2026-11-19): уроки 3–30 — огласовка, похожая буква, нет гласной; с 31 — короткий мадд;
# с 38 — нет шадды. Шадда и мадд — только мягкая подсказка (ADR-0086 п. 3).
_BASE_RULES: frozenset[str] = frozenset({"vowel", "lookalike", "no_vowel"})
_SHORT_MADD_FROM = 31
_NO_SHADDA_FROM = 38
_SOFT_KINDS: frozenset[str] = frozenset({"short_madd", "no_shadda"})
# Уроки, где протянутая гласная на слоге — не ошибка (ADR-0086 п. 4)
_LONG_IS_SHORT_LESSONS = range(3, 31)


@dataclass(frozen=True, slots=True)
class CardPolicy:
    """Пороги «вариантов карточки» (ADR-0087 п. 4, ADR-0088 п. 4; утвердил автор 2026-11-19,
    строгие).

    Маржа — log P(верное) − log P(лучшая ошибка): ≥ ``pass_margin`` — «засчитано»,
    от ``error_margin`` до него — «прочитай ещё раз», ниже — «ошибка». Соперник «другой слог»
    (другая, не похожая буква): маржа ниже ``other_error`` — «ошибка», от ``other_error`` до
    ``other_again`` — «ещё раз».
    """

    pass_margin: float = 0.0  # ADR-0087 п. 4, ADR-0088 п. 4
    error_margin: float = -4.0
    other_again: float = -3.0
    other_error: float = -6.0

    def __post_init__(self) -> None:
        if not self.error_margin <= self.pass_margin:
            raise ValueError("Нужно error_margin <= pass_margin")
        if not self.other_error <= self.other_again <= self.pass_margin:
            raise ValueError("Нужно other_error <= other_again <= pass_margin")

    @property
    def soft_kinds(self) -> frozenset[str]:
        """Виды, которые дают только мягкую подсказку, не «ошибку» и не «ещё раз»."""
        return _SOFT_KINDS

    @property
    def maroof_lessons(self) -> range:
        """Уроки на «вариантах карточки» (MostafaMaroof): решение автора 2026-11-19 — вся книга и
        суры (ADR-0088); сузить — например, ``range(1, 42)``."""
        return range(1, sys.maxsize)

    def long_is_short(self, lesson: int) -> bool:
        return lesson in _LONG_IS_SHORT_LESSONS

    def rules_for(self, lesson: int) -> frozenset[str]:
        """Какие типичные ошибки ищем на уроке: только то, что уже пройдено (SRC-164)."""
        rules = set(_BASE_RULES)
        if lesson >= _SHORT_MADD_FROM:
            rules.add("short_madd")
        if lesson >= _NO_SHADDA_FROM:
            rules.add("no_shadda")
        return frozenset(rules)

    def after_repeat(self, previous: Verdict | None, current: Verdict) -> tuple[Verdict, bool]:
        """«Ещё раз» — не больше раза подряд (ADR-0087 п. 4): второй раз подряд — «засчитано»,
        попытка уходит учителю. Ответ — (вердикт, учителю ли)."""
        if current is Verdict.AGAIN and previous is Verdict.AGAIN:
            return Verdict.PASSED, True
        return current, False
