"""Главная после /start и 🏠; старые кнопки «начала занятия» и «Поделиться» (ADR-0050, ADR-0089).

«Начало занятия» с истиазой и басмалой убрано автором 2026-11-21: истиазы в книге нет. Кнопки
«🎙 Читать истиазу» и «⏭ Пропустить» из старых сообщений показывают главную.
"""

from typing import Final

from aiogram import Router
from aiogram.types import CallbackQuery
from dishka import FromDishka

from muallim.application.use_cases.progress import GetProgress, Progress
from muallim.application.use_cases.screen import ScreenState
from muallim.domain.curriculum import Curriculum
from muallim.domain.learner import Learner
from muallim.presentation.telegram import screens, texts
from muallim.presentation.telegram.callbacks import Opening, ShareLesson
from muallim.presentation.telegram.display import Display, message_of
from muallim.presentation.telegram.screens import Screen

router: Final = Router(name="learner.daily")


async def home_screen(
    cur: Curriculum,
    progress: Progress,
    learner: Learner,
    screen_state: ScreenState,
    quiz_waiting: int = 0,
) -> Screen:
    """Главная; на экране — меню, не карточка (голосовое не оценивается)."""
    await screen_state.menu(learner)
    return screens.home(cur, progress, quiz_waiting)


@router.callback_query(Opening.filter())
async def cb_old_opening(
    cb: CallbackQuery,
    display: FromDishka[Display],
    learner: FromDishka[Learner],
    cur: FromDishka[Curriculum],
    progress: FromDishka[GetProgress],
    screen_state: FromDishka[ScreenState],
) -> None:
    """Кнопка «начала занятия» из старого сообщения — главная."""
    if msg := message_of(cb):
        p = await progress.execute(learner)
        await display.show(msg, await home_screen(cur, p, learner, screen_state))
    await cb.answer()


@router.callback_query(ShareLesson.filter())
async def cb_old_share(cb: CallbackQuery) -> None:
    """«📤 Поделиться» из старого сообщения: открытка убрана (автор 2026-11-21)."""
    await cb.answer(texts.STALE_BUTTON, show_alert=True)
