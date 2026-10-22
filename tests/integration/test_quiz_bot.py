"""«🧠 Закрепление» через настоящие обработчики (FR-53, ADR-0066): шапка «k из 10», верный ответ —
сразу следующий вопрос, неверный — разбор и «▶️ Дальше», старые кнопки — «устарела», ступень ③ —
голосовое пишется в попытки и связывается с вопросом.
"""

from collections.abc import Callable
from dataclasses import replace

import pytest
from aiogram import Dispatcher
from aiogram.types import InlineKeyboardMarkup
from dishka import AsyncContainer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from muallim.application.ports.repositories import LearnerRepository
from muallim.domain import quiz
from muallim.domain.curriculum import Curriculum
from muallim.domain.quiz import QuizAnswer as QuizRow
from muallim.infrastructure.db.repositories.quiz import SqlQuizAnswerRepository
from muallim.infrastructure.db.tables import quiz_answers
from muallim.presentation.telegram import texts
from muallim.presentation.telegram.callbacks import Consent, GoItem, Quiz, QuizAnswer, QuizSkip
from tests.integration import test_bot_flow as flow
from tests.integration.test_bot_flow import Learner

pytestmark = pytest.mark.integration

# окружение бота и ученик — те же фикстуры, что в сквозном пути (SQLite, DI, заглушка модели)
bot_app = flow.bot_app
learner_factory = flow.learner_factory


async def _ready(make: Callable[[int], Learner], curriculum: Curriculum, tg: int) -> Learner:
    """Ученик без согласия прочитал по строке в двух уроках букв — закрепление открыто."""
    ali = make(tg)
    await ali.write("/start")
    await ali.press(Consent(granted=False))
    for lesson in ("L004", "L005"):
        practice = next(i for i in curriculum.lessons if i.id == lesson).practice_items[0]
        await ali.press(GoItem(item_id=practice.id))
        await ali.voice()
    return ali


async def _open_row(container: AsyncContainer, tg: int) -> QuizRow:
    async with container() as request:
        learner = await (await request.get(LearnerRepository)).get_by_telegram_id(tg)
        assert learner is not None
        rows = await SqlQuizAnswerRepository(await request.get(AsyncSession)).history(learner.id)
        return next(r for r in reversed(rows) if r.answered_at is None)


def _answer_buttons(ali: Learner) -> list[str]:
    markup = ali.last_screen().reply_markup
    assert markup is not None
    prefix = QuizAnswer.__prefix__ + ":"
    return [
        str(b.callback_data)
        for row in markup.inline_keyboard
        for b in row
        if b.callback_data and b.callback_data.startswith(prefix)
    ]


def _header(position: int, correct: int) -> str:
    return texts.QUIZ_HEADER.format(position=position, total=quiz.QUIZ_ROUND, correct=correct)


async def test_correct_answer_goes_straight_to_next_question(
    bot_app: tuple[Dispatcher, AsyncContainer],
    learner_factory: Callable[[int], Learner],
    curriculum: Curriculum,
) -> None:
    _, container = bot_app
    ali = await _ready(learner_factory, curriculum, 7101)
    await ali.press(Quiz())
    assert _header(1, 0) in ali.tg.texts()[-1]
    row = await _open_row(container, 7101)
    await ali.press(_answer_buttons(ali)[row.answer])
    assert texts.QUIZ_TOAST_RIGHT in ali.tg.alerts()
    assert _header(2, 1) in ali.tg.texts()[-1]
    assert _answer_buttons(ali) or texts.QUIZ_READ_ASK in ali.tg.texts()[-1]


async def test_wrong_answer_shows_right_one_and_next_button(
    bot_app: tuple[Dispatcher, AsyncContainer],
    learner_factory: Callable[[int], Learner],
    curriculum: Curriculum,
) -> None:
    _, container = bot_app
    ali = await _ready(learner_factory, curriculum, 7102)
    await ali.press(Quiz())
    row = await _open_row(container, 7102)
    await ali.press(_answer_buttons(ali)[(row.answer + 1) % 4])
    assert texts.QUIZ_TOAST_WRONG in ali.tg.alerts()
    assert row.options[row.answer] in ali.tg.texts()[-1]
    markup = ali.last_screen().reply_markup
    assert markup is not None
    assert Quiz().pack() in [b.callback_data for row in markup.inline_keyboard for b in row]
    async with container() as request:
        saved = await SqlQuizAnswerRepository(await request.get(AsyncSession)).get(row.id)
    assert saved is not None and saved.correct is False


