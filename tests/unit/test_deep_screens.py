"""FR-66, FR-67 (ADR-0082, срез 1): минимум кнопок, экран «📖 Углублённо», «⋯ Ещё».

Подписи кнопок — из «Решений автора 2026-11-08»; свободные тексты (черновики агента) проверяются
по ключевым фрагментам. Экраны строятся без Telegram (как tests/unit/test_screens.py).

Принятые имена (контракт для реализации): ``screens.deep(curriculum, item, reading=None, *,
view=None, video_url=None)``, ``screens.more()``, ``callbacks.Deep(item_id)``, ``callbacks.More``,
``screens.privacy(research_consent, pseudonym="")``.
"""

from html import escape
from typing import Any

import pytest
from aiogram.types import InlineKeyboardMarkup

from muallim.application.feedback import FeedbackRenderer
from muallim.application.use_cases.reading import CardReading
from muallim.application.use_cases.settings import TOGGLES, parse
from muallim.domain.curriculum import (
    Curriculum,
    ItemKind,
    LessonItem,
    letters_before,
    unit_title,
)
from muallim.domain.settings import HowToRead, LearnerSettings
from muallim.domain.sura import find_sura
from muallim.presentation.telegram import callbacks as cb
from muallim.presentation.telegram import render, screens, texts
from tests.unit.test_screens import _head, _letters, _progress, _result, _with_errors

DEEP = texts.DEEP_BUTTON
HOME = "🏠"
MORE = "⋯ Ещё"
YOUTUBE = "🎥 Видеоурок на YouTube"
TO_LESSON = "◀️ К уроку"
LEGEND = ("с̣ — точка снизу: твёрдый звук",)
READING = CardReading((("с̣а", False), ("ба", False)), LEGEND)
CALLBACK_LIMIT = 64  # байт, Telegram Bot API


@pytest.fixture
def captions_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(render, "available", lambda: False)


def _rows(kb: InlineKeyboardMarkup) -> list[list[tuple[str, Any]]]:
    return [[(b.text, b.callback_data) for b in row] for row in kb.inline_keyboard]


def _flat(kb: InlineKeyboardMarkup) -> list[tuple[str, Any]]:
    return [pair for row in _rows(kb) for pair in row]


def _labels(kb: InlineKeyboardMarkup) -> list[str]:
    return [t for t, _ in _flat(kb)]


def _row_with(kb: InlineKeyboardMarkup, label: str) -> list[tuple[str, Any]]:
    found = [row for row in _rows(kb) if label in [t for t, _ in row]]
    assert len(found) == 1, f"{label!r}: {_rows(kb)}"
    return found[0]


def _middle_step(c: Curriculum) -> LessonItem:
    """Шаг буквы или слога внутри урока: есть и «Назад», и «Дальше» в том же уроке."""
    for lesson in _letters(c):
        for i, item in enumerate(lesson.items[:-1]):
            if i > 0 and item.kind in (ItemKind.LETTER, ItemKind.SYLLABLE):
                return item
    raise AssertionError("нет подходящего шага")


# ---------- карточка ----------
def test_card_has_listen_and_deep_in_first_row(curriculum: Curriculum, captions_only: None) -> None:
    item = _middle_step(curriculum)
    s = screens.card(curriculum, item, has_audio=True, is_teacher=False)
    assert _rows(s.keyboard)[0] == [
        (texts.LISTEN_BUTTON, cb.Listen(item_id=item.id).pack()),
        (DEEP, cb.Deep(item_id=item.id).pack()),
    ]


def test_card_keeps_listen_caption_for_plan_listen() -> None:
    """На подпись «🔊 Как правильно» ссылается PLAN_LISTEN — она не меняется (ADR-0082 п. 2)."""
    assert texts.LISTEN_BUTTON == "🔊 Как правильно"
    assert "«Как правильно»" in texts.PLAN_LISTEN


def test_card_without_sound_and_video_has_only_deep_in_first_row(
    curriculum: Curriculum, captions_only: None
) -> None:
    item = _middle_step(curriculum)
    s = screens.card(curriculum, item, has_audio=False, is_teacher=False)
    assert _rows(s.keyboard)[0] == [(DEEP, cb.Deep(item_id=item.id).pack())]


