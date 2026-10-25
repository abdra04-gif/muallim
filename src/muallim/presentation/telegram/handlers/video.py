"""Ролик «🎬 Как произносить» (FR-56, ADR-0074): кнопка ``Watch`` с карточки алфавита и после
попытки на ней (``breakdown``/``sheet`` — только для старых кнопок, новые не ставятся);
авторолик над карточкой — ``show_card`` (handlers/reference.py).

Просмотр (``video_played``) пишется только после того, как ролик ушёл в Telegram.
"""

import logging
from typing import Final

from aiogram import Bot, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery, Message
from dishka import FromDishka

from muallim.application.ports.storage import Video
from muallim.application.use_cases.settings import GetSettings
from muallim.application.use_cases.video import GetArticulationVideo, RecordVideoPlayed
from muallim.domain.learner import Learner
from muallim.presentation.telegram import texts
from muallim.presentation.telegram.callbacks import Watch
from muallim.presentation.telegram.display import Display, drop_sound, message_of

logger: Final = logging.getLogger(__name__)
router: Final = Router(name="learner.video")

SOURCES: Final = frozenset({"card", "after", "breakdown", "sheet"})  # ``from`` кнопок; auto — сам


async def send_articulation(
    bot: Bot, chat_id: int, display: Display, video: Video
) -> Message | None:
    """Отправить ролик; не ушёл — предупреждение в лог (с ключом ролика) и None."""
    try:
        return await display.send_video(bot, chat_id, video)
    except TelegramAPIError:
        logger.warning("Ролик %s не отправлен", video.key, exc_info=True)
        return None


@router.callback_query(Watch.filter())
async def cb_watch(
    cb: CallbackQuery,
    callback_data: Watch,
    learner: FromDishka[Learner],
    uc: FromDishka[GetArticulationVideo],
    played: FromDishka[RecordVideoPlayed],
    display: FromDishka[Display],
    learner_settings: FromDishka[GetSettings],
) -> None:
    """С автозвуком ролик над карточкой — один, как эталон 🔊 (TD-FN-93 п. 2)."""
    video = await uc.execute(callback_data.v) if callback_data.src in SOURCES else None
    if video is None:  # ролик убран или отклонён (``bad``) после перезапуска
        await cb.answer(texts.STALE_BUTTON, show_alert=True)
        return
    msg = message_of(cb)
    if msg is not None and msg.bot is not None:
        sent = await send_articulation(msg.bot, msg.chat.id, display, video)
        if sent is not None:
            if (await learner_settings.execute(learner)).auto_reference:
                await drop_sound(display, msg)
                display.keep_sound(msg.chat.id, sent.message_id)
            await played.execute(
                learner,
                video.key,
                source=callback_data.src,
                item_id=callback_data.item_id or None,
                letter=callback_data.letter or None,
            )
    await cb.answer()
