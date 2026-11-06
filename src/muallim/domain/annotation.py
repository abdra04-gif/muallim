"""Разметка попыток человеком: метки, проверка фонем, коды разметчиков и приглашения.

Одни и те же правила для пакета Excel (``research/annotation.py``) и разметки в Telegram (FR-17):
руководство — docs/data/annotation-guide.md. ``agree`` — бот услышал верно, ``fix`` — записать,
что прозвучало на самом деле (решение автора 2026-10-18, ADR-0040).

Разметка по клеткам (FR-62, ADR-0079): учитель оценивает чтение ученика — отмечает клетки (слоги
аята суры или буквы строки) и вид ошибки; ``corrected_phonemes`` выводится только там, где это
однозначно, ``agree``/``fix`` считается само.
"""

import hashlib
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Final
from uuid import UUID

from muallim.domain import arabic
from muallim.domain.assessment import assess, phoneme_errors
from muallim.domain.phonetics import CONSONANTS, SPECIAL, VOWELS
from muallim.domain.syllables import Ayah

# Версия docs/data/annotation-guide.md — пишется в каждую метку (это проверяет тест).
GUIDE_VERSION: Final = "2.1"


class AnnotationStatus(StrEnum):
    AGREE = "agree"  # бот услышал верно: actual = что услышал бот
    FIX = "fix"  # бот ошибся: в actual — что прозвучало на самом деле
    AUDIO_UNUSABLE = "audio_unusable"  # шум, тишина, обрезано, несколько голосов
    OFF_TASK = "off_task"  # прочитано не то, что на карточке


USABLE: Final = frozenset({AnnotationStatus.AGREE, AnnotationStatus.FIX})  # попытку можно оценить


class AnnotationSource(StrEnum):
    EXCEL = "excel"  # пакет tasks.csv
    TELEGRAM = "telegram"  # кнопки в боте


class Entry(StrEnum):
    """Как введено «что прозвучало» (FR-62): клетками или фонемами (пакет Excel, «⌨️ вручную»)."""

    CELLS = "cells"
    PHONEMES = "phonemes"


class Layout(StrEnum):
    """Раскладка клеток: слоги аята суры (``ayat.yaml``) или буквы со знаками."""

    SYLLABLES = "syllables"
    LETTERS = "letters"


class MarkGroup(StrEnum):
    SAID = "said"  # сказал неправильно
    TAJWID = "tajwid"  # таджвид
    READING = "reading"  # как читает


class MarkKind(StrEnum):
    """Вид ошибки в клетке (решение автора 2026-10-31): 11 видов в трёх группах."""

    LETTER = "letter"  # не та буква
    VOWEL = "vowel"  # огласовка
    MADD = "madd"  # коротко / долго
    SHADDA_SUKUN = "shadda_sukun"
    MISSING = "missing"  # не прочитана вся клетка
    EXTRA = "extra"  # лишний звук
    TAFKHIM = "tafkhim"  # твёрдо / мягко
    GHUNNA = "ghunna"  # ихфа, идгам
    QALQALA = "qalqala"
    HALTING = "halting"  # запнулся, по буквам
    WRONG_STOP = "wrong_stop"  # остановился не там

    @property
    def group(self) -> "MarkGroup":
        return _KIND_GROUP[self]

    @property
    def code(self) -> str:
        """Короткий код для ``callback_data`` (≤ 3 латинских символов)."""
        return _KIND_CODE[self]

    @classmethod
    def by_code(cls, code: str) -> "MarkKind | None":
        return _CODE_KIND.get(code)


_SAID: Final = ("letter", "vowel", "madd", "shadda_sukun", "missing", "extra")
_TAJWID: Final = ("tafkhim", "ghunna", "qalqala")
_KIND_GROUP: Final = {
    k: MarkGroup.SAID if k in _SAID else MarkGroup.TAJWID if k in _TAJWID else MarkGroup.READING
    for k in MarkKind
}
_KIND_CODE: Final = {
    MarkKind.LETTER: "l", MarkKind.VOWEL: "v", MarkKind.MADD: "md", MarkKind.SHADDA_SUKUN: "ss",
    MarkKind.MISSING: "mi", MarkKind.EXTRA: "ex", MarkKind.TAFKHIM: "tf", MarkKind.GHUNNA: "gh",
    MarkKind.QALQALA: "qq", MarkKind.HALTING: "ht", MarkKind.WRONG_STOP: "ws",
}  # fmt: skip
_CODE_KIND: Final = {code: kind for kind, code in _KIND_CODE.items()}


