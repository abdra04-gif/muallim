"""FR-63 (ADR-0080): разметка 3.0 — из отметки главного вида выводится «что прозвучало».

Шесть главных видов: Буква (какая прозвучала), Пропуск (какой звук пропущен), Огласовка
(а / и / у / никакой), Лишний звук, Шадда (удвоение переворачивается), Сукун (какая гласная
прозвучала). Остальные шесть (Длина, Твёрдость, Гунна, Калькаля, Запинка, Пауза не там) строки
не дают. «Бот прав» сохраняет ответ бота; отметки бота (``marks_from_bot``) становятся
черновиком «Исправить».

Расклад эталона ``P`` по слогам (индексы фонем):
0 «ٱلْ» P[0:3] · 1 «حَمْ» P[3:6] · 2 «دُ» P[6:8] · 3 «لِ» P[8:10] · 4 «لَّ» P[10:15] ·
5 «هِ» P[15:17] · 6 «رَ» P[17:19] · 7 «بِّ» P[19:22] · 8 «ٱلْ» P[22:23] · 9 «عَـٰ» P[23:27] ·
10 «لَ» P[27:29] · 11 «مِينَ» P[29:34].
"""

from typing import Any
from uuid import UUID

import pytest

import muallim.application.use_cases.annotation as uc
import muallim.domain.annotation as ann
from muallim.application.use_cases.annotation import NotAnnotator
from muallim.domain.annotation import AnnotationStatus, LabelError
from tests.unit.test_annotation_marks import (
    ANNOTATOR_TG,
    EXTRA_NUN,
    FATIHA_2,
    L024_07,
    L024_07_PHONEMES,
    NO_DAL,
    NO_SHADDA,
    STRANGER_TG,
    SUB_AIN,
    WRONG_VOWEL,
    P,
    World,
    _cells,
    _learner,
    _mark,
    _task,
)

FATHA, KASRA, DAMMA = "َ", "ِ", "ُ"
NO_VOWEL = "-"  # «никакой»: не фонема, чтобы не спутать со звуком
# 2026-11-07 (автор, TD-FN-150): «Длина» — на главном экране (книга учит мадд, строка выводится).
MORE = ["tafkhim", "ghunna", "qalqala", "halting", "wrong_stop"]


def _apply(*marks: tuple[str, int, str | None]) -> str | None:
    return ann.apply_marks(FATIHA_2, P, _cells(), [_mark(c, k, h) for k, c, h in marks])


# ---------- виды: семь главных, пять прочих, прежний ----------
def test_there_are_thirteen_kinds_seven_main_five_more_and_the_legacy_one() -> None:
    assert [str(k) for k in ann.MAIN_KINDS] == [
        "letter", "missing", "vowel", "extra", "shadda", "sukun", "madd",
    ]  # fmt: skip
    assert [str(k) for k in ann.MORE_KINDS] == MORE
    assert {str(k) for k in ann.MarkKind} == {
        *map(str, ann.MAIN_KINDS), *map(str, ann.MORE_KINDS), "shadda_sukun",
    }  # fmt: skip


def test_legacy_shadda_sukun_is_valid_but_not_offered() -> None:
    legacy = ann.MarkKind("shadda_sukun")
    assert legacy not in ann.MAIN_KINDS and legacy not in ann.MORE_KINDS
    ann.check_marks(_cells(), [ann.Mark(7, legacy)])  # прежние метки читаются


def test_no_vowel_marker_is_not_a_phoneme_so_it_cannot_be_confused_with_a_sound() -> None:
    assert ann.NO_VOWEL == NO_VOWEL
    assert NO_VOWEL not in ann.PHONEME_ALPHABET


# ---------- Огласовка: какая прозвучала ----------
@pytest.mark.parametrize(
    ("cell", "heard", "expected"),
    [
        (2, FATHA, WRONG_VOWEL),  # «دُ» прочитан с фатхой
        (2, NO_VOWEL, P[:7] + P[8:]),  # гласной не было совсем
        (6, DAMMA, P[:18] + DAMMA + P[19:]),  # «رَ» → «رُ»
        (0, KASRA, P[:1] + KASRA + P[2:]),  # «ٱلْ»: огласовка — у хамзы
        # «مِينَ»: за краткой — долгая «ии»; она становится долгой «аа», а не «а» + «ии»
        (11, FATHA, P[:30] + FATHA + "اا" + P[33:]),
        (4, KASRA, P[:12] + KASRA + "ۦۦ" + P[15:]),  # «لَّ» (долгая «аа») → долгая «ии»
        (9, DAMMA, P[:24] + DAMMA + "ۥۥ" + P[27:]),  # «عَـٰ» → долгая «уу»
    ],
)
def test_vowel_mark_replaces_the_short_vowel_of_the_cell(
    cell: int, heard: str, expected: str
) -> None:
    assert _apply(("vowel", cell, heard)) == expected