def test_card_drops_lessons_and_sheet_buttons(curriculum: Curriculum, captions_only: None) -> None:
    """«📚 Уроки» и «📋 Шпаргалка букв» уехали: шпаргалка — в «Углублённо», уроки — на главную."""
    item = curriculum.item("L006-03")  # урок 6: до него есть пройденные буквы (раньше — шпаргалка)
    assert letters_before(curriculum, curriculum.locate(item.id)[0].id)
    s = screens.card(curriculum, item, has_audio=True, is_teacher=False)
    assert texts.LESSONS_BUTTON not in _labels(s.keyboard)
    assert texts.SHEET_BUTTON not in _labels(s.keyboard)
    assert not [d for _, d in _flat(s.keyboard) if d.startswith(("lessons:", "sheet:"))]


def test_sura_card_keeps_whole_sura_and_memory_row(
    curriculum: Curriculum, captions_only: None
) -> None:
    lesson = next(les for les in curriculum.lessons if les.section == "sura")
    sura = find_sura(curriculum, lesson.id)
    assert sura is not None
    s = screens.card(curriculum, lesson.items[1], has_audio=True, is_teacher=False)
    assert [
        (texts.WHOLE_SURA_BUTTON, cb.SuraOpen(n=sura.number, m="t").pack()),
        (texts.MEMORY_BUTTON, cb.SuraOpen(n=sura.number, m="m").pack()),
    ] in _rows(s.keyboard)
    assert texts.WHOLE_SURA_BUTTON == "📜 Вся сура" and texts.MEMORY_BUTTON == "🎯 Наизусть"


def test_teacher_still_sees_record_button_on_new_card(
    curriculum: Curriculum, captions_only: None
) -> None:
    item = _middle_step(curriculum)
    teacher = screens.card(curriculum, item, has_audio=True, is_teacher=True)
    learner = screens.card(curriculum, item, has_audio=True, is_teacher=False)
    record = cb.RecordReference(item_id=item.id).pack()
    assert record in [d for _, d in _flat(teacher.keyboard)]
    assert record not in [d for _, d in _flat(learner.keyboard)]


def test_deep_button_is_on_every_card_kind(curriculum: Curriculum, captions_only: None) -> None:
    """«Чтоб везде всё было»: и правило, и алфавит, и сура, и слог (решение автора 2026-11-08)."""
    seen = set()
    for lesson in curriculum.lessons:
        for item in lesson.items:
            s = screens.card(curriculum, item, has_audio=False, is_teacher=False)
            assert (DEEP, cb.Deep(item_id=item.id).pack()) in _flat(s.keyboard), item.id
            seen.add(item.kind)
    assert {ItemKind.RULE, ItemKind.ALPHABET, ItemKind.LETTER, ItemKind.SYLLABLE} <= seen


def _one_of_each_kind(c: Curriculum) -> dict[str, LessonItem]:
    letters = _letters(c)
    sura = next(i for les in c.lessons if les.section == "sura" for i in les.items if i.quran)
    return {
        "syllable": _syllable_item(c),
        "letter": _head(letters[1]),
        "rule": next(i for les in c.lessons for i in les.items if i.kind is ItemKind.RULE),
        "alphabet": next(i for les in c.lessons for i in les.items if i.kind is ItemKind.ALPHABET),
        "sura": sura,
    }


@pytest.mark.parametrize("kind", ["syllable", "letter", "rule", "alphabet", "sura"])
@pytest.mark.parametrize("mode", list(HowToRead))
def test_card_hides_tip_how_to_read_and_book_page_in_card_text(
    curriculum: Curriculum, captions_only: None, kind: str, mode: HowToRead
) -> None:
    """Подсказка, «Как читается» и «книга, с. N» — только в «Углублённо», для любого вида
    карточки и любой настройки «Как читается» (в т. ч. суры: автор подтвердил)."""
    item = _one_of_each_kind(curriculum)[kind]
    s = screens.card(
        curriculum,
        item,
        has_audio=True,
        is_teacher=False,
        reading=READING,
        view=LearnerSettings(how_to_read=mode),
    )
    assert "Как читается" not in s.caption and "с̣а-ба" not in s.caption
    assert "tg-spoiler" not in s.caption
    assert "книга, с." not in s.caption
    if kind != "rule":  # у правила tip — сам текст правила (CARD_RULE), он на карточке остаётся
        assert not item.tip or escape(item.tip) not in s.caption
    if kind in ("syllable", "letter"):
        assert item.name in s.caption and item.sound in s.caption
        assert "💡" not in s.caption
    if kind == "syllable":
        assert "голосовое" in s.caption  # «🎙 …»


