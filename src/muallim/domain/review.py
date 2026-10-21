"""«🔁 Повторение» 1·3·7 дней — вычисляется из истории попыток, без своей таблицы (FR-52 (б),
ADR-0062 п. 4 и «Решения автора 2026-10-21»).

Строка входит в повторение, если не засчитана и со второй попытки подряд; срок — следующий
местный день. Засчитана в срок или позже — следующая ступень (+3, затем +7 дней), после третьей —
выходит; не засчитана на повторении — сначала (+1 день); засчитана раньше срока — ничего не
меняется; просрочка не наказывается. На день — не больше ``REVIEW_DAILY_LIMIT`` строк: сначала
самые просроченные (затем по книге), свободные места — строки пройденных уроков с 1–2 буквами, в
которых ученик чаще всего ошибается.
"""

from collections import Counter
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum
from typing import Final

from muallim.domain.assessment import PronunciationError
from muallim.domain.curriculum import Curriculum, LessonItem
from muallim.domain.phonetics import CONSONANTS

# Параметры методики (M-18): меняет только автор (ADR-0062).
REVIEW_INTERVALS: Final[tuple[int, ...]] = (1, 3, 7)  # дней до следующей ступени
REVIEW_DAILY_LIMIT: Final[int] = 10  # строк на день (В2)
RECENT_ATTEMPTS_FOR_LETTERS: Final[int] = 20  # по скольким последним попыткам искать частые буквы
FREQUENT_LETTERS: Final[int] = 2  # сколько самых частых букв берём

_HAMZA_FORMS: Final[str] = "أإؤئآ"  # в фонемах Muaalem хамза — всегда «ء»


class ReviewReason(StrEnum):
    DUE = "due"  # подошёл срок по 1·3·7
    FREQUENT_LETTER = "frequent_letter"  # пройденная строка с буквой, где ученик часто ошибается


@dataclass(frozen=True, slots=True)
class Outcome:
    """Исход одной попытки: строка, местный день ученика, засчитана ли (вердикт не ``failed``)."""

    item_id: str
    day: date
    passed: bool


@dataclass(frozen=True, slots=True)
class ReviewState:
    item_id: str
    stage: int  # 1..len(REVIEW_INTERVALS)
    due: date


@dataclass(frozen=True, slots=True)
class ReviewEntry:
    item_id: str
    reason: ReviewReason


def schedule(outcomes: Iterable[Outcome]) -> dict[str, ReviewState]:
    """Строки в повторении сейчас; ``outcomes`` — в порядке попыток."""
    states: dict[str, ReviewState] = {}
    failed_once: set[str] = set()  # прошлая попытка строки вне повторения — не засчитана
    for o in outcomes:
        current = states.get(o.item_id)
        if current is None:
            if o.passed:
                failed_once.discard(o.item_id)
            elif o.item_id in failed_once:
                failed_once.discard(o.item_id)
                states[o.item_id] = _at(o.item_id, 1, o.day)
            else:
                failed_once.add(o.item_id)
        elif not o.passed:
            states[o.item_id] = _at(o.item_id, 1, o.day)
        elif o.day >= current.due:
            if current.stage >= len(REVIEW_INTERVALS):
                del states[o.item_id]
            else:
                states[o.item_id] = _at(o.item_id, current.stage + 1, o.day)
    return states


def _at(item_id: str, stage: int, day: date) -> ReviewState:
    return ReviewState(item_id, stage, day + timedelta(days=REVIEW_INTERVALS[stage - 1]))


def error_letters(errors: Iterable[PronunciationError]) -> dict[str, int]:
    """Сколько ошибок пришлось на каждую согласную эталона (огласовки не считаются)."""
    counts: Counter[str] = Counter()
    for e in errors:
        counts.update({c for c in e.expected if c in CONSONANTS})
    return dict(counts)


def due_today(
    states: Mapping[str, ReviewState],
    today: date,
    curriculum: Curriculum,
    *,
    passed_lessons: Collection[str] = (),
    letter_errors: Mapping[str, int] | None = None,
    limit: int = REVIEW_DAILY_LIMIT,
) -> tuple[ReviewEntry, ...]:
    """Строки на сегодня: к сроку (самые просроченные, затем по книге), затем — на свободные места
    до ``limit`` — строки пройденных уроков с самыми частыми буквами ошибок ученика (по книге).
    Строк, которых больше нет в программе, не показываем."""
    order = {item.id: n for n, item in enumerate(_book(curriculum))}
    due = sorted(
        (s for s in states.values() if s.due <= today and s.item_id in order),
        key=lambda s: (s.due, order[s.item_id]),
    )
    picked = [ReviewEntry(s.item_id, ReviewReason.DUE) for s in due[:limit]]
    letters = _frequent(letter_errors or {})
    if not letters:
        return tuple(picked)
    taken = {e.item_id for e in picked}
    for lesson in curriculum.lessons:
        if lesson.id not in passed_lessons:
            continue
        for item in lesson.practice_items:
            if len(picked) >= limit:
                return tuple(picked)
            if item.id not in taken and letters & _letters(item.text):
                picked.append(ReviewEntry(item.id, ReviewReason.FREQUENT_LETTER))
    return tuple(picked)


def _book(curriculum: Curriculum) -> Sequence[LessonItem]:
    return [item for lesson in curriculum.lessons for item in lesson.items]


def _frequent(letter_errors: Mapping[str, int]) -> set[str]:
    """Самые частые буквы; при равенстве — в порядке словаря (сортировка устойчивая)."""
    ranked = sorted((c for c, n in letter_errors.items() if n > 0), key=lambda c: -letter_errors[c])
    return set(ranked[:FREQUENT_LETTERS])


def _letters(text: str) -> set[str]:
    """Согласные строки так, как их пишет Muaalem (формы хамзы — «ء»)."""
    return {"ء" if c in _HAMZA_FORMS else c for c in text} & CONSONANTS
