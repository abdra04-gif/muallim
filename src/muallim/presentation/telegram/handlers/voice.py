"""Голосовое ученика → проверка чтения → результат; любое другое сообщение — подсказка.

Подключается последним (``handlers/__init__.py``): ``fallback`` ловит всё, что не поймали другие.
"""

import io
import logging
from typing import Final

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from dishka import FromDishka

from muallim.application.ports.recognition import RecognitionError
from muallim.application.ports.storage import ReferenceAudioLibrary
from muallim.application.use_cases.cards import OpenItem
from muallim.application.use_cases.progress import GetProgress
from muallim.application.use_cases.recitation import AssessRecitation
from muallim.application.use_cases.reference import RecordReference
from muallim.domain.curriculum import Curriculum
from muallim.domain.learner import Learner
from muallim.domain.policy import Verdict
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
) -> None:
    assert m.voice is not None  # гарантирует фильтр F.voice  # noqa: S101
    if m.voice.duration < 1:
        await m.reply(texts.VOICE_TOO_SHORT)
        return
    buf = io.BytesIO()
    await bot.download(m.voice, destination=buf)

    item_id = await take_recording(state)
    if item_id is not None and await recorder.execute(learner, item_id, buf.getvalue()):
        logger.info("Эталон для %s записал учитель %s", item_id, learner.pseudonym)
        await m.reply(texts.RECORD_SAVED.format(item=item_id))
        return

    item = cards.current(learner)
    if not item.is_practice:
        await m.reply(texts.NOT_PRACTICE)
        return
    wait = await m.reply(texts.LISTENING.format(item=item.text))
    try:
        result = await uc.execute(learner, buf.getvalue())
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
    if result.item.id == opening.OPENING_ITEMS[-1] and attempt.verdict is not Verdict.FAILED:
        resume_id = await opening.finish(state)  # басмала прочитана — вернуть, где остановился
        resume = cur.item(resume_id) if resume_id else None
    await wait.delete()
    screen = screens.result(cur, result, library.has(result.item.id), resume)
    await display.send(bot, m.chat.id, screen)


@router.message()
async def fallback(
    m: Message,
    bot: Bot,
    display: FromDishka[Display],
    learner: FromDishka[Learner],
    cur: FromDishka[Curriculum],
    progress: FromDishka[GetProgress],
) -> None:
    await m.answer(texts.SEND_VOICE)
    await display.send(bot, m.chat.id, screens.home(cur, await progress.execute(learner)))
