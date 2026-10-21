"""FR-52 (пакет В, круг 1, ADR-0062): шпаргалка букв по книге, «новая буква / уже знаешь»,
ошибка в букве урока — первой строкой разбора.

Решения автора 2026-10-21 (ADR-0062, В3): строгость к букве урока НЕ вводится — зачёт как раньше
(от 80 %, OQ-14); ошибка в букве урока только выделяется в разборе первой строкой.
Буквы шпаргалки — по книге, строго до урока (у урока хэмзэ — пусто, у урока م — ء ر ز).
Экраны проверяются без Telegram и без картинок; распознавание — готовая оценка ``assess``.
"""

from typing import Any
from uuid import UUID

import pytest
from aiogram.types import InlineKeyboardMarkup

from muallim.application.feedback import Explanation
from muallim.application.use_cases.progress import LessonProgress, Progress
from muallim.application.use_cases.recitation import RecitationResult
from muallim.domain import curriculum as book
from muallim.domain.assessment import assess
from muallim.domain.attempt import Attempt
from muallim.domain.curriculum import Curriculum, ItemKind, Lesson, LessonItem
from muallim.domain.policy import GradingPolicy, Verdict
from muallim.presentation.telegram import callbacks as cb
from muallim.presentation.telegram import render, screens, texts, views
from tests.fakes import FixedClock

CALLBACK_LIMIT = 64  # байт, Telegram Bot API
HAMZA, RA, ZAY, MIM = "L003", "L004", "L005", "L006"  # первые уроки букв (с. 11–12)
AFTER_LETTERS = "L031"  # «Долгие гласные (мадд)» — первый урок после 28 букв
MIM_LINE = "L006-06"  # «أَمْ إِمْ أُمْ مُرْ مُزْ رُمْ أَمَرَ أُمِرَ أَمْرُ»


@pytest.fixture(autouse=True)
def _captions_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """Подписи и кнопки — без рисования картинок (и без libraqm)."""
    monkeypatch.setattr(render, "available", lambda: False)


def _buttons(kb: InlineKeyboardMarkup) -> list[tuple[str, Any]]:
    return [(b.text, b.callback_data) for row in kb.inline_keyboard for b in row]


def _datas(kb: InlineKeyboardMarkup) -> list[str]:
    return [d for _, d in _buttons(kb)]


def _head(lesson: Lesson) -> LessonItem:
    """Головная карточка урока буквы — «буква с тремя огласовками» (kind LETTER)."""
    return next(i for i in lesson.items if i.kind is ItemKind.LETTER)


def _letter_lessons(c: Curriculum) -> list[Lesson]:
    return [les for les in c.lessons if les.section == "letter"]


def _progress(c: Curriculum, current: str) -> Progress:
    lessons = tuple(LessonProgress(les, 0, ()) for les in c.lessons)
    return Progress(lessons, attempts_total=5, continue_item=c.item(current))


def _sheet_buttons(kb: InlineKeyboardMarkup) -> list[str]:
    prefix = cb.LettersSheet.__prefix__ + ":"
    return [d for d in _datas(kb) if d.startswith(prefix)]


def _marker(template: str) -> str:
    """Неизменная часть шаблона до первого поля — по ней видно, что строки нет."""
    return template.split("{", maxsplit=1)[0].strip()


# ---------- домен: буквы по книге до урока ----------
def test_hamza_lesson_has_no_letters_before(curriculum: Curriculum) -> None:
    assert book.letters_before(curriculum, HAMZA) == ()


def test_lessons_before_the_letters_have_no_letters_before(curriculum: Curriculum) -> None:
    assert book.letters_before(curriculum, "L001") == ()
    assert book.letters_before(curriculum, "L002") == ()


def test_mim_lesson_knows_hamza_ra_zay_in_book_order(curriculum: Curriculum) -> None:
    expected = tuple(_head(curriculum.lesson(lid)) for lid in (HAMZA, RA, ZAY))
    assert book.letters_before(curriculum, MIM) == expected


