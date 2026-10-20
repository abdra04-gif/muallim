"""Перезапуск бота не теряет экран и начало занятия (QAS-05, NFR-REL-01, TD-FN-90 п. 1, ADR-0061).

Имитация перезапуска: новый Dispatcher (пустой MemoryStorage) и новый контейнер на ТОЙ ЖЕ БД.
Что на экране (карточка / меню), идёт ли начало занятия и «пропустил сегодня» — в
`learner_settings`, а не в FSM. Дата начала занятия — местная (смещение ученика), не UTC.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
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
from muallim.domain.assessment import assess
from muallim.domain.attempt import Attempt
from muallim.domain.policy import GradingPolicy
from muallim.infrastructure.db.engine import create_engine
from muallim.infrastructure.db.repositories.attempts import SqlAttemptRepository
from muallim.infrastructure.db.tables import attempts, metadata
from muallim.infrastructure.db.views import create_views
from muallim.infrastructure.system import SystemClock
from muallim.presentation.telegram import texts
from muallim.presentation.telegram.callbacks import GoItem, Home, Opening
from muallim.presentation.telegram.handlers import router
from muallim.presentation.telegram.opening import OPENING_ITEMS
from tests.integration.test_bot_flow import Learner
from tests.integration.test_opening_bot import (
    RESUME,
    _current_item,
    _labels,
    _person,
    _press_label,
    _seed,
)

pytestmark = pytest.mark.integration
ISTI_ADHA, BASMALA = OPENING_ITEMS


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


SEEDED = {UUID(int=11), UUID(int=12), UUID(int=99)}  # попытки из _seed и теста (г)


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
    await ali.press(Opening(act="skip"))
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
    await ali.press(Opening(act="skip"))
    await ali.press(GoItem(item_id="L006-02"))
    await bot.restart(ali)
    await ali.voice()
    assert texts.VOICE_ON_HOME not in ali.tg.texts()
    assert await _new_attempts(bot) == ["L006-02"]


async def test_home_screen_survives_restart(bot: Bot) -> None:
    """(б) Был на главной, бот перезапустился — голосовое не оценивается (VOICE_ON_HOME, FR-50)."""
    ali = _person(bot.dp)
    await ali.write("/start")
    await ali.press(Opening(act="skip"))
    await ali.press(GoItem(item_id="L006-02"))
    await ali.voice()  # урок открыт — оценивается
    await ali.press(Home())
    await bot.restart(ali)
    await ali.voice()
    assert texts.VOICE_ON_HOME in ali.tg.texts()
    assert await _new_attempts(bot) == ["L006-02"], "голосовое с главной не в зачёт"


async def test_isti_adha_on_screen_after_restart_is_assessed_as_isti_adha(bot: Bot) -> None:
    """Открыл истиазу (курсор остался на L006-01), перезапуск — голосовое — попытка истиазы."""
    ali = _person(bot.dp)
    await ali.write("/start")
    await ali.press(Opening(act="start"))
    await bot.restart(ali)
    await ali.voice()
    assert await _new_attempts(bot) == [ISTI_ADHA]
    assert await _current_item(bot.container) == RESUME


async def test_opening_survives_restart_and_does_not_move_cursor(bot: Bot) -> None:
    """(в) Прочитал истиазу, перезапуск, «▶️ Дальше» на басмалу — курсор не сдвинулся (FR-49)."""
    ali = _person(bot.dp)
    await ali.write("/start")
    await ali.press(Opening(act="start"))
    await ali.voice()  # истиаза
    await bot.restart(ali)
    await _press_label(ali, texts.NEXT_BUTTON)  # → басмала
    await ali.voice()
    assert await _new_attempts(bot) == [ISTI_ADHA, BASMALA]
    assert await _current_item(bot.container) == RESUME
    go_on = [data for text, data in _labels(ali) if text.startswith("▶️ Продолжить")]
    assert go_on == [GoItem(item_id=RESUME).pack()], "после басмалы — туда, где остановился"


async def test_skipped_opening_survives_restart(bot: Bot) -> None:
    """«Пропустить» сегодня — после перезапуска начало занятия сегодня не предлагается снова."""
    ali = _person(bot.dp)
    await ali.write("/start")
    assert texts.OPENING_TITLE in ali.tg.texts()[-1]
    await ali.press(Opening(act="skip"))
    await bot.restart(ali)
    await ali.write("/start")
    assert texts.OPENING_TITLE not in ali.tg.texts()[-1]


# ---------- (г) «сегодня» — по местной дате ученика ----------
EVENING_UTC = datetime(2030, 3, 10, 20, 30, tzinfo=UTC)
PRACTICED_UTC = datetime(2030, 3, 10, 10, 0, tzinfo=UTC)  # занимался днём 10 марта


@pytest.mark.parametrize(
    ("offset", "offered"),
    [(300, True), (None, False)],
    ids=["almaty_utc+5_already_tomorrow", "default_utc+3_still_today"],
)
async def test_opening_day_is_the_learners_local_date(
    bot: Bot, monkeypatch: pytest.MonkeyPatch, offset: int | None, offered: bool
) -> None:
    """В 20:30 UTC в Алматы (UTC+5) уже 01:30 следующего дня: занятие днём было «вчера» —
    начало занятия предлагается. При умолчании UTC+3 (23:30) — тот же день, не предлагается."""
    async with bot.container() as request:
        session = await request.get(AsyncSession)
        a = assess("x", "x")
        await SqlAttemptRepository(session).add(
            Attempt(UUID(int=99), UUID(int=1), ISTI_ADHA, "v", "stub", a,
                    GradingPolicy().verdict(a), None, None, 1, PRACTICED_UTC),
            (),
        )  # fmt: skip
        if offset is not None:
            from muallim.application.ports.repositories import (  # noqa: PLC0415
                LearnerSettingsRepository,
            )

            repo = await request.get(LearnerSettingsRepository)
            await repo.save(
                UUID(int=1), replace(await repo.get(UUID(int=1)), utc_offset_min=offset)
            )
        await session.commit()
    monkeypatch.setattr(SystemClock, "now", lambda self: EVENING_UTC)

    ali = _person(bot.dp)
    await ali.write("/start")
    assert (texts.OPENING_TITLE in ali.tg.texts()[-1]) is offered


async def test_yesterdays_opening_expires_at_local_midnight(
    bot: Bot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """UTC+5: открыл истиазу в 23:50 местного; в 00:10 — уже новый день, голосовое не истиазы."""
    from muallim.application.ports.repositories import (  # noqa: PLC0415
        LearnerSettingsRepository,
    )

    async with bot.container() as request:
        repo = await request.get(LearnerSettingsRepository)
        await repo.save(UUID(int=1), replace(await repo.get(UUID(int=1)), utc_offset_min=300))
        await (await request.get(AsyncSession)).commit()
    before_midnight = datetime(2030, 3, 10, 18, 50, tzinfo=UTC)  # 23:50 в Алматы
    monkeypatch.setattr(SystemClock, "now", lambda self: before_midnight)
    ali = _person(bot.dp)
    await ali.write("/start")
    await ali.press(Opening(act="start"))
    monkeypatch.setattr(SystemClock, "now", lambda self: before_midnight + timedelta(minutes=20))
    await ali.voice()  # 00:10 по Алматы, 19:10 UTC — по UTC ещё тот же день
    assert ISTI_ADHA not in await _new_attempts(bot), "вчерашнее начало занятия не действует"
    assert await _current_item(bot.container) == RESUME
