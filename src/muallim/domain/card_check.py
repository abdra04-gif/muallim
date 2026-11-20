"""«Варианты карточки»: верное чтение против типичных ошибок (ADR-0086, ADR-0087, ADR-0088 п. 3).

Модель только слушает: ``score(вариант)`` — log P(вариант | запись). Здесь — какие варианты ошибок
бывают у карточки (в записи фонетизатора бота) и какой ответ дать по их баллам. Пороги —
`policy.CardPolicy` (ADR-0087 п. 4, ADR-0088 п. 4). Прототип и замеры —
`docs/research/phase3/library_check.py::answer`
(правило последнего слога «ясная гласная», ADR-0087 п. 9).
"""

import math
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Final, Literal

from muallim.domain.phonetics import CONSONANTS, LONG_VOWELS, SHORT_VOWELS
from muallim.domain.policy import CardPolicy, Verdict

# Похожие буквы — пары буквенных тестов (`docs/research/phase3/compare_models.py::U_LOOK`);
# утверждает человек. Отношение симметрично: د похожа на ت — и ت на د.
LOOKALIKE: Final[dict[str, str]] = {
    "د": "تض", "ت": "دط", "ص": "س", "س": "صث", "ض": "د", "ط": "ت", "ظ": "زذ", "ز": "ظذ", "ث": "س",
    "ح": "ه", "ه": "ح", "ع": "ء", "ء": "ع", "ق": "ك", "ك": "ق", "ذ": "زظ",
}  # fmt: skip

ALL_RULES: Final = frozenset({"vowel", "lookalike", "no_vowel", "short_madd", "no_shadda"})
OTHER_SYLLABLE: Final = "other_syllable"
LAST_VOWEL: Final = "last_vowel"  # подсказка: «протяни последнюю гласную»
# Маржа «бесконечно» — только для записи в БД (JSON без inf); на решение не влияет
MARGIN_CAP: Final = 1000.0

# Гласные фонетизатора бота: огласовки, ималя ۪ (مَجْر۪ىٰهَا, L096-02) и краткая дамма ؙ
# (تَأْمَ۫نَّا, L096-03); знаки мадда — и протяжка ـ после ималя (`quran_transcript`)
_VOWEL_SIGNS: Final = SHORT_VOWELS | {"۪", "ؙ"}
_MADD_SIGNS: Final = LONG_VOWELS | {"ـ"}
_MADD_OF: Final = {"َ": "ا", "ِ": "ۦ", "ُ": "ۥ", "۪": "ـ", "ؙ": "ۥ"}  # огласовка → её знак мадда
_VOWEL_ORDER: Final = ("َ", "ِ", "ُ")

Outcome = Literal["passed", "again", "error"]


@dataclass(frozen=True, slots=True)
class CardDecision:
    """Ответ по карточке. ``winner`` — что, по мнению модели, прочитано: лучшее верное чтение
    («засчитано», «ещё раз») или победившая ошибка; ``kind`` — вид этой ошибки."""

    outcome: Outcome
    winner: str
    kind: str | None
    # Маржи уходят в ``attempts.model_output`` (JSON, без inf): бесконечность (соперника не слышно
    # совсем или верное невозможно) — ±``MARGIN_CAP``
    margin: float  # верное − лучшая типичная ошибка
    margin_other: float  # верное − лучший «другой слог»
    other_syllable: bool = False
    hints: tuple[str, ...] = ()
    unheard: bool = False  # «ещё раз», потому что бот не расслышал (тишина, слишком коротко)


@dataclass(frozen=True, slots=True)
class _Unit:
    """Буква (повтор — шадда) с огласовкой и знаками мадда: ``text[start:end]``."""

    start: int
    letter: str
    count: int
    vowel: str  # "" — без гласной
    madd: int
    end: int


def _units(text: str) -> list[_Unit]:
    units = []
    i = 0
    while i < len(text):
        c = text[i]
        if c not in CONSONANTS:
            i += 1
            continue
        j = i
        while j < len(text) and text[j] == c:
            j += 1
        vowel = text[j] if j < len(text) and text[j] in _VOWEL_SIGNS else ""
        k = j + bool(vowel)
        m = k
        while vowel and m < len(text) and text[m] in _MADD_SIGNS:
            m += 1
        units.append(_Unit(i, c, j - i, vowel, m - k, m))
        i = m
    return units


def _syllable(letter: str, count: int, vowel: str, madd: int) -> str:
    return letter * count + vowel + (_MADD_OF[vowel] * madd if vowel else "")


def _near(a: str, b: str) -> bool:
    return b in LOOKALIKE.get(a, "") or a in LOOKALIKE.get(b, "")


