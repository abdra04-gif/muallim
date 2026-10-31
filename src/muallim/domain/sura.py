"""Сура целиком и наизусть (FR-57…FR-59, ADR-0076): суры программы и оценка чтения по аятам.

Ученик читает суру одним голосовым, без остановки. Оценка — по аятам: какой аят чистый, какой
пропущен, где забыто слово, где ошибка произношения. Самоисправление и молчание — не ошибки
(решение автора 2026-10-31), но сохраняются событиями: по ним видно, где забывают (FR-60).
"""

import difflib
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from muallim.domain.assessment import ErrorKind, assess
from muallim.domain.curriculum import Curriculum, Lesson, LessonItem
from muallim.domain.phonetics import CONSONANTS
from muallim.domain.policy import GradingPolicy

SURA_SECTION = "sura"
BASMALA = "1:1"
_ANCHOR = 3  # совпавший кусок короче — случайное совпадение, а не прочитанное
_SIMILAR = 0.5  # лишний кусок настолько похож на соседнее слово — это перечитывание
_EXTRA_WORD = 3  # лишний кусок не короче (и с согласной) — лишнее слово, а не лишний звук
_TITLE = re.compile(r"^\s*\d+\.\s*(?:Сура\s+)?(?P<name>.*?)(?:\s*\(\d+/\d+\))?\s*$")


# ---------- суры программы ----------


@dataclass(frozen=True, slots=True)
class Sura:
    number: int
    name: str  # как в заголовке урока: «ад-Духа», «аль-Бакара, 1–5»
    lessons: tuple[Lesson, ...]  # уроки суры по порядку (части 1/2, 2/2…)
    ayahs: tuple[LessonItem, ...]  # карточки аятов; басмала перед сурой — не аят
    opening: LessonItem | None = None  # басмала перед сурой (у аль-Фатихи — None: это её аят 1)


def suras(curriculum: Curriculum) -> tuple[Sura, ...]:
    """Суры программы в порядке книги: подряд идущие уроки одной суры — одна сура."""
    groups: list[tuple[int, list[Lesson]]] = []
    for lesson in curriculum.lessons:
        if lesson.section != SURA_SECTION:
            continue
        number = _lesson_sura(lesson)
        if number is None:
            continue
        if groups and groups[-1][0] == number:
            groups[-1][1].append(lesson)
        else:
            groups.append((number, [lesson]))
    return tuple(_sura(number, lessons) for number, lessons in groups)


def find_sura(curriculum: Curriculum, lesson_id: str) -> Sura | None:
    """Сура, к которой относится урок; None — урок не про суру."""
    for sura in suras(curriculum):
        if any(lesson.id == lesson_id for lesson in sura.lessons):
            return sura
    return None


def _ref(item: LessonItem) -> tuple[int, int] | None:
    sura, _, aya = item.quran.partition(":")
    if not (sura.isdigit() and aya.isdigit()):
        return None
    return int(sura), int(aya)


def _lesson_sura(lesson: Lesson) -> int | None:
    refs = [r for r in (_ref(i) for i in lesson.items) if r is not None]
    if not refs:
        return None
    other = [s for s, _ in refs if s != 1]  # басмала (1:1) стоит перед каждой сурой
    return other[0] if other else 1


def _sura(number: int, lessons: list[Lesson]) -> Sura:
    ayahs: list[LessonItem] = []
    opening: LessonItem | None = None
    for lesson in lessons:
        for item in lesson.items:
            ref = _ref(item)
            if ref is None:
                continue
            if ref[0] == number:
                ayahs.append(item)
            elif item.quran == BASMALA and opening is None and not ayahs:
                opening = item
    match = _TITLE.match(lessons[0].title)
    name = match["name"] if match else lessons[0].title
    return Sura(number, name, tuple(lessons), tuple(ayahs), opening)


# ---------- чтение суры: сохраняется для исследования (FR-60) ----------


class SuraMode(StrEnum):
    TEXT = "text"  # по тексту: «📖 Вся сура»
    MEMORY = "memory"  # наизусть: «🎯 Наизусть» (🧠 — у «Закрепления»)