def test_vowel_mark_without_an_answer_gives_nothing() -> None:
    assert _apply(("vowel", 2, None)) is None  # «не знаю» — строки нет


def test_no_vowel_on_a_long_syllable_gives_nothing() -> None:
    """«Никакой» у долгого слога: что стало с маддом — неясно, строки нет."""
    assert _apply(("vowel", 9, NO_VOWEL)) is None


def test_vowel_mark_on_a_cell_without_a_short_vowel_gives_nothing() -> None:
    assert _apply(("vowel", 8, FATHA)) is None  # «ٱلْ» внутри фразы: только ل


# ---------- Сукун: какая гласная прозвучала ----------
@pytest.mark.parametrize(
    ("cell", "heard", "expected"),
    [
        (1, DAMMA, P[:6] + DAMMA + P[6:]),  # «حَمْ» → م с дамма
        (0, KASRA, P[:3] + KASRA + P[3:]),  # «ٱلْ» → ل с кясрой
        (8, KASRA, P[:23] + KASRA + P[23:]),  # «ٱلْ» внутри фразы
        (11, FATHA, P + FATHA),  # «مِينَ»: ن в конце получила гласную
    ],
)
def test_sukun_mark_puts_the_heard_vowel_after_the_silent_consonant(
    cell: int, heard: str, expected: str
) -> None:
    assert _apply(("sukun", cell, heard)) == expected


@pytest.mark.parametrize("cell", [2, 4, 9, 7])
def test_sukun_mark_on_a_cell_without_a_sukun_consonant_gives_nothing(cell: int) -> None:
    """В «دُ», «لَّ», «عَـٰ», «بِّ» каждая согласная уже с гласной или удвоена."""
    assert _apply(("sukun", cell, FATHA)) is None


def test_sukun_mark_without_a_vowel_gives_nothing() -> None:
    assert _apply(("sukun", 1, None)) is None


# ---------- Шадда: удвоение переворачивается ----------
@pytest.mark.parametrize(
    ("cell", "expected"),
    [
        (7, NO_SHADDA),  # «بِّ»: удвоение потеряно
        (4, P[:10] + P[11:]),  # «لَّ»: то же
        (2, P[:6] + "د" + P[6:]),  # «دُ»: удвоения не было — прозвучало
    ],
)
def test_shadda_mark_flips_the_doubling_of_the_cells_only_consonant(
    cell: int, expected: str
) -> None:
    assert _apply(("shadda", cell, None)) == expected


@pytest.mark.parametrize("cell", [0, 1, 11])
def test_shadda_mark_on_a_cell_with_two_different_consonants_gives_nothing(cell: int) -> None:
    assert _apply(("shadda", cell, None)) is None


# ---------- Лишний звук: после звуков слога ----------
@pytest.mark.parametrize(
    ("cell", "heard", "expected"),
    [
        (11, "ن", EXTRA_NUN),
        (2, "ا", P[:8] + "ا" + P[8:]),
        (5, "و", P[:17] + "و" + P[17:]),
    ],
)
def test_extra_mark_inserts_the_sound_after_the_sounds_of_the_cell(
    cell: int, heard: str, expected: str
) -> None:
    assert _apply(("extra", cell, heard)) == expected


def test_extra_mark_without_a_sound_gives_nothing() -> None:
    assert _apply(("extra", 11, None)) is None