async def test_pressing_the_same_answer_twice_is_stale(
    bot_app: tuple[Dispatcher, AsyncContainer],
    learner_factory: Callable[[int], Learner],
    curriculum: Curriculum,
) -> None:
    _, container = bot_app
    ali = await _ready(learner_factory, curriculum, 7103)
    await ali.press(Quiz())
    row = await _open_row(container, 7103)
    button = _answer_buttons(ali)[row.answer]
    await ali.press(button)
    await ali.press(button)
    assert texts.QUIZ_STALE in ali.tg.alerts()


async def test_old_format_answer_button_is_stale(
    bot_app: tuple[Dispatcher, AsyncContainer],
    learner_factory: Callable[[int], Learner],
    curriculum: Curriculum,
) -> None:
    """Кнопка из сообщения до ADR-0066 (``qa:<карточка>:<огласовка>:<seed>:<вариант>``)."""
    ali = await _ready(learner_factory, curriculum, 7104)
    await ali.press("qa:L004-05:0:5:1")
    assert texts.STALE_BUTTON in ali.tg.alerts()


async def test_reopening_quiz_shows_the_same_unanswered_question(
    bot_app: tuple[Dispatcher, AsyncContainer],
    learner_factory: Callable[[int], Learner],
    curriculum: Curriculum,
) -> None:
    _, container = bot_app
    ali = await _ready(learner_factory, curriculum, 7105)
    await ali.press(Quiz())
    first = await _open_row(container, 7105)
    await ali.write("/start")
    await ali.press(Quiz())
    assert (await _open_row(container, 7105)).id == first.id
    async with container() as request:
        session = await request.get(AsyncSession)
        n = len((await session.execute(select(quiz_answers.c.id))).all())
    assert n == 1


async def test_read_step_voice_is_assessed_and_linked(
    bot_app: tuple[Dispatcher, AsyncContainer],
    learner_factory: Callable[[int], Learner],
    curriculum: Curriculum,
) -> None:
    """Ступень ③: открытый вопрос «прочитай строку буквы» — голосовое идёт в попытки, вопрос
    получает ``attempt_id`` и ответ, под разбором — «▶️ Дальше по закреплению»."""
    _, container = bot_app
    ali = await _ready(learner_factory, curriculum, 7106)
    await ali.press(Quiz())
    row = await _open_row(container, 7106)
    async with container() as request:
        session = await request.get(AsyncSession)
        await session.execute(quiz_answers.delete().where(quiz_answers.c.id == row.id))
        await SqlQuizAnswerRepository(session).add(
            replace(row, step=3, item_id=row.letter_id, options=(), answer=-1)
        )
        await session.commit()
    await ali.press(Quiz())  # тот же открытый вопрос — теперь ступень ③
    assert texts.QUIZ_READ_ASK in ali.tg.texts()[-1]
    await ali.voice()
    async with container() as request:
        saved = await SqlQuizAnswerRepository(await request.get(AsyncSession)).get(row.id)
    assert saved is not None and saved.attempt_id is not None and saved.correct is True
    assert (texts.QUIZ_READ_NEXT, Quiz().pack()) in [
        (b.text, b.callback_data)
        for r in (ali.last_screen().reply_markup or _empty()).inline_keyboard
        for b in r
    ]


def _empty() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[])


async def test_cant_speak_now_moves_on_without_voice(
    bot_app: tuple[Dispatcher, AsyncContainer],
    learner_factory: Callable[[int], Learner],
    curriculum: Curriculum,
) -> None:
    """Ступень ③ без голоса: «🎙 Не могу сейчас говорить» — следующий вопрос, не ③, не ошибка."""
    _, container = bot_app
    ali = await _ready(learner_factory, curriculum, 7107)
    await ali.press(Quiz())
    row = await _open_row(container, 7107)
    async with container() as request:
        session = await request.get(AsyncSession)
        await session.execute(quiz_answers.delete().where(quiz_answers.c.id == row.id))
        await SqlQuizAnswerRepository(session).add(
            replace(row, step=3, item_id=row.letter_id, options=(), answer=-1)
        )
        await session.commit()
    await ali.press(Quiz())
    assert texts.QUIZ_CANT_SPEAK in [
        b.text for r in (ali.last_screen().reply_markup or _empty()).inline_keyboard for b in r
    ]
    await ali.press(QuizSkip(a=row.id.hex))
    assert _header(2, 0) in ali.tg.texts()[-1]
    assert texts.QUIZ_READ_ASK not in ali.tg.texts()[-1]
    async with container() as request:
        saved = await SqlQuizAnswerRepository(await request.get(AsyncSession)).get(row.id)
    assert saved is not None and saved.answered_at is not None and saved.correct is None
    await ali.press(QuizSkip(a=row.id.hex))  # второе нажатие — устарела
    assert texts.QUIZ_STALE in ali.tg.alerts()