@dataclass(frozen=True, slots=True)
class ReadingChunk:
    """Кусок записи 6–10 с: строка для разметки и датасета."""

    start_ms: int
    end_ms: int
    heard: str
    first_ayah: int | None
    last_ayah: int | None


# ---------- оценка чтения ----------


@dataclass(frozen=True, slots=True)
class AyahReference:
    """Эталон аята: фонемы по словам, последнее — с остановкой; ``wasl_last`` — без остановки."""

    item_id: str
    number: int
    words: tuple[str, ...]
    wasl_last: str = ""

    @property
    def text(self) -> str:
        return "".join(self.words)


class AyahOutcome(StrEnum):
    CLEAN = "clean"  # засчитан (порог GradingPolicy, ни одного забытого слова)
    PRONUNCIATION = "pronunciation"  # прочитан, но с ошибками произношения ниже порога
    FORGOT_PART = "forgot_part"  # забыто хотя бы одно слово
    SKIPPED = "skipped"  # пропущен целиком, а следующие прочитаны
    NOT_REACHED = "not_reached"  # чтение закончилось раньше


class EventKind(StrEnum):
    PRONUNCIATION = "pronunciation"  # ошибка произношения (вид — ``error_kind``)
    FORGOT_WORD = "forgot_word"  # слово не прозвучало
    EXTRA = "extra"  # лишнее слово
    SELF_CORRECTED = "self_corrected"  # ошибся или повторил и сам прочитал верно — не ошибка
    PAUSE = "pause"  # молчание — не ошибка


@dataclass(frozen=True, slots=True)
class SuraEvent:
    kind: EventKind
    ayah: int  # номер аята в суре
    word: int | None  # слово в аяте, с нуля
    expected: str = ""
    heard: str = ""
    error_kind: ErrorKind | None = None
    duration_ms: int | None = None


@dataclass(frozen=True, slots=True)
class AyahResult:
    item_id: str
    number: int
    outcome: AyahOutcome
    score: int
    reference: str
    heard: str
    forgotten_words: int = 0
    extra_words: int = 0
    pronunciation_errors: int = 0


@dataclass(frozen=True, slots=True)
class SuraAssessment:
    ayahs: tuple[AyahResult, ...]
    events: tuple[SuraEvent, ...]
    score: int  # 0..100 по всей суре, без самоисправлений
    reference: str
    heard: str
    heard_ayahs: tuple[int, ...] = ()  # номер аята для каждого знака ``heard`` (0 — басмала)

    def ayahs_between(self, start: int, end: int) -> tuple[int | None, int | None]:
        """Первый и последний аят в куске ``heard[start:end]``; None — в куске нет аятов."""
        found = [n for n in self.heard_ayahs[start:end] if n]
        return (min(found), max(found)) if found else (None, None)

    @property
    def clean_count(self) -> int:
        return sum(a.outcome is AyahOutcome.CLEAN for a in self.ayahs)

    @property
    def complete(self) -> bool:
        """Сура прочитана целиком: все аяты чистые (зачёт «всё или ничего», FR-58)."""
        return bool(self.ayahs) and self.clean_count == len(self.ayahs)


@dataclass(frozen=True, slots=True)
class _Word:
    ayah: int  # индекс аята в списке (у басмалы — -1)
    index: int  # слово в аяте
    start: int
    end: int
    text: str


