"""Напоминание о занятии: рассылка одним тиком (FR-51, ADR-0061 п. 4, В1–В4, NFR-SEC-04).

Тик вызывается в тесте один раз с поддельным временем — без настоящего цикла asyncio. Настоящие
DI, сценарии и SQLite; вместо Telegram — сессия в памяти, которая умеет отвечать 403 (ученик
заблокировал бота) и 429 (слишком часто). Ожидаемый интерфейс:

- ``muallim.presentation.telegram.reminders.send_due_reminders(bot, container, now) -> int`` —
  один тик: кому пора (``domain.settings.reminder_due``), тем ``texts.REMINDER`` с кнопкой
  «▶️ Продолжить: <урок>»; ``reminder_sent_on`` коммитится до отправки; возвращает число
  доставленных;
- ``muallim.presentation.telegram.reminders.run_reminders`` — бесконечный цикл тиков;
- ``muallim.bootstrap.main.background_jobs()`` — задачи, которые бот запускает рядом с polling.
- ``muallim.bootstrap.main.start_background(bot, container, jobs) -> list[asyncio.Task[None]]`` —
  запускает задачи; упавшая задача (не отменённая) пишет ERROR в логгер ``muallim.*`` (ревью).

Ревью (ADR-0061 п. 4, NFR-SEC-07): движок БД скрывает параметры запросов; отметка «сегодня
напомнили» — условный UPDATE с проверкой rowcount; сбой на одном ученике не обрывает тик.
"""

import asyncio
import logging
import traceback
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest
from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.methods import SendMessage, TelegramMethod
from aiogram.types import User
from dishka import AsyncContainer
from dishka.integrations.aiogram import setup_dishka
from pydantic import SecretStr
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from muallim.application.ports.repositories import (
    LearnerRepository,
    LearnerSettingsRepository,
    UnitOfWork,
)
from muallim.application.use_cases.curriculum import PublishCurriculum
from muallim.application.use_cases.progress import GetProgress
from muallim.application.use_cases.reminders import DueReminders
from muallim.bootstrap.config import Settings
from muallim.bootstrap.di import create_container
from muallim.domain.assessment import assess
from muallim.domain.attempt import Attempt
from muallim.domain.curriculum import Curriculum
from muallim.domain.learner import Learner as LearnerRecord
from muallim.domain.policy import GradingPolicy
from muallim.domain.settings import LearnerSettings
from muallim.infrastructure.db.engine import create_engine
from muallim.infrastructure.db.repositories.attempts import SqlAttemptRepository
from muallim.infrastructure.db.repositories.learners import SqlLearnerRepository
from muallim.infrastructure.db.repositories.settings import SqlLearnerSettingsRepository
from muallim.infrastructure.db.tables import interaction_events, metadata
from muallim.infrastructure.db.views import create_views
from muallim.presentation.telegram import texts
from muallim.presentation.telegram.callbacks import GoItem
from muallim.presentation.telegram.handlers import router
from tests.integration.test_bot_flow import FakeTelegram, Learner

pytestmark = pytest.mark.integration

# 21:10 UTC 20 октября = 07:10 21 октября в UTC+10: местная дата — не дата UTC
NOW = datetime(2026, 10, 20, 21, 10, tzinfo=UTC)
OFFSET = 10 * 60
MORNING = 7 * 60  # напомнить в 07:00 местного
LOCAL_TODAY = date(2026, 10, 21)
RESUME = "L006-01"  # где остановился ученик
PRACTICE_ITEM = "L001-02"
YESTERDAY = NOW - timedelta(days=1)  # 07:10 20 октября местного
EARLIER_TODAY = NOW - timedelta(hours=1)  # 20:10 UTC 20-го — но уже 06:10 21-го местного
TICK_TIMEOUT_S = 5  # тик не ждёт 429 по 30 с и не зависает

ALI, BOTA, CHINGIZ, DANA, ERLAN = 8101, 8102, 8103, 8104, 8105


@dataclass(frozen=True, slots=True)
class Pupil:
    tg: int
    practiced_at: datetime | None = YESTERDAY
    reminder_minute: int | None = MORNING
    blocked_bot: bool = False