# ---------- Пропуск: какой звук ----------
@pytest.mark.parametrize(
    ("cell", "heard", "expected"),
    [
        (2, None, NO_DAL),  # без выбора — весь слог (как раньше)
        (2, "د", P[:6] + P[7:]),  # согласная пропущена, гласная осталась
        (2, DAMMA, P[:7] + P[8:]),  # гласная пропущена, согласная осталась
        (7, "ب", P[:19] + P[21:]),  # обе половины шадды
        (7, KASRA, P[:21] + P[22:]),
    ],
)
def test_missing_mark_removes_the_named_sound_or_the_whole_cell(
    cell: int, heard: str | None, expected: str
) -> None:
    assert _apply(("missing", cell, heard)) == expected


def test_missing_mark_for_a_sound_that_is_not_in_the_cell_gives_nothing() -> None:
    assert _apply(("missing", 2, "ن")) is None


# ---------- несколько отметок ----------
def test_marks_in_different_cells_are_combined() -> None:
    both = _apply(("vowel", 2, FATHA), ("shadda", 7, None))
    after_vowel = P[:7] + FATHA + P[8:]
    assert both == after_vowel[:20] + after_vowel[21:]


def test_two_marks_in_one_cell_give_nothing() -> None:
    assert _apply(("vowel", 2, FATHA), ("extra", 2, "ن")) is None


# ---------- Длина: долгий ↔ краткий (2026-11-07, TD-FN-150) ----------
@pytest.mark.parametrize(
    ("cell", "expected"),
    [
        (9, P[:25] + P[27:]),  # «عَـٰ»: долгая «аа» прочитана кратко
        (4, P[:13] + P[15:]),  # «لَّ»
        (11, P[:31] + P[33:]),  # «مِينَ»: «ии» кратко
        (3, P[:10] + "ۦۦ" + P[10:]),  # «لِ» протянут — долгая «ии» (2 харакята)
        (1, P[:5] + "اا" + P[5:]),  # «حَمْ» → «хаам»
    ],
)
def test_length_mark_turns_long_into_short_and_short_into_long(cell: int, expected: str) -> None:
    assert _apply(("madd", cell, None)) == expected


def test_length_mark_on_a_cell_without_a_vowel_gives_nothing() -> None:
    assert _apply(("madd", 8, None)) is None  # «ٱلْ» внутри фразы: только ل


@pytest.mark.parametrize("kind", [*MORE, "shadda_sukun"])
def test_a_mark_of_a_kind_that_gives_no_phonemes_spoils_the_whole_string(kind: str) -> None:
    assert _apply(("vowel", 2, FATHA), (kind, 9, None)) is None


def test_derived_string_is_a_valid_phoneme_record() -> None:
    for marks in (
        [("vowel", 2, FATHA)], [("sukun", 1, DAMMA)], [("shadda", 7, None)],
        [("extra", 11, "ن")], [("missing", 2, "د")], [("letter", 9, "ء")],
        [("vowel", 4, KASRA)], [("vowel", 11, FATHA)], [("madd", 9, None)], [("madd", 3, None)],
    ):  # fmt: skip
        actual = _apply(*marks)
        assert actual is not None
        ann.check_phonemes(actual)


# ---------- строка вне сур: клетки по буквам ----------
@pytest.mark.parametrize(
    ("mark", "expected"),
    [
        (("vowel", 0, FATHA), L024_07_PHONEMES[:1] + FATHA + L024_07_PHONEMES[2:]),  # «مُ» → «مَ»
        (("sukun", 1, FATHA), L024_07_PHONEMES[:3] + FATHA + L024_07_PHONEMES[3:]),  # «حْ» → «حَ»
        (("shadda", 0, None), L024_07_PHONEMES[:1] + "م" + L024_07_PHONEMES[1:]),  # «مُ» → «مّ»
    ],
)
def test_kinds_work_the_same_for_letter_cells(
    mark: tuple[str, int, str | None], expected: str
) -> None:
    kind, cell, heard = mark
    cells = _cells(L024_07, syllables=False)
    got = ann.apply_marks(L024_07, L024_07_PHONEMES, cells, [_mark(cell, kind, heard)])
    assert got == expected


# ---------- проверка отметок ----------
@pytest.mark.parametrize(
    "mark",
    [
        ("vowel", 2, FATHA), ("vowel", 2, NO_VOWEL), ("vowel", 2, None),
        ("sukun", 1, KASRA), ("sukun", 1, None), ("shadda", 7, None),
        ("extra", 11, "ن"), ("extra", 11, "ا"), ("extra", 11, "و"), ("extra", 11, "ي"),
        ("missing", 2, "د"), ("missing", 2, DAMMA), ("missing", 2, None),
        ("madd", 9, None), ("tafkhim", 6, None), ("halting", 0, None),
    ],
)  # fmt: skip
def test_valid_answers_pass_the_check(mark: tuple[str, int, str | None]) -> None:
    kind, cell, heard = mark
    ann.check_marks(_cells(), [_mark(cell, kind, heard)])


