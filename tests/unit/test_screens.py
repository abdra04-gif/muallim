"""Экраны бота без Telegram: подписи и кнопки (ADR-0024, ADR-0025)."""

from collections.abc import Set as AbstractSet
from dataclasses import replace
from typing import Any
from uuid import UUID

import pytest
from aiogram.types import InlineKeyboardMarkup

from muallim.application.feedback import Explanation
from muallim.application.use_cases.progress import LessonProgress, Progress
from muallim.application.use_cases.reading import CardReading
from muallim.application.use_cases.recitation import RecitationResult
from muallim.domain.assessment import assess
from muallim.domain.attempt import Attempt
from muallim.domain.curriculum import Curriculum, ItemKind, Lesson, LessonItem
from muallim.domain.policy import GradingPolicy
from muallim.presentation.telegram import callbacks as cb
from muallim.presentation.telegram import render, screens, texts
from tests.fakes import FixedClock


def _buttons(kb: InlineKeyboardMarkup) -> list[tuple[str, Any]]:
    return [(b.text, b.callback_data) for row in kb.inline_keyboard for b in row]


def _letters(c: Curriculum) -> list[Lesson]:
    return [les for les in c.lessons if les.section == "letter"]


def _head(lesson: Lesson) -> LessonItem:
    """Строка книги «буква с тремя огласовками» (до ADR-0032 — первая карточка урока)."""
    return next(i for i in lesson.items if i.kind is ItemKind.LETTER)


def _progress(
    c: Curriculum,
    done: AbstractSet[str] = frozenset(),
    started: AbstractSet[str] = frozenset(),
    current: str | None = None,
) -> Progress:
    lessons = []
    for lesson in c.lessons:
        n = len(lesson.practice_items)
        mastered = n if lesson.id in done else (1 if lesson.id in started else 0)
        lessons.append(LessonProgress(lesson, mastered, ()))
    item = c.item(current) if current else c.first_item()
    return Progress(
        tuple(lessons), attempts_total=5, streak_days=3, today_attempts=2, continue_item=item
    )


def _has_home(kb: InlineKeyboardMarkup) -> bool:
    return any(data == cb.Home().pack() for _, data in _buttons(kb))


def test_home_offers_continue_from_current_item(curriculum: Curriculum) -> None:
    item = _letters(curriculum)[2].items[1]
    s = screens.home(curriculum, _progress(curriculum, current=item.id))
    buttons = _buttons(s.keyboard)
    assert buttons[0][1] == cb.GoItem(item_id=item.id).pack() and "Продолжить" in buttons[0][0]
    assert "🔥 Серия: <b>3 дня</b>" in s.caption
    datas = [d for _, d in buttons]
    assert cb.Quiz().pack() in datas and cb.Signs().pack() in datas


def test_fresh_learner_starts_with_basmala_lesson(curriculum: Curriculum) -> None:
    p = replace(_progress(curriculum), attempts_total=0)
    s = screens.home(curriculum, p)
    label, data = _buttons(s.keyboard)[0]
    assert "Начать" in label and data == cb.GoItem(item_id=curriculum.first_item().id).pack()


def test_lessons_screen_lists_book_parts_with_progress(curriculum: Curriculum) -> None:
    first_letter = _letters(curriculum)[0]
    s = screens.lessons(
        curriculum, _progress(curriculum, done={first_letter.id}), part=None, page=0
    )
    labels = [t for t, d in _buttons(s.keyboard) if d.startswith("lessons:")]
    assert len(labels) == 9 and "1. Знакомство" in labels[0]
    assert "1/28" in labels[1]  # «Буквы»: пройден 1 урок из 28
    assert _has_home(s.keyboard)


