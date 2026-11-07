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
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Final
from uuid import UUID

from muallim.domain import arabic
from muallim.domain.assessment import ErrorKind, PronunciationError, assess, phoneme_errors
from muallim.domain.phonetics import CONSONANTS, LONG_VOWELS, QALQALA, SHORT_VOWELS, SPECIAL, VOWELS
from muallim.domain.syllables import Ayah

# Версия docs/data/annotation-guide.md — пишется в каждую метку (это проверяет тест).
GUIDE_VERSION: Final = "3.0"


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


class PhonemesSource(StrEnum):
    """Откуда строка «что прозвучало» — надёжность для обучения (FR-63, ADR-0080)."""

    TYPED = "typed"  # введена учителем (пакет Excel, «Фонемы вручную»)
    MARKS = "marks"  # собрана из отметок учителя (``apply_marks``)
    CONFIRMED = "confirmed"  # «Бот прав»: ответ бота
    REFERENCE = "reference"  # «Чисто»: эталон


class Layout(StrEnum):
    """Раскладка клеток: слоги аята суры (``ayat.yaml``) или буквы со знаками."""

    SYLLABLES = "syllables"
    LETTERS = "letters"


class MarkGroup(StrEnum):
    SAID = "said"  # сказал неправильно
    TAJWID = "tajwid"  # таджвид
    # Как читает (запинка, пауза). Не «reading»: «ошибка чтения» RQ-1 — другое (TD-FN-150).
    FLUENCY = "fluency"


class MarkKind(StrEnum):
    """Вид ошибки в клетке (решение автора 2026-10-31): три группы.

    FR-63 (ADR-0080): на экране семь главных видов (``MAIN_KINDS``, с 2026-11-07 — и «Длина») и
    пять прочих (``MORE_KINDS``, кнопка «Ещё»); ``shadda_sukun`` — только у прежних меток.
    """

    LETTER = "letter"  # не та буква
    VOWEL = "vowel"  # огласовка
    MADD = "madd"  # коротко / долго
    SHADDA_SUKUN = "shadda_sukun"  # прежний вид (до FR-63): на экране не предлагается
    SHADDA = "shadda"  # удвоение не то (прозвучало / нет)
    SUKUN = "sukun"  # на месте сукуна прозвучала гласная
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


_SAID: Final = ("letter", "vowel", "madd", "shadda_sukun", "missing", "extra", "shadda", "sukun")
_TAJWID: Final = ("tafkhim", "ghunna", "qalqala")
_KIND_GROUP: Final = {
    k: MarkGroup.SAID if k in _SAID else MarkGroup.TAJWID if k in _TAJWID else MarkGroup.FLUENCY
    for k in MarkKind
}
_KIND_CODE: Final = {
    MarkKind.LETTER: "l", MarkKind.VOWEL: "v", MarkKind.MADD: "md", MarkKind.SHADDA_SUKUN: "ss",
    MarkKind.MISSING: "mi", MarkKind.EXTRA: "ex", MarkKind.TAFKHIM: "tf", MarkKind.GHUNNA: "gh",
    MarkKind.QALQALA: "qq", MarkKind.HALTING: "ht", MarkKind.WRONG_STOP: "ws",
    MarkKind.SHADDA: "sd", MarkKind.SUKUN: "sk",
}  # fmt: skip
_CODE_KIND: Final = {code: kind for kind, code in _KIND_CODE.items()}

# Главный экран разметки (по порядку на экране) и панель «Ещё» (FR-63).
# 2026-11-07 (автор, TD-FN-150): «Длина» — на главном экране (книга учит мадд, строка выводится).
MAIN_KINDS: Final = (
    MarkKind.LETTER, MarkKind.MISSING, MarkKind.VOWEL, MarkKind.EXTRA, MarkKind.SHADDA,
    MarkKind.SUKUN, MarkKind.MADD,
)  # fmt: skip
MORE_KINDS: Final = (
    MarkKind.TAFKHIM, MarkKind.GHUNNA, MarkKind.QALQALA, MarkKind.HALTING, MarkKind.WRONG_STOP,
)  # fmt: skip
# Долгий того же звука: фатха → аа, кясра → ии, дамма → уу.
_LONG_OF: Final = {"\u064e": "ا", "\u0650": "ۦ", "\u064f": "ۥ"}
NO_VOWEL: Final = (
    "-"  # у «Огласовка»: гласной не было совсем; не фонема, чтобы не спутать со звуком
)


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
    """Отметка учителя: клетка, вид ошибки и что прозвучало (буква, звук или гласная — смотря по
    виду, FR-63); None — вопроса нет или «не знаю»."""

    cell: int
    kind: MarkKind
    heard: str | None = None