def test_card_keeps_head_letter_line_and_quran_line(
    curriculum: Curriculum, captions_only: None
) -> None:
    lesson = _letters(curriculum)[1]
    head = _head(lesson)
    s = screens.card(curriculum, head, has_audio=True, is_teacher=False)
    assert unit_title(lesson) in s.caption and "шаг" in s.caption
    assert head.name in s.caption and head.sound in s.caption
    quran = next(i for les in curriculum.lessons for i in les.items if i.quran == "112:1")
    assert "Коран 112:1" in screens.card(curriculum, quran, True, False).caption


# ---------- «📖 Углублённо» ----------
def _syllable_item(c: Curriculum) -> LessonItem:
    return next(i for les in _letters(c) for i in les.items if i.kind is ItemKind.SYLLABLE)


def test_deep_shows_tip_how_to_read_and_book_page(
    curriculum: Curriculum, captions_only: None
) -> None:
    item = _head(_letters(curriculum)[1])  # строка буквы с подсказкой и страницей книги
    assert item.tip and item.source is not None
    s = screens.deep(curriculum, item, READING)
    assert escape(item.tip) in s.caption  # подсказка целиком, с учётом HTML-экранирования
    assert f"с. {item.source.page}" in s.caption and "книга" in s.caption


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        (HowToRead.SPOILER, "<tg-spoiler>с̣а-ба"),
        (HowToRead.SHOWN, "с̣а-ба"),
        (HowToRead.HIDDEN, None),
    ],
)
def test_deep_shows_how_to_read_by_setting(
    curriculum: Curriculum, captions_only: None, mode: HowToRead, expected: str | None
) -> None:
    item = _head(_letters(curriculum)[1])
    s = screens.deep(curriculum, item, READING, view=LearnerSettings(how_to_read=mode))
    if expected is None:  # «Не показывать»: строки нет, подсказка остаётся
        assert "Как читается" not in s.caption and "с̣а-ба" not in s.caption
        assert escape(item.tip) in s.caption
        return
    assert expected in s.caption and LEGEND[0] in s.caption
    assert ("tg-spoiler" in s.caption) is (mode is HowToRead.SPOILER)


def test_deep_without_book_page_has_no_book_line(
    curriculum: Curriculum, captions_only: None
) -> None:
    from dataclasses import replace  # noqa: PLC0415

    item = replace(_head(_letters(curriculum)[1]), source=None)
    assert "книга, с." not in screens.deep(curriculum, item).caption


def test_deep_video_button_is_url_with_default_stub(
    curriculum: Curriculum, captions_only: None
) -> None:
    item = _head(_letters(curriculum)[1])
    url = "https://www.youtube.com/"
    s = screens.deep(curriculum, item, video_url=url)
    (button,) = [b for row in s.keyboard.inline_keyboard for b in row if b.text == YOUTUBE]
    assert button.url == url and button.callback_data is None  # URL-кнопка, а не callback


def test_deep_without_video_link_has_no_video_button(
    curriculum: Curriculum, captions_only: None
) -> None:
    item = _head(_letters(curriculum)[1])
    s = screens.deep(curriculum, item, video_url=None)
    assert YOUTUBE not in _labels(s.keyboard)
    assert not [b for row in s.keyboard.inline_keyboard for b in row if b.url]


def test_deep_back_returns_to_card(curriculum: Curriculum, captions_only: None) -> None:
    item = _middle_step(curriculum)
    s = screens.deep(curriculum, item, video_url="https://www.youtube.com/")
    assert (TO_LESSON, cb.GoItem(item_id=item.id).pack()) in _flat(s.keyboard)