class ReminderTelegram(FakeTelegram):
    """Telegram в памяти, который может отказать: 403 — заблокировал бота, 429 — подожди."""

    def __init__(self) -> None:
        super().__init__()
        self.forbidden: set[int] = set()
        self.retry_after_on_first = False
        self.attempted: list[int] = []  # кому бот пытался написать — по порядку
        self.before_send: Callable[[int], Awaitable[None]] | None = None

    async def make_request(
        self, bot: Bot, method: TelegramMethod[Any], timeout: int | None = None
    ) -> Any:
        if isinstance(method, SendMessage):
            assert isinstance(method.chat_id, int)
            self.attempted.append(method.chat_id)
            if self.before_send is not None:
                await self.before_send(method.chat_id)
            if method.chat_id in self.forbidden:
                raise TelegramForbiddenError(
                    method=method, message="Forbidden: bot was blocked by the user"
                )
            if self.retry_after_on_first and len(self.attempted) == 1:
                raise TelegramRetryAfter(
                    method=method, message="Too Many Requests: retry after 30", retry_after=30
                )
        return await super().make_request(bot, method, timeout)

    def delivered(self) -> list[SendMessage]:
        return [c for c in self.calls if isinstance(c, SendMessage)]


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


def _id(tg: int) -> UUID:
    return UUID(int=tg)


async def _seed(container: AsyncContainer, *pupils: Pupil) -> None:
    """Ученики с напоминанием в 07:00 по UTC+10, остановились на уроке 6."""
    async with container() as request:
        session = await request.get(AsyncSession)
        learners, attempts = SqlLearnerRepository(session), SqlAttemptRepository(session)
        for n, p in enumerate(pupils):
            await learners.add(
                LearnerRecord(
                    _id(p.tg), p.tg, f"L-rem{n}", "ru", NOW - timedelta(days=30),
                    current_item_id=RESUME, blocked_bot=p.blocked_bot,
                )
            )  # fmt: skip
            if p.practiced_at is not None:
                a = assess("x", "x")
                await attempts.add(
                    Attempt(UUID(int=10_000 + n), _id(p.tg), PRACTICE_ITEM, "v", "stub", a,
                            GradingPolicy().verdict(a), None, None, 1, p.practiced_at),
                    (),
                )  # fmt: skip
        await session.commit()
        repo = await request.get(LearnerSettingsRepository)
        for p in pupils:
            await repo.change(
                _id(p.tg), {"reminder_minute": p.reminder_minute, "utc_offset_min": OFFSET}
            )
        await session.commit()


async def _tick(container: AsyncContainer, tg: ReminderTelegram, now: datetime = NOW) -> int:
    from muallim.presentation.telegram.reminders import send_due_reminders  # noqa: PLC0415

    bot = Bot("1:test", session=tg)
    sent: int = await asyncio.wait_for(send_due_reminders(bot, container, now), TICK_TIMEOUT_S)
    return sent


async def _settings(container: AsyncContainer, tg: int) -> LearnerSettings:
    async with container() as request:
        found: LearnerSettings = await (await request.get(LearnerSettingsRepository)).get(_id(tg))
    return found


async def _blocked(container: AsyncContainer, tg: int) -> bool:
    async with container() as request:
        learner = await (await request.get(LearnerRepository)).get_by_telegram_id(tg)
    assert learner is not None
    blocked: bool = learner.blocked_bot
    return blocked


async def _reminder_events(container: AsyncContainer) -> list[UUID | None]:
    async with container() as request:
        session = await request.get(AsyncSession)
        rows = await session.execute(
            select(interaction_events.c.learner_id).where(
                interaction_events.c.event == "reminder_sent"
            )
        )
        return [r[0] for r in rows]


# ---------- кому и что ----------
async def test_due_learner_gets_reminder_with_continue_button(
    app: tuple[Dispatcher, AsyncContainer],
) -> None:
    _, container = app
    await _seed(container, Pupil(ALI))
    tg = ReminderTelegram()
    assert await _tick(container, tg) == 1
    [message] = tg.delivered()
    assert message.chat_id == ALI
    assert message.text.startswith(texts.REMINDER.split("{")[0]), message.text
    markup = message.reply_markup
    assert markup is not None and hasattr(markup, "inline_keyboard")
    buttons = [b for row in markup.inline_keyboard for b in row]
    title = (await container.get(Curriculum)).locate(RESUME)[0].title
    assert [(b.text, b.callback_data) for b in buttons] == [
        (texts.CONTINUE_BUTTON.format(title=title), GoItem(item_id=RESUME).pack())
    ]


async def test_reminder_sent_on_is_local_date_and_committed_before_sending(
    app: tuple[Dispatcher, AsyncContainer],
) -> None:
    """Не больше одного в день даже при сбое: дата в БД — до отправки (ADR-0061 п. 4)."""
    _, container = app
    await _seed(container, Pupil(ALI))
    tg = ReminderTelegram()
    seen: list[date | None] = []

    async def look(_: int) -> None:  # другая сессия БД видит только закоммиченное
        seen.append((await _settings(container, ALI)).reminder_sent_on)

    tg.before_send = look
    await _tick(container, tg)
    assert seen == [LOCAL_TODAY], "местная дата UTC+10, а не дата UTC"
    assert (await _settings(container, ALI)).reminder_sent_on == LOCAL_TODAY


