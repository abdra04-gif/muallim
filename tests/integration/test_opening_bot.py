"""Начало занятия: истиаза и басмала раз в день, двумя голосовыми подряд (ADR-0050, SRC-110).

Предпочтительный способ — остановка после истиазы и после басмалы (каждая — аят), поэтому
ученик читает две карточки урока 1 по очереди, а потом возвращается туда, где остановился.
"""

from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path
from uuid import UUID

import pytest
from aiogram import Dispatcher
from aiogram.types import User
from dishka import AsyncContainer
from dishka.integrations.aiogram import setup_dishka
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from muallim.application.use_cases.curriculum import PublishCurriculum
from muallim.bootstrap.config import Settings
from muallim.bootstrap.di import create_container
from muallim.domain.assessment import assess
from muallim.domain.attempt import Attempt
from muallim.domain.learner import Learner as LearnerRecord
from muallim.domain.policy import GradingPolicy
from muallim.infrastructure.db.engine import create_engine
from muallim.infrastructure.db.repositories.attempts import SqlAttemptRepository
from muallim.infrastructure.db.repositories.learners import SqlLearnerRepository
from muallim.infrastructure.db.tables import metadata
from muallim.infrastructure.db.views import create_views
from muallim.infrastructure.system import SystemClock
from muallim.presentation.telegram import texts
from muallim.presentation.telegram.callbacks import GoItem, Opening
from muallim.presentation.telegram.handlers import router
from muallim.presentation.telegram.opening import OPENING_ITEMS
from tests.integration.test_bot_flow import FakeTelegram, Learner

pytestmark = pytest.mark.integration

TG = 6001
RESUME = "L006-01"


@pytest.fixture
async def app(tmp_path: Path) -> AsyncIterator[tuple[Dispatcher, AsyncContainer]]:
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
    container = create_container(settings)
    async with container() as request:
        await (await request.get(PublishCurriculum)).execute()
        await _seed(await request.get(AsyncSession))
    dp = Dispatcher()
    dp.include_router(router)
    setup_dishka(container=container, router=dp, auto_inject=True)
    await dp.emit_startup()
    try:
        yield dp, container
    finally:
        await dp.emit_shutdown()
        await container.close()
        dp.sub_routers.remove(router)
        router._parent_router = None


async def _seed(session: AsyncSession) -> None:
    """Ученик прошёл урок 1 вчера и остановился на уроке 6; сегодня ещё не занимался."""
    yesterday = SystemClock().now() - timedelta(days=1)
    learner = LearnerRecord(UUID(int=1), TG, "L-open", "ru", yesterday, current_item_id=RESUME)
    await SqlLearnerRepository(session).add(learner)
    repo = SqlAttemptRepository(session)
    for n, item_id in enumerate(OPENING_ITEMS, start=1):
        a = assess("x", "x")
        await repo.add(
            Attempt(UUID(int=10 + n), learner.id, item_id, "v", "stub", a,
                    GradingPolicy().verdict(a), None, None, 1, yesterday),
            (),
        )  # fmt: skip
    await session.commit()


def _person(dp: Dispatcher) -> Learner:
    from aiogram import Bot  # noqa: PLC0415

    tg = FakeTelegram()
    user = User(id=TG, is_bot=False, first_name="Ученик", language_code="ru")
    return Learner(dp, Bot("1:test", session=tg), tg, user)


async def test_daily_opening_reads_two_lines_then_resumes(
    app: tuple[Dispatcher, AsyncContainer],
) -> None:
    dp, _ = app
    ali = _person(dp)
    await ali.write("/start")
    assert texts.OPENING_TITLE in ali.tg.texts()[-1]

    await ali.press(Opening(act="start"))  # истиаза
    await ali.voice()
    await ali.press(GoItem(item_id=OPENING_ITEMS[1]))  # басмала
    await ali.voice()
    markup = ali.last_screen().reply_markup
    assert markup is not None
    resume = [b for row in markup.inline_keyboard for b in row if b.text.startswith("▶️ Продолжить")]
    assert [b.callback_data for b in resume] == [GoItem(item_id=RESUME).pack()], (
        "после басмалы — туда, где остановился"
    )

    await ali.write("/start")  # второй раз за день — сразу главная
    assert texts.OPENING_TITLE not in ali.tg.texts()[-1]


async def test_opening_can_be_skipped(app: tuple[Dispatcher, AsyncContainer]) -> None:
    dp, _ = app
    ali = _person(dp)
    await ali.write("/start")
    await ali.press(Opening(act="skip"))
    assert texts.OPENING_TITLE not in ali.tg.texts()[-1]
    await ali.write("/start")
    assert texts.OPENING_TITLE not in ali.tg.texts()[-1]
