"""Блок «Для исследования» — учителю, а не новичку; «Бот ошибся» можно отменить (FR-50).

Настоящие обработчики, DI и SQLite; учитель задан в TEACHER_IDS, ученик — обычный.
"""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from aiogram import Bot, Dispatcher
from aiogram.types import User
from dishka import AsyncContainer
from dishka.integrations.aiogram import setup_dishka
from pydantic import SecretStr

from muallim.application.use_cases.curriculum import PublishCurriculum
from muallim.bootstrap.config import Settings
from muallim.bootstrap.di import create_container
from muallim.infrastructure.db.engine import create_engine
from muallim.infrastructure.db.tables import metadata
from muallim.infrastructure.db.views import create_views
from muallim.presentation.telegram import texts
from muallim.presentation.telegram.callbacks import Dispute, GoItem
from muallim.presentation.telegram.handlers import router
from tests.integration.test_bot_flow import FakeTelegram, Learner

pytestmark = pytest.mark.integration

TEACHER, PUPIL = 7101, 7102
ISTI_ADHA = "L001-02"


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
        recitations_dir=tmp_path / "recitations", teacher_ids=str(TEACHER), log_file=None,
    )  # fmt: skip
    container = create_container(settings)
    async with container() as request:
        await (await request.get(PublishCurriculum)).execute()
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


def _person(dp: Dispatcher, tg: int) -> Learner:
    fake = FakeTelegram()
    user = User(id=tg, is_bot=False, first_name="Ученик", language_code="ru")
    return Learner(dp, Bot("1:test", session=fake), fake, user)


async def _read_isti_adha(dp: Dispatcher, tg: int) -> Learner:
    person = _person(dp, tg)
    await person.write("/start")
    await person.press(GoItem(item_id=ISTI_ADHA))
    await person.voice()
    return person


def _result_text(person: Learner) -> str:
    """Подпись результата и второе сообщение с разбором — всё, что пришло после «Слушаю…»."""
    shown = person.tg.texts()
    start = max(i for i, t in enumerate(shown) if t.startswith(texts.LISTENING.split("{")[0]))
    return "\n".join(shown[start + 1 :])


async def test_teacher_sees_research_block(app: tuple[Dispatcher, AsyncContainer]) -> None:
    dp, _ = app
    result = _result_text(await _read_isti_adha(dp, TEACHER))
    assert texts.VERDICT_EXCELLENT in result
    assert "Для исследования" in result and "Попытка №" in result


async def test_pupil_does_not_see_research_block(app: tuple[Dispatcher, AsyncContainer]) -> None:
    dp, _ = app
    result = _result_text(await _read_isti_adha(dp, PUPIL))
    assert texts.VERDICT_EXCELLENT in result
    assert "Для исследования" not in result and "Попытка №" not in result


async def test_staff_access_is_wired_in_di(app: tuple[Dispatcher, AsyncContainer]) -> None:
    from muallim.application.use_cases.staff import StaffAccess  # noqa: PLC0415 — новый сценарий

    _, container = app
    async with container() as request:
        assert isinstance(await request.get(StaffAccess), StaffAccess)


async def test_dispute_menu_can_be_cancelled(app: tuple[Dispatcher, AsyncContainer]) -> None:
    dp, _ = app
    pupil = await _read_isti_adha(dp, PUPIL)
    await pupil.press(pupil.button(Dispute))
    markup = pupil.last_screen().reply_markup
    assert markup is not None
    assert texts.CANCEL_BUTTON in [b.text for row in markup.inline_keyboard for b in row]
