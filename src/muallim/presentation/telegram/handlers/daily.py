"""Начало занятия (истиаза и басмала раз в день) и открытка «урок пройден» (ADR-0050)."""

from typing import Final

from aiogram import Bot, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BufferedInputFile, CallbackQuery
from dishka import FromDishka

from muallim.application.ports.storage import ReferenceAudioLibrary
from muallim.application.use_cases.cards import OpenItem
from muallim.application.use_cases.progress import GetProgress, Progress
from muallim.application.use_cases.reading import HowToRead
from muallim.application.use_cases.reference import GetReferenceAudio, RecordReference
from muallim.application.use_cases.screen import ScreenState
from muallim.application.use_cases.settings import GetSettings
from muallim.domain.curriculum import Curriculum
from muallim.domain.learner import Learner
from muallim.presentation.telegram import opening, screens, texts
from muallim.presentation.telegram.callbacks import Opening, ShareLesson
from muallim.presentation.telegram.display import Display, message_of
from muallim.presentation.telegram.handlers.reference import show_card
from muallim.presentation.telegram.screens import Screen

router: Final = Router(name="learner.daily")


async def home_or_opening(
    cur: Curriculum,
    progress: Progress,
    learner: Learner,
    screen_state: ScreenState,
    quiz_waiting: int = 0,
) -> Screen:
    """Главная — или сначала «Начнём занятие», если сегодня его ещё не было.

    Начатое начало занятия при этом снимается (🏠, /start), на экране — меню, не карточка.
    """
    await screen_state.menu(learner, finish=True)
    if await screen_state.needs_opening(learner, progress):
        return screens.opening(cur)
    return screens.home(cur, progress, quiz_waiting)


@router.callback_query(Opening.filter())
async def cb_opening(
    cb: CallbackQuery,
    callback_data: Opening,
    display: FromDishka[Display],
    learner: FromDishka[Learner],
    cur: FromDishka[Curriculum],
    progress: FromDishka[GetProgress],
    cards: FromDishka[OpenItem],
    library: FromDishka[ReferenceAudioLibrary],
    recorder: FromDishka[RecordReference],
    reading: FromDishka[HowToRead],
    screen_state: FromDishka[ScreenState],
    learner_settings: FromDishka[GetSettings],
    reference: FromDishka[GetReferenceAudio],
) -> None:
    p = await progress.execute(learner)
    msg = message_of(cb)
    if callback_data.act == "skip":
        await screen_state.skip_opening(learner)
        if msg:
            await display.show(msg, screens.home(cur, p))
        await cb.answer()
        return
    resume = p.continue_item or cur.first_item()
    item = await cards.execute(learner, opening.OPENING_ITEMS[0], move=False)  # FR-49
    await screen_state.begin_opening(learner, resume.id, item.id)
    if msg:
        view = await learner_settings.execute(learner)
        has_audio = library.has(item.id)
        screen = screens.card(
            cur,
            item,
            has_audio,
            recorder.allowed(learner),
            reading.execute(learner, item),
            view=view,
        )
        await show_card(
            msg, display, screen, learner=learner, item_id=item.id, has_audio=has_audio,
            view=view, reference=reference,
        )  # fmt: skip
    await cb.answer()


@router.callback_query(ShareLesson.filter())
async def cb_share(
    cb: CallbackQuery,
    callback_data: ShareLesson,
    bot: Bot,
    learner: FromDishka[Learner],
    cur: FromDishka[Curriculum],
    progress: FromDishka[GetProgress],
) -> None:
    """Открытка отдельным сообщением — ученик пересылает её сам. Без имени и псевдонима."""
    try:
        lesson = cur.lesson(callback_data.lesson)
    except KeyError:
        await cb.answer(texts.STALE_BUTTON, show_alert=True)
        return
    me = await bot.me()
    screen = screens.postcard(cur, lesson, await progress.execute(learner), me.username or "")
    msg = message_of(cb)
    if msg is not None:
        try:
            if screen.image is not None:
                photo = BufferedInputFile(screen.image, filename="muallim.png")
                await bot.send_photo(msg.chat.id, photo, caption=screen.caption)
            else:
                await bot.send_message(msg.chat.id, screen.caption)
        except TelegramAPIError:
            await cb.answer(texts.SOMETHING_WENT_WRONG, show_alert=True)
            return
    await cb.answer(texts.SHARE_SENT)
