"""Алфавит фонем Quran Phonetic Script, с которым работает модель Muaalem.

Источник набора символов: Abdelfattah et al., 2025, arXiv:2509.00094, раздел о Quran Phonetic
Script (см. docs/research/sources.md, SRC-002). Здесь только символы и их классы: названия букв
и подсказки на русском — это учебный контент, он лежит в curriculum/lexicon.ru.yaml.
"""

from enum import StrEnum
from typing import Final

# 28 согласных: хамза вместо алифа, т.к. алиф с огласовкой читается как хамза.
CONSONANTS: Final[frozenset[str]] = frozenset("ءبتثجحخدذرزسشصضطظعغفقكلمنوهي")

SHORT_VOWELS: Final[frozenset[str]] = frozenset("َُِ")  # фатха, кясра, дамма
LONG_VOWELS: Final[frozenset[str]] = frozenset("اۦۥ")  # мадд: аа, ии, уу
QALQALA: Final[str] = "ڇ"  # «отскок» звука при остановке

VOWELS: Final[frozenset[str]] = SHORT_VOWELS | LONG_VOWELS | {QALQALA}

# Остальные символы фонетизатора quran-transcript (``quran_transcript.alphabet.phonetics``):
# ималя (۪ ـ), облегчённая хамза (ٲ), скрытые нун и мим — ихфа (ں ۾), сакт (ۜ), краткая дамма (ؙ).
SPECIAL: Final[frozenset[str]] = frozenset("\u06ea\u0640\u0672\u06ba\u06fe\u06dc\u0619")


class Zone(StrEnum):
    """Где рождается звук — три упрощённые зоны для начинающих (ADR-0050).

    Упрощение 17 мест образования (махāридж) аль-Джазарийи (SRC-059) до «горло / язык / губы»;
    утвердил автор 2026-10-18.
    """

    THROAT = "throat"
    TONGUE = "tongue"
    LIPS = "lips"


_THROAT: Final[frozenset[str]] = frozenset("ءأإؤئآهعحغخ")
_LIPS: Final[frozenset[str]] = frozenset("بمفو")


def articulation_zone(letter: str) -> Zone | None:
    """Зона буквы; None — не согласный (алиф-мадд, не арабская буква)."""
    if letter in _THROAT:
        return Zone.THROAT
    if letter in _LIPS:
        return Zone.LIPS
    return Zone.TONGUE if letter in CONSONANTS else None


_SYLLABLE_VOWELS: Final[frozenset[str]] = (
    SHORT_VOWELS | LONG_VOWELS | frozenset("\u06ea\u0640\u0619")
)


def count_syllables(phonemes: str) -> int:
    """Число слогов в эталоне. Слог считаем по согласным — так делит учебник на начальных уроках."""
    return sum(1 for ch in phonemes if ch in CONSONANTS)


def syllable_at(phonemes: str, index: int) -> int:
    """Номер слога (с 1), к которому относится позиция ``index`` в эталоне."""
    return count_syllables(phonemes[: index + 1]) or 1


def syllables(phonemes: str) -> tuple[tuple[int, int], ...]:
    """Слоги для показа ученику: согласная с гласными после неё.

    Согласная без гласной (сукун, первая половина ташдида) закрывает предыдущий слог:
    «баб», «раб-ба». Границы — [начало, конец).
    """
    spans: list[list[int]] = []
    for i, ch in enumerate(phonemes):
        if ch in CONSONANTS:
            spans.append([i, i + 1])
        elif spans:
            spans[-1][1] = i + 1
        else:
            spans.append([i, i + 1])
    merged: list[list[int]] = []
    for span in spans:
        voiced = any(c in _SYLLABLE_VOWELS for c in phonemes[span[0] : span[1]])
        if merged and not voiced:
            merged[-1][1] = span[1]
        else:
            merged.append(span)
    return tuple((a, b) for a, b in merged)


def syllable_index(phonemes: str, consonant: int | None) -> int:
    """Какой из ``syllables`` показать для ошибки в ``consonant``-й согласной (с 1).

    None — эталон из одного слога: показываем первый.
    """
    parts = syllables(phonemes)
    if consonant is None or not parts:
        return 0
    seen = 0
    for index, (start, end) in enumerate(parts):
        seen += sum(1 for ch in phonemes[start:end] if ch in CONSONANTS)
        if seen >= consonant:
            return index
    return len(parts) - 1