@dataclass(frozen=True, slots=True)
class CellMark:
    """Отметка, как её хранит БД: с позицией кусочка в тексте и ⚠️ бота на клетке."""

    cell: int
    layout: Layout
    char_start: int
    char_end: int
    piece: str
    kind: MarkKind
    heard: str | None
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


def _cell_positions(where: Sequence[int], cell: int) -> list[int]:
    return [pos for pos, c in enumerate(where) if c == cell]


def cell_sounds(text: str, reference: str, cells: Sequence[Cell], cell: int) -> str:
    """Звуки эталона в клетке без повторов, по порядку — варианты для «Пропуск» (FR-63)."""
    where = phoneme_cells(text, reference, cells)
    out: list[str] = []
    for pos, owner in enumerate(where):
        if owner == cell and reference[pos] != QALQALA and reference[pos] not in out:
            out.append(reference[pos])
    return "".join(out)


def _vowel_after(reference: str, pos: int) -> bool:
    """После фонемы ``pos`` стоит гласная или мадд — тогда у согласной нет сукуна."""
    nxt = reference[pos + 1 : pos + 2]
    return bool(nxt) and (nxt in SHORT_VOWELS or nxt in LONG_VOWELS)


def _consonants(reference: str, positions: Sequence[int]) -> list[int]:
    return [pos for pos in positions if reference[pos] in CONSONANTS]


def _from_letter(
    reference: str, heard: str | None, positions: Sequence[int], out: "_Edits"
) -> bool:
    consonants = _consonants(reference, positions)
    if heard is None or len({reference[pos] for pos in consonants}) != 1:
        return False
    out.replace.update(dict.fromkeys(consonants, heard))
    return True


def _from_missing(
    reference: str, heard: str | None, positions: Sequence[int], out: "_Edits"
) -> bool:
    if heard is None:  # весь слог
        out.replace.update(dict.fromkeys(positions, ""))
        return bool(positions)
    found = [pos for pos in positions if reference[pos] == heard]
    doubled = len(found) == 2 and found[1] == found[0] + 1 and heard in CONSONANTS
    if len(found) != 1 and not doubled:
        return False
    out.replace.update(dict.fromkeys(found, ""))
    return True


def _from_vowel(reference: str, heard: str | None, positions: Sequence[int], out: "_Edits") -> bool:
    """Краткая заменена названной; у долгого слога долгая — того же звука («аа» → «ии»), иначе
    вышла бы невозможная запись «и» + «аа» (исправлено 2026-11-07, TD-FN-150). «Никакой» у
    долгого слога — неясно, что стало с маддом: строки нет."""
    vowels = [pos for pos in positions if reference[pos] in SHORT_VOWELS]
    long = [pos for pos in positions if reference[pos] in LONG_VOWELS]
    if heard is None or len(vowels) != 1 or not (heard in SHORT_VOWELS or heard == NO_VOWEL):
        return False
    if heard == NO_VOWEL:
        out.replace[vowels[0]] = ""
        return not long
    out.replace[vowels[0]] = heard
    out.replace.update(dict.fromkeys(long, _LONG_OF[heard]))
    return True


def _from_madd(reference: str, heard: str | None, positions: Sequence[int], out: "_Edits") -> bool:
    """«Длина» (2026-11-07, TD-FN-150): долгий прочитан кратко — долгая снята; краткий протянут —
    долгая того же звука на 2 харакята. Только в клетке ровно с одной краткой гласной."""
    vowels = [pos for pos in positions if reference[pos] in SHORT_VOWELS]
    long = [pos for pos in positions if reference[pos] in LONG_VOWELS]
    if heard is not None or len(vowels) != 1:
        return False
    if long:
        out.replace.update(dict.fromkeys(long, ""))
    else:
        out.after[vowels[0]] = _LONG_OF[reference[vowels[0]]] * 2
    return True


def _from_sukun(reference: str, heard: str | None, positions: Sequence[int], out: "_Edits") -> bool:
    silent = [
        pos for pos in _consonants(reference, positions)
        if not _vowel_after(reference, pos) and reference[pos + 1 : pos + 2] != reference[pos]
    ]  # fmt: skip
    if heard is None or heard not in SHORT_VOWELS or len(silent) != 1:
        return False
    out.after[silent[0]] = heard
    return True


def _from_shadda(
    reference: str, heard: str | None, positions: Sequence[int], out: "_Edits"
) -> bool:
    consonants = _consonants(reference, positions)
    if heard is not None or len({reference[pos] for pos in consonants}) != 1:
        return False
    if len(consonants) == 1:  # удвоения не было — прозвучало
        out.replace[consonants[0]] = reference[consonants[0]] * 2
        return True
    if len(consonants) == 2 and consonants[1] == consonants[0] + 1:  # удвоение потеряно
        out.replace[consonants[1]] = ""
        return True
    return False