@pytest.mark.parametrize(
    "mark",
    [
        ("vowel", 2, "ب"),  # согласная — не гласная
        ("vowel", 2, DAMMA),  # в «دُ» и так дамма — это не ошибка огласовки
        ("vowel", 6, FATHA),  # в «رَ» и так фатха
        ("vowel", 2, "x"),
        ("sukun", 1, NO_VOWEL),  # у сукуна гласная обязательна, «никакой» — это и есть сукун
        ("sukun", 1, "ب"),
        ("shadda", 7, "ب"),  # у шадды ответа нет
        ("shadda", 7, FATHA),
        ("extra", 11, FATHA),  # лишний звук — согласная или долгая гласная, не краткая
        ("extra", 11, "x"),
        ("extra", 11, NO_VOWEL),
        ("missing", 2, "x"),
        ("missing", 2, NO_VOWEL),
        ("madd", 9, "ا"),  # у видов без вопроса ответа нет
        ("tafkhim", 6, FATHA),
        ("halting", 0, "ب"),
        ("shadda_sukun", 7, FATHA),
    ],
)
def test_invalid_answers_are_rejected_with_a_hint(mark: tuple[str, int, str | None]) -> None:
    kind, cell, heard = mark
    with pytest.raises(LabelError):
        ann.check_marks(_cells(), [_mark(cell, kind, heard)])


# ---------- отметки бота ----------
@pytest.mark.parametrize(
    ("heard", "expected"),
    [
        (P, []),
        (SUB_AIN, [("letter", 9, "ء")]),
        (WRONG_VOWEL, [("vowel", 2, FATHA)]),
        (NO_SHADDA, [("shadda", 7, None)]),
        (NO_DAL, [("missing", 2, None)]),  # слог пропущен целиком — одна отметка на слог
        (EXTRA_NUN, [("extra", 11, "ن")]),
        (P[:25] + P[26:], [("madd", 9, None)]),  # укороченный мадд
        (WRONG_VOWEL[:23] + "ء" + WRONG_VOWEL[24:], [("vowel", 2, FATHA), ("letter", 9, "ء")]),
    ],
)
def test_bot_errors_become_marks_in_their_cells(
    heard: str, expected: list[tuple[str, int, str | None]]
) -> None:
    got = ann.marks_from_bot(FATIHA_2, P, heard, _cells())
    assert list(got) == [_mark(c, k, h) for k, c, h in expected]


@pytest.mark.parametrize("heard", [SUB_AIN, WRONG_VOWEL, NO_SHADDA, NO_DAL, EXTRA_NUN])
def test_marks_of_the_bot_give_back_exactly_what_the_bot_heard(heard: str) -> None:
    marks = ann.marks_from_bot(FATIHA_2, P, heard, _cells())
    assert ann.apply_marks(FATIHA_2, P, _cells(), marks) == heard


def test_an_error_that_fits_no_kind_still_marks_its_cell() -> None:
    """Замена двух звуков одним («حَ» → «خ»): вид неточный, но клетка отмечена.

    «Бот прав» так не теряет ошибку бота.
    """
    heard = P[:3] + "خ" + P[5:]
    marks = ann.marks_from_bot(FATIHA_2, P, heard, _cells())
    assert {m.cell for m in marks} == {1}


def test_one_cell_never_gets_the_same_kind_twice() -> None:
    heard = P[:19] + "مم" + P[21:]  # обе половины шадды заменены: две ошибки в одной клетке
    marks = ann.marks_from_bot(FATIHA_2, P, heard, _cells())
    assert len({(m.cell, m.kind) for m in marks}) == len(marks)


# ---------- надёжность строки ----------
def test_phonemes_sources_are_typed_marks_confirmed_reference() -> None:
    assert {str(s) for s in ann.PhonemesSource} == {"typed", "marks", "confirmed", "reference"}


def test_guide_version_is_three() -> None:
    assert ann.GUIDE_VERSION == "3.0"


