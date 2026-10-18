"""Разметка в Telegram через настоящие обработчики (FR-17): кто может войти и что сохраняется.

Как tests/integration/test_bot_flow.py: настоящие диспетчер, роутеры, DI, SQLite; вместо
серверов Telegram — сессия в памяти, которая ещё умеет «отправить голосовое».
"""

from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from aiogram import Bot, Dispatcher
from aiogram.methods import SendVoice, TelegramMethod
from aiogram.types import Chat, Message, User
from dishka import AsyncContainer
from dishka.integrations.aiogram import setup_dishka
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from muallim.application.ports.storage import AudioStore
from muallim.application.use_cases.curriculum import PublishCurriculum
from muallim.bootstrap.config import Settings
from muallim.bootstrap.di import create_container
from muallim.bootstrap.main import routers
from muallim.domain.assessment import assess
from muallim.domain.attempt import Attempt
from muallim.domain.learner import Learner as LearnerRecord
from muallim.domain.policy import GradingPolicy
from muallim.infrastructure.db.engine import create_engine
from muallim.infrastructure.db.repositories.attempts import SqlAttemptRepository
from muallim.infrastructure.db.repositories.learners import SqlLearnerRepository
from muallim.infrastructure.db.tables import annotations, metadata
from muallim.infrastructure.db.views import create_views
from muallim.presentation.telegram.callbacks import AnnotateAct
from muallim.research import annotators
from tests.fakes import FixedClock
from tests.integration.test_bot_flow import BOT_USER, NOW, FakeTelegram, Learner

pytestmark = pytest.mark.integration

ANNOTATOR_TG, STRANGER_TG, INVITED_TG = 900, 901, 902


class VoiceTelegram(FakeTelegram):
    """Ещё и голосовые: запоминает, с защитой ли от пересылки они отправлены."""

    def __init__(self) -> None:
        super().__init__()
        self.voices: list[SendVoice] = []

    async def make_request(
        self, bot: Bot, method: TelegramMethod[Any], timeout: int | None = None
    ) -> Any:
        if isinstance(method, SendVoice):
            self.calls.append(method)
            self.voices.append(method)
            self._next_id += 1
            assert isinstance(method.chat_id, int)
            return Message(
                message_id=self._next_id, date=NOW, chat=Chat(id=method.chat_id, type="private"),
                from_user=BOT_USER,
            ).as_(bot)  # fmt: skip
        return await super().make_request(bot, method, timeout)


@pytest.fixture
async def app(tmp_path: Path) -> AsyncIterator[tuple[Dispatcher, AsyncContainer]]:
    url = f"sqlite+aiosqlite:///{tmp_path / 'bot.sqlite3'}"
    engine = create_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)
        await conn.run_sync(create_views)
    await engine.dispose()
    settings = Settings(
        bot_token=SecretStr("1:test"),
        database_url=SecretStr(url),
        asr_backend="stub",
        audio_dir=tmp_path / "audio",
        reference_audio_dir=tmp_path / "reference",
        recitations_dir=tmp_path / "recitations",
        annotator_ids=f"A1:{ANNOTATOR_TG}",
    )
    container = create_container(settings)
    async with container() as request:
        await (await request.get(PublishCurriculum)).execute()
        await _seed(await request.get(AsyncSession), await request.get(AudioStore))
    dp = Dispatcher()
    used = routers()
    dp.include_routers(*used)
    setup_dishka(container=container, router=dp, auto_inject=True)
    await dp.emit_startup()
    try:
        yield dp, container
    finally:
        await dp.emit_shutdown()
        await container.close()
        for r in used:
            dp.sub_routers.remove(r)
            r._parent_router = None


async def _seed(session: AsyncSession, store: AudioStore) -> None:
    """Одна попытка ученика с согласием и записью: бот услышал س вместо ص."""
    clock = FixedClock()
    learner = LearnerRecord(UUID(int=1), 111, "L-aaaa", "ru", clock.now(), research_consent=True)
    await SqlLearnerRepository(session).add(learner)
    sha = await store.save(b"OggS-learner-voice")
    result = assess("صَ", "سَ")
    await SqlAttemptRepository(session).add(
        Attempt(UUID(int=10), learner.id, "L01-14", "v1", "muaalem", result,
                GradingPolicy().verdict(result), sha, 900, 10, clock.now()),
        ("msg",),
    )  # fmt: skip
    await session.commit()


