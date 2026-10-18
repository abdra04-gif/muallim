"""Точка входа: ``uv run muallim``."""

import asyncio
import logging
import sys
from contextlib import suppress

from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand
from dishka.integrations.aiogram import setup_dishka

from muallim.application.ports.recognition import PronunciationRecognizer
from muallim.application.use_cases.curriculum import PublishCurriculum
from muallim.bootstrap.config import Settings
from muallim.bootstrap.di import create_container
from muallim.bootstrap.logs import configure_logging
from muallim.presentation.telegram import texts
from muallim.presentation.telegram.annotation import router as annotator_router
from muallim.presentation.telegram.handlers import router

COMMANDS = [
    BotCommand(command="start", description="Начать"),
    BotCommand(command="lessons", description="Уроки"),
    BotCommand(command="quiz", description="Закрепление букв"),
    BotCommand(command="signs", description="Знаки над и под буквами"),
    BotCommand(command="help", description="Как заниматься"),
    BotCommand(command="progress", description="Мой прогресс"),
    BotCommand(command="privacy", description="Мои данные и согласие"),
    BotCommand(command="me", description="Мой ID"),
]


def routers() -> tuple[Router, ...]:
    """Порядок важен: разметчик раньше ученика — у ученика последний обработчик ловит всё."""
    return annotator_router, router


async def main() -> None:
    settings = Settings()  # поля читаются из окружения и .env
    secrets = (settings.bot_token.get_secret_value(), settings.database_url.get_secret_value())
    configure_logging(settings.log_level, secrets)
    container = create_container(settings)
    await container.get(PronunciationRecognizer)  # загрузить модель до приёма сообщений
    async with container() as request:  # снимок программы в БД: страница и строка у каждой попытки
        added = await (await request.get(PublishCurriculum)).execute()
    logging.getLogger(__name__).info("Программа в БД: новых карточек %s", added)

    bot = Bot(
        settings.bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    await bot.set_my_commands(COMMANDS)
    await bot.set_my_description(texts.BOT_DESCRIPTION)
    await bot.set_my_short_description(texts.BOT_SHORT_DESCRIPTION)

    dp = Dispatcher()
    dp.include_routers(*routers())
    setup_dishka(container=container, router=dp, auto_inject=True)
    try:
        await dp.start_polling(bot)
    finally:
        await container.close()
        await bot.session.close()


def run() -> None:
    if sys.argv[1:2] == ["--test"]:  # проверка из терминала, без Telegram и .env (TD-FN-61)
        from muallim.bootstrap import console  # noqa: PLC0415 — console импортирует этот модуль

        print(asyncio.run(console.run_console(sys.argv[2:] or ["/start"])))  # noqa: T201
        return
    with suppress(KeyboardInterrupt):
        asyncio.run(main())