def test_part_screen_shows_lesson_status_and_paginates(curriculum: Curriculum) -> None:
    letters = _letters(curriculum)
    p = _progress(
        curriculum, done={letters[1].id}, started={letters[2].id}, current=letters[2].items[0].id
    )
    s = screens.lessons(curriculum, p, part=1, page=0)
    labels = [t for t, _ in _buttons(s.keyboard)]
    assert any(t.startswith("✅") and "ر" in t for t in labels)
    assert any(t.startswith("🟡") and "ز" in t for t in labels)
    assert (
        sum(1 for _, d in _buttons(s.keyboard) if d.startswith("go:")) == screens.LESSONS_PER_PAGE
    )
    assert ("▶️", cb.Lessons(part=1, page=1).pack()) in _buttons(s.keyboard)
    assert ("◀️ Части", cb.Lessons(part=-1).pack()) in _buttons(s.keyboard)
    last = screens.lessons(curriculum, p, part=1, page=99)
    assert any("ظ" in t for t, _ in _buttons(last.keyboard))


def test_card_next_on_last_item_opens_next_lesson(curriculum: Curriculum) -> None:
    lesson = _letters(curriculum)[1]
    nxt = curriculum.next_lesson(lesson.id)
    assert nxt is not None
    s = screens.card(curriculum, lesson.items[-1], has_audio=False, is_teacher=False)
    label = texts.NEXT_LESSON_BUTTON.format(title=nxt.title)  # последний шаг — следующий урок
    assert (label, cb.GoItem(item_id=nxt.items[0].id).pack()) in _buttons(s.keyboard)
    assert _has_home(s.keyboard) and "с. 11" in s.caption


def test_card_offers_previous_lesson(curriculum: Curriculum) -> None:
    lesson = _letters(curriculum)[1]
    prev = curriculum.previous_lesson(lesson.id)
    assert prev is not None
    s = screens.card(curriculum, lesson.items[0], has_audio=False, is_teacher=False)  # FR-50
    label = f"⬅️ Предыдущий урок: {prev.title}"
    assert (label, cb.GoItem(item_id=prev.items[0].id).pack()) in _buttons(s.keyboard)


def test_first_card_has_no_previous_lesson(curriculum: Curriculum) -> None:
    s = screens.card(curriculum, curriculum.first_item(), has_audio=False, is_teacher=False)
    assert not any(t.startswith("⬅️ Предыдущий урок") for t, _ in _buttons(s.keyboard))


def test_rule_card_explains_without_voice_prompt(curriculum: Curriculum) -> None:
    rule = next(i for les in curriculum.lessons for i in les.items if i.kind is ItemKind.RULE)
    s = screens.card(curriculum, rule, has_audio=False, is_teacher=False)
    assert rule.name in s.caption and "голосовое" not in s.caption
    assert "Правило" in s.caption


def test_alphabet_card_shows_names(curriculum: Curriculum) -> None:
    item = next(i for les in curriculum.lessons for i in les.items if i.kind is ItemKind.ALPHABET)
    s = screens.card(curriculum, item, has_audio=False, is_teacher=False)
    assert "элиф" in s.caption and "голосовое" not in s.caption


def test_quran_card_shows_reference_and_listen(curriculum: Curriculum) -> None:
    item = next(i for les in curriculum.lessons for i in les.items if i.quran == "112:1")
    s = screens.card(curriculum, item, has_audio=True, is_teacher=False)
    assert "112:1" in s.caption
    assert (texts.LISTEN_BUTTON, cb.Listen(item_id=item.id).pack()) in _buttons(s.keyboard)


def test_only_teacher_sees_record_button(curriculum: Curriculum) -> None:
    item = _letters(curriculum)[1].items[0]
    teacher = _buttons(screens.card(curriculum, item, has_audio=False, is_teacher=True).keyboard)
    learner = _buttons(screens.card(curriculum, item, has_audio=False, is_teacher=False).keyboard)
    record = cb.RecordReference(item_id=item.id).pack()
    assert any(d == record for _, d in teacher) and all(d != record for _, d in learner)


@pytest.mark.parametrize("name", ["help_screen", "privacy", "signs"])
def test_service_screens_have_home(name: str) -> None:
    s = {"help_screen": screens.help_screen, "signs": screens.signs}.get(name, lambda: None)()
    s = s or screens.privacy(False)
    assert _has_home(s.keyboard)


