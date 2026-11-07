"""Согласие, анкета, «Мои данные» и удаление (FR-09, FR-10, FR-44)."""

from typing import Final

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from dishka import FromDishka

from muallim.application.use_cases.learners import DeleteMyData, Questionnaire, SetResearchConsent
from muallim.application.use_cases.progress import GetProgress
from muallim.application.use_cases.screen import ScreenState
from muallim.domain.curriculum import Curriculum
from muallim.domain.learner import Learner, Question
from muallim.presentation.telegram import keyboards, screens, texts
from muallim.presentation.telegram.callbacks import Consent, DeleteData, Privacy, Profile
from muallim.presentation.telegram.display import Display, drop_sound, message_of
from muallim.presentation.telegram.screens import Screen

router: Final = Router(name="learner.data")


@router.callback_query(Privacy.filter())
async def cb_privacy(
    cb: CallbackQuery,
    display: FromDishka[Display],
    learner: FromDishka[Learner],
    screen_state: FromDishka[ScreenState],
) -> None:
    await screen_state.menu(learner)  # не карточка: голосовое здесь не оценивается
    if msg := message_of(cb):
        await drop_sound(display, msg)  # ушёл с карточки — автоэталон убрать
        await display.show(msg, screens.privacy(learner.research_consent))
    await cb.answer()


@router.callback_query(Consent.filter())
async def cb_consent(
    cb: CallbackQuery,
    screen_state: FromDishka[ScreenState],
    callback_data: Consent,
    display: FromDishka[Display],
    learner: FromDishka[Learner],
    uc: FromDishka[SetResearchConsent],
    cur: FromDishka[Curriculum],
    progress: FromDishka[GetProgress],
    questionnaire: FromDishka[Questionnaire],
) -> None:
    await screen_state.menu(learner)  # не карточка: голосовое здесь не оценивается
    await uc.execute(learner, callback_data.granted)
    await cb.answer(texts.CONSENT_SAVED_YES if callback_data.granted else texts.CONSENT_SAVED_NO)
    if msg := message_of(cb):
        if question := await _next_question(
            questionnaire, learner
        ):  # анкета — сразу после согласия
            screen = screens.profile_question(question, cb.from_user.first_name)
        elif callback_data.then == "privacy":
            screen = screens.privacy(learner.research_consent)
        else:
            screen = screens.home(cur, await progress.execute(learner))
        await display.show(msg, screen)


async def _next_question(questionnaire: Questionnaire, learner: Learner) -> Question | None:
    """Следующий вопрос анкеты; None — анкета не нужна или закончена."""
    return (
        await questionnaire.next_question(learner) if await questionnaire.needed(learner) else None
    )


@router.callback_query(Profile.filter())
async def cb_profile(
    cb: CallbackQuery,
    screen_state: FromDishka[ScreenState],
    callback_data: Profile,
    display: FromDishka[Display],
    learner: FromDishka[Learner],
    questionnaire: FromDishka[Questionnaire],
    cur: FromDishka[Curriculum],
    progress: FromDishka[GetProgress],
) -> None:
    """Анкета по экранам: ответ или «Пропустить» сохраняются сразу, дальше — следующий вопрос."""
    await screen_state.menu(learner)  # не карточка: голосовое здесь не оценивается
    try:
        question = Question(callback_data.q)
    except ValueError:  # кнопка от старой версии анкеты
        await cb.answer(texts.STALE_BUTTON)
        return
    if callback_data.v == "skip":
        await questionnaire.skip(learner, question)
    else:
        value = cb.from_user.first_name if callback_data.v == "tg" else callback_data.v
        await questionnaire.answer(learner, question, value)  # повторное нажатие ничего не меняет
    msg = message_of(cb)
    if following := await _next_question(questionnaire, learner):
        await cb.answer()
        if msg:
            await display.show(msg, screens.profile_question(following, cb.from_user.first_name))
        return
    await cb.answer(texts.PROFILE_THANKS)
    if msg:
        await display.show(msg, screens.home(cur, await progress.execute(learner)))


@router.callback_query(DeleteData.filter(F.confirmed.is_(False)))
async def cb_delete_ask(
    cb: CallbackQuery,
    display: FromDishka[Display],
    learner: FromDishka[Learner],
    screen_state: FromDishka[ScreenState],
) -> None:
    await screen_state.menu(learner)  # не карточка: голосовое здесь не оценивается
    if msg := message_of(cb):
        await display.show(msg, Screen(texts.DELETE_CONFIRM, keyboards.delete_confirm()))
    await cb.answer()


@router.callback_query(DeleteData.filter(F.confirmed.is_(True)))
async def cb_delete(
    cb: CallbackQuery,
    state: FSMContext,
    learner: FromDishka[Learner],
    uc: FromDishka[DeleteMyData],
) -> None:
    await uc.execute(learner)
    await state.clear()  # ожидание эталона забыто; экран и начало занятия удалены каскадом
    if msg := message_of(cb):
        await msg.edit_text(texts.DELETE_DONE)
    await cb.answer()