def assess_sura(
    ayahs: Sequence[AyahReference],
    heard: str,
    policy: GradingPolicy,
    *,
    opening: Sequence[str] = (),
    preamble: Sequence[str] = (),
    pauses: Sequence[tuple[int, int]] = (),
) -> SuraAssessment:
    """Оценить чтение суры по аятам.

    ``opening`` — басмала перед сурой, ``preamble`` — истиаза перед ней (урок 1 учит начинать с
    них): прочитал или нет — не ошибка, в аяты не входят. ``pauses`` — молчание: (позиция в
    ``heard``, длительность мс).
    """
    if not ayahs:
        raise ValueError("Нужен хотя бы один аят")
    words, ends = _layout(ayahs, heard, _prefix(heard, preamble, opening))
    reference = "".join(w.text for w in words)

    kept, corrections = _drop_self_corrections(reference, heard, words)
    clean = "".join(heard[i] for i in kept)
    matcher = difflib.SequenceMatcher(None, reference, clean, autojunk=False)
    ops = matcher.get_opcodes()

    events: list[SuraEvent] = []
    results: list[AyahResult] = []
    reached = _reached(ops, words, len(ayahs))
    pieces = _heard_by_ayah(ops, clean, words, len(ayahs), reached)
    last_reached = max((i for i, r in enumerate(reached) if r), default=-1)
    for i, ayah in enumerate(ayahs):
        ayah_words = [w for w in words if w.ayah == i]
        start = ayah_words[0].start
        ref_text = reference[start : ends[i]]
        got = pieces[i]
        if not reached[i]:
            outcome = AyahOutcome.NOT_REACHED if i > last_reached else AyahOutcome.SKIPPED
            results.append(AyahResult(ayah.item_id, ayah.number, outcome, 0, ref_text, got))
            continue
        result, ayah_events = _ayah(
            ayah, ref_text, got, words=ayah_words, offset=start, policy=policy
        )
        results.append(result)
        events.extend(ayah_events)

    events.extend(
        SuraEvent(EventKind.SELF_CORRECTED, ayahs[w.ayah].number, w.index)
        for w in corrections
        if w.ayah >= 0
    )
    for position, duration in pauses:
        word = _word_at(_ref_position(ops, _clean_position(kept, position)), words)
        if word is not None and word.ayah >= 0:
            events.append(
                SuraEvent(
                    EventKind.PAUSE, ayahs[word.ayah].number, word.index, duration_ms=duration
                )
            )
    events.sort(key=lambda e: (e.ayah, -1 if e.word is None else e.word))
    score = round(matcher.ratio() * 100) if clean else 0
    numbers = [a.number for a in ayahs]
    owner = _owners(reached)
    clean_ayahs = [
        a if a < 0 else owner[a] for a in _ayah_per_char(ops, words, len(ayahs), len(clean))
    ]
    per_char = [0] * len(heard)
    for c, original in enumerate(kept):
        per_char[original] = 0 if clean_ayahs[c] < 0 else numbers[clean_ayahs[c]]
    dropped = set(range(len(heard))) - set(kept)
    for k in sorted(dropped):  # перечитанное — к аяту предыдущего знака
        per_char[k] = per_char[k - 1] if k else 0
    return SuraAssessment(tuple(results), tuple(events), score, reference, heard, tuple(per_char))


def _ayah_per_char(
    ops: Sequence[tuple[str, int, int, int, int]], words: Sequence[_Word], count: int, size: int
) -> list[int]:
    """Индекс аята для каждого знака очищенного услышанного (-1 — басмала)."""
    out = [count - 1] * size
    for op, i1, _, j1, j2 in ops:
        for k in range(j1, j2):
            out[k] = _ayah_of(i1 + (k - j1) if op == "equal" else i1, words, count)
    return out


def _starts_with(heard: str, opening: str) -> bool:
    if not opening or not heard:
        return False
    head = heard[: len(opening)]
    return difflib.SequenceMatcher(None, opening, head, autojunk=False).ratio() >= 0.6


def _prefix(heard: str, preamble: Sequence[str], opening: Sequence[str]) -> tuple[str, ...]:
    """Что ученик прочитал перед сурой: истиаза и басмала, одна из них или ничего."""
    for words in (tuple(preamble) + tuple(opening), tuple(preamble), tuple(opening)):
        if words and _starts_with(heard, "".join(words)):
            return words
    return ()