def test_signs_screen_explains_marks_above_and_below() -> None:
    caption = screens.signs().caption
    for word in ("фатха", "кясра", "дамма", "сукун", "ташдид", "танвин", "мадд"):
        assert word in caption.lower(), word


def test_progress_screen_lists_done_lessons(curriculum: Curriculum) -> None:
    letters = _letters(curriculum)
    s = screens.progress(curriculum, _progress(curriculum, done={letters[0].id, letters[1].id}))
    assert "2 из" in s.caption and _has_home(s.keyboard)


# Экраны закрепления — tests/unit/test_quiz_screens.py (ADR-0066).


def _styles(kb: InlineKeyboardMarkup) -> dict[str, str | None]:
    return {b.text: b.style for row in kb.inline_keyboard for b in row}


def test_deleting_data_is_red_and_consent_is_not_coloured() -> None:
    """Удаление — опасное действие. Согласие на исследование цветом не подталкиваем: оба ответа
    равны (этика, TD-SEC-02)."""
    from muallim.presentation.telegram import keyboards  # noqa: PLC0415

    assert _styles(keyboards.delete_confirm())[texts.DELETE_YES_BUTTON] == "danger"
    assert _styles(screens.privacy(True).keyboard)[texts.PRIVACY_DELETE_BUTTON] == "danger"
    assert set(_styles(keyboards.consent()).values()) == {None}
    assert texts.PRIVACY_DENY_BUTTON in _styles(screens.privacy(True).keyboard)
    assert _styles(screens.privacy(True).keyboard)[texts.PRIVACY_DENY_BUTTON] is None


def _result(c: Curriculum, item_id: str, heard: str, completed: bool) -> RecitationResult:
    item = c.item(item_id)
    a = assess(item.text, heard)
    attempt = Attempt(
        UUID(int=1), UUID(int=2), item.id, "v", "stub", a, GradingPolicy().verdict(a),
        None, None, 1, FixedClock().now(),
    )  # fmt: skip
    return RecitationResult(
        item, attempt, (Explanation("Ошибка"),) if a.errors else (), "", c.next_item(item.id),
        lesson_completed=completed,
    )  # fmt: skip


def test_result_celebrates_completed_lesson_and_offers_next(curriculum: Curriculum) -> None:
    lesson = _letters(curriculum)[1]
    nxt = curriculum.next_lesson(lesson.id)
    assert nxt is not None
    last = lesson.items[-1]
    s = screens.result(curriculum, _result(curriculum, last.id, last.text, True), has_audio=False)
    assert "Урок пройден" in s.caption
    assert any(
        "Следующий урок" in t and d == cb.GoItem(item_id=nxt.items[0].id).pack()
        for t, d in _buttons(s.keyboard)
    )
    assert _has_home(s.keyboard)


def test_result_of_later_step_has_no_previous_lesson(curriculum: Curriculum) -> None:
    """«Предыдущий урок» — только на первом шаге урока (FR-50)."""
    lesson = _letters(curriculum)[1]
    prev = curriculum.previous_lesson(lesson.id)
    assert prev is not None
    item = _head(lesson)
    assert item != lesson.items[0]
    s = screens.result(curriculum, _result(curriculum, item.id, item.text, False), has_audio=True)
    to_prev = {cb.GoItem(item_id=i.id).pack() for i in prev.items}
    assert not [t for t, d in _buttons(s.keyboard) if d in to_prev]


def test_result_on_first_lesson_has_no_previous_lesson(curriculum: Curriculum) -> None:
    item = curriculum.first_item()
    s = screens.result(curriculum, _result(curriculum, item.id, item.text, False), has_audio=False)
    assert not any(t.startswith("⬅️ Предыдущий урок") for t, _ in _buttons(s.keyboard))


