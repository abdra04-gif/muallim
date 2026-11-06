"""FR-62 (ADR-0079): разметка учителем по клеткам — правила домена и сценарии на тестовых портах.

Учитель оценивает **чтение ученика**, а не бота: «✅ Прочитал чисто» — эталон без меток; иначе —
метки «клетка → вид (→ буква)». Клетки аята суры — слоги из ``curriculum/syllables/ayat.yaml``,
остальных строк — буквы (``domain.arabic.clusters``). ``apply_marks`` выводит
``corrected_phonemes`` только там, где это однозначно; ``agree``/``fix`` считается само.

Тексты — curriculum/course.ru.yaml и curriculum/syllables/ayat.yaml; эталоны в фонемах — выход
quran-transcript с MOSHAF_PARAMS бота (как в tests/unit/test_arabic_text.py и
test_error_groups.py). Новых имён домена ещё нет — они берутся через модуль (``ann.X``), чтобы
каждый тест падал сам по себе, а не весь файл при сборке.
"""

from functools import cache
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
import yaml

import muallim.application.use_cases.annotation as uc
import muallim.domain.annotation as ann
from muallim.application.use_cases.annotation import AnnotatorAccess, NextAnnotation, NotAnnotator
from muallim.domain import arabic
from muallim.domain.annotation import AnnotationSource, AnnotationStatus, AnnotationTask, LabelError
from muallim.domain.learner import Learner
from muallim.domain.syllables import SyllableCell
from tests.fakes import (
    FixedClock,
    InMemoryAnnotationTasks,
    InMemoryAnnotators,
    InMemoryAudio,
    ListEventLog,
    SpyUoW,
)

ROOT = Path(__file__).resolve().parents[2]
AYAT = ROOT / "curriculum" / "syllables" / "ayat.yaml"
COURSE = ROOT / "curriculum" / "course.ru.yaml"


@cache
def _item_texts() -> dict[str, str]:
    """Тексты пунктов программы как есть (порядок огласовок — как в course.ru.yaml, не NFC)."""
    lessons = yaml.safe_load(COURSE.read_text(encoding="utf-8"))["lessons"]
    return {i["id"]: i["text"] for les in lessons for i in les["items"]}


# L097-03 (1:2) — в ayat.yaml 12 слогов: ٱلْ|حَمْ|دُ  لِ|لَّ|هِ  رَ|بِّ  ٱلْ|عَـٰ|لَ|مِينَ
FATIHA_2 = _item_texts()["L097-03"]  # ٱلْحَمْدُ لِلَّهِ رَبِّ ٱلْعَـٰلَمِينَ
FATIHA_2_PHONEMES = "ءَلحَمدُلِللَااهِرَببِلعَاالَمِۦۦن"
P = FATIHA_2_PHONEMES
# Фонемы каждой клетки в P: согласная клетки и всё до следующей согласной другой клетки
# (по domain.arabic.owners): «دُ» — P[6:8], «لِ» — P[8:10], «بِّ» — P[19:22] (обе половины
# шадды), «ٱلْ» после «رَبِّ» — P[22:23] (ٱ внутри фразы не читается), «عَـٰ» — P[23:27],
# «مِينَ» — P[29:34], первая «ٱلْ» — P[0:3].
SUB_AIN = P[:23] + "ء" + P[24:]  # ع → ء в клетке 9 «عَـٰ»
NO_SHADDA = P[:20] + P[21:]  # шадда «بِّ» не выдержана (клетка 7)
NO_DAL = P[:6] + P[8:]  # пропущен слог «دُ» (клетка 2)
EXTRA_NUN = P + "ن"  # лишний звук после последней согласной (клетка 11)
WRONG_VOWEL = P[:7] + "َ" + P[8:]  # «دُ» прочитан с фатхой (клетка 2)
SHORT_MADD = P[:25] + P[26:]  # мадд «عَـٰ» укорочен (клетка 9)
EXTRA_BEFORE_ALL = "ه" + P  # лишний звук до первой согласной — предыдущей нет (клетка 0)

# L024-07 (урок ح, с. 21) — не сура: клетки по буквам
L024_07 = _item_texts()["L024-07"]  # مُحْسِنُ مَحْشَرُ مِنْحَرُ مَحْفَلُ أَحْسَنَ
L024_07_PHONEMES = "مُحسِنُمَحشَرُمِنحَرُمَحفَلُءَحسَنَ"
L024_07_HA_AS_HA = L024_07_PHONEMES[:9] + "ه" + L024_07_PHONEMES[10:]  # ح → ه в «مَحْشَرُ»