def _layout(
    ayahs: Sequence[AyahReference], heard: str, opening: Sequence[str]
) -> tuple[list[_Word], list[int]]:
    """Слова эталона подряд; окончание аята — без остановки, если ученик читал слитно."""
    words: list[_Word] = []
    ends: list[int] = []
    pos = 0
    for k, text in enumerate(opening):
        words.append(_Word(-1, k, pos, pos + len(text), text))
        pos += len(text)
    for i, ayah in enumerate(ayahs):
        for k, written in enumerate(ayah.words):
            text = written
            last = k == len(ayah.words) - 1
            if last and ayah.wasl_last and i + 1 < len(ayahs):
                following = ayahs[i + 1].words[0] if ayahs[i + 1].words else ""
                if ayah.wasl_last + following in heard and written + following not in heard:
                    text = ayah.wasl_last
            words.append(_Word(i, k, pos, pos + len(text), text))
            pos += len(text)
        ends.append(pos)
    return words, ends


def _word_at(position: int, words: Sequence[_Word]) -> _Word | None:
    for word in words:
        if word.start <= position < word.end:
            return word
    return words[-1] if words and position >= words[-1].end else None


def _similar(a: str, b: str) -> bool:
    return bool(a and b) and difflib.SequenceMatcher(None, a, b).ratio() >= _SIMILAR


def _drop_self_corrections(
    reference: str, heard: str, words: Sequence[_Word]
) -> tuple[list[int], list[_Word]]:
    """Лишние куски, похожие на соседнее слово, — перечитывание: убрать из услышанного."""
    matcher = difflib.SequenceMatcher(None, reference, heard, autojunk=False)
    drop: set[int] = set()
    corrected: list[_Word] = []
    for op, i1, _, j1, j2 in matcher.get_opcodes():
        if op != "insert":
            continue
        extra = heard[j1:j2]
        if not _is_word(extra):  # лишний знак (قُل → قُلُ) — ошибка, а не перечитывание
            continue
        near = (_word_at(k, words) for k in (i1 - 1, i1, i1 + 1) if k >= 0)
        candidates = [w for w in dict.fromkeys(near) if w is not None and _similar(extra, w.text)]
        if not candidates:
            continue
        best = max(candidates, key=lambda w: difflib.SequenceMatcher(None, extra, w.text).ratio())
        drop.update(range(j1, j2))
        corrected.append(best)
    return [i for i in range(len(heard)) if i not in drop], corrected


def _clean_position(kept: Sequence[int], position: int) -> int:
    return sum(1 for i in kept if i < position)


def _ref_position(ops: Sequence[tuple[str, int, int, int, int]], position: int) -> int:
    for op, i1, i2, j1, j2 in ops:
        if j1 <= position < j2 or (op != "delete" and position == j2 == j1):
            return i1 + min(position - j1, max(i2 - i1 - 1, 0)) if op == "equal" else i1
    return ops[-1][2] if ops else 0


def _ayah_of(position: int, words: Sequence[_Word], count: int) -> int:
    """Аят по позиции в эталоне; басмала перед сурой — -1."""
    word = _word_at(position, words)
    if word is None:
        return count - 1
    return min(word.ayah, count - 1)


def _heard_by_ayah(
    ops: Sequence[tuple[str, int, int, int, int]],
    clean: str,
    words: Sequence[_Word],
    count: int,
    reached: Sequence[bool],
) -> list[str]:
    """Услышанное, разложенное по аятам по выравниванию с эталоном.

    Звуки, случайно совпавшие с непрочитанным аятом (пропущен, не дошёл), отдаются соседнему
    прочитанному: иначе в нём появляются ложные ошибки (ревью кода 2026-10-31).
    """
    owner = _owners(reached)
    pieces = [""] * count
    for op, i1, i2, j1, j2 in ops:
        if op == "equal":
            for k in range(i2 - i1):
                ayah = _ayah_of(i1 + k, words, count)
                if ayah >= 0:
                    pieces[owner[ayah]] += clean[j1 + k]
        elif op in ("replace", "insert") and (ayah := _ayah_of(i1, words, count)) >= 0:
            pieces[owner[ayah]] += clean[j1:j2]
    return pieces


def _owners(reached: Sequence[bool]) -> list[int]:
    """Чей звук: непрочитанный аят — ближайшему прочитанному перед ним (нет такого — после)."""
    owner = list(range(len(reached)))
    last = next((i for i, r in enumerate(reached) if r), None)
    for i, r in enumerate(reached):
        if r:
            last = i
        elif last is not None:
            owner[i] = last
    return owner