@pytest.mark.parametrize("kind", ["syllable", "letter", "rule", "alphabet", "sura"])
def test_deep_back_exists_for_every_kind_even_without_tip_or_source(
    curriculum: Curriculum, captions_only: None, kind: str
) -> None:
    from dataclasses import replace  # noqa: PLC0415

    bare = replace(_one_of_each_kind(curriculum)[kind], tip="", source=None)
    for item in (_one_of_each_kind(curriculum)[kind], bare):
        s = screens.deep(curriculum, item, video_url=None)
        assert (TO_LESSON, cb.GoItem(item_id=item.id).pack()) in _flat(s.keyboard)


def test_deep_has_no_book_page_button_without_page_file(
    curriculum: Curriculum, captions_only: None
) -> None:
    """Файлов страниц книги в боте пока нет (срез 2): кнопки «📄 Страница книги» тоже нет."""
    item = _middle_step(curriculum)
    s = screens.deep(curriculum, item, video_url="https://www.youtube.com/")
    assert "📄 Страница книги" not in _labels(s.keyboard)


def test_deep_offers_letters_sheet_only_when_letters_are_known(
    curriculum: Curriculum, captions_only: None
) -> None:
    late = curriculum.item("L006-03")
    lesson = curriculum.locate(late.id)[0]
    s = screens.deep(curriculum, late)
    [(_, data)] = [p for p in _flat(s.keyboard) if p[0] == texts.SHEET_BUTTON]
    assert cb.LettersSheet.unpack(data).lesson_id == lesson.id
    first = _letters(curriculum)[0].items[0]
    assert not letters_before(curriculum, curriculum.locate(first.id)[0].id)
    assert texts.SHEET_BUTTON not in _labels(screens.deep(curriculum, first).keyboard)


def test_deep_works_for_every_card_kind_and_fits_callback_limit(
    curriculum: Curriculum, captions_only: None
) -> None:
    for lesson in curriculum.lessons:
        for item in lesson.items:
            s = screens.deep(curriculum, item, video_url="https://www.youtube.com/")
            assert len(s.caption) <= screens.CAPTION_LIMIT, item.id
            for _, data in _flat(s.keyboard):
                assert data is None or len(data.encode()) <= CALLBACK_LIMIT, item.id


def test_callback_data_within_64_bytes(curriculum: Curriculum, captions_only: None) -> None:
    longest = max(
        (i.id for les in curriculum.lessons for i in les.items), key=lambda x: len(x.encode())
    )
    assert len(cb.Deep(item_id=longest).pack().encode()) <= CALLBACK_LIMIT
    assert len(cb.More().pack().encode()) <= CALLBACK_LIMIT
    assert cb.Deep.__prefix__ != cb.More.__prefix__
    assert cb.Deep.unpack(cb.Deep(item_id=longest).pack()).item_id == longest
    for lesson in curriculum.lessons:
        for item in lesson.items:
            s = screens.card(curriculum, item, has_audio=True, is_teacher=True)
            for _, data in _flat(s.keyboard):
                assert len(data.encode()) <= CALLBACK_LIMIT, item.id


# ---------- результат ----------
def _ok(c: Curriculum, item: LessonItem, **kw: Any) -> screens.Screen:
    return screens.result(c, _result(c, item.id, item.text, False), has_audio=True, **kw)


def _wrong(c: Curriculum, item: LessonItem, **kw: Any) -> screens.Screen:
    r = _result(c, item.id, "سَ سِ سُ", False)
    assert r.attempt.assessment.errors, "для теста нужна ошибка"
    return screens.result(c, r, has_audio=True, **kw)


def test_result_ok_has_no_deep_button(curriculum: Curriculum, captions_only: None) -> None:
    item = _middle_step(curriculum)
    s = _ok(curriculum, item)
    assert DEEP not in _labels(s.keyboard)
    rows = _rows(s.keyboard)
    assert rows[0] == [(texts.LISTEN_BUTTON, cb.Listen(item_id=item.id).pack())]


def test_result_drops_lessons_button(curriculum: Curriculum, captions_only: None) -> None:
    item = _middle_step(curriculum)
    for s in (_ok(curriculum, item), _wrong(curriculum, item)):
        assert texts.LESSONS_BUTTON not in _labels(s.keyboard)