ANNOTATOR_TG, STRANGER_TG = 900, 901
ALL_KINDS = {
    "letter", "vowel", "madd", "shadda_sukun", "missing", "extra",
    "tafkhim", "ghunna", "qalqala", "halting", "wrong_stop",
}  # fmt: skip


@cache
def _ayat() -> dict[str, list[list[list[str]]]]:
    rows = yaml.safe_load(AYAT.read_text(encoding="utf-8"))["ayat"]
    return {r["text"]: r["words"] for r in rows}


def _ayah(text: str) -> tuple[tuple[SyllableCell, ...], ...]:
    return tuple(tuple(SyllableCell(p, s) for p, s in word) for word in _ayat()[text])


def _pieces(text: str) -> list[str]:
    return [piece for word in _ayat()[text] for piece, _ in word]


def _cells(text: str = FATIHA_2, *, syllables: bool = True) -> Any:
    return ann.annotation_cells(text, _ayah(text) if syllables else None)


def _mark(cell: int, kind: str, letter: str | None = None) -> Any:
    return ann.Mark(cell, ann.MarkKind(kind), letter)


# ---------- виды ошибок ----------
def test_there_are_eleven_mark_kinds() -> None:
    assert {str(k) for k in ann.MarkKind} == ALL_KINDS


def test_mark_kinds_fall_into_three_groups_as_approved() -> None:
    """Сказал неправильно · таджвид · как читает (решение автора 2026-10-31)."""
    group = {str(k): k.group for k in ann.MarkKind}
    said = {group[k] for k in ("letter", "vowel", "madd", "shadda_sukun", "missing", "extra")}
    tajwid = {group[k] for k in ("tafkhim", "ghunna", "qalqala")}
    reading = {group[k] for k in ("halting", "wrong_stop")}
    assert len(said) == len(tajwid) == len(reading) == 1
    assert len(said | tajwid | reading) == 3


def test_mark_kind_codes_are_short_unique_and_fit_a_button() -> None:
    codes = [k.code for k in ann.MarkKind]
    assert len(set(codes)) == len(codes) == 11
    assert all(1 <= len(c) <= 3 and c.isascii() and ":" not in c for c in codes)


# ---------- клетки ----------
def test_sura_ayah_cells_are_its_syllables_in_reading_order() -> None:
    cells = _cells()
    assert [c.index for c in cells] == list(range(12))
    assert [c.piece for c in cells] == _pieces(FATIHA_2)
    assert all(FATIHA_2[c.start : c.end] == c.piece for c in cells)


def test_cell_pieces_add_up_to_the_text_for_every_ayah_of_the_file() -> None:
    for text in _ayat():
        cells = _cells(text)
        assert "".join(c.piece for c in cells) == text.replace(" ", ""), text
        assert all(text[c.start : c.end] == c.piece for c in cells), text
        assert [c.start for c in cells] == sorted(c.start for c in cells), text


def test_line_without_syllables_is_split_into_letters() -> None:
    cells = _cells(L024_07, syllables=False)
    clusters = arabic.clusters(L024_07)
    assert [(c.index, c.start, c.end) for c in cells] == [
        (n, k.start, k.end) for n, k in enumerate(clusters)
    ]
    assert [c.piece for c in cells] == [L024_07[k.start : k.end] for k in clusters]


# L031-03 — долгие гласные: буква мадда без огласовки — в клетке своей согласной (дополнено
# 2026-11-01, п. 5). Эталон — выход quran-transcript (tests/unit/test_error_groups.py).
L031_03 = _item_texts()["L031-03"]  # بَا بِي بُو تَا تِي تُو ثَا ثِي ثُو
L031_03_PHONEMES = "بَاابِۦۦبُۥۥتَااتِۦۦتُۥۥثَااثِۦۦثُۥۥ"


def test_madd_letter_shares_the_cell_of_its_consonant() -> None:
    """В клетке всегда есть звук: «بَا» — одна клетка, а не «بَ» и пустая «ا»."""
    ba = L031_03.split()[0]  # «بَا»
    (cell,) = ann.annotation_cells(ba, None)
    assert cell.piece == ba
    cells = _cells(L031_03, syllables=False)
    assert [c.piece for c in cells] == L031_03.split()  # каждое слово — слог с маддом
    assert all(L031_03[c.start : c.end] == c.piece for c in cells)


