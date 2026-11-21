"""Начало книги — как в книге (автор 2026-11-21, «Муаллим 2.0», срез 1, ADR-0089).

С. 10 книги: басмала заголовком (с переводом), затем «Арабский алфавит», затем хамза — первое
упражнение. Басмалу новичок видит на скане с. 10, отдельной карточки нет (урок L001 снят, номера
остальных уроков в БД прежние). Истиазы нет нигде, ежедневное «начало занятия» убрано целиком.
На карточках алфавита — ролик Абу Ясина «Урок 1. Арабский алфавит».
"""

from typing import Any

import pytest
from aiogram.types import InlineKeyboardMarkup

from muallim.application.use_cases.progress import LessonProgress, Progress
from muallim.application.use_cases.settings import TOGGLES
from muallim.domain.curriculum import Curriculum, ItemKind
from muallim.domain.settings import LearnerSettings
from muallim.infrastructure.curriculum.lesson_links import YamlLessonLinks
from muallim.presentation.telegram import render, screens, texts
from muallim.presentation.telegram.callbacks import GoItem, PageOpen
from tests.conftest import CURRICULUM_DIR

ALPHABET_VIDEO = "https://www.youtube.com/watch?v=o4oRsk4BIMU"  # Абу Ясин, сверено 2026-11-18
ISTI_ADHA_START = "أَعُوذُ بِٱللَّهِ"  # «قُلْ أَعُوذُ» в сурах 113, 114 и на с. 52 — текст книги


@pytest.fixture(autouse=True)
def _captions_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(render, "available", lambda: False)


def _buttons(kb: InlineKeyboardMarkup) -> list[tuple[str, Any, Any]]:
    return [(b.text, b.callback_data, b.url) for row in kb.inline_keyboard for b in row]


def _progress(c: Curriculum, attempts: int, current: str | None = None) -> Progress:
    lessons = tuple(LessonProgress(les, 0, ()) for les in c.lessons)
    item = c.item(current) if current else None
    return Progress(lessons, attempts_total=attempts, continue_item=item)


# ---------- программа: с. 10 по книге ----------
def test_program_starts_with_the_alphabet_of_page_ten(curriculum: Curriculum) -> None:
    """Урок L001 (истиаза, басмала) снят; первый урок — «Арабский алфавит». Номера прежние: на
    lesson.number завязаны пороги проверки (CardPolicy, ADR-0088) и колонка lesson_number в БД."""
    first = curriculum.lessons[0]
    assert (first.id, first.number, first.section) == ("L002", 2, "alphabet")
    assert curriculum.first_item().id == "L002-01"
    assert "L001" not in {les.id for les in curriculum.lessons}


def test_no_basmala_card_on_page_ten(curriculum: Curriculum) -> None:
    """Басмала — заголовок книги на скане, не упражнение: на с. 10 её карточки нет."""
    assert not [i.id for i in curriculum.page(10).items if i.quran == "1:1"]


def test_page_ten_goes_alphabet_then_hamza(curriculum: Curriculum) -> None:
    page = curriculum.page(10)
    assert [les.section for les in page.lessons][:2] == ["alphabet", "letter"]
    assert page.items[0].kind is ItemKind.RULE and page.items[1].kind is ItemKind.ALPHABET


def test_no_isti_adha_anywhere_in_the_program(curriculum: Curriculum) -> None:
    found = [i.id for les in curriculum.lessons for i in les.items if ISTI_ADHA_START in i.text]
    assert found == []


# ---------- экраны ----------
def test_newcomer_home_opens_the_scan_of_page_ten(curriculum: Curriculum) -> None:
    """«▶️ Начать первый урок» → скан с. 10 (урок = страница, ADR-0084), а не сразу карточка."""
    s = screens.home(curriculum, _progress(curriculum, attempts=0))
    first = _buttons(s.keyboard)[0]
    assert first[:2] == (texts.START_BUTTON, PageOpen(n=10).pack())


def test_returning_learner_home_still_continues_the_card(curriculum: Curriculum) -> None:
    s = screens.home(curriculum, _progress(curriculum, attempts=3, current="L006-01"))
    assert _buttons(s.keyboard)[0][1] == GoItem(item_id="L006-01").pack()


def test_page_ten_start_opens_the_alphabet(curriculum: Curriculum) -> None:
    s = screens.page_intro(curriculum, curriculum.page(10), None)
    assert (texts.PAGE_START, GoItem(item_id="L002-01").pack(), None) in _buttons(s.keyboard)


def test_alphabet_card_links_the_alphabet_video(curriculum: Curriculum) -> None:
    item = next(i for i in curriculum.page(10).items if i.kind is ItemKind.ALPHABET)
    s = screens.card(
        curriculum, item, has_audio=False, is_teacher=False, lesson_video=ALPHABET_VIDEO
    )
    assert (texts.ALPHABET_VIDEO_BUTTON, None, ALPHABET_VIDEO) in _buttons(s.keyboard)
    assert texts.ALPHABET_VIDEO_BUTTON == "🎬 Видео: арабский алфавит · 5 мин"  # автор 2026-11-21


def test_card_without_lesson_video_has_no_video_link(curriculum: Curriculum) -> None:
    item = next(i for i in curriculum.page(10).items if i.kind is ItemKind.ALPHABET)
    s = screens.card(curriculum, item, has_audio=False, is_teacher=False)
    assert texts.ALPHABET_VIDEO_BUTTON not in [t for t, _, _ in _buttons(s.keyboard)]


def test_alphabet_lesson_has_its_own_video_link() -> None:
    links = YamlLessonLinks.load(CURRICULUM_DIR / "lesson_links.yaml")
    assert links.for_lesson("L002") == ALPHABET_VIDEO


# ---------- «начало занятия» убрано ----------
def test_settings_have_no_daily_opening_toggle() -> None:
    assert TOGGLES == ("large_font",)
    labels = [t for t, _, _ in _buttons(screens.settings(LearnerSettings()).keyboard)]
    assert not [t for t in labels if "🌙" in t or "истиаз" in t.casefold()], labels


def test_no_learner_text_mentions_isti_adha() -> None:
    said = [
        name
        for name, value in vars(texts).items()
        if isinstance(value, str) and "истиаз" in value.casefold()
    ]
    assert said == []


def test_voice_on_home_sends_newcomer_to_the_scan_too(curriculum: Curriculum) -> None:
    """Голосовое на главной у новичка — та же дорога, что «Начать»: скан с. 10 (ревью)."""
    s = screens.voice_on_home(curriculum, _progress(curriculum, attempts=0))
    assert _buttons(s.keyboard)[0][1] == PageOpen(n=10).pack()


def test_voice_on_home_continues_a_returning_learner(curriculum: Curriculum) -> None:
    s = screens.voice_on_home(curriculum, _progress(curriculum, attempts=3, current="L006-01"))
    assert _buttons(s.keyboard)[0][1] == GoItem(item_id="L006-01").pack()


def test_lesson_titles_have_no_book_numbers(curriculum: Curriculum) -> None:
    """Автор 2026-11-21 (4Б): ученик не видит «2. Арабский алфавит» — номер урока только внутри
    (`lesson.number`, на нём пороги проверки), в названии его нет."""
    numbered = [les.title for les in curriculum.lessons if les.title[:1].isdigit()]
    assert numbered == []
    assert curriculum.lessons[0].title == "Арабский алфавит"