def test_result_keeps_resume_row_after_basmala(curriculum: Curriculum, captions_only: None) -> None:
    basmala = curriculum.item("L001-02")  # любой шаг «начала занятия»
    resume = _middle_step(curriculum)
    r = _result(curriculum, basmala.id, basmala.text, False)
    s = screens.result(curriculum, r, True, resume=resume)
    label = texts.RESUME_BUTTON.format(title=curriculum.locate(resume.id)[0].title)
    assert _row_with(s.keyboard, label) == [(label, cb.GoItem(item_id=resume.id).pack())]


def test_result_breakdown_unchanged(curriculum: Curriculum, renderer: FeedbackRenderer) -> None:
    """ADR-0070 не трогаем: подпись — те же пункты групп и план; картинка — тот же рисунок."""
    r = _with_errors(curriculum, renderer)
    assert r.breakdown is not None
    s = screens.result(curriculum, r, has_audio=True)
    shown = s.caption + s.details
    for n, group in enumerate(r.breakdown.groups[: screens.views.MAX_ERRORS_SHOWN]):
        assert screens._group_point(curriculum, n, group) in shown
    assert texts.PLAN_LISTEN in shown and texts.ERROR_NUMBERS[0] in shown
    assert "Что сделать" not in s.caption
    if render.available():
        counter = texts.RESULT_WORDS.format(
            ok=r.breakdown.words_ok,
            words=screens.views.plural(r.breakdown.words_ok, texts.WORD_FORMS),
            total=r.breakdown.words_total,
        )
        expected = render.result_marks(text=r.item.text, breakdown=r.breakdown, score_label=counter)
        assert s.image == expected


def test_home_label_is_the_same_icon_on_card_result_and_more(
    curriculum: Curriculum, captions_only: None
) -> None:
    assert texts.HOME_BUTTON == HOME
    item = _middle_step(curriculum)
    for kb in (
        screens.card(curriculum, item, True, False).keyboard,
        _ok(curriculum, item).keyboard,
        _wrong(curriculum, item).keyboard,
        screens.more().keyboard,
    ):
        assert (HOME, cb.Home().pack()) in _flat(kb)


# ---------- главная ----------
def test_home_has_continue_lessons_quiz_more(curriculum: Curriculum, captions_only: None) -> None:
    item = _letters(curriculum)[2].items[1]
    s = screens.home(curriculum, _progress(curriculum, current=item.id))
    rows = _rows(s.keyboard)
    assert len(rows) == 3
    [(label, data)] = rows[0]
    assert label.startswith("▶️ Продолжить") and data == cb.GoItem(item_id=item.id).pack()
    assert [t for t, _ in rows[1]] == [texts.LESSONS_BUTTON, texts.QUIZ_BUTTON]
    assert rows[1][1][1] == cb.Quiz().pack()
    assert rows[2] == [(MORE, cb.More().pack())]
    assert texts.LESSONS_BUTTON == "📚 Уроки" and texts.QUIZ_BUTTON == "🧠 Закрепление"


def test_home_drops_signs_progress_settings_and_memory(
    curriculum: Curriculum, captions_only: None
) -> None:
    s = screens.home(curriculum, _progress(curriculum))
    datas = [d for _, d in _flat(s.keyboard)]
    for gone in (cb.Signs(), cb.ShowProgress(), cb.ShowSettings(), cb.SuraList()):
        assert gone.pack() not in datas, gone
    for label in (
        texts.SIGNS_BUTTON, texts.PROGRESS_BUTTON, texts.SETTINGS_BUTTON, texts.MEMORY_BUTTON,
    ):  # fmt: skip
        assert label not in _labels(s.keyboard)


def test_fresh_learner_home_still_starts_first_lesson(
    curriculum: Curriculum, captions_only: None
) -> None:
    p = _progress(curriculum)
    from dataclasses import replace  # noqa: PLC0415

    s = screens.home(curriculum, replace(p, attempts_total=0))
    [(label, data)] = _rows(s.keyboard)[0]
    assert label == texts.START_BUTTON
    assert data == cb.GoItem(item_id=curriculum.first_item().id).pack()
    assert (MORE, cb.More().pack()) in _flat(s.keyboard)


