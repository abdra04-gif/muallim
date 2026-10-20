"""Согласие, анкета, «Мои данные» и удаление (FR-09, FR-10, FR-44)."""

from typing import Final

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from dishka import FromDishka

from muallim.application.use_cases.learners import DeleteMyData, Questionnaire, SetResearchConsent
from muallim.application.use_cases.progress import GetProgress
from muallim.domain.curriculum import Curriculum
from muallim.domain.learner import ArabicReading, Learner, NativeLanguage
from muallim.presentation.telegram import keyboards, on_screen, screens, texts
from muallim.presentation.telegram.callbacks import Consent, DeleteData, Privacy, Profile
from muallim.presentation.telegram.display import Display, message_of
from muallim.presentation.telegram.handlers.commands import PROFILE_START
from muallim.presentation.telegram.screens import Screen

router: Final = Router(name="learner.data")


@router.callback_query(Privacy.filter())
async def cb_privacy(
    cb: CallbackQuery, state: FSMContext, display: FromDishka[Display], learner: FromDishka[Learner]
) -> None:
    await on_screen.menu(state)  # не карточка: голосовое здесь не оценивается
    if msg := message_of(cb):
        await display.show(msg, screens.privacy(learner.research_consent))
    await cb.answer()


@router.callback_query(Consent.filter())
async def cb_consent(
    cb: CallbackQuery,
    state: FSMContext,
    callback_data: Consent,
    display: FromDishka[Display],
    learner: FromDishka[Learner],
    uc: FromDishka[SetResearchConsent],
    cur: FromDishka[Curriculum],
    progress: FromDishka[GetProgress],
    questionnaire: FromDishka[Questionnaire],
) -> None:
    await on_screen.menu(state)  # не карточка: голосовое здесь не оценивается
    await uc.execute(learner, callback_data.granted)
    await cb.answer(texts.CONSENT_SAVED_YES if callback_data.granted else texts.CONSENT_SAVED_NO)
    if msg := message_of(cb):
        if await questionnaire.needed(learner):  # анкета — один раз, сразу после согласия (FR-44)
            screen = PROFILE_START
        elif callback_data.then == "privacy":
            screen = screens.privacy(learner.research_consent)
        else:
            screen = screens.home(cur, await progress.execute(learner))
        await display.show(msg, screen)


@router.callback_query(Profile.filter())
async def cb_profile(
    cb: CallbackQuery,
    state: FSMContext,
    callback_data: Profile,
    display: FromDishka[Display],
    learner: FromDishka[Learner],
    questionnaire: FromDishka[Questionnaire],
    cur: FromDishka[Curriculum],
    progress: FromDishka[GetProgress],
) -> None:
    """Анкета по шагам: 18+ → родной язык → опыт чтения; ответы копятся в кнопке (FR-44)."""
    await on_screen.menu(state)  # не карточка: голосовое здесь не оценивается
    msg = message_of(cb)
    if callback_data.adult and not callback_data.lang:
        await cb.answer()
        if msg:
            await display.show(msg, Screen(texts.PROFILE_LANGUAGE, keyboards.profile_language()))
        return
    if callback_data.adult and not callback_data.read:
        await cb.answer()
        if msg:
            await display.show(
                msg, Screen(texts.PROFILE_READING, keyboards.profile_reading(callback_data.lang))
            )
        return
    if callback_data.adult:
        try:
            native = NativeLanguage(callback_data.lang)
            reading = ArabicReading(callback_data.read)
        except ValueError:  # кнопка от старой версии анкеты
            await cb.answer(texts.STALE_BUTTON)
            return
        saved = await questionnaire.answer(learner, adult=True, native=native, reading=reading)
        await cb.answer(texts.PROFILE_THANKS if saved else None)
    else:
        saved = await questionnaire.answer(learner, adult=False)
        await cb.answer(texts.PROFILE_MINOR if saved else None)
    if msg:
        await display.show(msg, screens.home(cur, await progress.execute(learner)))


@router.callback_query(DeleteData.filter(F.confirmed.is_(False)))
async def cb_delete_ask(cb: CallbackQuery, state: FSMContext, display: FromDishka[Display]) -> None:
    await on_screen.menu(state)  # не карточка: голосовое здесь не оценивается
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
    await state.clear()  # начало занятия, экран, ожидание эталона — всё забыто
    if msg := message_of(cb):
        await msg.edit_text(texts.DELETE_DONE)
    await cb.answer()
