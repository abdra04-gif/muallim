"""Шпаргалка букв по книге до урока (FR-52, ADR-0062 п. 7): экран меню, «◀️ Назад» — на карточку
или «🔤 Знаки», 🔊 — существующий ``Listen`` головной карточки буквы (handlers/reference.py).
Роликов 🎬 в шпаргалке нет (решение автора 2026-10-25, ADR-0074)."""

from typing import Final

from aiogram import Router
from aiogram.types import CallbackQuery
from dishka import FromDishka

from muallim.application.ports.storage import ArticulationVideoLibrary, ReferenceAudioLibrary
from muallim.application.use_cases.screen import ScreenState
from muallim.domain.curriculum import Curriculum, letters_before
from muallim.domain.learner import Learner
from muallim.presentation.telegram import screens, texts
from muallim.presentation.telegram.callbacks import LettersSheet
from muallim.presentation.telegram.display import Display, drop_sound, message_of

router: Final = Router(name="learner.letters")


@router.callback_query(LettersSheet.filter())
async def cb_letters_sheet(
    cb: CallbackQuery,
    callback_data: LettersSheet,
    display: FromDishka[Display],
    learner: FromDishka[Learner],
    screen_state: FromDishka[ScreenState],
    cur: FromDishka[Curriculum],
    library: FromDishka[ReferenceAudioLibrary],
    videos: FromDishka[ArticulationVideoLibrary],
) -> None:
    """Шпаргалка букв до урока (FR-52): экран меню, 🔊 — обычный ``Listen`` головной карточки."""
    try:
        known = letters_before(cur, callback_data.lesson_id)
        if callback_data.item_id:
            cur.item(callback_data.item_id)
    except KeyError:
        await cb.answer(texts.STALE_BUTTON, show_alert=True)
        return
    await screen_state.menu(learner)  # не карточка: голосовое здесь не оценивается
    if msg := message_of(cb):
        await drop_sound(display, msg)  # ушёл с карточки — автоэталон убрать
        audio = frozenset(head.id for head in known if library.has(head.id))
        screen = screens.letters_sheet(
            cur, callback_data.lesson_id, audio, back_item=callback_data.item_id, videos=videos
        )
        await display.show(msg, screen)
    await cb.answer()