# ---------- «Бот прав» ----------
async def test_bot_right_saves_what_the_bot_heard_with_its_marks() -> None:
    w = World()
    saved = await w.submit().confirm_bot(_learner(ANNOTATOR_TG), UUID(int=1), seconds_spent=7)
    assert saved is True
    (label,) = w.tasks.labels
    assert (label.status, label.actual, label.entry) == (AnnotationStatus.AGREE, SUB_AIN, "cells")
    assert label.phonemes_source == "confirmed" and label.seconds_spent == 7
    ((mark,),) = w.tasks.marks[UUID(int=1)]
    assert (mark.cell, str(mark.kind), mark.heard, mark.bot_flagged) == (
        9, "letter", "ء", True,
    )  # fmt: skip
    assert w.uow.commits == 1 and w.events.events[-1][0] == "annotation_submitted"


async def test_bot_right_when_the_bot_found_nothing_is_agree_without_marks() -> None:
    w = World()
    await w.submit().confirm_bot(_learner(ANNOTATOR_TG), UUID(int=2))
    (label,) = w.tasks.labels
    assert (label.status, label.actual, label.phonemes_source) == (
        AnnotationStatus.AGREE, P, "confirmed",
    )  # fmt: skip
    assert w.tasks.marks[UUID(int=2)] == [[]]


async def test_bot_right_keeps_the_heard_calqala_as_the_bot_heard_it() -> None:
    w = World()
    heard = P + "ڇ"  # калькаля при остановке — не ошибка (M-03)
    w.tasks.tasks = [_task(4, FATIHA_2, P, heard)]
    await w.submit().confirm_bot(_learner(ANNOTATOR_TG), UUID(int=4))
    assert w.tasks.labels[-1].actual == heard


async def test_bot_right_keeps_self_correction_and_comment() -> None:
    w = World()
    await w.submit().confirm_bot(
        _learner(ANNOTATOR_TG), UUID(int=1), self_corrected=True, comment=" шум "
    )
    label = w.tasks.labels[-1]
    assert (label.self_corrected, label.comment) == (True, "шум")


async def test_bot_right_for_deleted_attempt_saves_nothing() -> None:
    w = World()
    assert await w.submit().confirm_bot(_learner(ANNOTATOR_TG), UUID(int=99)) is False
    assert w.tasks.labels == [] and w.uow.commits == 0


async def test_stranger_cannot_confirm_the_bot() -> None:
    w = World()
    with pytest.raises(NotAnnotator):
        await w.submit().confirm_bot(_learner(STRANGER_TG), UUID(int=1))
    assert w.tasks.labels == []


# ---------- откуда строка ----------
async def test_phonemes_source_follows_how_the_string_was_made() -> None:
    w = World()
    me = _learner(ANNOTATOR_TG)
    await w.submit().execute(me, UUID(int=2), [])  # «Чисто» — эталон
    await w.submit().execute(me, UUID(int=1), [_mark(9, "letter", "ء")])  # из отметок
    await w.submit().execute(me, UUID(int=3), [_mark(5, "madd")])  # строка не выводится
    assert [lb.phonemes_source for lb in w.tasks.labels] == ["reference", "marks", None]


async def test_manual_entry_is_typed_and_old_bot_right_is_confirmed() -> None:
    w = World()
    manual = uc.SubmitAnnotation(w.access, w.tasks, w.uow, w.events, w.clock)
    me = _learner(ANNOTATOR_TG)
    await manual.execute(me, UUID(int=1), AnnotationStatus.FIX, actual=NO_DAL)
    await manual.execute(me, UUID(int=2), AnnotationStatus.AGREE)
    assert [lb.phonemes_source for lb in w.tasks.labels] == ["typed", "confirmed"]


async def test_new_kinds_are_saved_with_their_answers() -> None:
    w = World()
    marks: list[Any] = [_mark(2, "vowel", FATHA), _mark(7, "shadda"), _mark(1, "sukun", DAMMA)]
    await w.submit().execute(_learner(ANNOTATOR_TG), UUID(int=2), marks)
    saved = {(m.cell, str(m.kind), m.heard) for m in w.tasks.marks[UUID(int=2)][-1]}
    assert saved == {(2, "vowel", FATHA), (7, "shadda", None), (1, "sukun", DAMMA)}