def _variants(
    text: str, rules: frozenset[str], *, separate_syllables: bool
) -> tuple[list[tuple[str, str]], list[str], list[str], str | None]:
    """Варианты ошибок: (вид, строка) типичных, «ясной гласной» последнего слога, «другого слога»
    и чтение без последней гласной (только для карточки из отдельных слогов)."""
    units = _units(text)
    typical: list[tuple[str, str]] = []
    tail: list[str] = []
    other: list[str] = []
    no_last: str | None = None
    for n, u in enumerate(units):

        def put(syllable: str, u: _Unit = u) -> str:
            return text[: u.start] + syllable + text[u.end :]

        is_last = separate_syllables and len(units) > 1 and n == len(units) - 1 and bool(u.vowel)
        if u.vowel:
            for o in _VOWEL_ORDER:
                if o != u.vowel:
                    variant = put(_syllable(u.letter, u.count, o, u.madd))
                    if is_last:
                        tail.append(variant)
                    elif "vowel" in rules:
                        typical.append(("vowel", variant))
            without = put(u.letter * u.count)
            if is_last:
                no_last = without
            elif "no_vowel" in rules:
                typical.append(("no_vowel", without))
            if u.madd and "short_madd" in rules:
                typical.append(("short_madd", put(_syllable(u.letter, u.count, u.vowel, 0))))
        if u.count > 1 and "no_shadda" in rules:
            typical.append(("no_shadda", put(_syllable(u.letter, 1, u.vowel, u.madd))))
        if "lookalike" in rules:
            typical.extend(
                ("lookalike", put(_syllable(o, u.count, u.vowel, u.madd)))
                for o in LOOKALIKE.get(u.letter, "")
            )
        other.extend(_other_syllables(text, u))
    return typical, tail, other, no_last


def _other_syllables(text: str, u: _Unit) -> list[str]:
    """Слог с другой, не похожей буквой и любой огласовкой (соперник «другой слог», §11.8g)."""
    vowels = _VOWEL_ORDER if u.vowel else ("",)
    return [
        text[: u.start] + _syllable(o, u.count, w, u.madd) + text[u.end :]
        for o in sorted(CONSONANTS)
        if o != u.letter and not _near(u.letter, o)
        for w in vowels
    ]


def _diff(a: float, b: float) -> float:
    """a − b; оба −inf (модель не слышит ни того, ни другого) — 0, не nan."""
    return 0.0 if a == b == -math.inf else a - b


def _finite(value: float) -> float:
    return max(-MARGIN_CAP, min(MARGIN_CAP, value))


def _logsumexp(values: Sequence[float]) -> float:
    top = max(values)
    if top == -math.inf:
        return top
    return top + math.log(sum(math.exp(v - top) for v in values))


def full_reading(accepted: Sequence[str]) -> str:
    """Чтение со всеми гласными (слитное): от него строятся варианты ошибок и разбор ошибки."""
    return max(accepted, key=lambda a: sum(c in _VOWEL_SIGNS for c in a))


def syllable_card(text: str) -> bool:
    """Карточка из отдельных слогов («بُ», «رَ رِ رُ»): в каждом слове одна буква. Такие
    читаются со всеми гласными — чтение с остановкой не засчитывается (FR-70 п. 2)."""
    words = text.split()
    return bool(words) and all(
        sum(unicodedata.category(c) == "Lo" for c in word) == 1 for word in words
    )


def accepted_references(
    text: str, references: Sequence[tuple[str, str]]
) -> tuple[tuple[str, str], ...]:
    """Верные чтения карточки (FR-70 п. 2): карточка из отдельных слогов читается со всеми
    гласными — только слитно (wasl, первый эталон); остальные — и слитно, и с остановкой."""
    return tuple(references[:1]) if syllable_card(text) else tuple(references)


def card_verdict(decision: CardDecision) -> Verdict:
    """Исход в вердикт (ADR-0088 п. 5, 6): засчитано без подсказок — «отлично», с мягкой
    подсказкой — «засчитано», «ещё раз» — свой вердикт, ошибка — «нужно повторить»."""
    if decision.outcome == "passed":
        return Verdict.PASSED if decision.hints else Verdict.EXCELLENT
    return Verdict.AGAIN if decision.outcome == "again" else Verdict.FAILED


def _scored_at_once(variants: Sequence[str], score_many: Any) -> dict[str, float]:
    """Баллы всех вариантов одним вызовом батча; нет батча — пусто (считаются поштучно)."""
    if score_many is None:
        return {}
    unique = list(dict.fromkeys(variants))
    return dict(zip(unique, score_many(unique), strict=True))


