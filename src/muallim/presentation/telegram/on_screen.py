"""Что сейчас на экране ученика: карточка урока или меню (главная, прогресс, знаки…).

Голосовое оценивается, только когда открыта карточка (решение автора 2026-10-20): на главной
урок не открыт — бот предлагает его открыть (``texts.VOICE_ON_HOME``). Карточка начала занятия
помечается отдельно: её попытка — только в день начала занятия. Хранится в FSM; нет записи
(старая сессия) — как раньше, оценивается карточка курсора.
"""

from dataclasses import dataclass
from typing import Final

from aiogram.fsm.context import FSMContext

_KEY: Final = "on_screen"  # id карточки; "" — меню
_OPENING: Final = "on_screen_opening"  # карточка открыта как шаг начала занятия


@dataclass(frozen=True, slots=True)
class OnScreen:
    item_id: str | None  # None — на экране меню, не карточка
    opening: bool = False


async def card(state: FSMContext, item_id: str, *, opening: bool = False) -> None:
    await state.update_data({_KEY: item_id, _OPENING: opening})


async def menu(state: FSMContext) -> None:
    await state.update_data({_KEY: "", _OPENING: False})


async def shown(state: FSMContext) -> OnScreen | None:
    """None — неизвестно (сессия до этого изменения)."""
    data = await state.get_data()
    value = data.get(_KEY)
    if not isinstance(value, str):
        return None
    return OnScreen(value or None, bool(data.get(_OPENING)))
