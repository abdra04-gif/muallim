"""Учитель записывает эталон в боте (ADR-0024) — через настоящие обработчики и DI.

Шаг «жду эталон» раньше жил в словаре модуля: два диспетчера (тесты, режим --test, второй
процесс) видели одно состояние. Теперь он в FSM диспетчера (change-scenarios.md).
"""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from aiogram import Bot, Dispatcher, Router
from aiogram.methods import SendMessage
from aiogram.types import User
from dishka import AsyncContainer
from dishka.integrations.aiogram import setup_dishka
from pydantic import SecretStr

from muallim.application.use_cases.curriculum import PublishCurriculum
from muallim.bootstrap.config import Settings
from muallim.bootstrap.di import create_container
from muallim.domain.curriculum import Curriculum
from muallim.infrastructure.db.engine import create_engine
from muallim.infrastructure.db.tables import metadata
from muallim.infrastructure.db.views import create_views
from muallim.presentation.telegram import texts
from muallim.presentation.telegram.callbacks import RecordReference
from muallim.presentation.telegram.handlers import router
from tests.integration.test_bot_flow import FakeTelegram, Learner

pytestmark = pytest.mark.integration

TEACHER = 7001


async def _app(tmp_path: Path, name: str) -> tuple[Dispatcher, AsyncContainer]:
    url = f"sqlite+aiosqlite:///{tmp_path / f'{name}.sqlite3'}"
    engine = create_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)
        await conn.run_sync(create_views)
    await engine.dispose()
    settings = Settings(
        bot_token=SecretStr("1:test"),
        database_url=SecretStr(url),
        asr_backend="stub",
        audio_dir=tmp_path / name / "audio",
        reference_audio_dir=tmp_path / name / "reference",
        recitations_dir=tmp_path / name / "recitations",
        teacher_ids=str(TEACHER),
        log_file=None,
    )
    container = create_container(settings)
    async with container() as request:
        await (await request.get(PublishCurriculum)).execute()
    return Dispatcher(), container


@pytest.fixture
async def two_bots(tmp_path: Path) -> AsyncIterator[list[tuple[Dispatcher, AsyncContainer]]]:
    """Два независимых бота; модульный роутер ученика подключается к ним по очереди."""
    apps = [await _app(tmp_path, "one"), await _app(tmp_path, "two")]
    yield apps
    for _, container in apps:
        await container.close()


async def _attach(dp: Dispatcher, container: AsyncContainer, r: Router) -> None:
    dp.include_router(r)
    setup_dishka(container=container, router=dp, auto_inject=True)
    await dp.emit_startup()


async def _detach(dp: Dispatcher, r: Router) -> None:
    await dp.emit_shutdown()
    dp.sub_routers.remove(r)
    r._parent_router = None


def _teacher(dp: Dispatcher) -> Learner:
    tg = FakeTelegram()
    user = User(id=TEACHER, is_bot=False, first_name="Учитель", language_code="ru")
    return Learner(dp, Bot("1:test", session=tg), tg, user)


def _replies(who: Learner) -> list[str]:
    return [str(c.text) for c in who.tg.calls if isinstance(c, SendMessage)]


async def test_teacher_voice_after_record_button_becomes_reference(
    two_bots: list[tuple[Dispatcher, AsyncContainer]], curriculum: Curriculum
) -> None:
    (dp, container), _ = two_bots
    item = next(i for lesson in curriculum.lessons for i in lesson.items if i.is_practice)
    await _attach(dp, container, router)
    try:
        teacher = _teacher(dp)
        await teacher.write("/start")
        await teacher.press(RecordReference(item_id=item.id))
        await teacher.voice()
        assert texts.RECORD_SAVED.format(item=item.id) in _replies(teacher)
        await teacher.voice()  # следующее голосовое — снова обычное чтение, не эталон
        assert _replies(teacher).count(texts.RECORD_SAVED.format(item=item.id)) == 1
    finally:
        await _detach(dp, router)


async def test_waiting_for_reference_is_not_shared_between_bots(
    two_bots: list[tuple[Dispatcher, AsyncContainer]], curriculum: Curriculum
) -> None:
    (first, c1), (second, c2) = two_bots
    item = next(i for lesson in curriculum.lessons for i in lesson.items if i.is_practice)
    await _attach(first, c1, router)
    try:
        teacher = _teacher(first)
        await teacher.write("/start")  # нужен экран, на котором «нажимается» кнопка
        await teacher.press(RecordReference(item_id=item.id))
    finally:
        await _detach(first, router)
    await _attach(second, c2, router)
    try:
        other = _teacher(second)
        await other.write("/start")
        await other.voice()
        assert texts.RECORD_SAVED.format(item=item.id) not in _replies(other)
    finally:
        await _detach(second, router)
