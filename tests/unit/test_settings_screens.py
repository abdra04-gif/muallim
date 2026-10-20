"""Главная после ⚙️ Настроек: шесть кнопок, «Как заниматься» и «Мои данные» — внутри (FR-51).

ADR-0061, пакет Б, круг 3: Продолжить / Уроки, Закрепление / Знаки, Прогресс / ⚙️ Настройки.
Проверяется экран (подпись и кнопки) без Telegram.
"""

from typing import Any

import pytest
from aiogram.types import InlineKeyboardMarkup

from muallim.application.use_cases.progress import LessonProgress, Progress
from muallim.domain.curriculum import Curriculum
from muallim.presentation.telegram import callbacks as cb
from muallim.presentation.telegram import render, screens, texts


@pytest.fixture(autouse=True)
def _captions_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(render, "available", lambda: False)


def _buttons(kb: InlineKeyboardMarkup) -> list[tuple[str, Any]]:
    return [(b.text, b.callback_data) for row in kb.inline_keyboard for b in row]


def _progress(c: Curriculum) -> Progress:
    lessons = tuple(LessonProgress(les, 0, ()) for les in c.lessons)
    return Progress(lessons, attempts_total=3, continue_item=c.item("L006-02"))


def test_home_ends_with_progress_and_settings(curriculum: Curriculum) -> None:
    buttons = _buttons(screens.home(curriculum, _progress(curriculum)).keyboard)
    assert buttons[1:] == [
        (texts.LESSONS_BUTTON, cb.Lessons(part=-1).pack()),
        (texts.QUIZ_BUTTON, cb.Quiz().pack()),
        (texts.SIGNS_BUTTON, cb.Signs().pack()),
        (texts.PROGRESS_BUTTON, cb.ShowProgress().pack()),
        (texts.SETTINGS_BUTTON, cb.ShowSettings().pack()),
    ]
    assert buttons[0][1] == cb.GoItem(item_id="L006-02").pack()  # ▶️ Продолжить


def test_home_has_no_help_or_privacy_buttons(curriculum: Curriculum) -> None:
    buttons = _buttons(screens.home(curriculum, _progress(curriculum)).keyboard)
    labels = [text for text, _ in buttons]
    assert texts.HELP_BUTTON not in labels and texts.PRIVACY_BUTTON not in labels
    assert cb.Help().pack() not in [data for _, data in buttons]
    assert cb.Privacy().pack() not in [data for _, data in buttons]


def test_settings_button_is_labelled_settings() -> None:
    assert texts.SETTINGS_BUTTON.startswith("⚙️") and "Настройки" in texts.SETTINGS_BUTTON
