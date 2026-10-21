"""Точка входа: ``uv run muallim``."""

import asyncio
import logging
import sys
from collections.abc import Callable, Coroutine, Iterable
from contextlib import suppress
from typing import Any

from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand
from dishka import AsyncContainer
from dishka.integrations.aiogram import setup_dishka

from muallim.application.ports.recognition import PronunciationRecognizer
from muallim.application.ports.system import BuildInfo
from muallim.application.use_cases.curriculum import PublishCurriculum
from muallim.bootstrap.config import Settings
from muallim.bootstrap.di import create_container
from muallim.bootstrap.logs import configure_logging
from muallim.domain.curriculum import Curriculum
from muallim.presentation.telegram import reminders, texts
from muallim.presentation.telegram.annotation import router as annotator_router
from muallim.presentation.telegram.errors import router as errors_router
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
    """Порядок важен: разметчик раньше ученика — у ученика последний обработчик ловит всё.

    Перехватчик сбоев — отдельный роутер: событие ошибки проходит всё дерево (ADR-0048).
    """
    return annotator_router, router, errors_router


BackgroundJob = Callable[[Bot, AsyncContainer], Coroutine[Any, Any, None]]


def background_jobs() -> tuple[BackgroundJob, ...]:
    """Задачи рядом с polling (ADR-0061 п. 4); ``muallim --test`` их не запускает."""
    return (reminders.run_reminders,)


def start_background(
    bot: Bot, container: AsyncContainer, jobs: Iterable[BackgroundJob]
) -> list[asyncio.Task[None]]:
    """Запустить задачи рядом с polling; упавшая (не отменённая) задача — ERROR в лог."""
    tasks = []
    for job in jobs:
        task = asyncio.create_task(job(bot, container), name=getattr(job, "__name__", "job"))
        task.add_done_callback(_log_crash)
        tasks.append(task)
    return tasks


def _log_crash(task: asyncio.Task[None]) -> None:
    if task.cancelled() or (error := task.exception()) is None:
        return
    logging.getLogger(__name__).error("Фоновая задача %s упала", task.get_name(), exc_info=error)


async def main() -> None:
    settings = Settings()  # поля читаются из окружения и .env
    secrets = (settings.bot_token.get_secret_value(), settings.database_url.get_secret_value())
    configure_logging(settings.log_level, secrets, file=settings.log_file)
    log = logging.getLogger(__name__)
    container = create_container(settings)
    recognizer = await container.get(PronunciationRecognizer)  # загрузить модель до сообщений
    log.info(
        "Запуск: версия %s, программа %s, распознавание %s (%s)",
        (await container.get(BuildInfo)).version,
        (await container.get(Curriculum)).version,
        settings.asr_backend,
        type(recognizer).__name__,
    )
    async with container() as request:  # снимок программы в БД: страница и строка у каждой попытки
        added = await (await request.get(PublishCurriculum)).execute()
    log.info("Программа в БД: новых карточек %s", added)

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
    jobs = start_background(bot, container, background_jobs())
    try:
        await dp.start_polling(bot)
    finally:
        log.info("Остановка бота")
        for task in jobs:
            task.cancel()
        await asyncio.gather(*jobs, return_exceptions=True)
        await container.close()
        await bot.session.close()


def run() -> None:
    if sys.argv[1:2] == ["--test"]:  # проверка из терминала, без Telegram и .env (TD-FN-61)
        from muallim.bootstrap import console  # noqa: PLC0415 — console импортирует этот модуль

        print(asyncio.run(console.run_console(sys.argv[2:] or ["/start"])))  # noqa: T201
        return
    try:
        with suppress(KeyboardInterrupt):
            asyncio.run(main())
    except Exception:  # бот упал целиком (БД, модель, сеть) — в лог и файл, не только в stderr
        logging.getLogger(__name__).critical("Бот остановлен из-за ошибки", exc_info=True)
        raise
