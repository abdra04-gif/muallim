"""Вернувшийся ученик: главная, голосовое вне урока, «Продолжить» (FR-49, FR-50, TD-FN-90).

Ежедневное «начало занятия» с истиазой и басмалой (ADR-0050) убрано: истиазы в книге нет (автор
2026-11-21). Ученик, прошедший урок 1 вчера, сразу видит главную; кнопки «начала занятия» из
старых сообщений бота не роняют его, а показывают главную.
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

from muallim.application.ports.repositories import AttemptRepository, LearnerRepository
from muallim.application.use_cases.curriculum import PublishCurriculum
from muallim.bootstrap.config import Settings
from muallim.bootstrap.di import create_container
from muallim.domain.assessment import assess
from muallim.domain.attempt import Attempt
from muallim.domain.curriculum import Curriculum
from muallim.domain.learner import Learner as LearnerRecord
from muallim.domain.policy import GradingPolicy
from muallim.infrastructure.db.engine import create_engine
from muallim.infrastructure.db.repositories.attempts import SqlAttemptRepository
from muallim.infrastructure.db.repositories.learners import SqlLearnerRepository
from muallim.infrastructure.db.tables import metadata
from muallim.infrastructure.db.views import create_views
from muallim.infrastructure.system import SystemClock
from muallim.presentation.telegram import screens, texts
from muallim.presentation.telegram.callbacks import GoItem, Home, Opening
from muallim.presentation.telegram.handlers import router
from tests.integration.test_bot_flow import FakeTelegram, Learner

pytestmark = pytest.mark.integration

TG = 6001
RESUME = "L006-01"
BASMALA = "L001-03"  # старая попытка снятой карточки (урок L001 снят, ADR-0089) — как в живой БД


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
    for n, item_id in enumerate((BASMALA,), start=1):
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


async def _current_item(container: AsyncContainer) -> str | None:
    async with container() as request:
        learner = await (await request.get(LearnerRepository)).get_by_telegram_id(TG)
    assert learner is not None
    current: str | None = learner.current_item_id
    return current


def _labels(ali: Learner) -> list[tuple[str, str]]:
    markup = ali.last_screen().reply_markup
    assert markup is not None
    return [(b.text, b.callback_data or "") for row in markup.inline_keyboard for b in row]


async def _press_label(ali: Learner, prefix: str) -> None:
    """Нажать кнопку последнего экрана по началу надписи — как ученик."""
    found = [data for text, data in _labels(ali) if text.startswith(prefix)]
    assert found, f"нет кнопки «{prefix}…»: {_labels(ali)}"
    await ali.press(found[0])


# ---------- «начало занятия» убрано (автор 2026-11-21) ----------
async def test_returning_learner_goes_straight_home(
    app: tuple[Dispatcher, AsyncContainer],
) -> None:
    """Урок 1 пройден вчера, сегодня не занимался — сразу главная, «Продолжить» где остановился."""
    dp, _ = app
    ali = _person(dp)
    await ali.write("/start")
    assert ali.button(GoItem) == GoItem(item_id=RESUME).pack()
    assert not [d for _, d in _labels(ali) if d.startswith(Opening.__prefix__)]
    assert "истиаз" not in ali.tg.texts()[-1].casefold()


@pytest.mark.parametrize("act", ["start", "skip"])
async def test_old_opening_button_shows_home(
    app: tuple[Dispatcher, AsyncContainer], act: str
) -> None:
    """«🎙 Читать истиазу» / «⏭ Пропустить» из старого сообщения — главная, курсор на месте."""
    dp, container = app
    ali = _person(dp)
    await ali.write("/start")
    await ali.press(Opening(act=act))
    assert ali.button(GoItem) == GoItem(item_id=RESUME).pack()
    assert "истиаз" not in ali.tg.texts()[-1].casefold()
    assert await _current_item(container) == RESUME


async def test_voice_on_a_card_removed_from_the_program_is_not_assessed(
    app: tuple[Dispatcher, AsyncContainer],
) -> None:
    """Ревью 2026-11-21: на экране осталась истиаза L001-02 («начало занятия» при выкладке) —
    голосовое не засчитывается чужой карточке: «открой урок», попытки нет, на экране меню."""
    from muallim.application.ports.repositories import LearnerSettingsRepository  # noqa: PLC0415

    dp, container = app
    async with container() as request:
        repo = await request.get(LearnerSettingsRepository)
        await repo.change(UUID(int=1), {"screen_item_id": "L001-02", "screen_opening": True})
        await (await request.get(AsyncSession)).commit()
    before = await _attempt_count(container)
    ali = _person(dp)
    await ali.voice()
    assert texts.VOICE_ON_HOME in ali.tg.texts()
    assert await _attempt_count(container) == before
    await ali.voice()  # экран уже меню — снова не засчитано
    assert await _attempt_count(container) == before


@pytest.mark.parametrize("leave", ["menu", "home"])
async def test_voice_on_home_is_not_assessed(
    app: tuple[Dispatcher, AsyncContainer], leave: str, curriculum: Curriculum
) -> None:
    """На экране главная — урок не открыт: попытку не пишем, предлагаем открыть урок."""
    dp, container = app
    ali = _person(dp)
    await ali.write("/start")
    if leave == "home":
        await ali.press(GoItem(item_id="L006-02"))
        await ali.voice()  # урок открыт — оценивается
        await ali.press(Home())
    async with container() as request:
        learner = await (await request.get(LearnerRepository)).get_by_telegram_id(TG)
        assert learner is not None
        before = await (await request.get(AttemptRepository)).count(learner.id)
    await ali.voice()
    assert texts.VOICE_ON_HOME in ali.tg.texts()
    reply = [m for m in ali.tg.shown if (m.text or "") == texts.VOICE_ON_HOME]
    assert reply and reply[-1].reply_markup is not None
    buttons = [
        (b.text, b.callback_data) for row in reply[-1].reply_markup.inline_keyboard for b in row
    ]
    target = "L006-02" if leave == "home" else RESUME
    title = screens.where(curriculum, curriculum.item(target))  # «Стр. 11 · م · Мим»
    assert (texts.CONTINUE_BUTTON.format(title=title), GoItem(item_id=target).pack()) in buttons
    async with container() as request:
        assert await (await request.get(AttemptRepository)).count(learner.id) == before


async def test_voice_after_opening_a_card_is_assessed(
    app: tuple[Dispatcher, AsyncContainer],
) -> None:
    dp, _ = app
    ali = _person(dp)
    await ali.write("/start")
    await ali.press(GoItem(item_id="L006-02"))
    await ali.voice()
    assert texts.VERDICT_EXCELLENT in ali.tg.texts()[-1]
    assert texts.VOICE_ON_HOME not in ali.tg.texts()


# ---------- TD-FN-90 без изменения схемы (пакет Б, круг 1; ADR-0061, ADR-0058) ----------
async def _attempt_count(container: AsyncContainer) -> int:
    async with container() as request:
        learner = await (await request.get(LearnerRepository)).get_by_telegram_id(TG)
        assert learner is not None
        count: int = await (await request.get(AttemptRepository)).count(learner.id)
    return count


async def test_unknown_command_marks_menu_so_voice_is_not_assessed(
    app: tuple[Dispatcher, AsyncContainer],
) -> None:
    """TD-FN-90 п. 2 (FR-50): «/abc» показывает главную — на экране меню, голосовое не в зачёт."""
    dp, container = app
    ali = _person(dp)
    await ali.write("/start")
    await ali.press(GoItem(item_id="L006-02"))  # карточка открыта
    await ali.write("/abc")  # неизвестная команда — главная
    before = await _attempt_count(container)
    await ali.voice()
    assert texts.VOICE_ON_HOME in ali.tg.texts()
    assert await _attempt_count(container) == before


async def test_voice_on_menu_is_not_downloaded(app: tuple[Dispatcher, AsyncContainer]) -> None:
    """TD-FN-90 п. 6 (FR-50): на экране меню голосовое не оценивается — и не скачивается."""
    from aiogram.methods import GetFile  # noqa: PLC0415

    dp, _ = app
    ali = _person(dp)
    await ali.write("/start")
    await ali.voice()
    assert texts.VOICE_ON_HOME in ali.tg.texts()
    assert not [c for c in ali.tg.calls if isinstance(c, GetFile)], "запись с главной скачана"


async def test_quiz_answer_shows_the_options_the_learner_saw(
    app: tuple[Dispatcher, AsyncContainer],
    curriculum: Curriculum,
) -> None:
    """TD-FN-90 п. 4 (ADR-0025, FR-49): ответ закрепления показывает ровно те варианты, что были
    на кнопках, даже если между вопросом и ответом ученик начал новый урок буквы. С ADR-0066
    варианты хранятся в строке ``quiz_answers`` с момента показа."""
    from muallim.infrastructure.db.repositories.quiz import SqlQuizAnswerRepository  # noqa: PLC0415
    from muallim.presentation.telegram.callbacks import Quiz, QuizAnswer  # noqa: PLC0415

    lessons = {les.id: les for les in curriculum.lessons}
    dp, container = app
    ali = _person(dp)
    await ali.write("/start")
    for lesson in ("L003", "L005"):  # начаты уроки букв: по попытке в каждом
        practice = next(i for i in lessons[lesson].items if i.is_practice)
        await ali.press(GoItem(item_id=practice.id))
        await ali.voice()
    await ali.press(Quiz())
    asked = [(text, data) for text, data in _labels(ali) if data.startswith(QuizAnswer.__prefix__)]
    async with container() as request:
        rows = await SqlQuizAnswerRepository(await request.get(AsyncSession)).history(UUID(int=1))
    shown = rows[-1]
    assert [text for text, _ in asked] == list(shown.options)

    await ali.press(GoItem(item_id="L004-02"))  # начал новый урок буквы (курсор — урок 4)
    await ali.press(asked[(shown.answer + 1) % 4][1])  # неверно, кнопкой со старого экрана
    answered = [text for text, data in _labels(ali) if data == "noop"]
    assert answered == list(shown.options), "на экране ответа — те же варианты, что на кнопках"