@pytest.fixture
def person(
    app: tuple[Dispatcher, AsyncContainer],
) -> Callable[[int], tuple[Learner, VoiceTelegram]]:
    dp, _ = app

    def make(telegram_id: int) -> tuple[Learner, VoiceTelegram]:
        tg = VoiceTelegram()
        bot = Bot("1:test", session=tg)
        user = User(id=telegram_id, is_bot=False, first_name="Человек", language_code="ru")
        return Learner(dp, bot, tg, user), tg

    return make


async def _labels(container: AsyncContainer) -> list[dict[str, Any]]:
    async with container() as request:
        session = await request.get(AsyncSession)
        rows = (await session.execute(select(annotations))).mappings().all()
        return [dict(r) for r in rows]


def _act(act: str) -> str:
    return AnnotateAct(a=UUID(int=10).hex, act=act).pack()


async def test_stranger_sees_nothing_of_annotation(
    app: tuple[Dispatcher, AsyncContainer], person: Callable[[int], tuple[Learner, VoiceTelegram]]
) -> None:
    _, container = app
    stranger, tg = person(STRANGER_TG)
    await stranger.write("/annotate")
    assert tg.voices == []  # ни одной записи ученика
    assert not any("A1" in t or "разметк" in t.lower() for t in tg.texts())
    # подделанная кнопка тоже не работает: доступ проверяется на каждом нажатии
    await stranger.press(_act("ok"))
    assert await _labels(container) == []


async def test_annotator_from_settings_confirms_bot(
    app: tuple[Dispatcher, AsyncContainer], person: Callable[[int], tuple[Learner, VoiceTelegram]]
) -> None:
    _, container = app
    annotator, tg = person(ANNOTATOR_TG)
    await annotator.write("/annotate")
    (voice,) = tg.voices
    assert voice.protect_content is True  # запись ученика нельзя переслать или сохранить
    shown = "\n".join(tg.texts())
    assert "ص → س" in shown and "سَ" in shown  # видит, что нашёл и что услышал бот
    assert "L-aaaa" not in shown and "111" not in shown  # и не видит, кто ученик

    await annotator.press(annotator.button(AnnotateAct))  # первая кнопка — «бот прав»
    (label,) = await _labels(container)
    assert (label["annotator"], label["label"], label["corrected_phonemes"]) == ("A1", "agree", "سَ")
    assert label["source"] == "telegram" and label["seconds_spent"] is not None


async def test_annotator_fixes_phonemes_with_hints(
    app: tuple[Dispatcher, AsyncContainer], person: Callable[[int], tuple[Learner, VoiceTelegram]]
) -> None:
    _, container = app
    annotator, tg = person(ANNOTATOR_TG)
    await annotator.write("/annotate")
    await annotator.press(_act("fix"))
    await annotator.write("أَ")  # описка: хамза другим знаком
    assert "хамза пишется одним знаком «ء»" in tg.texts()[-1]
    assert await _labels(container) == []
    await annotator.write("صَ")
    (label,) = await _labels(container)
    assert (label["label"], label["corrected_phonemes"]) == ("fix", "صَ")


async def test_invited_annotator_gets_in_with_code_once(
    app: tuple[Dispatcher, AsyncContainer], person: Callable[[int], tuple[Learner, VoiceTelegram]]
) -> None:
    _, container = app
    async with container() as request:
        session = await request.get(AsyncSession)
        code = await annotators.create_invite(session, "A2", FixedClock())
        await session.commit()
    invited, tg = person(INVITED_TG)
    await invited.write(f"/annotate {code}")
    assert len(tg.voices) == 1
    await invited.press(_act("bad"))
    (label,) = await _labels(container)
    assert (label["annotator"], label["label"]) == ("A2", "audio_unusable")

    other, other_tg = person(STRANGER_TG)
    await other.write(f"/annotate {code}")  # код уже использован
    assert other_tg.voices == []


async def test_revoked_annotator_loses_access_immediately(
    app: tuple[Dispatcher, AsyncContainer], person: Callable[[int], tuple[Learner, VoiceTelegram]]
) -> None:
    _, container = app
    annotator, _ = person(ANNOTATOR_TG)
    await annotator.write("/annotate")
    async with container() as request:
        session = await request.get(AsyncSession)
        await annotators.revoke(session, "A1", FixedClock())
        await session.commit()
    await annotator.press(_act("ok"))
    assert await _labels(container) == []
