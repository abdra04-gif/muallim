"""⚙️ Настройки ученика (FR-51, ADR-0061): экран, смена значения, «🪪 Мой ID».

Экран — одно окно (ADR-0024): нажатие ставит значение и перерисовывает экран на месте.
«Как заниматься» и «Мои данные» открываются отсюда прежними обработчиками и ведут обратно
кнопкой «◀️ Настройки». Напоминание (ADR-0061 п. 3): 🔔 → час → «который у тебя час?» → настройки.
"""

from typing import Final

from aiogram import F, Router
from aiogram.types import CallbackQuery
from dishka import FromDishka

from muallim.application.ports.system import Clock
from muallim.application.use_cases.screen import ScreenState
from muallim.application.use_cases.settings import REMINDER_MINUTE, ChangeSetting, GetSettings
from muallim.domain.learner import Learner
from muallim.presentation.telegram import screens, texts
from muallim.presentation.telegram.callbacks import ChangeSetting as ChangeSettingCallback
from muallim.presentation.telegram.callbacks import Me, ShowSettings
from muallim.presentation.telegram.display import Display, drop_sound, message_of

router: Final = Router(name="learner.settings")


@router.callback_query(ShowSettings.filter())
@router.callback_query(F.data == "settings")  # кнопка ⚙️ из сообщений до поля ``page``
async def cb_settings(
    cb: CallbackQuery,
    display: FromDishka[Display],
    learner: FromDishka[Learner],
    screen_state: FromDishka[ScreenState],
    uc: FromDishka[GetSettings],
    callback_data: ShowSettings | None = None,
) -> None:
    page = callback_data.page if callback_data is not None else ""
    if page == "hint":  # заголовок «🔤 Как читается:» — объяснение (TD-FN-93 п. 5)
        await cb.answer(texts.HOW_TO_READ_HINT, show_alert=True)
        return
    await screen_state.menu(learner)  # не карточка: голосовое здесь не оценивается
    if msg := message_of(cb):
        await drop_sound(display, msg)
        current = await uc.execute(learner)
        screen = (
            screens.reminder_hours(current) if page == "reminder" else screens.settings(current)
        )
        await display.show(msg, screen)
    await cb.answer()


@router.callback_query(ChangeSettingCallback.filter())
async def cb_change_setting(
    cb: CallbackQuery,
    callback_data: ChangeSettingCallback,
    display: FromDishka[Display],
    learner: FromDishka[Learner],
    uc: FromDishka[ChangeSetting],
    clock: FromDishka[Clock],
) -> None:
    try:
        changed = await uc.execute(learner, callback_data.name, callback_data.value)
    except ValueError:  # кнопка от другой версии экрана или подделанная
        await cb.answer(texts.STALE_BUTTON, show_alert=True)
        return
    if msg := message_of(cb):
        asks_time = callback_data.name == REMINDER_MINUTE and changed.reminder_minute is not None
        screen = screens.reminder_ask_time(clock.now()) if asks_time else screens.settings(changed)
        await display.show(msg, screen)
    await cb.answer()


@router.callback_query(Me.filter())
async def cb_me(
    cb: CallbackQuery, display: FromDishka[Display], learner: FromDishka[Learner]
) -> None:
    """Как /me, но на месте экрана настроек — с кнопкой обратно (TD-FN-93 п. 4)."""
    if msg := message_of(cb):
        await display.show(msg, screens.me(learner.pseudonym))
    await cb.answer()