async def test_reminder_is_logged_as_interaction_event(
    app: tuple[Dispatcher, AsyncContainer],
) -> None:
    _, container = app
    await _seed(container, Pupil(ALI))
    await _tick(container, ReminderTelegram())
    assert await _reminder_events(container) == [_id(ALI)]


async def test_second_tick_on_the_same_local_day_sends_nothing(
    app: tuple[Dispatcher, AsyncContainer],
) -> None:
    _, container = app
    await _seed(container, Pupil(ALI))
    tg = ReminderTelegram()
    await _tick(container, tg)
    assert await _tick(container, tg, NOW + timedelta(minutes=1)) == 0
    assert await _tick(container, tg, NOW + timedelta(hours=2)) == 0
    assert len(tg.delivered()) == 1
    assert await _reminder_events(container) == [_id(ALI)]


@pytest.mark.parametrize(
    "pupil",
    [
        Pupil(BOTA, practiced_at=EARLIER_TODAY),  # сегодня по местному, вчера по UTC
        Pupil(CHINGIZ, blocked_bot=True),
        Pupil(DANA, reminder_minute=None),
        Pupil(ERLAN, practiced_at=NOW - timedelta(days=15)),  # 14 дней молчания — пауза
    ],
    ids=["practiced-today", "blocked-bot", "switched-off", "silent-15-days"],
)
async def test_learner_who_should_not_be_reminded_gets_nothing(
    app: tuple[Dispatcher, AsyncContainer], pupil: Pupil
) -> None:
    _, container = app
    await _seed(container, Pupil(ALI), pupil)
    tg = ReminderTelegram()
    assert await _tick(container, tg) == 1
    assert tg.attempted == [ALI]
    assert (await _settings(container, pupil.tg)).reminder_sent_on is None
    assert await _reminder_events(container) == [_id(ALI)]


# ---------- Telegram отказал ----------
async def test_blocked_by_learner_marks_blocked_bot_and_others_still_get_it(
    app: tuple[Dispatcher, AsyncContainer],
) -> None:
    _, container = app
    await _seed(container, Pupil(ALI), Pupil(BOTA, practiced_at=YESTERDAY))
    tg = ReminderTelegram()
    tg.forbidden = {ALI}
    assert await _tick(container, tg) == 1  # тик не падает
    assert await _blocked(container, ALI) is True
    assert await _blocked(container, BOTA) is False
    assert [m.chat_id for m in tg.delivered()] == [BOTA]


async def test_blocked_learner_is_unblocked_when_writing_to_bot_again(
    app: tuple[Dispatcher, AsyncContainer],
) -> None:
    dp, container = app
    await _seed(container, Pupil(ALI))
    tg = ReminderTelegram()
    tg.forbidden = {ALI}
    await _tick(container, tg)
    assert await _blocked(container, ALI) is True

    chat = FakeTelegram()
    ali = Learner(
        dp, Bot("1:test", session=chat), chat,
        User(id=ALI, is_bot=False, first_name="Ученик", language_code="ru"),
    )  # fmt: skip
    await ali.write("/start")
    assert await _blocked(container, ALI) is False


async def test_too_many_requests_does_not_crash_and_rest_waits_for_next_tick(
    app: tuple[Dispatcher, AsyncContainer],
) -> None:
    """429: тик не падает и не ждёт retry_after, остальным — на следующем тике (ADR-0061 п. 4)."""
    _, container = app
    await _seed(container, Pupil(ALI), Pupil(BOTA))
    tg = ReminderTelegram()
    tg.retry_after_on_first = True
    assert await _tick(container, tg) == 0
    assert len(tg.attempted) == 1, "после 429 в этот тик больше не пишем"
    [first] = tg.attempted

    assert await _tick(container, tg, NOW + timedelta(minutes=1)) == 1
    [delivered] = tg.delivered()
    assert delivered.chat_id != first and delivered.chat_id in {ALI, BOTA}


