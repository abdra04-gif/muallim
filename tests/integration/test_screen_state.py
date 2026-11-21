"""Перезапуск бота не теряет экран (QAS-05, NFR-REL-01, TD-FN-90 п. 1, ADR-0061).

Имитация перезапуска: новый Dispatcher (пустой MemoryStorage) и новый контейнер на ТОЙ ЖЕ БД.
Что на экране (карточка / меню) — в `learner_settings`, а не в FSM. «Начало занятия» убрано
(автор 2026-11-21: истиазы в книге нет).
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import pytest
from aiogram import Dispatcher
from dishka import AsyncContainer
from dishka.integrations.aiogram import setup_dishka
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from muallim.application.use_cases.curriculum import PublishCurriculum
from muallim.bootstrap.config import Settings
from muallim.bootstrap.di import create_container
from muallim.infrastructure.db.engine import create_engine
from muallim.infrastructure.db.tables import attempts, metadata
from muallim.infrastructure.db.views import create_views
from muallim.presentation.telegram import texts
from muallim.presentation.telegram.callbacks import GoItem, Home
from muallim.presentation.telegram.handlers import router
from tests.integration.test_bot_flow import Learner
from tests.integration.test_returning_learner_bot import (
    _current_item,
    _person,
    _seed,
)

pytestmark = pytest.mark.integration


@dataclass
class Bot:
    """Процесс бота: диспетчер и контейнер; restart() — как остановка и новый запуск."""

    settings: Settings
    dp: Dispatcher
    container: AsyncContainer

    @classmethod
    async def start(cls, settings: Settings) -> "Bot":
        container = create_container(settings)
        async with container() as request:  # как main.py при старте
            await (await request.get(PublishCurriculum)).execute()
        dp = Dispatcher()  # новый MemoryStorage: всё из FSM потеряно
        dp.include_router(router)
        setup_dishka(container=container, router=dp, auto_inject=True)
        await dp.emit_startup()
        return cls(settings, dp, container)

    async def stop(self) -> None:
        await self.dp.emit_shutdown()
        await self.container.close()
        self.dp.sub_routers.remove(router)
        router._parent_router = None

    async def restart(self, *people: Learner) -> None:
        await self.stop()
        fresh = await Bot.start(self.settings)
        self.dp, self.container = fresh.dp, fresh.container
        for person in people:  # тот же чат и те же сообщения на экране, новый процесс
            person.dp = self.dp


@pytest.fixture
async def bot(tmp_path: Path) -> AsyncIterator[Bot]:
    url = f"sqlite+aiosqlite:///{tmp_path / 'bot.sqlite3'}"
    engine = create_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)
        await conn.run_sync(create_views)
    await engine.dispose()
    settings = Settings(
        bot_token=SecretStr("1:test"), database_url=SecretStr(url), asr_backend="stub",
        audio_dir=tmp_path / "audio", reference_audio_dir=tmp_path / "reference",
        recitations_dir=tmp_path / "recitations", log_file=None,
    )  # fmt: skip
    app = await Bot.start(settings)
    async with app.container() as request:
        await _seed(await request.get(AsyncSession))  # урок 1 пройден вчера, курсор — L006-01
    try:
        yield app
    finally:
        await app.stop()


SEEDED = {UUID(int=11)}  # попытка из _seed (басмала вчера)


async def _new_attempts(bot: Bot) -> list[str]:
    """Карточки попыток, сделанных в тесте голосовыми, по порядку."""
    async with bot.container() as request:
        session = await request.get(AsyncSession)
        query = select(attempts.c.id, attempts.c.item_id).order_by(attempts.c.created_at)
        rows = (await session.execute(query)).all()
    return [item for id_, item in rows if id_ not in SEEDED]


# ---------- QAS-05: курсор (было) и экран (новое) ----------
async def test_continue_after_restart_opens_the_same_card(bot: Bot) -> None:
    """QAS-05 как был: «▶️ Продолжить» после перезапуска — та же карточка (0 потерянных позиций)."""
    ali = _person(bot.dp)
    await ali.write("/start")
    await ali.press(GoItem(item_id="L006-02"))
    await ali.voice()  # сегодня занимался — после /start сразу главная
    await bot.restart(ali)
    await ali.write("/start")
    assert ali.button(GoItem) == GoItem(item_id="L006-02").pack()
    assert await _current_item(bot.container) == "L006-02"


async def test_open_card_survives_restart(bot: Bot) -> None:
    """(а) Открыл карточку L006-02, бот перезапустился — голосовое оценивается по L006-02."""
    ali = _person(bot.dp)
    await ali.write("/start")
    await ali.press(GoItem(item_id="L006-02"))
    await bot.restart(ali)
    await ali.voice()
    assert texts.VOICE_ON_HOME not in ali.tg.texts()
    assert await _new_attempts(bot) == ["L006-02"]


async def test_home_screen_survives_restart(bot: Bot) -> None:
    """(б) Был на главной, бот перезапустился — голосовое не оценивается (VOICE_ON_HOME, FR-50)."""
    ali = _person(bot.dp)
    await ali.write("/start")
    await ali.press(GoItem(item_id="L006-02"))
    await ali.voice()  # урок открыт — оценивается
    await ali.press(Home())
    await bot.restart(ali)
    await ali.voice()
    assert texts.VOICE_ON_HOME in ali.tg.texts()
    assert await _new_attempts(bot) == ["L006-02"], "голосовое с главной не в зачёт"