def _reached(
    ops: Sequence[tuple[str, int, int, int, int]], words: Sequence[_Word], count: int
) -> list[bool]:
    """Аят прочитан, если совпала хотя бы треть его звуков: короткий общий кусок с соседним
    аятом («لَىٰ») — случайность, а не чтение."""
    matched = [0] * count
    size = [0] * count
    for word in words:
        if word.ayah >= 0:
            size[word.ayah] += word.end - word.start
    for op, i1, i2, _, _ in ops:
        if op != "equal" or i2 - i1 < _ANCHOR:
            continue
        for k in range(i1, i2):
            hit = _word_at(k, words)
            if hit is not None and hit.ayah >= 0:
                matched[hit.ayah] += 1
    return [m >= _ANCHOR and 3 * m >= n for m, n in zip(matched, size, strict=True)]


def _ayah(
    ayah: AyahReference,
    reference: str,
    heard: str,
    *,
    words: Sequence[_Word],
    offset: int,
    policy: GradingPolicy,
) -> tuple[AyahResult, list[SuraEvent]]:
    assessment = assess(reference, heard)
    matcher = difflib.SequenceMatcher(None, reference, heard, autojunk=False)
    deleted = {
        k for op, i1, i2, _, _ in matcher.get_opcodes() if op == "delete" for k in range(i1, i2)
    }
    forgotten = [
        w
        for w in words
        if (sounds := [k for k in range(w.start, w.end) if reference[k - offset] in CONSONANTS])
        and all(k - offset in deleted for k in sounds)
    ]
    forgotten_ids = {w.index for w in forgotten}

    events = [SuraEvent(EventKind.FORGOT_WORD, ayah.number, w.index, w.text) for w in forgotten]
    extra = pronunciation = 0
    for error in assessment.errors:
        word = _word_at(error.position + offset, words)
        index = word.index if word is not None else None
        if index in forgotten_ids and error.heard == "":
            continue
        if error.expected == "" and _is_word(error.heard):
            extra += 1
            events.append(SuraEvent(EventKind.EXTRA, ayah.number, index, "", error.heard))
            continue
        pronunciation += 1
        events.append(
            SuraEvent(
                EventKind.PRONUNCIATION,
                ayah.number,
                index,
                error.expected,
                error.heard,
                error.kind,
            )
        )
    if forgotten:
        outcome = AyahOutcome.FORGOT_PART
    elif policy.is_mastered(assessment.score) and not extra:
        outcome = AyahOutcome.CLEAN
    else:
        outcome = AyahOutcome.PRONUNCIATION
    result = AyahResult(
        ayah.item_id,
        ayah.number,
        outcome,
        assessment.score,
        reference,
        heard,
        forgotten_words=len(forgotten),
        extra_words=extra,
        pronunciation_errors=pronunciation,
    )
    return result, events


def _is_word(text: str) -> bool:
    return len(text) >= _EXTRA_WORD and any(ch in CONSONANTS for ch in text)


@dataclass(frozen=True, slots=True)
class SuraReading:
    """Одно голосовое со всей сурой (по тексту или наизусть)."""

    id: UUID
    learner_id: UUID
    sura: int
    mode: SuraMode
    attempt_number: int  # какая по счёту попытка этой суры в этом режиме
    days_since_last: int | None  # дней с прошлого чтения суры в любом режиме; None — впервые
    studied_by_text: bool  # все уроки суры были пройдены до этого чтения
    assessment: SuraAssessment
    chunks: tuple[ReadingChunk, ...]
    credited: tuple[str, ...]  # карточки, засчитанные этим чтением (FR-58)
    model_version: str
    curriculum_version: str
    app_version: str
    audio_sha256: str | None  # только с согласия ученика
    audio_duration_ms: int
    processing_ms: int
    created_at: datetime
    policy: GradingPolicy | None = None  # порог, по которому оценено (ADR-0019, TD-FN-116)

    @property
    def passed(self) -> bool:
        return self.assessment.complete