def _from_extra(reference: str, heard: str | None, positions: Sequence[int], out: "_Edits") -> bool:
    del reference
    if heard is None or not positions:
        return False
    out.after[positions[-1]] = heard
    return True


@dataclass(slots=True)
class _Edits:
    """Правки эталона: ``replace[поз]`` — вместо фонемы, ``after[поз]`` — вставка после неё."""

    replace: dict[int, str] = field(default_factory=dict)
    after: dict[int, str] = field(default_factory=dict)


_DERIVE: Final = {
    MarkKind.LETTER: _from_letter,
    MarkKind.MISSING: _from_missing,
    MarkKind.VOWEL: _from_vowel,
    MarkKind.SUKUN: _from_sukun,
    MarkKind.SHADDA: _from_shadda,
    MarkKind.EXTRA: _from_extra,
    MarkKind.MADD: _from_madd,
}  # остальные виды (пять за «Ещё» и прежний «Шадда/сукун») строки не дают


def apply_marks(
    text: str, reference: str, cells: Sequence[Cell], marks: Sequence[Mark]
) -> str | None:
    """«Что прозвучало» из отметок — только где однозначно, иначе None (FR-63, ADR-0080).

    Нет отметок — эталон. По одной отметке в слоге из семи главных видов: «Буква» с буквой —
    согласная заменена (обе половины шадды); «Пропуск» — убран названный звук (без названия —
    весь слог); «Огласовка» — краткая заменена названной или убрана (``NO_VOWEL``); «Лишний звук»
    — вставлен после звуков слога; «Шадда» — удвоение единственной согласной переворачивается;
    «Сукун» — гласная вставлена после согласной без гласной; «Длина» — долгий ↔ краткий
    (2026-11-07). Любой другой вид, отметка без ответа
    или две отметки в одном слоге — строка не выводится.
    """
    if not marks:
        return reference
    where = phoneme_cells(text, reference, cells)
    if not where:
        return None
    by_cell: dict[int, list[Mark]] = {}
    for mark in marks:
        by_cell.setdefault(mark.cell, []).append(mark)
    edits = _Edits()
    for cell, given in by_cell.items():
        mark = given[0]
        derive = _DERIVE.get(mark.kind)
        if len(given) != 1 or derive is None:
            return None
        if not derive(reference, mark.heard, _cell_positions(where, cell), edits):
            return None
    return "".join(
        edits.replace.get(pos, ch) + edits.after.get(pos, "") for pos, ch in enumerate(reference)
    )


def marks_from_bot(
    text: str, reference: str, heard: str, cells: Sequence[Cell]
) -> tuple[Mark, ...]:
    """Ошибки бота как отметки по клеткам — для «Бот прав» и черновика «Исправить» (FR-63).

    Замена нескольких звуков и прочие замены, не сводимые к виду, отмечают клетку видом «Буква»
    без ответа: ошибка бота не теряется, но вид неточный. Один вид в клетке — один раз.
    """
    where = phoneme_cells(text, reference, cells)
    if not where:
        return ()
    errors = assess(reference, heard).errors
    deleted: dict[int, set[int]] = {}  # клетка → позиции пропущенных звуков
    for error in errors:
        if error.kind in (ErrorKind.SOUND_MISSING, ErrorKind.VOWEL_MISSING):
            cell = where[min(error.position, len(where) - 1)]
            deleted.setdefault(cell, set()).add(error.position)
    whole = {
        cell for cell, gone in deleted.items()
        if gone and gone >= set(_cell_positions(where, cell))
    }  # fmt: skip
    found: dict[tuple[int, MarkKind], Mark] = {}
    last = len(where) - 1
    for error in errors:
        # Замена нескольких звуков может лечь на границу слогов: отмечаем каждую клетку (как «!»).
        spanned = sorted(
            {where[min(error.position + k, last)] for k in range(max(len(error.expected), 1))}
        )
        for cell in spanned:
            mark = _mark_of(error, cell, whole)
            found.setdefault((mark.cell, mark.kind), mark)
    return tuple(sorted(found.values(), key=lambda m: m.cell))


def _extra_mark(cell: int, error: PronunciationError) -> Mark:
    one = len(error.heard) == 1 and (error.heard in CONSONANTS or error.heard in LONG_VOWELS)
    return Mark(cell, MarkKind.EXTRA, error.heard if one else None)


def _vowel_mark(cell: int, error: PronunciationError) -> Mark:
    if error.heard in SHORT_VOWELS:
        return Mark(cell, MarkKind.VOWEL, error.heard)
    return Mark(cell, MarkKind.LETTER)  # долгая вместо краткой: вид приблизительный


