"""«🧠 Закрепление» (FR-53, ADR-0066): вопрос, ответ кнопкой, итог раунда."""

from typing import Final
from uuid import UUID

from aiogram import Router
from aiogram.types import CallbackQuery
from dishka import FromDishka

from muallim.application.use_cases.progress import GetProgress
from muallim.application.use_cases.quiz import PracticeQuiz, QuizStale
from muallim.application.use_cases.screen import ScreenState
from muallim.domain.curriculum import Curriculum
from muallim.domain.learner import Learner
from muallim.domain.quiz import Step
from muallim.presentation.telegram import screens, texts
from muallim.presentation.telegram.callbacks import Quiz, QuizAnswer, QuizSkip
from muallim.presentation.telegram.display import Display, drop_sound, message_of
from muallim.presentation.telegram.screens import Screen

router: Final = Router(name="learner.quiz")


async def quiz_screen(
    uc: PracticeQuiz,
    learner: Learner,
    screen_state: ScreenState,
    cur: Curriculum,
    progress: GetProgress,
) -> Screen:
    """Открытый или следующий вопрос закрепления; на ступени ③ на экране — строка буквы, и
    голосовое оценивается по ней (ADR-0066 п. 8)."""
    view = await uc.current(learner)
    if view is None:
        await screen_state.menu(learner)
        if rest := await uc.rest(learner):  # буквы отдыхают до срока — «на сегодня всё»
            return screens.quiz_rest(rest)
        return screens.quiz_unavailable(cur, await progress.execute(learner))
    if view.question.step == Step.READ:
        await screen_state.card(learner, view.question.item_id)
    else:
        await screen_state.menu(learner)  # не карточка: голосовое здесь не оценивается
    return screens.quiz(view)


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
    screen = await quiz_screen(uc, learner, screen_state, cur, progress)
    if msg := message_of(cb):
        await drop_sound(display, msg)  # ушёл с карточки — автоэталон убрать
        await display.show(msg, screen)
    await cb.answer()


@router.callback_query(QuizAnswer.filter())
async def cb_quiz_answer(
    cb: CallbackQuery,
    screen_state: FromDishka[ScreenState],
    callback_data: QuizAnswer,
    display: FromDishka[Display],
    learner: FromDishka[Learner],
    uc: FromDishka[PracticeQuiz],
    cur: FromDishka[Curriculum],
    progress: FromDishka[GetProgress],
) -> None:
    """Верно — сразу следующий вопрос; неверно — разбор и «▶️ Дальше»; 10-й — итог раунда."""
    try:
        result = await uc.answer(learner, UUID(hex=callback_data.a), callback_data.p)
    except (ValueError, QuizStale):
        await cb.answer(texts.QUIZ_STALE, show_alert=True)
        return
    msg = message_of(cb)
    if msg:
        await drop_sound(display, msg)  # звук слога ступени ② — не над следующим вопросом
    if result.finished and result.summary is not None:
        await screen_state.menu(learner)
        summary = screens.quiz_summary(cur, result.summary)
        if msg and not result.correct:  # сначала верный ответ, потом итог (ADR-0066 п. 1)
            await display.show(msg, screens.quiz_answer(result))
            await display.send(msg.bot, msg.chat.id, summary)  # type: ignore[arg-type]
        elif msg:
            await display.show(msg, summary)
    elif msg:
        correct = result.correct
        screen = (
            await quiz_screen(uc, learner, screen_state, cur, progress)
            if correct
            else screens.quiz_answer(result)
        )
        await display.show(msg, screen)
    await cb.answer(texts.QUIZ_TOAST_RIGHT if result.correct else texts.QUIZ_TOAST_WRONG)


@router.callback_query(QuizSkip.filter())
async def cb_quiz_skip(
    cb: CallbackQuery,
    screen_state: FromDishka[ScreenState],
    callback_data: QuizSkip,
    display: FromDishka[Display],
    learner: FromDishka[Learner],
    uc: FromDishka[PracticeQuiz],
    cur: FromDishka[Curriculum],
    progress: FromDishka[GetProgress],
) -> None:
    """«Не могу сейчас слушать / говорить» — без ошибки, сразу следующий вопрос."""
    try:
        await uc.skip(learner, UUID(hex=callback_data.a))
    except (ValueError, QuizStale):
        await cb.answer(texts.QUIZ_STALE, show_alert=True)
        return
    screen = await quiz_screen(uc, learner, screen_state, cur, progress)
    if msg := message_of(cb):
        await drop_sound(display, msg)
        await display.show(msg, screen)
    await cb.answer()
