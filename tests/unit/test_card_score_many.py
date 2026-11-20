"""Решение по карточке с баллами одним вызовом и «не расслышано» (FR-70 п. 4, 6; ADR-0088 п. 2,
6; блокеры ревью «подсчёт вариантов в потоке бота» и «тишина дважды подряд — засчитано»).

Предложенный интерфейс:

- ``decide(..., score_many=None)`` — ``Callable[[Sequence[str]], Sequence[float]]``: баллы
  многих вариантов одним вызовом (батч-CTC). Передан — используется вместо поштучного ``score``;
  решение то же.
- ``CardDecision.unheard: bool`` — «ещё раз», потому что бот не расслышал (все баллы −inf или
  верное невозможно, а слышно только короче верного); у обычного «ещё раз» (не уверен) — False.
- Тишина — не попытка: правило в сценарии (`test_card_recitation.py`), ``after_repeat`` его не
  различает.

Карточки — из `curriculum/course.ru.yaml` («بُ», «رَ رِ رُ», «رَبَّ», «كَلَامُ»), строки — их
запись фонетизатором бота (как в `test_card_check.py`).
"""

import math
from collections.abc import Callable, Mapping, Sequence

import pytest

from muallim.domain.card_check import decide
from muallim.domain.policy import CardPolicy

UNHEARD = -1000.0

# (верные чтения, отдельные слоги, урок, таблица баллов) — разные исходы и правила
CASES: list[tuple[list[str], bool, int, dict[str, float]]] = [
    (["بُ"], True, 10, {"بُ": -1.0, "بَ": -5.0}),  # засчитано
    (["بُ"], True, 10, {"بُ": -5.0, "بَ": -3.0}),  # ещё раз
    (["بُ"], True, 10, {"بُ": -10.0, "بِ": -2.0}),  # ошибка
    (["بُ"], True, 10, {"بُ": -10.0, "زُ": -3.0}),  # другой слог
    (["رَرِرُ"], True, 4, {"رَرِرُ": -10.0, "رَرِر": -1.0}),  # последняя гласная
    (["رَببَ", "رَببڇ"], False, 38, {"رَببَ": -10.0, "رَببڇ": -11.0, "رَبَ": -2.0}),  # шадда
    (["كَلَاامُ", "كَلَاااام"], False, 34, {"كَلَاااام": -1.0, "كَلَاامِ": -6.0}),
]


def _table(table: Mapping[str, float], unheard: float = UNHEARD) -> Callable[[str], float]:
    return lambda variant: table.get(variant, unheard)


class _Batch:
    """score_many по той же таблице; считает вызовы и сколько вариантов спросили."""

    def __init__(self, score: Callable[[str], float]) -> None:
        self.score = score
        self.calls: list[int] = []

    def __call__(self, variants: Sequence[str]) -> list[float]:
        self.calls.append(len(variants))
        return [self.score(v) for v in variants]


@pytest.mark.parametrize(("accepted", "separate", "lesson", "table"), CASES)
def test_score_many_gives_the_same_decision(
    accepted: list[str], separate: bool, lesson: int, table: dict[str, float]
) -> None:
    policy = CardPolicy()
    rules = policy.rules_for(lesson)
    one_by_one = decide(accepted, _table(table), policy, separate_syllables=separate, rules=rules)
    batch = _Batch(_table(table))
    batched = decide(
        accepted, _table(table), policy, separate_syllables=separate, rules=rules,
        score_many=batch,
    )  # fmt: skip
    assert batched == one_by_one


@pytest.mark.parametrize(("accepted", "separate", "lesson", "table"), CASES)
def test_score_many_is_called_once_or_twice_not_per_variant(
    accepted: list[str], separate: bool, lesson: int, table: dict[str, float]
) -> None:
    """Вариантов у карточки десятки–сотни («другой слог» — каждая буква); вызовов — 1–2, и
    поштучный ``score`` не нужен."""
    single: list[str] = []

    def spy(variant: str) -> float:
        single.append(variant)
        return _table(table)(variant)

    batch = _Batch(_table(table))
    policy = CardPolicy()
    decide(
        accepted, spy, policy, separate_syllables=separate, rules=policy.rules_for(lesson),
        score_many=batch,
    )  # fmt: skip
    assert 1 <= len(batch.calls) <= 2
    assert sum(batch.calls) > 10  # спросили сразу много вариантов
    assert single == []


def test_score_many_with_silence_is_the_same_decision() -> None:
    silent = _table({}, unheard=-math.inf)
    one = decide(["بُ"], silent, CardPolicy(), separate_syllables=True)
    many = decide(["بُ"], silent, CardPolicy(), separate_syllables=True, score_many=_Batch(silent))
    assert many == one


# ---------- «не расслышано» в решении ----------
def test_silence_is_again_marked_unheard() -> None:
    d = decide(["بُ"], _table({}, unheard=-math.inf), CardPolicy(), separate_syllables=True)
    assert d.outcome == "again"
    assert d.unheard is True


def test_recording_shorter_than_the_correct_reading_is_unheard() -> None:
    """Верное −inf, слышно только «нет гласной» (короче верного) — бот не расслышал."""
    d = decide(["بُ"], _table({"ب": -2.0}, unheard=-math.inf), CardPolicy(), separate_syllables=True)
    assert d.outcome == "again"
    assert d.unheard is True


@pytest.mark.parametrize(
    ("accepted", "separate", "table"),
    [
        (["بُ"], True, {"بُ": -5.0, "بَ": -3.0}),  # не уверен: ошибка чуть впереди
        (["رَرِرُ"], True, {"رَرِرُ": -10.0, "رَرِر": -1.0}),  # протяни последнюю гласную
    ],
)
def test_unsure_again_is_not_unheard(
    accepted: list[str], separate: bool, table: dict[str, float]
) -> None:
    d = decide(accepted, _table(table), CardPolicy(), separate_syllables=separate)
    assert d.outcome == "again"
    assert d.unheard is False


@pytest.mark.parametrize("table", [{"بُ": -1.0}, {"بُ": -10.0, "بِ": -2.0}])
def test_passed_and_error_are_not_unheard(table: dict[str, float]) -> None:
    d = decide(["بُ"], _table(table), CardPolicy(), separate_syllables=True)
    assert d.unheard is False
