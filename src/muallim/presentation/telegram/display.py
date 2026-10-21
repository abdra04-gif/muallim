"""Показ экранов в одном сообщении (ADR-0024): кнопки меняют экран на месте, чат не растёт.

Новое сообщение — только для /команд и результата голосового; у предыдущего экрана кнопки
убираются, чтобы не путаться. Память ``Display`` — кэш file_id картинок и номер текущего экрана
чата; один объект на контейнер DI (bootstrap/di.py), поэтому два бота не мешают друг другу.
Сбрасывается при перезапуске — это не данные исследования.
"""

import logging
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Final

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InaccessibleMessage,
    InputMediaPhoto,
    Message,
)

from muallim.presentation.telegram.screens import Screen

logger: Final = logging.getLogger(__name__)


def message_of(cb: CallbackQuery) -> Message | None:
    msg = cb.message
    return None if msg is None or isinstance(msg, InaccessibleMessage) else msg


async def drop_sound(display: "Display", msg: Message) -> None:
    """Ученик ушёл с карточки в меню: автоэталон над ней больше не нужен (TD-FN-93 п. 1)."""
    if msg.bot is not None:
        await display.drop_sound(msg.bot, msg.chat.id)


@dataclass
class Display:
    file_ids: dict[str, str] = field(default_factory=dict)  # ключ картинки → Telegram file_id
    last_screen: dict[int, int] = field(default_factory=dict)  # чат → сообщение текущего экрана
    # чат → автоголосовое эталона над карточкой (ADR-0061); после перезапуска забывается — и
    # старое голосовое просто остаётся в чате
    sounds: dict[int, int] = field(default_factory=dict)

    def keep_sound(self, chat_id: int, message_id: int) -> None:
        self.sounds[chat_id] = message_id

    async def drop_sound(self, bot: Bot, chat_id: int) -> None:
        """Убрать прошлое автоголосовое: ученик ушёл с карточки, над которой оно было."""
        old = self.sounds.pop(chat_id, None)
        if old is not None:
            with suppress(TelegramBadRequest):
                await bot.delete_message(chat_id, old)

    def _photo(self, screen: Screen) -> str | BufferedInputFile:
        assert screen.image is not None  # noqa: S101
        cached = self.file_ids.get(screen.image_key) if screen.image_key else None
        return cached or BufferedInputFile(screen.image, filename="screen.png")

    def _remember(self, screen: Screen, msg: Message) -> None:
        if screen.image_key and msg.photo:
            self.file_ids[screen.image_key] = msg.photo[-1].file_id

    async def _retire(self, bot: Bot, chat_id: int, new_id: int) -> None:
        old = self.last_screen.get(chat_id)
        self.last_screen[chat_id] = new_id
        if old and old != new_id:
            with suppress(TelegramBadRequest):  # сообщение удалено или уже без кнопок
                await bot.edit_message_reply_markup(
                    chat_id=chat_id, message_id=old, reply_markup=None
                )

    async def send(self, bot: Bot, chat_id: int, screen: Screen) -> Message:
        """Экран — одним сообщением; с ``details`` — двумя, кнопки у второго (оно и есть экран)."""
        keyboard = None if screen.details else screen.keyboard
        if screen.image is not None:
            msg = await bot.send_photo(
                chat_id, self._photo(screen), caption=screen.caption, reply_markup=keyboard
            )
            self._remember(screen, msg)
        else:
            msg = await bot.send_message(chat_id, screen.caption, reply_markup=keyboard)
        if screen.details:
            msg = await bot.send_message(chat_id, screen.details, reply_markup=screen.keyboard)
        await self._retire(bot, chat_id, msg.message_id)
        return msg

    async def show(self, msg: Message, screen: Screen) -> None:
        """Заменить экран в том же сообщении; если тип не совпадает — новое вместо старого."""
        bot = msg.bot
        assert bot is not None  # noqa: S101
        if screen.details:  # экран из двух сообщений на месте одного не показать
            with suppress(TelegramBadRequest):
                await msg.delete()
            await self.send(bot, msg.chat.id, screen)
            return
        try:
            if screen.image is not None and msg.photo:
                media = InputMediaPhoto(
                    media=self._photo(screen), caption=screen.caption, parse_mode="HTML"
                )
                edited = await msg.edit_media(media, reply_markup=screen.keyboard)
                if isinstance(edited, Message):
                    self._remember(screen, edited)
                self.last_screen[msg.chat.id] = msg.message_id
                return
            if screen.image is None and msg.text:
                await msg.edit_text(screen.caption, reply_markup=screen.keyboard)
                self.last_screen[msg.chat.id] = msg.message_id
                return
        except TelegramBadRequest as error:
            if "not modified" in str(error):
                return
            logger.info("Экран не изменить на месте (%s) — отправляю заново", error)
        with suppress(TelegramBadRequest):
            await msg.delete()
        await self.send(bot, msg.chat.id, screen)
