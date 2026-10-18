"""Начало занятия (истиаза и басмала раз в день) и открытка «урок пройден» (ADR-0050)."""

from typing import Final

from aiogram import Bot, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery
from dishka import FromDishka

from muallim.application.ports.storage import ReferenceAudioLibrary
from muallim.application.use_cases.cards import OpenItem
from muallim.application.use_cases.progress import GetProgress, Progress
from muallim.application.use_cases.reading import HowToRead
from muallim.application.use_cases.reference import RecordReference
from muallim.domain.curriculum import Curriculum
from muallim.domain.learner import Learner
from muallim.presentation.telegram import opening, screens, texts
from muallim.presentation.telegram.callbacks import Opening, ShareLesson
from muallim.presentation.telegram.display import Display, message_of
from muallim.presentation.telegram.screens import Screen

router: Final = Router(name="learner.daily")


async def home_or_opening(cur: Curriculum, progress: Progress, state: FSMContext) -> Screen:
    """Главная — или сначала «Начнём занятие», если сегодня его ещё не было."""
    if opening.needs_opening(progress, await opening.skipped_on(state)):
        return screens.opening(cur)
    return screens.home(cur, progress)


@router.callback_query(Opening.filter())
async def cb_opening(
    cb: CallbackQuery,
    callback_data: Opening,
    state: FSMContext,
    display: FromDishka[Display],
    learner: FromDishka[Learner],
    cur: FromDishka[Curriculum],
    progress: FromDishka[GetProgress],
    cards: FromDishka[OpenItem],
    library: FromDishka[ReferenceAudioLibrary],
    recorder: FromDishka[RecordReference],
    reading: FromDishka[HowToRead],
) -> None:
    p = await progress.execute(learner)
    msg = message_of(cb)
    if callback_data.act == "skip":
        if p.today is not None:
            await opening.skip(state, p.today)
        if msg:
            await display.show(msg, screens.home(cur, p))
        await cb.answer()
        return
    resume = p.continue_item or cur.first_item()
    await opening.begin(state, resume.id)
    item = await cards.execute(learner, opening.OPENING_ITEMS[0])
    if msg:
        screen = screens.card(
            cur,
            item,
            library.has(item.id),
            recorder.allowed(learner),
            reading.execute(learner, item),
        )
        await display.show(msg, screen)
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
