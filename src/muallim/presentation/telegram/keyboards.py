from typing import Final

from aiogram.enums import ButtonStyle
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from muallim.domain.learner import Question
from muallim.presentation.telegram import texts
from muallim.presentation.telegram.callbacks import (
    Consent,
    DeleteData,
    DisputeReason,
    Privacy,
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


def profile_question(question: Question) -> InlineKeyboardMarkup:
    """Кнопки одного вопроса анкеты (FR-65); имя — без кнопок, его пишут (автор 2026-11-08)."""
    kb = InlineKeyboardBuilder()
    if question is Question.NAME:
        return InlineKeyboardMarkup(inline_keyboard=[])
    options, per_row = _PROFILE_OPTIONS[question]
    for code, label in options.items():
        kb.button(text=label, callback_data=Profile(q=question.value, v=code))
    full, rest = divmod(len(options), per_row)
    kb.adjust(*[per_row] * full, *([rest] if rest else []))
    return kb.as_markup()


def delete_confirm() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text=texts.DELETE_YES_BUTTON,
        callback_data=DeleteData(confirmed=True),
        style=ButtonStyle.DANGER,
    )
    kb.button(text=texts.CANCEL_BUTTON, callback_data=Privacy())  # отмена — назад в «Мои данные»
    kb.adjust(1)
    return kb.as_markup()
