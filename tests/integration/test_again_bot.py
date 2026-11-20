"""«Прочитай ещё раз» в боте не засчитано (FR-70 п. 6, 8; ADR-0088 п. 6): ступень ③ закрепления
не отвечена верно, аят из списка ошибок суры не получает ✅ (handlers/voice.py).

Окружение — как в сквозном пути (SQLite, DI, заглушка модели). Заглушка слушателя
(``StubCardListener``) подменена: модель «не уверена» — верное чтение чуть хуже прочих вариантов.
Возврат после басмалы (voice.py, ``opening_active``) здесь не проверяется: его закрывает правило
`tests/architecture/test_card_check_rules.py` (нет сравнений с ``Verdict.FAILED``).
"""

from collections.abc import Callable
from dataclasses import replace
from typing import Any

import pytest
from aiogram import Dispatcher
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from dishka import AsyncContainer
from sqlalchemy.ext.asyncio import AsyncSession

from muallim.domain.curriculum import Curriculum
from muallim.infrastructure.db.repositories.quiz import SqlQuizAnswerRepository
from muallim.infrastructure.db.tables import quiz_answers
from muallim.presentation.telegram import sura_errors
from muallim.presentation.telegram.callbacks import Consent, GoItem, Quiz
from muallim.presentation.telegram.screens import SuraErrorList
from tests.integration import test_bot_flow as flow
from tests.integration import test_quiz_bot as quiz_flow
from tests.integration.test_bot_flow import Learner

pytestmark = pytest.mark.integration

bot_app = flow.bot_app
learner_factory = flow.learner_factory
DUHA = 93


@pytest.fixture
def unsure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Каждое голосовое — «ещё раз»: верное −5, любой другой вариант −3 (маржа от −4 до 0)."""
    from muallim.application.ports.recognition import Listening  # noqa: PLC0415
    from muallim.infrastructure.asr import stub  # noqa: PLC0415

    async def listen(self: Any, audio: bytes, text: str, *, long_is_short: bool) -> Listening:
        reading = text.replace(" ", "")
        return Listening(
            references=(("wasl", reading),),
            model_version="stub",
            audio_duration_ms=0,
            raw="",
            score=lambda variant: -5.0 if variant == reading else -3.0,
            sounds=lambda variant: variant,
        )

    monkeypatch.setattr(stub.StubCardListener, "listen", listen)


async def test_again_does_not_answer_the_read_step_of_the_quiz(
    bot_app: tuple[Dispatcher, AsyncContainer],
    learner_factory: Callable[[int], Learner],
    curriculum: Curriculum,
    unsure: None,
) -> None:
    _, container = bot_app
    ali = await quiz_flow._ready(learner_factory, curriculum, 7206)
    await ali.press(Quiz())
    row = await quiz_flow._open_row(container, 7206)
    async with container() as request:
        session = await request.get(AsyncSession)
        await session.execute(quiz_answers.delete().where(quiz_answers.c.id == row.id))
        await SqlQuizAnswerRepository(session).add(
            replace(row, step=3, item_id=row.letter_id, options=(), answer=-1)
        )
        await session.commit()
    await ali.press(Quiz())
    await ali.voice()
    async with container() as request:
        saved = await SqlQuizAnswerRepository(await request.get(AsyncSession)).get(row.id)
    assert saved is not None and saved.attempt_id is not None
    assert saved.correct is False


async def test_again_does_not_tick_an_ayah_in_the_sura_error_list(
    bot_app: tuple[Dispatcher, AsyncContainer],
    learner_factory: Callable[[int], Learner],
    curriculum: Curriculum,
    unsure: None,
) -> None:
    dp, _ = bot_app
    ayah = next(i for les in curriculum.lessons if les.id == "L100" for i in les.items if i.quran)
    ali = learner_factory(7207)
    await ali.write("/start")
    await ali.press(Consent(granted=False))
    state = FSMContext(dp.storage, StorageKey(bot_id=ali.bot.id, chat_id=7207, user_id=7207))
    await sura_errors.remember(
        state, SuraErrorList(DUHA, "text", 10, 11, ((1, ayah.id, "skipped"),))
    )
    await ali.press(GoItem(item_id=ayah.id))
    await ali.voice()
    errors = await sura_errors.load(state, DUHA)
    assert errors is not None
    assert ayah.id not in errors.fixed