def test_missing_cell_with_madd_drops_the_long_vowel_too() -> None:
    cells = _cells(L031_03, syllables=False)
    marks = [_mark(0, "missing")]
    actual = ann.apply_marks(L031_03, L031_03_PHONEMES, cells, marks)
    assert actual == L031_03_PHONEMES[4:]  # без «بَاا»
    status = ann.marks_status(L031_03_PHONEMES, L031_03_PHONEMES, actual, marks)
    assert status is AnnotationStatus.FIX


def test_short_madd_is_the_cell_of_its_consonant_by_letters() -> None:
    cells = _cells(L031_03, syllables=False)
    heard = L031_03_PHONEMES[:3] + L031_03_PHONEMES[4:]  # «بَا» коротко
    assert ann.bot_cells(L031_03, L031_03_PHONEMES, heard, cells) == frozenset({0})


# ---------- где ошибку нашёл бот ----------
@pytest.mark.parametrize(
    ("heard", "expected"),
    [
        (P, set()),  # бот ошибок не нашёл
        (SUB_AIN, {9}),  # замена буквы → её слог
        (NO_SHADDA, {7}),  # шадда — слог «بِّ»
        (NO_DAL, {2}),  # пропуск слога
        (EXTRA_NUN, {11}),  # вставка — к клетке предыдущей согласной
        (WRONG_VOWEL, {2}),  # огласовка — слог её согласной
        (SHORT_MADD, {9}),  # укороченный мадд — слог, где он пишется
        (EXTRA_BEFORE_ALL, {0}),  # вставка в самом начале — к первой клетке
    ],
)
def test_bot_cells_point_to_the_syllable_of_each_bot_error(heard: str, expected: set[int]) -> None:
    assert ann.bot_cells(FATIHA_2, P, heard, _cells()) == frozenset(expected)


def test_bot_cells_by_letters_outside_suras() -> None:
    cells = _cells(L024_07, syllables=False)
    assert ann.bot_cells(L024_07, L024_07_PHONEMES, L024_07_HA_AS_HA, cells) == frozenset({5})


# ---------- что прозвучало: только однозначное ----------
@pytest.mark.parametrize(
    ("marks", "expected"),
    [
        ([], P),  # «✅ Прочитал чисто» — эталон
        ([("letter", 9, "ء")], SUB_AIN),  # одна звучащая согласная в слоге
        ([("letter", 7, "م")], P[:19] + "مم" + P[21:]),  # шадда — обе половины
        ([("letter", 8, "ر")], P[:22] + "ر" + P[23:]),  # ٱ внутри фразы не звучит
        ([("missing", 2, None)], NO_DAL),  # пропуск — согласная с огласовкой
        ([("missing", 7, None)], P[:19] + P[22:]),  # пропуск слога с шаддой
        ([("missing", 11, None)], P[:29]),  # пропуск слога с маддом
        ([("missing", 0, None)], P[3:]),  # «ٱلْ» в начале аята: ء, огласовка и ل
        ([("letter", 9, "ء"), ("missing", 2, None)], P[:6] + P[8:23] + "ء" + P[24:]),
    ],
)
def test_apply_marks_gives_phonemes_where_unambiguous(
    marks: list[tuple[str, int, str | None]], expected: str
) -> None:
    got = ann.apply_marks(FATIHA_2, P, _cells(), [_mark(c, k, h) for k, c, h in marks])
    assert got == expected


@pytest.mark.parametrize(
    "marks",
    [
        [("vowel", 2, None)],
        [("madd", 9, None)],
        [("shadda_sukun", 7, None)],
        [("extra", 11, None)],
        [("tafkhim", 6, None)],
        [("ghunna", 11, None)],
        [("qalqala", 2, None)],
        [("halting", 0, None)],
        [("wrong_stop", 5, None)],
        [("letter", 9, None)],  # не та буква, но какая — не указано
        [("letter", 1, "ه")],  # «حَمْ» — две звучащие согласные: какую заменить — неясно
        [("letter", 9, "ء"), ("vowel", 9, None)],  # в клетке ещё и огласовка
        [("missing", 2, None), ("vowel", 5, None)],
    ],
)
def test_apply_marks_gives_nothing_when_phonemes_are_not_determined(
    marks: list[tuple[str, int, str | None]],
) -> None:
    assert ann.apply_marks(FATIHA_2, P, _cells(), [_mark(c, k, h) for k, c, h in marks]) is None