def test_result_with_errors_offers_retry_and_dispute(curriculum: Curriculum) -> None:
    item = _head(_letters(curriculum)[1])
    s = screens.result(curriculum, _result(curriculum, item.id, "سَ سِ سُ", False), has_audio=False)
    buttons = _buttons(s.keyboard)
    # «Ещё раз» снова открывает карточку этой строки, а не только всплывающую подсказку
    assert ("🔁 Ещё раз", cb.GoItem(item_id=item.id).pack()) in buttons
    assert any(d.startswith("dispute:") for _, d in buttons)
    assert "Урок пройден" not in s.caption


def test_result_offers_back_to_previous_line(curriculum: Curriculum) -> None:
    item = _letters(curriculum)[1].items[1]
    prev = curriculum.previous_item(item.id)
    assert prev is not None
    s = screens.result(curriculum, _result(curriculum, item.id, item.text, False), has_audio=False)
    assert ("◀️ Назад", cb.GoItem(item_id=prev.id).pack()) in _buttons(s.keyboard)


def test_result_on_first_line_has_no_back(curriculum: Curriculum) -> None:
    item = curriculum.first_item()
    s = screens.result(curriculum, _result(curriculum, item.id, item.text, False), has_audio=False)
    assert not any(t == "◀️ Назад" for t, _ in _buttons(s.keyboard))