PHONEME_ALPHABET: Final = CONSONANTS | VOWELS | SPECIAL
# Частые описки при наборе арабского текста вместо фонетической записи (SRC-002).
_HINTS: Final = {
    **dict.fromkeys("أإآؤئ", "хамза пишется одним знаком «ء»"),
    "ّ": "удвоение пишется двумя одинаковыми буквами, без шадды",
    "ْ": "сукун не пишется: согласная без огласовки",
    **dict.fromkeys("ًٌٍ", "танвин пишется огласовкой и «ن»"),
}
# Невидимые знаки, которые добавляют Excel, редакторы и Telegram (направление письма, BOM).
_INVISIBLE: Final = str.maketrans(
    dict.fromkeys("\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069\ufeff", None)
)
_ANNOTATOR_CODE: Final = re.compile(r"[A-Za-z0-9_-]{1,64}")

INVITE_TTL: Final = timedelta(hours=24)  # приглашение действует сутки и один раз
MAX_INVITE_FAILURES: Final = 5  # неверных кодов подряд — и вход закрыт…
INVITE_LOCK: Final = timedelta(hours=1)  # …на час: подбирать код бессмысленно
# Без похожих знаков (0/O, 1/I/L): код диктуют голосом или переписывают с экрана.
INVITE_ALPHABET: Final = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
INVITE_LENGTH: Final = 12  # «KQ7M-29FX-HT3P»: ≈ 59 бит — подобрать нельзя


class LabelError(ValueError):
    """Метка противоречит правилам руководства; текст — что исправить, для разметчика."""


def clean_phonemes(text: str) -> str:
    """Без пробелов и невидимых знаков."""
    return "".join(text.translate(_INVISIBLE).split())


def check_phonemes(text: str) -> None:
    """Запись — только символами фонетического алфавита модели; иначе — подсказка, что не так."""
    if not text:
        raise LabelError("пустое поле «что прозвучало»")
    for ch in text:
        if ch not in PHONEME_ALPHABET:
            hint = _HINTS.get(ch, "в записи только буквы и огласовки фонетического алфавита")
            raise LabelError(f"символ «{ch}» не фонема — {hint}")


def check_label(status: AnnotationStatus, actual: str | None, bot_heard: str) -> None:
    """«agree» — фонемы бота без правок, «fix» — с правками: иначе метка противоречит записи."""
    if status is AnnotationStatus.AGREE and actual != bot_heard:
        raise LabelError(
            "стоит «agree», но «что прозвучало» отличается от того, что услышал бот. "
            "Бот ошибся — поставьте «fix»; согласны — верните его вариант."
        )
    if status is AnnotationStatus.FIX and actual == bot_heard:
        raise LabelError("стоит «fix», но ничего не исправлено. Если бот прав — поставьте «agree».")


def check_self_correction(status: AnnotationStatus, *, self_corrected: bool) -> None:
    """«Сам исправился» — отдельная категория чтения (решение автора 2026-10-18, SRC-068).

    Ученик ошибся и сам перечитал верно. Отмечается рядом с «agree»/«fix»: ответ модели
    оценивается как обычно. У плохой записи и чужого текста чтения не слышно — отметка не к месту.
    """
    if self_corrected and status not in USABLE:
        raise LabelError(
            "«сам исправился» ставится только к «agree» или «fix»: у плохой записи и чужого "
            "текста чтения не слышно."
        )


def valid_annotator_code(code: str) -> bool:
    """Код разметчика (A1, A2…): латиница, цифры, «-» и «_», до 64 символов. Имени — нет."""
    return bool(_ANNOTATOR_CODE.fullmatch(code))


