"""⚙️ Настройки ученика (FR-51, ADR-0061): экран, смена значения, «🪪 Мой ID».

Экран — одно окно (ADR-0024): нажатие ставит значение и перерисовывает экран на месте.
«Как заниматься» и «Мои данные» открываются отсюда прежними обработчиками.
"""

from typing import Final

from aiogram import Router
from aiogram.types import CallbackQuery
from dishka import FromDishka

from muallim.application.use_cases.screen import ScreenState
from muallim.application.use_cases.settings import ChangeSetting, GetSettings
from muallim.domain.learner import Learner
from muallim.presentation.telegram import screens, texts, views
from muallim.presentation.telegram.callbacks import ChangeSetting as ChangeSettingCallback
from muallim.presentation.telegram.callbacks import Me, ShowSettings
from muallim.presentation.telegram.display import Display, message_of

router: Final = Router(name="learner.settings")


@router.callback_query(ShowSettings.filter())
async def cb_settings(
    cb: CallbackQuery,
    display: FromDishka[Display],
    learner: FromDishka[Learner],
    screen_state: FromDishka[ScreenState],
    uc: FromDishka[GetSettings],
) -> None:
    await screen_state.menu(learner)  # не карточка: голосовое здесь не оценивается
    if msg := message_of(cb):
        await display.show(msg, screens.settings(await uc.execute(learner)))
    await cb.answer()


@router.callback_query(ChangeSettingCallback.filter())
async def cb_change_setting(
    cb: CallbackQuery,
    callback_data: ChangeSettingCallback,
    display: FromDishka[Display],
    learner: FromDishka[Learner],
    uc: FromDishka[ChangeSetting],
) -> None:
    try:
        changed = await uc.execute(learner, callback_data.name, callback_data.value)
    except ValueError:  # кнопка от другой версии экрана
        await cb.answer(texts.STALE_BUTTON, show_alert=True)
        return
    if msg := message_of(cb):
        await display.show(msg, screens.settings(changed))
    await cb.answer()


@router.callback_query(Me.filter())
async def cb_me(cb: CallbackQuery, learner: FromDishka[Learner]) -> None:
    """Как /me — отдельным сообщением: ID удобно скопировать, экран настроек остаётся."""
    if msg := message_of(cb):
        await msg.answer(views.me(learner.pseudonym))
    await cb.answer()
