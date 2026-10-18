"""Перехват сбоев (ADR-0048): отдельный роутер, ловит ошибки и ученика, и разметчика.

aiogram передаёт событие ошибки через всё дерево роутеров диспетчера, поэтому соседний роутер
ловит сбой в любом другом. Подключается в ``bootstrap/main.py::routers()``.
"""

import logging
from contextlib import suppress
from typing import Final

from aiogram import Bot, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import ErrorEvent

from muallim.presentation.telegram import texts

logger: Final = logging.getLogger(__name__)
router: Final = Router(name="errors")


@router.errors()
async def on_error(event: ErrorEvent, bot: Bot) -> bool:
    """В лог — с traceback, ученику — короткое сообщение вместо молчания.

    В лог — только номер и тип апдейта (ADR-0027): без текста сообщения и Telegram ID.
    """
    update = event.update
    logger.error(
        "Сбой обработки апдейта %s (%s)",
        update.update_id,
        update.event_type,
        exc_info=event.exception,
    )
    query = update.callback_query
    where = update.message or (query.message if query else None)
    if where is not None:
        with suppress(TelegramAPIError):
            await bot.send_message(where.chat.id, texts.SOMETHING_WENT_WRONG)
    return True