def test_apply_marks_by_letters_outside_suras() -> None:
    cells = _cells(L024_07, syllables=False)
    marks = [_mark(5, "letter", "ه")]
    assert ann.apply_marks(L024_07, L024_07_PHONEMES, cells, marks) == L024_07_HA_AS_HA


# ---------- согласие с ботом считается само ----------
@pytest.mark.parametrize(
    ("bot_heard", "marks", "expected"),
    [
        (P, [], "agree"),  # прочитал чисто, бот тоже ошибок не нашёл
        (SUB_AIN, [], "fix"),  # прочитал чисто, а бот нашёл ошибку
        (SUB_AIN, [("letter", 9, "ء")], "agree"),  # учитель слышит то же, что бот
        (P, [("letter", 9, "ء")], "fix"),  # бот ошибку пропустил
        (SUB_AIN, [("letter", 9, "ه")], "fix"),  # ошибка там же, но буква другая
        (SUB_AIN, [("vowel", 9, None)], "fix"),  # фонемы не выводятся — согласия не видно
        (NO_DAL, [("missing", 2, None)], "agree"),  # бот тоже не услышал слог «دُ»
        (P, [("missing", 2, None)], "fix"),  # бот пропуск не заметил
    ],
)
def test_marks_status_is_agree_only_when_reading_matches_what_bot_heard(
    bot_heard: str, marks: list[tuple[str, int, str | None]], expected: str
) -> None:
    given = [_mark(c, k, h) for k, c, h in marks]
    actual = ann.apply_marks(FATIHA_2, P, _cells(), given)
    assert ann.marks_status(bot_heard, P, actual, given) == AnnotationStatus(expected)


# ---------- проверка меток ----------
def test_valid_marks_pass_the_check() -> None:
    ann.check_marks(
        _cells(),
        [_mark(9, "letter", "ء"), _mark(9, "vowel"), _mark(11, "missing"), _mark(1, "letter")],
    )


@pytest.mark.parametrize(
    "marks",
    [
        [(12, "vowel", None)],  # клеток всего 12: номера 0–11
        [(-1, "vowel", None)],
        [(2, "vowel", "ء")],  # буква — только у «не та буква»
        [(2, "missing", "د")],
        [(9, "letter", "َ")],  # огласовка — не согласная
        [(9, "letter", "أ")],  # не фонема: хамза пишется «ء»
        [(9, "letter", "x")],
        [(9, "letter", "ع")],  # прозвучала та же буква, что в тексте, — это не «не та буква»
        [(2, "vowel", None), (2, "vowel", None)],  # один вид дважды в одной клетке
    ],
)
def test_check_marks_rejects_marks_against_the_rules(
    marks: list[tuple[int, str, str | None]],
) -> None:
    with pytest.raises(LabelError):
        ann.check_marks(_cells(), [_mark(c, k, h) for c, k, h in marks])


# ---------- сценарии ----------
class FakeSyllables:
    """Фейк порта ``AyahSyllables``: знает разбор только переданных текстов (из ayat.yaml)."""

    def __init__(self, *texts: str) -> None:
        self.ayat = {t: _ayah(t) for t in texts}

    def for_text(self, text: str) -> tuple[tuple[SyllableCell, ...], ...] | None:
        return self.ayat.get(text)


def _learner(tg: int) -> Learner:
    return Learner(UUID(int=tg), tg, f"L-{tg}", "ru", FixedClock().now())


def _task(n: int, text: str, reference: str, heard: str) -> AnnotationTask:
    return AnnotationTask(
        attempt_id=UUID(int=n), item_id=f"X{n}", item_text=text, page=None, line=None,
        bot_passed=heard == reference, bot_errors=(), reference_phonemes=reference,
        bot_heard=heard, learner_says=None, audio_sha256=f"{n:064x}",
    )  # fmt: skip


