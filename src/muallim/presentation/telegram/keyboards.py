from typing import Final

from aiogram.enums import ButtonStyle
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from muallim.domain.learner import NAME_MAX_LENGTH, Question
from muallim.presentation.telegram import texts
from muallim.presentation.telegram.callbacks import (
    Consent,
    DeleteData,
    DisputeReason,
    Home,
    Profile,
)

CANCEL = "cancel"  # DisputeReason.reason: закрыть меню «Бот ошибся» без жалобы


def dispute_reasons(attempt_hex: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for reason, title in texts.DISPUTE_REASONS.items():
        kb.button(text=title, callback_data=DisputeReason(attempt=attempt_hex, reason=reason))
    # передумал — меню закрывается, экран результата остаётся выше (FR-50)
    kb.button(
        text=texts.CANCEL_BUTTON, callback_data=DisputeReason(attempt=attempt_hex, reason=CANCEL)
    )
    kb.adjust(1)
    return kb.as_markup()


def consent() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.CONSENT_YES_BUTTON, callback_data=Consent(granted=True))
    kb.button(text=texts.CONSENT_NO_BUTTON, callback_data=Consent(granted=False))
    return kb.as_markup()


_PROFILE_OPTIONS: Final = {
    Question.AGE: (texts.PROFILE_AGE_OPTIONS, 3),
    Question.GENDER: (texts.PROFILE_GENDER_OPTIONS, 2),
    Question.NATIVE: (texts.PROFILE_LANGUAGES, 2),
    Question.READING: (texts.PROFILE_READING_OPTIONS, 1),
    Question.PRAYER: (texts.PROFILE_PRAYER_OPTIONS, 1),
}


def profile_question(question: Question, telegram_name: str = "") -> InlineKeyboardMarkup:
    """Кнопки одного вопроса анкеты и «Пропустить» отдельной строкой внизу (FR-65)."""
    kb = InlineKeyboardBuilder()
    if question is Question.NAME:
        if telegram_name:
            label = texts.PROFILE_NAME_TELEGRAM.format(name=telegram_name[:NAME_MAX_LENGTH])
            kb.button(text=label, callback_data=Profile(q=question.value, v="tg"))
        kb.button(text=texts.PROFILE_SKIP, callback_data=Profile(q=question.value, v="skip"))
        kb.adjust(1)
        return kb.as_markup()
    options, per_row = _PROFILE_OPTIONS[question]
    for code, label in options.items():
        kb.button(text=label, callback_data=Profile(q=question.value, v=code))
    kb.button(text=texts.PROFILE_SKIP, callback_data=Profile(q=question.value, v="skip"))
    full, rest = divmod(len(options), per_row)
    kb.adjust(*[per_row] * full, *([rest] if rest else []), 1)  # «Пропустить» — отдельной строкой
    return kb.as_markup()


def delete_confirm() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text=texts.DELETE_YES_BUTTON,
        callback_data=DeleteData(confirmed=True),
        style=ButtonStyle.DANGER,
    )
    kb.button(text=texts.CANCEL_BUTTON, callback_data=Home())
    kb.adjust(1)
    return kb.as_markup()