def test_letters_before_excludes_the_lesson_own_letter(curriculum: Curriculum) -> None:
    assert _head(curriculum.lesson(MIM)) not in book.letters_before(curriculum, MIM)


def test_lesson_after_the_alphabet_knows_all_28_letters(curriculum: Curriculum) -> None:
    heads = tuple(_head(les) for les in _letter_lessons(curriculum))
    assert len(heads) == 28
    assert book.letters_before(curriculum, AFTER_LETTERS) == heads


# ---------- шпаргалка: экран ----------
def test_sheet_lists_letter_name_and_sound_of_each_known_letter(curriculum: Curriculum) -> None:
    s = screens.letters_sheet(curriculum, MIM, audio=frozenset())
    for letter, lid in (("ء", HAMZA), ("ر", RA), ("ز", ZAY)):
        head = _head(curriculum.lesson(lid))
        assert letter in s.caption
        assert head.name in s.caption
        assert head.sound in s.caption


def test_sheet_keeps_book_order(curriculum: Curriculum) -> None:
    s = screens.letters_sheet(curriculum, MIM, audio=frozenset())
    sounds = [_head(curriculum.lesson(lid)).sound for lid in (HAMZA, RA, ZAY)]
    positions = [s.caption.index(sound) for sound in sounds]
    assert positions == sorted(positions)


def test_sheet_does_not_show_the_lesson_own_letter(curriculum: Curriculum) -> None:
    mim = _head(curriculum.lesson(MIM))
    s = screens.letters_sheet(curriculum, MIM, audio={mim.id})
    assert mim.sound not in s.caption
    assert cb.Listen(item_id=mim.id).pack() not in _datas(s.keyboard)


def test_sheet_offers_listen_for_each_letter_with_reference(curriculum: Curriculum) -> None:
    heads = [_head(curriculum.lesson(lid)) for lid in (HAMZA, RA, ZAY)]
    s = screens.letters_sheet(curriculum, MIM, audio={h.id for h in heads})
    buttons = _buttons(s.keyboard)
    for letter, head in zip(("ء", "ر", "ز"), heads, strict=True):
        listen = [t for t, d in buttons if d == cb.Listen(item_id=head.id).pack()]
        assert len(listen) == 1, buttons
        assert "🔊" in listen[0] and letter in listen[0]


def test_sheet_has_no_listen_for_letters_without_reference(curriculum: Curriculum) -> None:
    ra = _head(curriculum.lesson(RA))
    s = screens.letters_sheet(curriculum, MIM, audio={ra.id})
    listen = [d for d in _datas(s.keyboard) if d.startswith(cb.Listen.__prefix__ + ":")]
    assert listen == [cb.Listen(item_id=ra.id).pack()]


def test_sheet_from_card_goes_back_to_that_card(curriculum: Curriculum) -> None:
    s = screens.letters_sheet(curriculum, MIM, audio=frozenset(), back_item="L006-03")
    assert (texts.BACK_BUTTON, cb.GoItem(item_id="L006-03").pack()) in _buttons(s.keyboard)


def test_sheet_from_signs_goes_back_to_signs(curriculum: Curriculum) -> None:
    s = screens.letters_sheet(curriculum, MIM, audio=frozenset())
    assert (texts.BACK_BUTTON, cb.Signs().pack()) in _buttons(s.keyboard)


def test_full_sheet_fits_into_a_caption(curriculum: Curriculum) -> None:
    heads = {_head(les).id for les in _letter_lessons(curriculum)}
    s = screens.letters_sheet(curriculum, AFTER_LETTERS, audio=heads)
    assert len(s.caption) <= screens.CAPTION_LIMIT
    assert sum(1 for d in _datas(s.keyboard) if d.startswith("listen:")) == 28


def test_sheet_callback_fits_telegram_limit(curriculum: Curriculum) -> None:
    for lesson in curriculum.lessons:
        for item in lesson.items:
            packed = cb.LettersSheet(lesson_id=lesson.id, item_id=item.id).pack()
            assert len(packed.encode()) <= CALLBACK_LIMIT, packed
    assert cb.LettersSheet(lesson_id=MIM).pack()  # из «Знаков» — без карточки