def test_every_card_caption_fits_telegram_photo_limit(
    curriculum: Curriculum, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(render, "available", lambda: False)  # подписи без рисования
    for lesson in curriculum.lessons:
        for item in lesson.items:
            s = screens.card(curriculum, item, has_audio=True, is_teacher=True)
            assert len(s.caption) <= screens.CAPTION_LIMIT, item.id
    assert len(screens.signs().caption) <= screens.CAPTION_LIMIT


# ---------- «как читается» и подробные объяснения (FR-43) ----------
LEGEND = ("с̣ — точка снизу: твёрдый звук",)


def test_card_hides_reading_under_spoiler(curriculum: Curriculum) -> None:
    """Сначала ученик пробует прочитать буквы сам, транскрипция — по касанию (M-09)."""
    item = _head(_letters(curriculum)[1])
    shown = CardReading((("с̣а", False), ("ба", False)), LEGEND)
    s = screens.card(curriculum, item, has_audio=False, is_teacher=False, reading=shown)
    assert "<tg-spoiler>с̣а-ба" in s.caption and LEGEND[0] in s.caption
    assert "tg-spoiler" not in screens.card(curriculum, item, False, False).caption


def _with_errors(c: Curriculum) -> RecitationResult:
    item = _head(_letters(c)[1])
    base = _result(c, item.id, "سَ سِ سُ", False)
    return replace(
        base,
        feedback=(
            Explanation("«с̣а» → у тебя «са»\nс̣ — твёрдо, не «с».", "Подсказка: твёрдо."),
            Explanation("«ра» → у тебя «ла»\nНужно «р».", "Кончик языка дрожит."),
        ),
        expected_reading=(("с̣а", True), ("ра", False)),
        heard_reading=(("са", False), ("ра", False)),
        legend=LEGEND,
        practice=("с̣а",),
    )


def test_result_with_errors_compares_syllables_in_caption(curriculum: Curriculum) -> None:
    s = screens.result(curriculum, _with_errors(curriculum), has_audio=True)
    assert "Нужно:" in s.caption and "<u>с̣а</u>-ра" in s.caption
    assert "У тебя:" in s.caption and "са-ра" in s.caption


def test_result_explains_briefly_with_details_folded(curriculum: Curriculum) -> None:
    """Коротко — сразу; «👄 Подробнее» — свёрнуто; в конце одна строка «что сделать»."""
    s = screens.result(curriculum, _with_errors(curriculum), has_audio=True)
    assert "1️⃣ «с̣а» → у тебя «са»" in s.details and "2️⃣ «ра»" in s.details
    assert "<blockquote expandable>👄 Подробнее" in s.details
    assert "Подсказка: твёрдо." in s.details and "Кончик языка" in s.details
    assert "🔊" in s.details  # есть эталон — «послушай»
    quiet = screens.result(curriculum, _with_errors(curriculum), has_audio=False)
    assert "🔊" not in quiet.details


def test_result_shows_at_most_three_places(curriculum: Curriculum) -> None:
    """Методисты: исправлять несколько ошибок, а не все сразу (Neri et al.)."""
    r = replace(
        _with_errors(curriculum),
        feedback=tuple(Explanation(f"«с{i}» → у тебя «х»", "") for i in range(5)),
    )
    s = screens.result(curriculum, r, has_audio=True)
    assert "3️⃣" in s.details and "4️⃣" not in s.details and "ещё 2" in s.details


def test_result_praises_what_is_already_right(curriculum: Curriculum) -> None:
    """Сначала — что получилось: новичку важно видеть, что большая часть уже верно."""
    s = screens.result(curriculum, _with_errors(curriculum), has_audio=True)
    assert "✅ Прочитано верно — 1 из 2" in s.caption


def test_unread_syllables_are_not_praised(curriculum: Curriculum) -> None:
    r = replace(
        _with_errors(curriculum),
        expected_reading=(("ба", False), ("с̣а", True), ("ра", True)),
        unread_from=2,
    )
    assert "1 из 3" in screens.result(curriculum, r, has_audio=True).caption


def test_second_try_shows_progress_and_fixed_syllables(curriculum: Curriculum) -> None:
    r = replace(_with_errors(curriculum), previous_score=40, fixed=("ба", "ту"))
    s = screens.result(curriculum, r, has_audio=True)
    score = r.attempt.assessment.score
    assert f"Было 40% → стало {score}%" in s.caption
    assert "Исправлено: «ба», «ту»" in s.caption


def test_first_try_has_no_progress_line(curriculum: Curriculum) -> None:
    s = screens.result(curriculum, _with_errors(curriculum), has_audio=True)
    assert "Было" not in s.caption and "Исправлено" not in s.caption


def test_correct_result_is_one_message(curriculum: Curriculum) -> None:
    item = _head(_letters(curriculum)[1])
    s = screens.result(curriculum, _result(curriculum, item.id, item.text, False), has_audio=True)
    assert s.details == "" and "Что сделать" not in s.caption


def test_result_caption_fits_telegram_photo_limit(curriculum: Curriculum) -> None:
    """Подпись к фото — не больше 1024 символов; длинные объяснения уходят вторым сообщением."""
    r = replace(
        _with_errors(curriculum),
        feedback=tuple(Explanation("Очень подробно. " * 6, "Ещё. " * 30) for _ in range(6)),
        expected_reading=tuple((f"с̣а{i}", i % 2 == 0) for i in range(40)),
        heard_reading=tuple((f"са{i}", False) for i in range(40)),
    )
    s = screens.result(curriculum, r, has_audio=True)
    assert len(s.caption) <= 1024


def test_syllable_card_says_how_to_read_and_offers_listen(curriculum: Curriculum) -> None:
    item = next(i for les in _letters(curriculum) for i in les.items if i.kind is ItemKind.SYLLABLE)
    s = screens.card(curriculum, item, has_audio=True, is_teacher=False)
    assert item.sound in s.caption and item.tip in s.caption and "послушай" in s.caption
    assert (texts.LISTEN_BUTTON, cb.Listen(item_id=item.id).pack()) in _buttons(s.keyboard)


def test_rule_card_offers_listen_when_there_is_sound(curriculum: Curriculum) -> None:
    rule = next(i for les in _letters(curriculum) for i in les.items if i.kind is ItemKind.RULE)
    listen = (texts.LISTEN_BUTTON, cb.Listen(item_id=rule.id).pack())
    assert listen in _buttons(screens.card(curriculum, rule, True, False).keyboard)
    assert listen not in _buttons(screens.card(curriculum, rule, False, False).keyboard)
