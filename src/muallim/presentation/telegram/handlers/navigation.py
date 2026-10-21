"""Навигация кнопками: главная, уроки, прогресс, справка, знаки, закрепление, карточка."""

import random
from typing import Final

from aiogram import Router
from aiogram.types import CallbackQuery
from dishka import FromDishka

from muallim.application.ports.storage import ReferenceAudioLibrary
from muallim.application.use_cases.cards import OpenItem
from muallim.application.use_cases.progress import GetProgress
from muallim.application.use_cases.quiz import PracticeQuiz
from muallim.application.use_cases.reading import HowToRead
from muallim.application.use_cases.reference import GetReferenceAudio, RecordReference
from muallim.application.use_cases.screen import ScreenState
from muallim.application.use_cases.settings import GetSettings
from muallim.domain.curriculum import Curriculum
from muallim.domain.learner import Learner
from muallim.presentation.telegram import opening, screens, texts
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
from muallim.presentation.telegram.display import Display, drop_sound, message_of
from muallim.presentation.telegram.handlers.daily import home_or_opening
from muallim.presentation.telegram.handlers.reference import show_card

router: Final = Router(name="learner.navigation")


@router.callback_query(Home.filter())
@router.callback_query(Menu.filter())  # кнопки из старых сообщений
async def cb_home(
    cb: CallbackQuery,
    screen_state: FromDishka[ScreenState],
    display: FromDishka[Display],
    learner: FromDishka[Learner],
    cur: FromDishka[Curriculum],
    progress: FromDishka[GetProgress],
) -> None:
    if msg := message_of(cb):
        await drop_sound(display, msg)  # ушёл с карточки — автоэталон убрать
        await display.show(
            msg, await home_or_opening(cur, await progress.execute(learner), learner, screen_state)
        )
    await cb.answer()


@router.callback_query(Lessons.filter())
async def cb_lessons(
    cb: CallbackQuery,
    screen_state: FromDishka[ScreenState],
    callback_data: Lessons,
    display: FromDishka[Display],
    learner: FromDishka[Learner],
    cur: FromDishka[Curriculum],
    progress: FromDishka[GetProgress],
) -> None:
    await screen_state.menu(learner)  # не карточка: голосовое здесь не оценивается
    if msg := message_of(cb):
        await drop_sound(display, msg)  # ушёл с карточки — автоэталон убрать
        screen = screens.lessons(
            cur, await progress.execute(learner), callback_data.part, callback_data.page
        )
        await display.show(msg, screen)
    await cb.answer()


@router.callback_query(ShowProgress.filter())
async def cb_progress(
    cb: CallbackQuery,
    screen_state: FromDishka[ScreenState],
    display: FromDishka[Display],
    learner: FromDishka[Learner],
    cur: FromDishka[Curriculum],
    progress: FromDishka[GetProgress],
) -> None:
    await screen_state.menu(learner)  # не карточка: голосовое здесь не оценивается
    if msg := message_of(cb):
        await drop_sound(display, msg)  # ушёл с карточки — автоэталон убрать
        await display.show(msg, screens.progress(cur, await progress.execute(learner)))
    await cb.answer()


@router.callback_query(Help.filter())
async def cb_help(
    cb: CallbackQuery,
    display: FromDishka[Display],
    learner: FromDishka[Learner],
    screen_state: FromDishka[ScreenState],
) -> None:
    await screen_state.menu(learner)  # не карточка: голосовое здесь не оценивается
    if msg := message_of(cb):
        await drop_sound(display, msg)  # ушёл с карточки — автоэталон убрать
        await display.show(msg, screens.help_screen())
    await cb.answer()


@router.callback_query(Signs.filter())
async def cb_signs(
    cb: CallbackQuery,
    display: FromDishka[Display],
    learner: FromDishka[Learner],
    screen_state: FromDishka[ScreenState],
    cur: FromDishka[Curriculum],
    progress: FromDishka[GetProgress],
) -> None:
    await screen_state.menu(learner)  # не карточка: голосовое здесь не оценивается
    if msg := message_of(cb):
        await drop_sound(display, msg)  # ушёл с карточки — автоэталон убрать
        await display.show(msg, screens.signs(cur, await progress.execute(learner)))
    await cb.answer()


@router.callback_query(Quiz.filter())
async def cb_quiz(
    cb: CallbackQuery,
    screen_state: FromDishka[ScreenState],
    display: FromDishka[Display],
    learner: FromDishka[Learner],
    uc: FromDishka[PracticeQuiz],
    cur: FromDishka[Curriculum],
    progress: FromDishka[GetProgress],
) -> None:
    await screen_state.menu(learner)  # не карточка: голосовое здесь не оценивается
    q = await uc.next(learner, random.randrange(10**6))  # noqa: S311
    if msg := message_of(cb):
        await drop_sound(display, msg)  # ушёл с карточки — автоэталон убрать
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
    screen_state: FromDishka[ScreenState],
    callback_data: QuizAnswer,
    display: FromDishka[Display],
    learner: FromDishka[Learner],
    uc: FromDishka[PracticeQuiz],
) -> None:
    await screen_state.menu(learner)  # не карточка: голосовое здесь не оценивается
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
    screen_state: FromDishka[ScreenState],
    display: FromDishka[Display],
    learner: FromDishka[Learner],
    uc: FromDishka[OpenItem],
    cur: FromDishka[Curriculum],
    library: FromDishka[ReferenceAudioLibrary],
    recorder: FromDishka[RecordReference],
    reading: FromDishka[HowToRead],
    learner_settings: FromDishka[GetSettings],
    reference: FromDishka[GetReferenceAudio],
) -> None:
    try:
        # пока идёт начало занятия, кнопки его экранов не сдвигают «Продолжить» (FR-49);
        # переход к обычной карточке его завершает. Карточка, выбранная с экрана меню
        # («📚 Уроки»), — сознательный выбор: начало занятия завершается и курсор двигается.
        shown = await screen_state.execute(learner)
        in_opening = shown.opening_active
        if in_opening and shown.item_id is None:  # с экрана меню — начало занятия завершается
            in_opening = False
        item = await uc.execute(learner, callback_data.item_id, move=not in_opening)
        step = in_opening and item.id in opening.OPENING_ITEMS
        await screen_state.card(learner, item.id, opening=step, finish=not step)
    except KeyError:
        await cb.answer(texts.STALE_BUTTON, show_alert=True)
        return
    if msg := message_of(cb):
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


@router.callback_query(Noop.filter())
async def cb_noop(cb: CallbackQuery) -> None:
    await cb.answer()


@router.callback_query(Again.filter())  # кнопки «Ещё раз» из старых сообщений
async def cb_again(cb: CallbackQuery) -> None:
    await cb.answer(texts.RECORD_AGAIN)