# ---------- журнал без Telegram ID (ADR-0027, NFR-SEC-04) ----------
async def test_reminder_log_has_no_telegram_ids(
    app: tuple[Dispatcher, AsyncContainer], caplog: pytest.LogCaptureFixture
) -> None:
    _, container = app
    await _seed(container, Pupil(ALI), Pupil(BOTA))
    tg = ReminderTelegram()
    tg.forbidden = {BOTA}
    caplog.set_level(logging.DEBUG)
    await _tick(container, tg)
    ours = [r for r in caplog.records if r.name.startswith("muallim")]
    assert ours, "тик пишет в лог итог (число отправленных)"
    for record in ours:
        line = record.getMessage() + repr(record.args)
        assert str(ALI) not in line and str(BOTA) not in line, line


# ---------- запуск задачи (ADR-0061 п. 4) ----------
def test_bot_process_runs_reminder_job_next_to_polling() -> None:
    from muallim.bootstrap import main  # noqa: PLC0415
    from muallim.presentation.telegram import reminders  # noqa: PLC0415

    assert reminders.run_reminders in main.background_jobs()


async def test_console_mode_does_not_start_reminders(monkeypatch: pytest.MonkeyPatch) -> None:
    """``muallim --test``: проверка в терминале не рассылает напоминаний (временная база)."""
    from muallim.bootstrap import console, main  # noqa: PLC0415
    from muallim.presentation.telegram import reminders  # noqa: PLC0415

    started: list[str] = []

    async def spy(*args: Any, **kwargs: Any) -> int:
        started.append("tick")
        return 0

    monkeypatch.setattr(reminders, "run_reminders", spy)
    monkeypatch.setattr(reminders, "send_due_reminders", spy)
    monkeypatch.setattr(main, "background_jobs", lambda: (spy,))
    await console.run_console(["/start"])
    assert started == []


# ---------- ревью: параметры запросов не в логе (NFR-SEC-07) ----------
@pytest.mark.parametrize(
    "url", ["sqlite+aiosqlite:///:memory:", "postgresql+asyncpg://bot:pw@localhost/muallim"]
)
def test_db_engine_hides_query_parameters(url: str) -> None:
    """Параметры запроса (Telegram ID и т. п.) не попадают в текст ошибок SQLAlchemy."""
    engine = create_engine(url)
    assert engine.sync_engine.hide_parameters is True


def _log_texts(caplog: pytest.LogCaptureFixture) -> list[str]:
    """Что попадёт в файл лога от наших логгеров — сообщение и трассировка ошибки."""
    formatter = logging.Formatter()
    return [
        r.getMessage()
        + repr(r.args)
        + (formatter.formatException(r.exc_info) if r.exc_info else "")
        for r in caplog.records
        if r.name.startswith("muallim")
    ]


async def test_db_failure_in_tick_does_not_leak_telegram_id(
    app: tuple[Dispatcher, AsyncContainer], caplog: pytest.LogCaptureFixture
) -> None:
    """Настоящий IntegrityError с параметрами UPDATE learners (там telegram_user_id)."""
    _, container = app
    await _seed(container, Pupil(ALI), Pupil(BOTA))
    async with container() as request:
        session = await request.get(AsyncSession)
        await session.execute(
            text(
                "CREATE TRIGGER refuse_block BEFORE UPDATE OF blocked_bot ON learners "
                "WHEN NEW.blocked_bot = 1 BEGIN SELECT RAISE(ABORT, 'refused'); END"
            )
        )
        await session.commit()
    tg = ReminderTelegram()
    tg.forbidden = {ALI}  # 403 → blocked() → UPDATE learners падает
    caplog.set_level(logging.DEBUG)
    seen = []
    try:
        await _tick(container, tg)
    except Exception as error:  # noqa: BLE001 — тик может и упасть; важно, что в тексте ошибки
        seen.append("".join(traceback.format_exception(error)))
    seen += _log_texts(caplog)
    assert any("IntegrityError" in t for t in seen), "сбой БД где-то виден: в логе или наружу"
    for line in seen:
        assert str(ALI) not in line and str(BOTA) not in line, line


# ---------- ревью: атомарная отметка «сегодня напомнили» ----------
def _stale_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    """Чтение настроек видит «ещё не напоминали» — как сессия, прочитавшая до чужого коммита."""
    real = SqlLearnerSettingsRepository.get

    async def stale(self: SqlLearnerSettingsRepository, learner_id: UUID) -> LearnerSettings:
        return replace(await real(self, learner_id), reminder_sent_on=None)

    monkeypatch.setattr(SqlLearnerSettingsRepository, "get", stale)


