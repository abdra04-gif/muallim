"""«📖 Вся сура» и «Наизусть» (FR-57, FR-59, ADR-0076): кнопки и голосовое со всей сурой.

Голосовое уходит в проверку суры, только пока на экране сура: по тексту — сразу, наизусть — после
«Готов», когда текст уже скрыт (Telegram не сообщает боту, что ученик начал запись).
"""

import io
import logging
from typing import Final

from aiogram import Bot, Router
from aiogram.types import CallbackQuery, Message
from dishka import FromDishka

from muallim.application.ports.recognition import RecognitionError
from muallim.application.use_cases.screen import ScreenState
from muallim.application.use_cases.sura import ReadSura
from muallim.domain.learner import Learner
from muallim.domain.sura import SuraMode
from muallim.presentation.telegram import screens, texts
from muallim.presentation.telegram.callbacks import SuraList, SuraOpen, SuraReady
from muallim.presentation.telegram.display import Display, drop_sound, message_of

logger: Final = logging.getLogger(__name__)
router: Final = Router(name="learner.sura")

TEXT, LOOK, MEMORY = "text", "look", "memory"  # что на экране (ScreenState.sura)


@router.callback_query(SuraList.filter())
async def cb_sura_list(
    cb: CallbackQuery,
    screen_state: FromDishka[ScreenState],
    display: FromDishka[Display],
    learner: FromDishka[Learner],
    uc: FromDishka[ReadSura],
) -> None:
    await screen_state.menu(learner)  # список — не сура: голосовое здесь не проверяется
    if msg := message_of(cb):
        await drop_sound(display, msg)
        await display.show(msg, screens.sura_list(uc.curriculum, await uc.memorized(learner)))
    await cb.answer()


@router.callback_query(SuraOpen.filter())
async def cb_sura_open(
    cb: CallbackQuery,
    callback_data: SuraOpen,
    screen_state: FromDishka[ScreenState],
    display: FromDishka[Display],
    learner: FromDishka[Learner],
    uc: FromDishka[ReadSura],
) -> None:
    try:
        sura = uc.sura(callback_data.n)
    except KeyError:
        await cb.answer(texts.STALE_BUTTON, show_alert=True)
        return
    by_text = callback_data.m == "t"
    await screen_state.sura(learner, sura.number, TEXT if by_text else LOOK)
    if msg := message_of(cb):
        await drop_sound(display, msg)
        await display.show(msg, screens.sura_text(sura) if by_text else screens.sura_memory(sura))
    await cb.answer()


@router.callback_query(SuraReady.filter())
async def cb_sura_ready(
    cb: CallbackQuery,
    callback_data: SuraReady,
    screen_state: FromDishka[ScreenState],
    display: FromDishka[Display],
    learner: FromDishka[Learner],
    uc: FromDishka[ReadSura],
) -> None:
    try:
        sura = uc.sura(callback_data.n)
    except KeyError:
        await cb.answer(texts.STALE_BUTTON, show_alert=True)
        return
    await screen_state.sura(learner, sura.number, MEMORY)
    if msg := message_of(cb):  # тот же экран без текста: текст пропадает
        await display.show(msg, screens.sura_memory_ready(sura))
    await cb.answer()


async def read_sura_voice(
    m: Message,
    bot: Bot,
    sura: tuple[int, str],
    *,
    learner: Learner,
    uc: ReadSura,
    display: Display,
) -> None:
    """Голосовое на экране суры (вызывает обработчик голосовых)."""
    number, mode = sura
    if mode == LOOK:  # текст ещё на экране — это не чтение наизусть
        await m.reply(texts.SURA_PRESS_READY)
        return
    assert m.voice is not None  # noqa: S101 — вызывается из обработчика F.voice
    buf = io.BytesIO()
    await bot.download(m.voice, destination=buf)
    wait = await m.reply(texts.SURA_LISTENING)
    try:
        result = await uc.execute(
            learner, buf.getvalue(), number, SuraMode.TEXT if mode == TEXT else SuraMode.MEMORY
        )
    except RecognitionError as error:
        logger.warning(
            "Не удалось распознать суру %s ученика %s, этап %s",
            number,
            learner.pseudonym,
            error.stage,
            exc_info=True,
        )
        await wait.edit_text(texts.CANT_PROCESS)
        return
    except KeyError:  # суру убрали из программы
        await wait.edit_text(texts.STALE_BUTTON)
        return
    reading = result.reading
    logger.info(
        "Сура %s (%s): ученик %s, чисто %s из %s, %s мс",
        number,
        reading.mode,
        learner.pseudonym,
        reading.assessment.clean_count,
        len(reading.assessment.ayahs),
        reading.processing_ms,
    )
    await wait.delete()
    await display.send(bot, m.chat.id, screens.sura_result(result))
