"""Сравнение эталонных фонем с услышанными и классификация ошибок.

Результат — структурированные ошибки (тип, позиция, слог), а не готовый текст: так их можно
хранить в БД, считать статистику и размечать датасет (FR-05, FR-11). Текст для ученика строит
application/feedback.py.

Что считать ошибкой новичка — методическое решение человека (docs/pedagogy/methodology.md):
калькаля при остановке ошибкой не считается.
"""

import difflib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum

from muallim.domain.phonetics import (
    CONSONANTS,
    LONG_VOWELS,
    QALQALA,
    SHORT_VOWELS,
    VOWELS,
    count_syllables,
    syllable_at,
    syllables,
)

# «Не дочитал» — когда после последнего совпавшего куска эталона осталось хотя бы столько
# согласных, а услышано после него — не больше трети оставшегося (шум, обрывок).
UNREAD_MIN_CONSONANTS = 2
_ANCHOR = 3  # совпавший кусок короче — случайное совпадение, а не прочитанное


class ErrorKind(StrEnum):
    LETTER_SUBSTITUTION = "letter_substitution"  # одна согласная вместо другой
    VOWEL_SUBSTITUTION = "vowel_substitution"  # одна огласовка вместо другой
    SOUND_SUBSTITUTION = "sound_substitution"  # прочая замена одного звука
    FRAGMENT_SUBSTITUTION = "fragment_substitution"  # замена нескольких звуков
    MADD_TOO_SHORT = "madd_too_short"  # долгий гласный не дотянут
    VOWEL_MISSING = "vowel_missing"  # пропущена короткая огласовка
    SHADDA_MISSING = "shadda_missing"  # нет удвоения согласной
    SOUND_MISSING = "sound_missing"  # пропущен звук
    MADD_TOO_LONG = "madd_too_long"  # короткий гласный растянут в мадд
    EXTRA_SOUND = "extra_sound"  # лишний звук


@dataclass(frozen=True, slots=True)
class PronunciationError:
    kind: ErrorKind
    position: int  # индекс в эталонной строке фонем
    syllable: int | None  # None, если в эталоне один слог
    expected: str
    heard: str


@dataclass(frozen=True, slots=True)
class Assessment:
    reference: str
    heard: str
    score: int  # 0..100, сходство последовательностей фонем
    errors: tuple[PronunciationError, ...]


def assess(reference: str, heard: str) -> Assessment:
    """Сравнивает эталон с услышанным и возвращает оценку и список ошибок."""
    matcher = difflib.SequenceMatcher(None, reference, heard, autojunk=False)
    score = round(matcher.ratio() * 100)
    multi = count_syllables(reference) > 1
    errors: list[PronunciationError] = []

    def err(kind: ErrorKind, pos: int, expected: str, got: str) -> None:
        syllable = syllable_at(reference, pos) if multi else None
        errors.append(PronunciationError(kind, pos, syllable, expected, got))

    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        expected, got = reference[i1:i2], heard[j1:j2]
        if op == "replace":
            err(_substitution_kind(expected, got), i1, expected, got)
        elif op == "delete":
            start, stop = _slide_to_consonant(reference, i1, i2)
            for k, ch in enumerate(reference[start:stop]):
                pos = start + k
                kind = _deletion_kind(reference, pos, ch)
                if kind is not None:
                    err(kind, pos, ch, "")
        elif op == "insert":
            if all(ch == QALQALA for ch in got):
                continue  # калькаля при остановке — не ошибка новичка
            kind = (
                ErrorKind.MADD_TOO_LONG
                if all(ch in LONG_VOWELS for ch in got)
                else ErrorKind.EXTRA_SOUND
            )
            err(kind, i1, "", got)
    return Assessment(reference, heard, score, tuple(errors))


def unread_from(reference: str, heard: str) -> int | None:
    """С какого слога (индекс в ``syllables(reference)``) строка не дочитана; None — дочитана.

    Ученик остановился на середине: ошибки дальше — не ошибки чтения, а непрочитанный конец.
    """
    matcher = difflib.SequenceMatcher(None, reference, heard, autojunk=False)
    blocks = [b for b in matcher.get_matching_blocks() if b.size >= _ANCHOR]
    if not blocks:
        return None
    last = blocks[-1]
    stop, after = last.a + last.size, heard[last.b + last.size :]
    rest = reference[stop:]
    if count_syllables(rest) < UNREAD_MIN_CONSONANTS or 3 * len(after) > len(rest):
        return None
    for index, (_, end) in enumerate(syllables(reference)):
        if end > stop:  # слог, в котором остановился, тоже не дочитан
            return index if index > 0 else None
    return None


@dataclass(frozen=True, slots=True)
class Candidate:
    """Оценка по одному из допустимых эталонов (например, ``wasl`` или ``waqf``)."""

    variant: str
    assessment: Assessment


def assess_variants(
    references: Sequence[tuple[str, str]], heard: str
) -> tuple[Candidate, tuple[Candidate, ...]]:
    """Оценка по каждому эталону и лучший из них (при равенстве — первый по порядку).

    Все кандидаты сохраняются в попытке — так решение можно воспроизвести (ADR-0019).
    """
    candidates = tuple(Candidate(name, assess(ref, heard)) for name, ref in references)
    if not candidates:
        raise ValueError("Нужен хотя бы один эталон")
    return max(candidates, key=lambda c: c.assessment.score), candidates


def assess_best(references: Iterable[str], heard: str) -> Assessment:
    """Оценка по самому близкому из допустимых эталонов (например, с вакфом и без).

    При равенстве баллов берётся первый эталон — порядок задаёт распознаватель.
    """
    results = [assess(ref, heard) for ref in references]
    if not results:
        raise ValueError("Нужен хотя бы один эталон")
    return max(results, key=lambda a: a.score)


def _slide_to_consonant(reference: str, i1: int, i2: int) -> tuple[int, int]:
    """Пропуск, который можно сдвинуть вправо без изменения остатка, начинаем с согласной.

    «كَتَبَ» → «كَبَ»: difflib выбирает пропуск «َت» (гласный слога «ка» и «т»), хотя
    равноценно «تَ» — пропущен слог «та». Новичку нужен второй вариант.
    """
    while (
        reference[i1] not in CONSONANTS and i2 < len(reference) and reference[i1] == reference[i2]
    ):
        i1, i2 = i1 + 1, i2 + 1
    return i1, i2


def _substitution_kind(expected: str, got: str) -> ErrorKind:
    if len(expected) != 1 or len(got) != 1:
        return ErrorKind.FRAGMENT_SUBSTITUTION
    if expected in CONSONANTS and got in CONSONANTS:
        return ErrorKind.LETTER_SUBSTITUTION
    if expected in VOWELS and got in VOWELS:
        return ErrorKind.VOWEL_SUBSTITUTION
    return ErrorKind.SOUND_SUBSTITUTION


def _deletion_kind(reference: str, pos: int, ch: str) -> ErrorKind | None:
    if ch in LONG_VOWELS:
        return ErrorKind.MADD_TOO_SHORT
    if ch in SHORT_VOWELS:
        return ErrorKind.VOWEL_MISSING
    if ch == QALQALA:
        return None  # калькаля при остановке — не ошибка новичка
    neighbours = reference[max(pos - 1, 0) : pos] + reference[pos + 1 : pos + 2]
    if ch in CONSONANTS and ch in neighbours:
        return ErrorKind.SHADDA_MISSING
    return ErrorKind.SOUND_MISSING