class World:
    """A1 — разметчик из настроек; задачи: 1 — аят с ошибкой бота в «عَـٰ», 2 — тот же аят,
    бот ошибок не нашёл, 3 — строка урока ح (по буквам), бот услышал ه вместо ح."""

    def __init__(self) -> None:
        self.clock = FixedClock()
        self.tasks = InMemoryAnnotationTasks([
            _task(1, FATIHA_2, P, SUB_AIN),
            _task(2, FATIHA_2, P, P),
            _task(3, L024_07, L024_07_PHONEMES, L024_07_HA_AS_HA),
        ])  # fmt: skip
        self.audio = InMemoryAudio({t.audio_sha256: b"ogg" for t in self.tasks.tasks})
        self.events, self.uow = ListEventLog(), SpyUoW()
        self.access = AnnotatorAccess(InMemoryAnnotators(), {ANNOTATOR_TG: "A1"})
        self.syllables = FakeSyllables(FATIHA_2)

    def next(self) -> NextAnnotation:
        return NextAnnotation(
            self.access, self.tasks, self.audio, self.events, self.uow, syllables=self.syllables
        )

    def submit(self) -> Any:
        return uc.SubmitMarks(
            access=self.access, tasks=self.tasks, uow=self.uow, events=self.events,
            clock=self.clock, syllables=self.syllables,
        )  # fmt: skip


async def test_task_shown_to_annotator_has_syllable_cells_and_bot_cells() -> None:
    w = World()
    shown = await w.next().execute(_learner(ANNOTATOR_TG))
    assert shown is not None
    assert [c.piece for c in shown.task.cells] == _pieces(FATIHA_2)
    assert shown.task.bot_cells == frozenset({9})


async def test_task_outside_suras_has_letter_cells() -> None:
    w = World()
    exclude = frozenset({UUID(int=1), UUID(int=2)})
    shown = await w.next().execute(_learner(ANNOTATOR_TG), exclude)
    assert shown is not None
    assert len(shown.task.cells) == len(arabic.clusters(L024_07))
    assert shown.task.bot_cells == frozenset({5})


async def test_letter_mark_like_bot_is_saved_as_agree_with_its_cell() -> None:
    w = World()
    saved = await w.submit().execute(
        _learner(ANNOTATOR_TG), UUID(int=1), [_mark(9, "letter", "ء")], seconds_spent=12
    )
    assert saved is True
    (label,) = w.tasks.labels
    assert (label.annotator, label.status, label.actual) == ("A1", AnnotationStatus.AGREE, SUB_AIN)
    assert label.entry == "cells" and label.source is AnnotationSource.TELEGRAM
    assert label.seconds_spent == 12
    ((mark,),) = w.tasks.marks[UUID(int=1)]
    piece = _pieces(FATIHA_2)[9]
    assert (mark.cell, mark.layout, mark.piece, mark.kind) == (9, "syllables", piece, "letter")
    assert FATIHA_2[mark.char_start : mark.char_end] == piece
    assert (mark.heard_letter, mark.bot_flagged) == ("ء", True)
    assert w.uow.commits == 1
    assert w.events.events[-1][0] == "annotation_submitted"


async def test_clean_reading_is_the_reference_without_marks() -> None:
    w = World()
    me = _learner(ANNOTATOR_TG)
    await w.submit().execute(me, UUID(int=2), [])  # бот тоже ошибок не нашёл
    await w.submit().execute(me, UUID(int=1), [])  # бот нашёл ошибку, учитель — нет
    assert [(lb.status, lb.actual, lb.entry) for lb in w.tasks.labels] == [
        (AnnotationStatus.AGREE, P, "cells"), (AnnotationStatus.FIX, P, "cells"),
    ]  # fmt: skip
    assert [w.tasks.marks[UUID(int=n)] for n in (2, 1)] == [[[]], [[]]]


async def test_several_kinds_in_one_cell_are_saved_as_fix_without_phonemes() -> None:
    w = World()
    marks = [_mark(2, "vowel"), _mark(2, "tafkhim"), _mark(11, "missing")]
    await w.submit().execute(_learner(ANNOTATOR_TG), UUID(int=2), marks)
    (label,) = w.tasks.labels
    assert (label.status, label.actual, label.entry) == (AnnotationStatus.FIX, None, "cells")
    saved = {(m.cell, str(m.kind), m.bot_flagged) for m in w.tasks.marks[UUID(int=2)][-1]}
    assert saved == {(2, "vowel", False), (2, "tafkhim", False), (11, "missing", False)}


