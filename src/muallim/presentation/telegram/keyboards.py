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


def dispute_reasons(attempt_hex: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for reason, title in texts.DISPUTE_REASONS.items():
        kb.button(text=title, callback_data=DisputeReason(attempt=attempt_hex, reason=reason))
    kb.adjust(1)
    return kb.as_markup()


def consent() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Да, разрешаю", callback_data=Consent(granted=True))
    kb.button(text="🚫 Нет", callback_data=Consent(granted=False))
    return kb.as_markup()


def profile_adult() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Да, мне 18+", callback_data=Profile(adult=True))
    kb.button(text="Нет", callback_data=Profile(adult=False))
    return kb.as_markup()


def profile_language() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    options = (("ru", "Русский"), ("kk", "Казахский"), ("tt", "Татарский"), ("other", "Другой"))
    for code, label in options:
        kb.button(text=label, callback_data=Profile(adult=True, lang=code))
    kb.adjust(2)
    return kb.as_markup()


def profile_reading(lang: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    options = (
        ("none", "Совсем нет"),
        ("some_letters", "Знаю некоторые буквы"),
        ("slow_syllables", "Читаю медленно, по слогам"),
    )
    for code, label in options:
        kb.button(text=label, callback_data=Profile(adult=True, lang=lang, read=code))
    kb.adjust(1)
    return kb.as_markup()


def delete_confirm() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🗑 Да, удалить всё", callback_data=DeleteData(confirmed=True))
    kb.button(text="Отмена", callback_data=Home())
    kb.adjust(1)
    return kb.as_markup()
