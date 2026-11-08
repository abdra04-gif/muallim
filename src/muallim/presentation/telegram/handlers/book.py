"""Страницы книги (автор 2026-11-08): начало урока-страницы и «📄 Страница книги» из «Подробнее»."""

from typing import Final

from aiogram import Router
from aiogram.types import CallbackQuery
from dishka import FromDishka

from muallim.application.ports.storage import BookPages
from muallim.application.use_cases.cards import OpenItem
from muallim.application.use_cases.screen import ScreenState
from muallim.domain.curriculum import Curriculum
from muallim.domain.learner import Learner
from muallim.presentation.telegram import screens, texts
from muallim.presentation.telegram.callbacks import BookPage, PageOpen
from muallim.presentation.telegram.display import Display, drop_sound, message_of

router: Final = Router(name="book")


@router.callback_query(BookPage.filter())
async def cb_book_page(
    cb: CallbackQuery,
    callback_data: BookPage,
    display: FromDishka[Display],
    learner: FromDishka[Learner],
    uc: FromDishka[OpenItem],
    pages: FromDishka[BookPages],
) -> None:
    """«📄 Страница книги»: картинка страницы на месте «Подробнее»; карточка остаётся текущей."""
    image = await pages.get(callback_data.page)
    try:
        item = await uc.execute(learner, callback_data.item_id)
    except KeyError:
        item = None
    if image is None or item is None:
        await cb.answer(texts.STALE_BUTTON, show_alert=True)
        return
    if msg := message_of(cb):
        await display.show(msg, screens.book_page(item, callback_data.page, image))
    await cb.answer()


@router.callback_query(PageOpen.filter())
async def cb_page_open(
    cb: CallbackQuery,
    callback_data: PageOpen,
    display: FromDishka[Display],
    learner: FromDishka[Learner],
    screen_state: FromDishka[ScreenState],
    cur: FromDishka[Curriculum],
    pages: FromDishka[BookPages],
) -> None:
    """Начало урока-страницы: скан страницы всегда (автор 2026-11-08), «▶️ Начать»."""
    try:
        page = cur.page(callback_data.n)
    except KeyError:
        await cb.answer(texts.STALE_BUTTON, show_alert=True)
        return
    await screen_state.menu(learner)  # не карточка: голосовое здесь не оценивается
    if msg := message_of(cb):
        await drop_sound(display, msg)
        image = await pages.get(page.number)
        await display.show(msg, screens.page_intro(cur, page, image))
    await cb.answer()
