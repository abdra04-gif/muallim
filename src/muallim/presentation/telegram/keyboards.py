from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from muallim.presentation.telegram import texts
from muallim.presentation.telegram.callbacks import (
    Consent,
    DeleteData,
    DisputeReason,
    Home,
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


def delete_confirm() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🗑 Да, удалить всё", callback_data=DeleteData(confirmed=True))
    kb.button(text="Отмена", callback_data=Home())
    kb.adjust(1)
    return kb.as_markup()