def test_home_text_is_short(curriculum: Curriculum, captions_only: None) -> None:
    letters = _letters(curriculum)
    p = _progress(curriculum, done={letters[0].id, letters[1].id}, current=letters[2].items[0].id)
    s = screens.home(curriculum, p)
    lines = [ln for ln in s.caption.splitlines() if ln.strip()]
    assert len(lines) <= 4, lines
    assert "пройдено страниц" in s.caption
    assert unit_title(letters[2]) in s.caption  # «Дальше: Стр. 11 · ز · Зэй»
    assert "сегодня" not in s.caption.lower() and "▰" not in s.caption and "▱" not in s.caption


def test_home_keeps_alphabet_map_picture(curriculum: Curriculum) -> None:
    if not render.available():
        pytest.skip("нет libraqm: картинки не рисуются")
    s = screens.home(curriculum, _progress(curriculum))
    assert s.image is not None and s.image_key.startswith("map:")


def test_lessons_from_home_opens_current_part(curriculum: Curriculum, captions_only: None) -> None:
    """Главная → часть, где ученик сейчас (по курсору), а не список частей."""
    item = _letters(curriculum)[2].items[1]
    lesson = curriculum.locate(item.id)[0]
    p = _progress(curriculum, current=item.id)
    s = screens.home(curriculum, p)
    [(_, data)] = [pair for pair in _flat(s.keyboard) if pair[0] == texts.LESSONS_BUTTON]
    target = cb.Lessons.unpack(data)
    assert target.part >= 0
    assert lesson in curriculum.parts()[target.part][1]
    page = screens.lessons(curriculum, p, target.part, target.page)
    number = curriculum.page_of(item.id)[0].number
    assert any(f"Стр. {number} " in t for t in _labels(page.keyboard))  # страница видна


def test_parts_button_still_lists_parts(curriculum: Curriculum, captions_only: None) -> None:
    p = _progress(curriculum)
    page = screens.lessons(curriculum, p, part=1, page=0)
    assert (texts.PARTS_BUTTON, cb.Lessons(part=-1).pack()) in _flat(page.keyboard)
    assert texts.PARTS_BUTTON == "◀️ Части"
    listing = screens.lessons(curriculum, p, part=-1)
    assert len([d for _, d in _flat(listing.keyboard) if d.startswith("lessons:")]) == 9


# ---------- «⋯ Ещё» ----------
def test_more_screen_lists_progress_signs_memory_settings_help_home(
    captions_only: None,
) -> None:
    s = screens.more()
    assert _rows(s.keyboard) == [
        [
            (texts.PROGRESS_BUTTON, cb.ShowProgress().pack()),
            (texts.SIGNS_BUTTON, cb.Signs().pack()),
        ],
        [
            (texts.MEMORY_BUTTON, cb.SuraList().pack()),
            (texts.SETTINGS_BUTTON, cb.ShowSettings().pack()),
        ],
        [(texts.HELP_BUTTON, cb.Help().pack())],
        [(HOME, cb.Home().pack())],
    ]
    assert texts.PROGRESS_BUTTON == "📊 Прогресс" and texts.SIGNS_BUTTON == "🔤 Знаки"
    assert texts.SETTINGS_BUTTON == "⚙️ Настройки" and texts.HELP_BUTTON == "❓ Как заниматься"


def test_help_screen_returns_to_more_not_settings() -> None:
    kb = screens.help_screen().keyboard
    assert cb.More().pack() in [d for _, d in _flat(kb)]
    assert cb.ShowSettings().pack() not in [d for _, d in _flat(kb)]


# ---------- настройки и «Мои данные» ----------
def test_settings_has_no_research_toggle() -> None:
    s = screens.settings(LearnerSettings())
    assert not [d for _, d in _flat(s.keyboard) if d and d.startswith("set:research_block")]
    assert not [t for t in _labels(s.keyboard) if "🔬" in t]
    assert "research_block" not in TOGGLES
    with pytest.raises(ValueError):
        parse("research_block", "true")


def test_settings_leads_back_to_more() -> None:
    """Настройки открываются из «Ещё» и возвращают туда же."""
    assert cb.More().pack() in [d for _, d in _flat(screens.settings(LearnerSettings()).keyboard)]