# ---------- шпаргалка: откуда открывается ----------
@pytest.mark.parametrize("item_id", ["L006-01", "L006-03", MIM_LINE, "L004-05"])
def test_card_with_known_letters_opens_the_sheet(curriculum: Curriculum, item_id: str) -> None:
    lesson, _ = curriculum.locate(item_id)
    s = screens.card(curriculum, curriculum.item(item_id), has_audio=False, is_teacher=False)
    expected = cb.LettersSheet(lesson_id=lesson.id, item_id=item_id).pack()
    assert (texts.SHEET_BUTTON, expected) in _buttons(s.keyboard)


@pytest.mark.parametrize("item_id", ["L001-02", "L002-02", "L003-01", "L003-10"])
def test_card_without_known_letters_has_no_sheet_button(
    curriculum: Curriculum, item_id: str
) -> None:
    s = screens.card(curriculum, curriculum.item(item_id), has_audio=False, is_teacher=False)
    assert _sheet_buttons(s.keyboard) == []
    assert texts.SHEET_BUTTON not in [t for t, _ in _buttons(s.keyboard)]


def test_signs_open_the_sheet_of_the_learner_current_lesson(curriculum: Curriculum) -> None:
    s = screens.signs(curriculum, _progress(curriculum, current="L006-03"))
    assert (texts.SHEET_BUTTON, cb.LettersSheet(lesson_id=MIM).pack()) in _buttons(s.keyboard)


@pytest.mark.parametrize("current", ["L001-02", "L003-04"])
def test_signs_without_known_letters_have_no_sheet_button(
    curriculum: Curriculum, current: str
) -> None:
    s = screens.signs(curriculum, _progress(curriculum, current=current))
    assert _sheet_buttons(s.keyboard) == []


# ---------- «новая буква / уже знаешь» ----------
def _first_step(c: Curriculum, lesson_id: str) -> str:
    item = c.lesson(lesson_id).items[0]
    return screens.card(c, item, has_audio=False, is_teacher=False).caption


def test_first_step_of_mim_names_new_letter_and_known_ones(curriculum: Curriculum) -> None:
    caption = _first_step(curriculum, MIM)
    assert texts.NEW_LETTER.format(letter="م", name="Мим") in caption
    assert texts.ALREADY_KNOW.format(letters="ء ر ز") in caption


def test_first_step_of_ra_knows_only_hamza(curriculum: Curriculum) -> None:
    caption = _first_step(curriculum, RA)
    assert texts.NEW_LETTER.format(letter="ر", name="Ра") in caption
    assert texts.ALREADY_KNOW.format(letters="ء") in caption


def test_first_letter_lesson_has_no_already_know(curriculum: Curriculum) -> None:
    caption = _first_step(curriculum, HAMZA)
    assert texts.NEW_LETTER.format(letter="ء", name="Хэмзэ") in caption
    marker = _marker(texts.ALREADY_KNOW)
    assert marker, "у «уже знаешь» должна быть постоянная часть до {letters}"
    assert marker not in caption


@pytest.mark.parametrize("item_id", ["L006-02", "L006-05", MIM_LINE])
def test_later_steps_do_not_repeat_new_letter(curriculum: Curriculum, item_id: str) -> None:
    s = screens.card(curriculum, curriculum.item(item_id), has_audio=False, is_teacher=False)
    assert texts.NEW_LETTER.format(letter="م", name="Мим") not in s.caption
    assert texts.ALREADY_KNOW.format(letters="ء ر ز") not in s.caption


def test_non_letter_lesson_has_no_new_letter(curriculum: Curriculum) -> None:
    caption = _first_step(curriculum, AFTER_LETTERS)
    marker = _marker(texts.NEW_LETTER)
    assert marker, "у «новая буква» должна быть постоянная часть до {letter}"
    assert marker not in caption