_BOT_MARKS: Final[dict[ErrorKind, Callable[[int, PronunciationError], Mark]]] = {
    ErrorKind.LETTER_SUBSTITUTION: lambda c, e: Mark(c, MarkKind.LETTER, e.heard),
    ErrorKind.VOWEL_SUBSTITUTION: _vowel_mark,
    ErrorKind.VOWEL_MISSING: lambda c, _: Mark(c, MarkKind.VOWEL, NO_VOWEL),
    ErrorKind.SOUND_MISSING: lambda c, e: Mark(c, MarkKind.MISSING, e.expected),
    ErrorKind.SHADDA_MISSING: lambda c, _: Mark(c, MarkKind.SHADDA),
    ErrorKind.MADD_TOO_SHORT: lambda c, _: Mark(c, MarkKind.MADD),
    ErrorKind.MADD_TOO_LONG: lambda c, _: Mark(c, MarkKind.MADD),
    ErrorKind.EXTRA_SOUND: _extra_mark,
}


def _mark_of(error: PronunciationError, cell: int, whole: set[int]) -> Mark:
    if error.kind in (ErrorKind.SOUND_MISSING, ErrorKind.VOWEL_MISSING) and cell in whole:
        return Mark(cell, MarkKind.MISSING)  # слог пропущен целиком — одна отметка на слог
    make = _BOT_MARKS.get(error.kind)
    # Прочие замены (звук вместо гласной, несколько звуков): клетка отмечена, вид приблизительный.
    return make(cell, error) if make else Mark(cell, MarkKind.LETTER)


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


_ANSWERS: Final[dict[MarkKind, tuple[Callable[[str], bool], str]]] = {
    MarkKind.VOWEL: (
        lambda h: h in SHORT_VOWELS or h == NO_VOWEL,
        "у «Огласовка» ответ — фатха, кясра, дамма или «никакой»",
    ),
    MarkKind.SUKUN: (
        lambda h: h in SHORT_VOWELS,
        "у «Сукун» ответ — какая гласная прозвучала: фатха, кясра или дамма",
    ),
    MarkKind.EXTRA: (
        lambda h: len(h) == 1 and (h in CONSONANTS or h in LONG_VOWELS),
        "у «Лишний звук» ответ — одна согласная или долгая гласная",
    ),
    MarkKind.MISSING: (
        lambda h: len(h) == 1 and h in PHONEME_ALPHABET,
        "у «Пропуск» ответ — один звук фонетического алфавита",
    ),
}


def _check_answer(mark: Mark, cells: Sequence[Cell]) -> None:
    """Ответ «что прозвучало» (``heard``) подходит к виду (FR-63, ADR-0080)."""
    kind, heard = mark.kind, mark.heard
    if heard is None:
        return
    if kind is MarkKind.VOWEL and _written_vowels(cells[mark.cell].piece) == {heard}:
        raise LabelError(f"в «{cells[mark.cell].piece}» и так «{heard}» — это не ошибка огласовки")
    if kind is MarkKind.LETTER:
        if heard not in CONSONANTS:
            hint = _HINTS.get(heard, "нужна одна согласная фонетического алфавита")
            raise LabelError(f"«{heard}» — не согласная: {hint}")
        if written_letters(cells[mark.cell].piece) == heard:
            raise LabelError(f"в клетке и так написана «{heard}» — это не «не та буква»")
        return
    rule = _ANSWERS.get(kind)
    if rule is None:
        raise LabelError("ответ «что прозвучало» есть только у видов с вопросом")
    ok, hint = rule
    if not ok(heard):
        raise LabelError(hint)


def _written_vowels(piece: str) -> set[str]:
    """Краткие гласные, написанные в кусочке (огласовки текста — те же знаки, что в фонемах)."""
    return {ch for ch in piece if ch in SHORT_VOWELS}


def check_marks(cells: Sequence[Cell], marks: Sequence[Mark]) -> None:
    """Отметки по правилам руководства: клетка есть в раскладке, вид в клетке — один раз и ответ
    «что прозвучало» подходит к виду (буква — у «Буква», гласная — у «Огласовка» и «Сукун»…)."""
    seen: set[tuple[int, MarkKind]] = set()
    for mark in marks:
        if not 0 <= mark.cell < len(cells):
            raise LabelError(f"клетки {mark.cell + 1} нет: в строке {len(cells)} клеток")
        if (mark.cell, mark.kind) in seen:
            raise LabelError("один и тот же вид ошибки отмечен в клетке дважды")
        seen.add((mark.cell, mark.kind))
        _check_answer(mark, cells)


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
    phonemes_source: PhonemesSource | None = None  # откуда ``actual`` (FR-63); None — нет строки
