"""Навигация кнопками: главная, уроки, прогресс, справка, знаки, закрепление, карточка."""

import random
from typing import Final

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from dishka import FromDishka

from muallim.application.ports.storage import ReferenceAudioLibrary
from muallim.application.ports.system import Clock
from muallim.application.use_cases.cards import OpenItem
from muallim.application.use_cases.progress import GetProgress
from muallim.application.use_cases.quiz import PracticeQuiz
from muallim.application.use_cases.reading import HowToRead
from muallim.application.use_cases.reference import RecordReference
from muallim.domain.curriculum import Curriculum
from muallim.domain.learner import Learner
from muallim.presentation.telegram import on_screen, opening, screens, texts
from muallim.presentation.telegram.callbacks import (
    Again,
    GoItem,
    Help,
    Home,
    Lessons,
    Menu,
    Noop,
    Quiz,
    QuizAnswer,
    ShowProgress,
    Signs,
)
from muallim.presentation.telegram.display import Display, message_of
from muallim.presentation.telegram.handlers.daily import home_or_opening

router: Final = Router(name="learner.navigation")


@router.callback_query(Home.filter())
@router.callback_query(Menu.filter())  # кнопки из старых сообщений
async def cb_home(
    cb: CallbackQuery,
    state: FSMContext,
    display: FromDishka[Display],
    learner: FromDishka[Learner],
    cur: FromDishka[Curriculum],
    progress: FromDishka[GetProgress],
) -> None:
    if msg := message_of(cb):
        await display.show(msg, await home_or_opening(cur, await progress.execute(learner), state))
    await cb.answer()


@router.callback_query(Lessons.filter())
async def cb_lessons(
    cb: CallbackQuery,
    state: FSMContext,
    callback_data: Lessons,
    display: FromDishka[Display],
    learner: FromDishka[Learner],
    cur: FromDishka[Curriculum],
    progress: FromDishka[GetProgress],
) -> None:
    await on_screen.menu(state)  # не карточка: голосовое здесь не оценивается
    if msg := message_of(cb):
        screen = screens.lessons(
            cur, await progress.execute(learner), callback_data.part, callback_data.page
        )
        await display.show(msg, screen)
    await cb.answer()


@router.callback_query(ShowProgress.filter())
async def cb_progress(
    cb: CallbackQuery,
    state: FSMContext,
    display: FromDishka[Display],
    learner: FromDishka[Learner],
    cur: FromDishka[Curriculum],
    progress: FromDishka[GetProgress],
) -> None:
    await on_screen.menu(state)  # не карточка: голосовое здесь не оценивается
    if msg := message_of(cb):
        await display.show(msg, screens.progress(cur, await progress.execute(learner)))
    await cb.answer()


@router.callback_query(Help.filter())
async def cb_help(cb: CallbackQuery, state: FSMContext, display: FromDishka[Display]) -> None:
    await on_screen.menu(state)  # не карточка: голосовое здесь не оценивается
    if msg := message_of(cb):
        await display.show(msg, screens.help_screen())
    await cb.answer()


@router.callback_query(Signs.filter())
async def cb_signs(cb: CallbackQuery, state: FSMContext, display: FromDishka[Display]) -> None:
    await on_screen.menu(state)  # не карточка: голосовое здесь не оценивается
    if msg := message_of(cb):
        await display.show(msg, screens.signs())
    await cb.answer()


@router.callback_query(Quiz.filter())
async def cb_quiz(
    cb: CallbackQuery,
    state: FSMContext,
    display: FromDishka[Display],
    learner: FromDishka[Learner],
    uc: FromDishka[PracticeQuiz],
    cur: FromDishka[Curriculum],
    progress: FromDishka[GetProgress],
) -> None:
    await on_screen.menu(state)  # не карточка: голосовое здесь не оценивается
    q = await uc.next(learner, random.randrange(10**6))  # noqa: S311
    if msg := message_of(cb):
        await display.show(
            msg,
            screens.quiz(q)
            if q
            else screens.quiz_unavailable(cur, await progress.execute(learner)),
        )
    await cb.answer()


@router.callback_query(QuizAnswer.filter())
async def cb_quiz_answer(
    cb: CallbackQuery,
    state: FSMContext,
    callback_data: QuizAnswer,
    display: FromDishka[Display],
    learner: FromDishka[Learner],
    uc: FromDishka[PracticeQuiz],
) -> None:
    await on_screen.menu(state)  # не карточка: голосовое здесь не оценивается
    data = callback_data
    try:
        q = await uc.answer(learner, data.i, data.v, data.s, data.p, started=data.k)
    except (KeyError, IndexError):
        await cb.answer(texts.STALE_BUTTON, show_alert=True)
        return
    if msg := message_of(cb):
        await display.show(msg, screens.quiz_answer(q, data.p))
    await cb.answer("✅" if data.p == q.answer else "❌")


@router.callback_query(GoItem.filter())
async def cb_go(
    cb: CallbackQuery,
    callback_data: GoItem,
    state: FSMContext,
    clock: FromDishka[Clock],
    display: FromDishka[Display],
    learner: FromDishka[Learner],
    uc: FromDishka[OpenItem],
    cur: FromDishka[Curriculum],
    library: FromDishka[ReferenceAudioLibrary],
    recorder: FromDishka[RecordReference],
    reading: FromDishka[HowToRead],
) -> None:
    try:
        # пока идёт начало занятия, кнопки его экранов не сдвигают «Продолжить» (FR-49);
        # переход к обычной карточке его завершает. Карточка, выбранная с экрана меню
        # («📚 Уроки»), — сознательный выбор: начало занятия завершается и курсор двигается.
        in_opening = await opening.active(state, clock.now().date())
        shown = await on_screen.shown(state)
        if in_opening and shown is not None and shown.item_id is None:
            await opening.finish(state)
            in_opening = False
        item = await uc.execute(learner, callback_data.item_id, move=not in_opening)
        step = in_opening and item.id in opening.OPENING_ITEMS
        if in_opening and not step:
            await opening.finish(state)
        await on_screen.card(state, item.id, opening=step)
    except KeyError:
        await cb.answer(texts.STALE_BUTTON, show_alert=True)
        return
    if msg := message_of(cb):
        screen = screens.card(
            cur,
            item,
            library.has(item.id),
            recorder.allowed(learner),
            reading.execute(learner, item),
        )
        await display.show(msg, screen)
    await cb.answer()


@router.callback_query(Noop.filter())
async def cb_noop(cb: CallbackQuery) -> None:
    await cb.answer()


@router.callback_query(Again.filter())  # кнопки «Ещё раз» из старых сообщений
async def cb_again(cb: CallbackQuery) -> None:
    await cb.answer(texts.RECORD_AGAIN)
