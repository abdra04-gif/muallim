"""Голосовое ученика → проверка чтения → результат; любое другое сообщение — подсказка.

Подключается последним (``handlers/__init__.py``): ``fallback`` ловит всё, что не поймали другие.
"""

import io
import logging
from contextlib import suppress
from typing import Final

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from dishka import FromDishka

from muallim.application.ports.recognition import RecognitionError
from muallim.application.ports.storage import ReferenceAudioLibrary
from muallim.application.use_cases.cards import OpenItem
from muallim.application.use_cases.progress import GetProgress
from muallim.application.use_cases.quiz import PracticeQuiz
from muallim.application.use_cases.recitation import AssessRecitation
from muallim.application.use_cases.reference import RecordReference
from muallim.application.use_cases.screen import ScreenState
from muallim.application.use_cases.settings import GetSettings
from muallim.application.use_cases.staff import StaffAccess
from muallim.domain.curriculum import Curriculum, ItemKind
from muallim.domain.learner import Learner
from muallim.domain.policy import Verdict
from muallim.domain.quiz import read_passed
from muallim.presentation.telegram import opening, screens, texts
from muallim.presentation.telegram.display import Display
from muallim.presentation.telegram.handlers.reference import take_recording

logger: Final = logging.getLogger(__name__)
router: Final = Router(name="learner.voice")


@router.message(F.voice)
async def on_voice(
    m: Message,
    bot: Bot,
    state: FSMContext,
    display: FromDishka[Display],
    learner: FromDishka[Learner],
    uc: FromDishka[AssessRecitation],
    cards: FromDishka[OpenItem],
    library: FromDishka[ReferenceAudioLibrary],
    recorder: FromDishka[RecordReference],
    cur: FromDishka[Curriculum],
    staff_access: FromDishka[StaffAccess],
    progress: FromDishka[GetProgress],
    screen_state: FromDishka[ScreenState],
    learner_settings: FromDishka[GetSettings],
    quiz: FromDishka[PracticeQuiz],
) -> None:
    assert m.voice is not None  # гарантирует фильтр F.voice  # noqa: S101
    if m.voice.duration < 1:
        await m.reply(texts.VOICE_TOO_SHORT)
        return
    buf = io.BytesIO()
    item_id = await take_recording(state)
    if item_id is not None:  # эталон учителя — с любого экрана
        await bot.download(m.voice, destination=buf)
        if await recorder.execute(learner, item_id, buf.getvalue()):
            logger.info("Эталон для %s записал учитель %s", item_id, learner.pseudonym)
            await m.reply(texts.RECORD_SAVED.format(item=item_id))
            return

    shown = await screen_state.execute(learner)
    if shown.item_id is None or shown.stale:
        # на экране меню (или вчерашнее начало занятия) — урок не открыт: не оцениваем,
        # предлагаем открыть (решение автора)
        if shown.stale:
            await screen_state.menu(learner, finish=True)
        screen = screens.voice_on_home(cur, await progress.execute(learner))
        await m.answer(screen.caption, reply_markup=screen.keyboard)
        return
    item = cards.current(learner)
    with suppress(KeyError):  # карточку убрали из программы — карточка курсора
        item = cur.item(shown.item_id)
    if item.kind is ItemKind.RULE:  # правило читают глазами, дальше — чтение (FR-49)
        await m.reply(texts.VOICE_ON_RULE)
        return
    if not item.is_practice:  # таблица алфавита — только посмотреть
        await m.reply(texts.NOT_PRACTICE)
        return
    if not buf.getbuffer().nbytes:  # скачиваем только то, что будем оценивать (TD-FN-90)
        await bot.download(m.voice, destination=buf)
    wait = await m.reply(texts.LISTENING.format(item=item.text))
    try:
        result = await uc.execute(learner, buf.getvalue(), item.id)
    except RecognitionError as error:
        logger.warning(
            "Не удалось распознать запись ученика %s, карточка %s, этап %s",
            learner.pseudonym,
            item.id,
            error.stage,
            exc_info=True,
        )
        await wait.edit_text(texts.CANT_PROCESS)
        return
    attempt = result.attempt
    logger.info(
        "Попытка %s: ученик %s, карточка %s, вердикт %s, балл %s, %s мс",
        attempt.id,
        learner.pseudonym,
        attempt.item_id,
        attempt.verdict,
        attempt.assessment.score,
        attempt.processing_ms,
    )
    resume = None
    basmala = result.item.id == opening.OPENING_ITEMS[-1]
    if shown.opening_active and basmala and attempt.verdict is not Verdict.FAILED:
        with suppress(KeyError):  # басмала прочитана — вернуть, где был
            resume = cur.item(shown.resume_item) if shown.resume_item else None
    # «Для исследования» и номер попытки — учителю и разметчику (FR-50) и ученику, который
    # включил их в ⚙️ Настройках (ADR-0061)
    staff = (await learner_settings.execute(learner)).research_block or (
        await staff_access.is_staff(learner)
    )
    await wait.delete()
    screen = screens.result(cur, result, library.has(result.item.id), resume, staff=staff)
    # ступень ③ закрепления: попытка — ответ на открытый вопрос этой строки (ADR-0066 п. 8)
    passed = read_passed(attempt.verdict)
    linked = await quiz.attach_attempt(learner, result.item.id, attempt.id, passed=passed)
    if linked is not None and not linked.finished:
        screen = screens.with_quiz_next(screen)
    await display.send(bot, m.chat.id, screen)
    if linked is not None and linked.summary is not None:
        await screen_state.menu(learner)
        await display.send(bot, m.chat.id, screens.quiz_summary(cur, linked.summary))


@router.message()
async def fallback(
    m: Message,
    bot: Bot,
    display: FromDishka[Display],
    learner: FromDishka[Learner],
    cur: FromDishka[Curriculum],
    progress: FromDishka[GetProgress],
    screen_state: FromDishka[ScreenState],
) -> None:
    """Текст вместо голосового — одна подсказка; экран с кнопками остаётся выше (FR-50).

    Неизвестная команда (в том числе /annotate постороннего) — главная: это не «текст вместо
    голосового», и ученику нужны кнопки.
    """
    if (m.text or "").startswith("/"):  # неизвестная команда — просто главная с кнопками
        await screen_state.menu(learner)  # на экране меню: голосовое не оценивается (FR-50)
        await display.send(bot, m.chat.id, screens.home(cur, await progress.execute(learner)))
        return
    await m.answer(texts.SEND_VOICE)


@router.callback_query()
async def stale_button(cb: CallbackQuery) -> None:
    """Кнопка, которую не узнал ни один обработчик (старый формат после выкладки), — не молчать."""
    await cb.answer(texts.STALE_BUTTON, show_alert=True)