def test_settings_moved_my_id_and_help_out() -> None:
    kb = screens.settings(LearnerSettings()).keyboard
    datas = [d for _, d in _flat(kb)]
    assert cb.Me().pack() not in datas and cb.Help().pack() not in datas
    assert texts.ME_BUTTON not in _labels(kb) and texts.HELP_BUTTON not in _labels(kb)
    assert cb.Privacy().pack() in datas  # «🔒 Мои данные» остались в настройках
    assert (HOME, cb.Home().pack()) in _flat(kb)


def test_privacy_screen_contains_my_id() -> None:
    s = screens.privacy(True, pseudonym="L-7f3a9c")
    assert "L-7f3a9c" in s.caption
    assert "L-7f3a9c" not in screens.privacy(True).caption  # без псевдонима — как раньше
    assert texts.PRIVACY_DELETE_BUTTON in _labels(s.keyboard)


# ---------- добавлено по замечаниям test-auditor ----------
def test_teacher_card_keeps_listen_and_deep_in_first_row(
    curriculum: Curriculum, captions_only: None
) -> None:
    item = _middle_step(curriculum)
    s = screens.card(curriculum, item, has_audio=True, is_teacher=True)
    assert _rows(s.keyboard)[0][:2] == [
        (texts.LISTEN_BUTTON, cb.Listen(item_id=item.id).pack()),
        (DEEP, cb.Deep(item_id=item.id).pack()),
    ]


def _last_of_lesson(c: Curriculum) -> LessonItem:
    lesson = _letters(c)[1]
    assert c.next_lesson(lesson.id) is not None
    return lesson.items[-1]


def test_wrong_result_without_sound_has_only_deep_in_first_row(
    curriculum: Curriculum, captions_only: None
) -> None:
    item = _middle_step(curriculum)
    r = _result(curriculum, item.id, "سَ سِ سُ", False)
    assert r.attempt.assessment.errors
    s = screens.result(curriculum, r, has_audio=False)
    assert _rows(s.keyboard)[0] == [(DEEP, cb.Deep(item_id=item.id).pack())]


def test_wrong_result_keeps_resume_row(curriculum: Curriculum, captions_only: None) -> None:
    basmala = curriculum.item("L001-02")
    resume = _middle_step(curriculum)
    r = _result(curriculum, basmala.id, "سَ سِ سُ", False)
    assert r.attempt.assessment.errors
    s = screens.result(curriculum, r, True, resume=resume)
    label = texts.RESUME_BUTTON.format(title=curriculum.locate(resume.id)[0].title)
    assert _row_with(s.keyboard, label) == [(label, cb.GoItem(item_id=resume.id).pack())]


def _last_of_course(c: Curriculum) -> LessonItem:
    last = c.lessons[-1].items[-1]
    assert c.next_item(last.id) is None
    return last


def test_first_card_of_course_has_no_back_and_no_previous_lesson(
    curriculum: Curriculum, captions_only: None
) -> None:
    first = curriculum.first_item()
    for s in (
        screens.card(curriculum, first, True, False),
        _ok(curriculum, first),
        _wrong(curriculum, first),
    ):
        labels = _labels(s.keyboard)
        assert texts.BACK_BUTTON not in labels
        assert not [t for t in labels if t.startswith("⬅️")]
        assert HOME in labels


def test_last_card_of_course_has_no_next_and_keeps_deep(
    curriculum: Curriculum, captions_only: None
) -> None:
    last = _last_of_course(curriculum)
    card = screens.card(curriculum, last, True, False)
    assert (DEEP, cb.Deep(item_id=last.id).pack()) in _flat(card.keyboard)
    assert texts.NEXT_BUTTON not in _labels(card.keyboard)
    assert not [t for t in _labels(card.keyboard) if t.startswith("➡️")]
    for s in (_ok(curriculum, last), _wrong(curriculum, last)):
        assert texts.NEXT_BUTTON not in _labels(s.keyboard)
        assert not [t for t in _labels(s.keyboard) if t.startswith("➡️")]
        assert HOME in _labels(s.keyboard)