def decide(
    accepted: Sequence[str],
    score: Callable[[str], float],
    policy: CardPolicy,
    *,
    separate_syllables: bool,
    rules: frozenset[str] = ALL_RULES,
    soft_kinds: frozenset[str] | None = None,
    # По смыслу sounds: Callable[[str], Sequence[str]] | None, score_many:
    # Callable[[Sequence[str]], Sequence[float]] | None. Any — потому что тесты зовут decide с
    # ``**kwargs: frozenset[str]``, и mypy --strict сверяет этот тип с каждым ключевым параметром.
    sounds: Any = None,
    score_many: Any = None,
) -> CardDecision:
    """Ответ по карточке.

    ``accepted`` — верные чтения в записи фонетизатора бота (слитно и с остановкой; варианты
    ошибок строятся от чтения с наибольшим числом гласных — слитного, где бы оно ни стояло).
    Карточка из отдельных слогов (``separate_syllables``, «رَ رِ رُ») читается со всеми
    гласными — чтение без последней гласной в ``accepted`` не передают.
    ``rules`` — какие ошибки ищем на уроке (`CardPolicy.rules_for`); ``soft_kinds`` — какие из них
    дают только подсказку (по умолчанию `CardPolicy.soft_kinds`). ``sounds`` — звуки варианта
    для модели: вариант, который звучит как верное чтение, — не ошибка (по умолчанию — сама строка).
    ``score_many`` — баллы многих вариантов одним вызовом (батч-CTC): передан — все варианты
    считаются им разом, решение то же.
    """
    if not accepted:
        raise ValueError("У карточки нет верного чтения")
    soft = policy.soft_kinds if soft_kinds is None else soft_kinds
    base = full_reading(accepted)
    typical, tail, other, no_last = _variants(base, rules, separate_syllables=separate_syllables)

    def heard_as(variant: str) -> tuple[str, ...]:
        return tuple(sounds(variant) if sounds else variant)

    right = {heard_as(a) for a in accepted}
    every = [*accepted, *(v for _, v in typical), *tail, *other, *([no_last] if no_last else [])]
    cache: dict[str, float] = _scored_at_once(every, score_many)

    def s(variant: str) -> float:
        if variant not in cache:
            cache[variant] = score(variant)
        return cache[variant]

    def best(variants: Sequence[str]) -> tuple[str, float]:
        scored = [(v, s(v)) for v in variants if heard_as(v) not in right]
        return max(scored, key=lambda x: x[1], default=("", -math.inf))

    good = _logsumexp([s(a) for a in accepted])
    reading = max(accepted, key=s)
    kinds: dict[str, str] = {}
    for kind, variant in typical:
        kinds.setdefault(variant, kind)
    hard = [v for v, k in kinds.items() if k not in soft]
    rival, rival_score = best(hard)
    stranger, stranger_score = best(other)
    margin = _diff(good, rival_score)
    margin_other = _diff(good, stranger_score)

    def answer(
        outcome: Outcome, hints: tuple[str, ...] = (), *, unheard: bool = False
    ) -> CardDecision:
        return CardDecision(
            outcome, reading, None, _finite(margin), _finite(margin_other), hints=hints,
            unheard=unheard,
        )  # fmt: skip

    def error(winner: str, kind: str, *, other_syllable: bool = False) -> CardDecision:
        return CardDecision(
            "error", winner, kind, _finite(margin), _finite(margin_other), other_syllable
        )

    heard_nothing = max([good, rival_score, stranger_score, *(s(v) for v in tail)])
    if heard_nothing == -math.inf:
        return answer("again", unheard=True)  # тишина: бот не расслышал
    shortest = min(len(heard_as(a)) for a in accepted)
    checked = [v for v in (*hard, *other) if heard_as(v) not in right] + tail
    heard = [v for v in checked if s(v) > -math.inf]
    if good == -math.inf and all(len(heard_as(v)) < shortest for v in heard):
        # верное невозможно: запись короче верного чтения — не расслышал
        return answer("again", unheard=True)
    if margin_other < policy.other_error:
        return error(stranger, OTHER_SYLLABLE, other_syllable=True)
    if margin < policy.error_margin:
        return error(rival, kinds[rival])
    outcome: Outcome = (
        "again" if margin_other < policy.other_again or margin < policy.pass_margin else "passed"
    )
    hints: list[str] = []
    if tail:  # «ясная гласная»: верная — засчитано, ясно другая — ошибка, почти не слышна — ещё раз
        last, last_score = best(tail)
        margin_last = _diff(good, last_score)
        if margin_last < policy.error_margin:
            return error(last, "vowel")
        if margin_last < policy.pass_margin:
            outcome = "again"
        elif no_last is not None and _diff(good, s(no_last)) < policy.pass_margin:
            outcome = "again"
            hints.append(LAST_VOWEL)
    for kind in sorted(soft & rules):
        soft_variants = [v for v, k in kinds.items() if k == kind]
        if _diff(good, best(soft_variants)[1]) < policy.pass_margin:
            hints.append(kind)
    return answer(outcome, tuple(hints))