def looks_like_invite(text: str) -> bool:
    """Похоже ли слово после /annotate на код приглашения. «/annotate привет» — нет: это
    обычный открытый вход (ADR-0072), а не неверный код."""
    normal = "".join(text.split()).replace("-", "").upper()
    return len(normal) == INVITE_LENGTH and all(c in INVITE_ALPHABET for c in normal)


_AUTO_CODE: Final = re.compile(r"A([1-9][0-9]*)")


def next_annotator_code(taken: frozenset[str]) -> str:
    """Код новичку при входе по /annotate: «A» и номер после наибольшего занятого.

    Дыры не занимаются: код отозванного или ушедшего разметчика новому не достаётся —
    иначе метки двух людей смешаются под одним кодом (κ считается по коду).
    """
    numbers = [int(m.group(1)) for code in taken if (m := _AUTO_CODE.fullmatch(code))]
    return f"A{max(numbers, default=0) + 1}"


def invite_digest(code: str) -> str:
    """Отпечаток кода приглашения: в БД хранится он, а не сам код (утечка БД не даёт войти)."""
    normal = "".join(code.split()).replace("-", "").upper()
    return hashlib.sha256(normal.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class Cell:
    """Клетка разметки: кусочек строки ``text[start:end]`` без пробелов; ``word`` — номер слова."""

    index: int
    start: int
    end: int
    piece: str
    word: int = 0


@dataclass(frozen=True, slots=True)
class Mark:
    """Отметка учителя: клетка, вид ошибки и (только у «не та буква») какая буква прозвучала."""

    cell: int
    kind: MarkKind
    heard_letter: str | None = None


@dataclass(frozen=True, slots=True)
class CellMark:
    """Отметка, как её хранит БД: с позицией кусочка в тексте и ⚠️ бота на клетке."""

    cell: int
    layout: Layout
    char_start: int
    char_end: int
    piece: str
    kind: MarkKind
    heard_letter: str | None
    bot_flagged: bool


def annotation_cells(text: str, syllables: Ayah | None) -> tuple[Cell, ...]:
    """Клетки строки: слоги аята (порядок чтения) или, без раскладки, буквы со знаками.

    Раскладка, чьи кусочки не ложатся ровно на текст, не используется — тогда по буквам.
    """
    if syllables is not None and (cells := _syllable_cells(text, syllables)) is not None:
        return cells
    return _letter_cells(text)


def _silent(letter: arabic.Cluster, last_in_word: bool) -> bool:
    """Согласная без знаков внутри слова (ٱ, лям перед солнечной) не звучит сама."""
    return letter.is_consonant and not letter.marks and not last_in_word


def _letter_cells(text: str) -> tuple[Cell, ...]:
    """По буквам: в клетке всегда есть звук (дополнено 2026-11-01, п. 5). Буква мадда без
    огласовки и татвиль — в клетке предыдущей согласной («بَا»), немая буква — следующей."""
    letters = arabic.clusters(text)
    by_word: dict[int, list[int]] = {}
    for n, word in enumerate(arabic.cluster_words(text)):
        by_word.setdefault(word, []).append(n)
    groups: list[tuple[int, list[int]]] = []  # (слово, буквы клетки)
    for word, members in by_word.items():
        cells: list[list[int]] = []
        pending: list[int] = []  # немые буквы ждут свою согласную
        for n in members:
            c = letters[n]
            if c.is_consonant and not _silent(c, last_in_word=n == members[-1]):
                cells.append([*pending, n])
                pending = []
            elif not c.is_consonant and cells and not pending:
                cells[-1].append(n)
            else:
                pending.append(n)
        if pending and cells:
            cells[-1] += pending
        elif pending:
            cells.append(pending)
        groups += [(word, g) for g in cells]
    out = []
    for i, (word, g) in enumerate(groups):
        start, end = letters[g[0]].start, letters[g[-1]].end
        out.append(Cell(i, start, end, text[start:end], word))
    return tuple(out)


def _syllable_cells(text: str, syllables: Ayah) -> tuple[Cell, ...] | None:
    cells: list[Cell] = []
    pos = 0
    for word_no, word in enumerate(syllables):
        while pos < len(text) and text[pos].isspace():
            pos += 1
        for syllable in word:
            piece = syllable.text
            if not piece or not text.startswith(piece, pos):
                return None
            cells.append(Cell(len(cells), pos, pos + len(piece), piece, word_no))
            pos += len(piece)
    return tuple(cells) if cells and not text[pos:].strip() else None


def layout_of(text: str, cells: Sequence[Cell]) -> Layout:
    """По буквам — когда клетки совпадают с клетками-буквами строки, иначе слоги."""
    letters = [(c.start, c.end) for c in _letter_cells(text)]
    return Layout.LETTERS if [(c.start, c.end) for c in cells] == letters else Layout.SYLLABLES


def _cell_at(cells: Sequence[Cell], char: int) -> int:
    for c in cells:
        if c.start <= char < c.end:
            return c.index
    return cells[-1].index


def phoneme_cells(text: str, reference: str, cells: Sequence[Cell]) -> tuple[int, ...]:
    """Клетка каждой фонемы эталона: у согласной — клетка её буквы (``arabic.owners``), у
    огласовки и мадда — клетка предыдущей согласной (в начале строки — первой согласной)."""
    owners = arabic.owners(text, reference)
    if not cells or not owners:
        return ()
    letters = arabic.clusters(text)
    owner = iter(owners)
    spoken = [
        _cell_at(cells, letters[next(owner)].start) if ch in CONSONANTS else None
        for ch in reference
    ]
    last = next(c for c in spoken if c is not None)
    out: list[int] = []
    for c in spoken:
        last = last if c is None else c
        out.append(last)
    return tuple(out)


def bot_cells(text: str, reference: str, heard: str, cells: Sequence[Cell]) -> frozenset[int]:
    """Клетки, где ошибку нашла модель (тот же разбор, что у бота): вставка — к клетке
    предыдущей согласной, в самом начале — к первой."""
    where = phoneme_cells(text, reference, cells)
    if not where:
        return frozenset()
    return frozenset(where[pos] for pos in phoneme_errors(reference, heard))


def bot_letters(text: str, reference: str, heard: str, cells: Sequence[Cell], cell: int) -> str:
    """Согласные, которые модель услышала на месте звуков этой клетки (для шага «буква»)."""
    where = phoneme_cells(text, reference, cells)
    found: list[str] = []
    for error in assess(reference, heard).errors:
        if where and where[min(error.position, len(where) - 1)] == cell:
            found += [ch for ch in error.heard if ch in CONSONANTS and ch not in found]
    return "".join(found)


def written_letters(piece: str) -> str:
    """Согласные кусочка так, как они записаны в фонемах (ة → ت, أ → ء), без повторов."""
    out: list[str] = []
    for c in arabic.clusters(piece):
        if c.is_consonant and (letter := arabic.phoneme_of(c.base)) not in out:
            out.append(letter)
    return "".join(out)


def pair_letters(written: str, pairs: Iterable[frozenset[str]]) -> list[str]:
    """Буквы, которые путают с буквами клетки (пары ``lexicon.pair_tips``), — в фонемах."""
    out: list[str] = []
    for pair in pairs:
        sounds = {arabic.phoneme_of(x) for x in pair}
        if sounds & set(written):
            out += [x for x in sorted(sounds - set(written)) if x in CONSONANTS and x not in out]
    return out


def apply_marks(
    text: str, reference: str, cells: Sequence[Cell], marks: Sequence[Mark]
) -> str | None:
    """«Что прозвучало» из отметок — только где однозначно, иначе None.

    Нет отметок — эталон. «Не та буква» с указанной буквой в клетке ровно с одной звучащей
    согласной — она заменена (обе половины шадды). «Пропустил» — удалены все фонемы клетки.
    Любой другой вид или несколько видов в клетке — фонемы не выводятся.
    """
    if not marks:
        return reference
    where = phoneme_cells(text, reference, cells)
    by_cell: dict[int, list[Mark]] = {}
    for mark in marks:
        by_cell.setdefault(mark.cell, []).append(mark)
    if not where:
        return None
    replace: dict[int, str] = {}
    drop: set[int] = set()
    for cell, given in by_cell.items():
        if len(given) != 1:
            return None
        mark = given[0]
        positions = [pos for pos, c in enumerate(where) if c == cell]
        if mark.kind is MarkKind.MISSING:
            drop.update(positions)
        elif mark.kind is MarkKind.LETTER and mark.heard_letter is not None:
            consonants = [pos for pos in positions if reference[pos] in CONSONANTS]
            if len({reference[pos] for pos in consonants}) != 1:
                return None
            replace.update(dict.fromkeys(consonants, mark.heard_letter))
        else:
            return None
    return "".join(replace.get(pos, ch) for pos, ch in enumerate(reference) if pos not in drop)


def marks_status(
    bot_heard: str, reference: str, actual: str | None, marks: Sequence[Mark]
) -> AnnotationStatus:
    """Учитель оценивает чтение, а не бота: ``agree`` — чтение по учителю совпало с тем, что
    услышал бот (те же ошибки на тех же местах). Фонемы не выводятся — согласия не видно, ``fix``.

    ``marks`` уже сведены в ``actual`` (``apply_marks``) — параметр для ясности вызова.
    """
    del marks
    if actual is None:
        return AnnotationStatus.FIX
    same = phoneme_errors(reference, actual) == phoneme_errors(reference, bot_heard)
    return AnnotationStatus.AGREE if same else AnnotationStatus.FIX


def check_marks(cells: Sequence[Cell], marks: Sequence[Mark]) -> None:
    """Отметки по правилам руководства: клетка есть в раскладке, вид в клетке — один раз, буква —
    только у «не та буква», согласная фонетического алфавита и не та, что написана в клетке."""
    seen: set[tuple[int, MarkKind]] = set()
    for mark in marks:
        if not 0 <= mark.cell < len(cells):
            raise LabelError(f"клетки {mark.cell + 1} нет: в строке {len(cells)} клеток")
        if (mark.cell, mark.kind) in seen:
            raise LabelError("один и тот же вид ошибки отмечен в клетке дважды")
        seen.add((mark.cell, mark.kind))
        letter = mark.heard_letter
        if letter is None:
            continue
        if mark.kind is not MarkKind.LETTER:
            raise LabelError("букву указывают только у «не та буква»")
        if letter not in CONSONANTS:
            hint = _HINTS.get(letter, "нужна одна согласная фонетического алфавита")
            raise LabelError(f"«{letter}» — не согласная: {hint}")
        if written_letters(cells[mark.cell].piece) == letter:
            raise LabelError(f"в клетке и так написана «{letter}» — это не «не та буква»")


@dataclass(frozen=True, slots=True)
class AnnotationTask:
    """Попытка в очереди разметчика: что читал ученик и что ответил бот. Кто ученик — не видно."""

    attempt_id: UUID
    item_id: str
    item_text: str
    page: int | None
    line: int | None
    bot_passed: bool
    bot_errors: tuple[tuple[str, str], ...]  # (нужно, услышано); "" — звука нет
    reference_phonemes: str
    bot_heard: str
    learner_says: str | None  # причина «бот ошибся» от ученика (ReportReason) или None
    audio_sha256: str
    cells: tuple[Cell, ...] = ()  # клетки разметки (FR-62); строит NextAnnotation
    bot_cells: frozenset[int] = field(default_factory=frozenset)  # где ошибку нашла модель


@dataclass(frozen=True, slots=True)
class Label:
    attempt_id: UUID
    annotator: str
    status: AnnotationStatus
    actual: str | None  # что прозвучало; None — оценить нельзя (audio_unusable, off_task)
    comment: str
    source: AnnotationSource
    seconds_spent: int | None  # от показа записи до ответа (только Telegram)
    created_at: datetime
    self_corrected: bool = False  # ученик ошибся и сам перечитал верно (руководство 2.1)
    entry: Entry | None = None  # клетками или фонемами (FR-62); None — плохая запись, не то
