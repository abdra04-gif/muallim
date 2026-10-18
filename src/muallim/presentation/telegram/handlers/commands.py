"""Команды ученика: /start, /lessons, /progress, /help, /privacy, /signs, /quiz, /me."""

import random
from typing import Final

from aiogram import Bot, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from dishka import FromDishka

from muallim.application.use_cases.learners import Questionnaire
from muallim.application.use_cases.progress import GetProgress
from muallim.application.use_cases.quiz import PracticeQuiz
from muallim.domain.curriculum import Curriculum
from muallim.domain.learner import Learner
from muallim.presentation.telegram import keyboards, screens, texts, views
from muallim.presentation.telegram.display import Display
from muallim.presentation.telegram.learner import NewLearner
from muallim.presentation.telegram.screens import Screen

router: Final = Router(name="learner.commands")

PROFILE_START: Final = Screen(texts.PROFILE_ADULT, keyboards.profile_adult())


@router.message(CommandStart())
async def start(
    m: Message,
    bot: Bot,
    display: FromDishka[Display],
    learner: FromDishka[Learner],
    is_new: FromDishka[NewLearner],
    cur: FromDishka[Curriculum],
    progress: FromDishka[GetProgress],
    questionnaire: FromDishka[Questionnaire],
) -> None:
    if is_new and not learner.research_consent:
        await m.answer(texts.WELCOME)
        await m.answer(texts.CONSENT_TEXT, reply_markup=keyboards.consent())
        return
    if await questionnaire.needed(learner):  # анкету бросили на середине — спросить ещё раз
        await display.send(bot, m.chat.id, PROFILE_START)
        return
    await display.send(bot, m.chat.id, screens.home(cur, await progress.execute(learner)))


@router.message(Command("lessons"))
async def lessons(
    m: Message,
    bot: Bot,
    display: FromDishka[Display],
    learner: FromDishka[Learner],
    cur: FromDishka[Curriculum],
    progress: FromDishka[GetProgress],
) -> None:
    screen = screens.lessons(cur, await progress.execute(learner), part=-1)
    await display.send(bot, m.chat.id, screen)


@router.message(Command("progress"))
async def progress_cmd(
    m: Message,
    bot: Bot,
    display: FromDishka[Display],
    learner: FromDishka[Learner],
    cur: FromDishka[Curriculum],
    progress: FromDishka[GetProgress],
) -> None:
    await display.send(bot, m.chat.id, screens.progress(cur, await progress.execute(learner)))


@router.message(Command("help"))
async def help_cmd(m: Message, bot: Bot, display: FromDishka[Display]) -> None:
    await display.send(bot, m.chat.id, screens.help_screen())


@router.message(Command("privacy"))
async def privacy(
    m: Message, bot: Bot, display: FromDishka[Display], learner: FromDishka[Learner]
) -> None:
    await display.send(bot, m.chat.id, screens.privacy(learner.research_consent))


@router.message(Command("signs"))
async def signs_cmd(m: Message, bot: Bot, display: FromDishka[Display]) -> None:
    await display.send(bot, m.chat.id, screens.signs())


@router.message(Command("quiz"))
async def quiz_cmd(
    m: Message,
    bot: Bot,
    display: FromDishka[Display],
    learner: FromDishka[Learner],
    uc: FromDishka[PracticeQuiz],
) -> None:
    q = await uc.next(learner, random.randrange(10**6))  # noqa: S311
    await display.send(bot, m.chat.id, screens.quiz(q) if q else screens.quiz_unavailable())


@router.message(Command("me"))
async def me(m: Message, learner: FromDishka[Learner]) -> None:
    await m.answer(views.me(learner.pseudonym))