# ---------- ошибка в букве урока — первой строкой разбора ----------
def _result(c: Curriculum, item_id: str, heard: str) -> RecitationResult:
    item = c.item(item_id)
    a = assess(item.text, heard)
    attempt = Attempt(
        UUID(int=1), UUID(int=2), item.id, "v", "stub", a, GradingPolicy().verdict(a),
        None, None, 1, FixedClock().now(),
    )  # fmt: skip
    return RecitationResult(
        item, attempt, tuple(Explanation(f"Ошибка {n}") for n in range(len(a.errors))), "",
        c.next_item(item.id),
    )  # fmt: skip


def _heard(c: Curriculum, *swaps: tuple[str, str]) -> str:
    text = c.item(MIM_LINE).text
    for old, new in swaps:
        assert old in text
        text = text.replace(old, new, 1)
    return text


def test_lesson_letter_swap_opens_the_explanation(curriculum: Curriculum) -> None:
    heard = _heard(curriculum, ("مُرْ", "نُرْ"))  # м прозвучала как н
    r = _result(curriculum, MIM_LINE, heard)
    s = screens.result(curriculum, r, has_audio=False)
    assert s.details.startswith(texts.LESSON_LETTER_WRONG.format(letter="م", heard="ن"))


def test_lesson_letter_line_comes_first_even_after_other_errors(curriculum: Curriculum) -> None:
    """Сначала в строке ошибка в ر (не буква урока), потом — в م: первой всё равно буква урока."""
    heard = _heard(curriculum, ("رُمْ", "لُمْ"), ("أَمَرَ", "أَنَرَ"))
    r = _result(curriculum, MIM_LINE, heard)
    errors = r.attempt.assessment.errors
    assert [e.expected for e in errors][:1] == ["ر"]  # порядок ошибок в строке
    s = screens.result(curriculum, r, has_audio=False)
    assert s.details.startswith(texts.LESSON_LETTER_WRONG.format(letter="م", heard="ن"))


def test_missing_lesson_letter_opens_the_explanation(curriculum: Curriculum) -> None:
    heard = _heard(curriculum, ("مُرْ", "رْ"))  # «мур» → «р»: буква м пропущена
    r = _result(curriculum, MIM_LINE, heard)
    s = screens.result(curriculum, r, has_audio=False)
    assert s.details.startswith(texts.LESSON_LETTER_MISSING.format(letter="م"))


def test_lesson_letter_error_does_not_change_verdict_or_score(curriculum: Curriculum) -> None:
    """В3 (автор 2026-10-21): зачёт как раньше — от 80 %; строгость отложена (OQ-14)."""
    heard = _heard(curriculum, ("مُرْ", "نُرْ"))
    r = _result(curriculum, MIM_LINE, heard)
    score = r.attempt.assessment.score
    assert score >= GradingPolicy().pass_threshold
    assert r.verdict is Verdict.PASSED
    s = screens.result(curriculum, r, has_audio=False)
    assert s.caption.startswith(texts.VERDICT_PASSED)
    assert texts.RESULT_SCORE.format(bar=views.bar(score), score=score) in s.caption
    assert texts.LESSON_LETTER_WRONG.format(letter="م", heard="ن") in s.details


def test_error_in_another_letter_has_no_lesson_letter_line(curriculum: Curriculum) -> None:
    heard = _heard(curriculum, ("رُمْ", "لُمْ"))  # ошибка в ر, буква урока — م
    r = _result(curriculum, MIM_LINE, heard)
    s = screens.result(curriculum, r, has_audio=False)
    assert s.details  # разбор есть
    for template in (texts.LESSON_LETTER_WRONG, texts.LESSON_LETTER_MISSING):
        marker = _marker(template)
        assert marker, "у строки о букве урока должна быть постоянная часть до {letter}"
        assert marker not in s.details
    assert texts.LESSON_LETTER_WRONG.format(letter="ر", heard="ل") not in s.details
