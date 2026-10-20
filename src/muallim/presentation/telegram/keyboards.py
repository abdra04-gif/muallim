from aiogram.enums import ButtonStyle
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

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


def profile_adult() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.PROFILE_ADULT_YES, callback_data=Profile(adult=True))
    kb.button(text=texts.PROFILE_ADULT_NO, callback_data=Profile(adult=False))
    return kb.as_markup()


def profile_language() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for code, label in texts.PROFILE_LANGUAGES.items():
        kb.button(text=label, callback_data=Profile(adult=True, lang=code))
    kb.adjust(2)
    return kb.as_markup()


def profile_reading(lang: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for code, label in texts.PROFILE_READING_OPTIONS.items():
        kb.button(text=label, callback_data=Profile(adult=True, lang=lang, read=code))
    kb.adjust(1)
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