async def test_marks_on_a_line_outside_suras_are_saved_by_letters() -> None:
    w = World()
    await w.submit().execute(_learner(ANNOTATOR_TG), UUID(int=3), [_mark(5, "letter", "ه")])
    (label,) = w.tasks.labels
    assert (label.status, label.actual) == (AnnotationStatus.AGREE, L024_07_HA_AS_HA)
    ((mark,),) = w.tasks.marks[UUID(int=3)]
    assert (mark.layout, mark.cell, mark.bot_flagged) == ("letters", 5, True)
    assert L024_07[mark.char_start : mark.char_end] == mark.piece


async def test_marks_against_the_rules_are_not_saved() -> None:
    w = World()
    with pytest.raises(LabelError):
        await w.submit().execute(_learner(ANNOTATOR_TG), UUID(int=1), [_mark(40, "vowel")])
    assert w.tasks.labels == [] and w.uow.commits == 0


async def test_stranger_cannot_save_marks() -> None:
    w = World()
    with pytest.raises(NotAnnotator):
        await w.submit().execute(_learner(STRANGER_TG), UUID(int=1), [])
    assert w.tasks.labels == []


async def test_marks_for_deleted_attempt_are_not_saved() -> None:
    w = World()
    assert await w.submit().execute(_learner(ANNOTATOR_TG), UUID(int=99), []) is False
    assert w.tasks.labels == []


async def test_every_label_keeps_its_own_cells() -> None:
    """Повторная разметка той же записи (↩️ Переделать) — новая метка со своими клетками."""
    w = World()
    me = _learner(ANNOTATOR_TG)
    await w.submit().execute(me, UUID(int=1), [_mark(9, "letter", "ء")])
    await w.submit().execute(me, UUID(int=1), [_mark(2, "missing"), _mark(5, "vowel")])
    first, second = w.tasks.marks[UUID(int=1)]
    assert [(m.cell, str(m.kind)) for m in first] == [(9, "letter")]
    assert sorted((m.cell, str(m.kind)) for m in second) == [(2, "missing"), (5, "vowel")]


async def test_self_correction_is_kept_with_marks() -> None:
    w = World()
    await w.submit().execute(
        _learner(ANNOTATOR_TG), UUID(int=1), [_mark(9, "letter", "ء")], self_corrected=True
    )
    assert w.tasks.labels[-1].self_corrected is True


async def test_comment_is_saved_with_the_marks() -> None:
    w = World()
    await w.submit().execute(
        _learner(ANNOTATOR_TG), UUID(int=1), [_mark(9, "vowel")], comment=" сомневаюсь "
    )
    assert w.tasks.labels[-1].comment == "сомневаюсь"


async def test_bot_is_right_by_the_same_rule_for_cells_and_manual_entry() -> None:
    """Одно правило «бот прав» (дополнено 2026-11-01, п. 5): ошибки относительно эталона равны.

    Бот услышал калькалю при остановке («ڇ») — по методике это не ошибка. «Чисто» клетками и
    тот же эталон, введённый вручную, дают ``agree``; в ``corrected_phonemes`` — что услышал бот
    (``check_label``, как в пакете Excel).
    """
    w = World()
    heard = P + "ڇ"
    w.tasks.tasks = [_task(4, FATIHA_2, P, heard), _task(5, FATIHA_2, P, heard)]
    assert ann.marks_status(heard, P, P, []) is AnnotationStatus.AGREE
    me = _learner(ANNOTATOR_TG)
    await w.submit().execute(me, UUID(int=4), [])
    manual = uc.SubmitAnnotation(w.access, w.tasks, w.uow, w.events, w.clock)
    await manual.execute(me, UUID(int=5), AnnotationStatus.FIX, actual=P, reading=True)
    assert [(lb.status, lb.actual) for lb in w.tasks.labels] == [
        (AnnotationStatus.AGREE, heard), (AnnotationStatus.AGREE, heard),
    ]  # fmt: skip


async def test_manual_phoneme_entry_is_marked_as_phonemes() -> None:
    """«Фонемы вручную» — прежний ``SubmitAnnotation``; в метке видно, как она введена."""
    w = World()
    submit = uc.SubmitAnnotation(w.access, w.tasks, w.uow, w.events, w.clock)
    await submit.execute(_learner(ANNOTATOR_TG), UUID(int=2), AnnotationStatus.FIX, actual=SUB_AIN)
    assert w.tasks.labels[-1].entry == "phonemes"