async def test_claim_refuses_when_db_already_has_today_despite_stale_snapshot(
    app: tuple[Dispatcher, AsyncContainer], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Два тика/процесса разом: дата ставится условным UPDATE (WHERE reminder_sent_on IS NULL
    OR <> сегодня) с проверкой rowcount — второй claim получает None, а не перезаписывает."""
    _, container = app
    await _seed(container, Pupil(ALI))
    async with container() as request:
        assert await (await request.get(DueReminders)).claim(_id(ALI), NOW) is not None
    _stale_snapshot(monkeypatch)
    async with container() as request:
        second = await (await request.get(DueReminders)).claim(_id(ALI), NOW + timedelta(minutes=1))
    assert second is None
    monkeypatch.undo()  # читать дату уже без подменённого снимка
    assert (await _settings(container, ALI)).reminder_sent_on == LOCAL_TODAY


async def test_tick_with_stale_snapshot_does_not_send_second_reminder(
    app: tuple[Dispatcher, AsyncContainer], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, container = app
    await _seed(container, Pupil(ALI))
    tg = ReminderTelegram()
    assert await _tick(container, tg) == 1
    _stale_snapshot(monkeypatch)
    assert await _tick(container, tg, NOW + timedelta(minutes=1)) == 0
    assert len(tg.delivered()) == 1
    assert await _reminder_events(container) == [_id(ALI)]


# ---------- ревью: сбой на одном ученике не обрывает тик ----------
async def test_failure_building_one_reminder_does_not_stop_the_tick(
    app: tuple[Dispatcher, AsyncContainer],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _, container = app
    await _seed(container, Pupil(ALI), Pupil(BOTA))
    real = GetProgress.execute

    async def broken_for_ali(self: GetProgress, learner: LearnerRecord) -> Any:
        if learner.telegram_user_id == ALI:
            raise RuntimeError("progress failed")
        return await real(self, learner)

    monkeypatch.setattr(GetProgress, "execute", broken_for_ali)
    caplog.set_level(logging.DEBUG)
    tg = ReminderTelegram()
    assert await _tick(container, tg) == 1
    assert [m.chat_id for m in tg.delivered()] == [BOTA]
    assert any("RuntimeError" in t for t in _log_texts(caplog)), "сбой на ученике — в лог"
    for line in _log_texts(caplog):
        assert str(ALI) not in line, line


async def test_learner_deleted_between_claim_and_send_does_not_stop_the_tick(
    app: tuple[Dispatcher, AsyncContainer],
) -> None:
    """«Удалить мои данные» во время рассылки: запись события про удалённого падает по FK."""
    _, container = app
    await _seed(container, Pupil(ALI), Pupil(BOTA))
    tg = ReminderTelegram()

    async def delete_ali(chat_id: int) -> None:
        if chat_id == ALI:
            async with container() as request:
                await (await request.get(LearnerRepository)).delete(_id(ALI))
                await (await request.get(UnitOfWork)).commit()

    tg.before_send = delete_ali
    await _tick(container, tg)  # не падает
    assert BOTA in [m.chat_id for m in tg.delivered()]
    assert await _reminder_events(container) == [_id(BOTA)]


# ---------- ревью: падение фоновой задачи видно в логе ----------
async def test_background_job_crash_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    """Ожидаемый интерфейс: ``main.start_background(bot, container, jobs) -> list[Task]`` —
    запускает задачи рядом с polling (``main()`` вызывает её с ``background_jobs()``) и вешает
    на каждую обработчик завершения: исключение задачи → запись ERROR в логгер ``muallim.*``."""
    from muallim.bootstrap import main  # noqa: PLC0415

    async def crash(bot: Bot, container: AsyncContainer) -> None:
        raise RuntimeError("job failed at start")

    caplog.set_level(logging.DEBUG)
    tasks = main.start_background(cast(Bot, None), cast(AsyncContainer, None), (crash,))
    await asyncio.wait(tasks, timeout=1)
    await asyncio.sleep(0)  # обработчики завершения — на следующем шаге цикла
    errors = [
        r for r in caplog.records if r.name.startswith("muallim") and r.levelno >= logging.ERROR
    ]
    assert errors, "задача упала молча"
    assert errors[0].exc_info is not None and isinstance(errors[0].exc_info[1], RuntimeError)


async def test_background_job_cancelled_on_shutdown_is_not_an_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from muallim.bootstrap import main  # noqa: PLC0415

    async def forever(bot: Bot, container: AsyncContainer) -> None:
        await asyncio.Event().wait()

    caplog.set_level(logging.DEBUG)
    tasks = main.start_background(cast(Bot, None), cast(AsyncContainer, None), (forever,))
    await asyncio.sleep(0)
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    await asyncio.sleep(0)
    assert [r for r in caplog.records if r.levelno >= logging.ERROR] == []
