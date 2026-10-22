"""Начало занятия: истиаза и басмала раз в день, двумя голосовыми подряд (ADR-0050, SRC-110).

Предпочтительный способ — остановка после истиазы и после басмалы (каждая — аят), поэтому
ученик читает две карточки урока 1 по очереди, а потом возвращается туда, где остановился.
"""

from collections.abc import AsyncIterator, Awaitable, Callable
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
from muallim.presentation.telegram import texts
from muallim.presentation.telegram.callbacks import DeleteData, GoItem, Home, Opening
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


# ---------- начало занятия не сдвигает «Продолжить» (FR-49, второй круг) ----------
async def _current_item(container: AsyncContainer) -> str | None:
    async with container() as request:
        learner = await (await request.get(LearnerRepository)).get_by_telegram_id(TG)
    assert learner is not None
    current: str | None = learner.current_item_id
    return current


async def test_opening_does_not_move_continue(app: tuple[Dispatcher, AsyncContainer]) -> None:
    dp, container = app
    ali = _person(dp)
    await ali.write("/start")
    await ali.press(Opening(act="start"))  # истиаза
    await ali.voice()
    await ali.press(GoItem(item_id=OPENING_ITEMS[1]))  # басмала
    await ali.voice()
    await ali.press(Home())
    assert ali.button(GoItem) == GoItem(item_id=RESUME).pack(), "«Продолжить» — где остановился"
    assert await _current_item(container) == RESUME


@pytest.mark.parametrize("leave", ["/start", "home"])
async def test_interrupted_opening_keeps_continue(
    app: tuple[Dispatcher, AsyncContainer], leave: str
) -> None:
    """Прочитал истиазу и ушёл на главную — «Продолжить» ведёт туда же, а не в урок 1."""
    dp, container = app
    ali = _person(dp)
    await ali.write("/start")
    await ali.press(Opening(act="start"))
    await ali.voice()
    if leave == "home":
        await ali.press(Home())
    else:
        await ali.write("/start")
    assert texts.OPENING_TITLE not in ali.tg.texts()[-1]  # сегодня уже занимался — главная
    assert ali.button(GoItem) == GoItem(item_id=RESUME).pack()
    assert await _current_item(container) == RESUME


# ---------- третий круг: начало занятия не сдвигает курсор и снимается (FR-49, FR-50) ----------
# Решения автора 2026-10-20: кнопки на шагах начала занятия курсор не двигают; голосовое при
# открытой главной не оценивается (VOICE_ON_HOME + «Продолжить»); начало занятия живёт один день.
Steps = Callable[[Learner], Awaitable[None]]


def _labels(ali: Learner) -> list[tuple[str, str]]:
    markup = ali.last_screen().reply_markup
    assert markup is not None
    return [(b.text, b.callback_data or "") for row in markup.inline_keyboard for b in row]


async def _press_label(ali: Learner, prefix: str) -> None:
    """Нажать кнопку последнего экрана по началу надписи — как ученик."""
    found = [data for text, data in _labels(ali) if text.startswith(prefix)]
    assert found, f"нет кнопки «{prefix}…»: {_labels(ali)}"
    await ali.press(found[0])


async def _opening_attempts(container: AsyncContainer) -> list[str]:
    """Попытки на истиазе и басмале (в _seed — две вчерашние)."""
    from sqlalchemy import select  # noqa: PLC0415

    from muallim.infrastructure.db.tables import attempts  # noqa: PLC0415

    async with container() as request:
        session = await request.get(AsyncSession)
        rows = await session.execute(
            select(attempts.c.item_id).where(attempts.c.item_id.in_(OPENING_ITEMS))
        )
        return [r[0] for r in rows]


async def _home_continue(ali: Learner) -> str:
    """🏠 → главная (если снова предложено начало занятия — «Пропустить») → «Продолжить»."""
    await ali.press(Home())
    if texts.OPENING_TITLE in ali.tg.texts()[-1]:
        await ali.press(Opening(act="skip"))
    head = texts.CONTINUE_BUTTON.split("{")[0]
    found = [data for text, data in _labels(ali) if text.startswith(head)]
    assert found, _labels(ali)
    return found[0]


async def _back_from_isti_adha_card(ali: Learner) -> None:
    await ali.press(Opening(act="start"))
    await _press_label(ali, texts.BACK_BUTTON)  # «◀️ Назад» → правило урока 1


async def _basmala_read(ali: Learner) -> None:
    await ali.press(Opening(act="start"))
    await ali.voice()  # истиаза
    await _press_label(ali, texts.NEXT_BUTTON)  # → басмала
    await ali.voice()  # басмала


async def _again_after_basmala(ali: Learner) -> None:
    await _basmala_read(ali)
    await _press_label(ali, texts.AGAIN_BUTTON)


async def _back_from_basmala_result(ali: Learner) -> None:
    await _basmala_read(ali)
    await _press_label(ali, texts.BACK_BUTTON)


async def _next_lesson_from_basmala_card(ali: Learner) -> None:
    await ali.press(Opening(act="start"))
    await ali.voice()
    await _press_label(ali, texts.NEXT_BUTTON)  # → басмала
    await _press_label(ali, texts.NEXT_LESSON_BUTTON.split("{")[0])  # «➡️ Следующий урок»


@pytest.mark.parametrize(
    "steps",
    [
        _back_from_isti_adha_card,
        _again_after_basmala,
        _back_from_basmala_result,
        _next_lesson_from_basmala_card,
    ],
    ids=["back_from_isti_adha", "again_after_basmala", "back_from_basmala", "next_lesson"],
)
async def test_opening_buttons_do_not_move_cursor(
    app: tuple[Dispatcher, AsyncContainer], steps: Steps
) -> None:
    dp, container = app
    ali = _person(dp)
    await ali.write("/start")
    await steps(ali)
    assert await _current_item(container) == RESUME
    assert await _home_continue(ali) == GoItem(item_id=RESUME).pack()
    assert await _current_item(container) == RESUME


async def _leave_by_skip(ali: Learner) -> None:
    await ali.press(Home())  # сегодня ещё не читал — снова «Начнём занятие»
    await ali.press(Opening(act="skip"))


async def _leave_by_home(ali: Learner) -> None:
    await ali.press(Home())


async def _leave_by_start(ali: Learner) -> None:
    await ali.write("/start")


@pytest.mark.parametrize(
    "leave", [_leave_by_skip, _leave_by_home, _leave_by_start], ids=["skip", "home", "start"]
)
async def test_left_opening_does_not_take_voice(
    app: tuple[Dispatcher, AsyncContainer], leave: Steps
) -> None:
    """Открыл истиазу и ушёл — следующее голосовое уже не попытка истиазы или басмалы."""
    dp, container = app
    ali = _person(dp)
    await ali.write("/start")
    await ali.press(Opening(act="start"))
    await leave(ali)
    await ali.voice()
    assert len(await _opening_attempts(container)) == 2  # только вчерашние из _seed


async def test_deleted_data_ends_opening(app: tuple[Dispatcher, AsyncContainer]) -> None:
    dp, container = app
    ali = _person(dp)
    await ali.write("/start")
    await ali.press(Opening(act="start"))
    await ali.press(DeleteData(confirmed=True))
    assert texts.DELETE_DONE in ali.tg.texts()[-1]
    await ali.voice()
    assert await _opening_attempts(container) == []  # вчерашние удалены, новых нет


@pytest.mark.parametrize("leave", ["skip", "home"])
async def test_voice_on_home_is_not_assessed(
    app: tuple[Dispatcher, AsyncContainer], leave: str, curriculum: Curriculum
) -> None:
    """На экране главная — урок не открыт: попытку не пишем, предлагаем открыть урок."""
    dp, container = app
    ali = _person(dp)
    await ali.write("/start")
    if leave == "skip":
        await ali.press(Opening(act="skip"))
    else:
        await ali.press(Opening(act="skip"))
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
    title = curriculum.locate(target)[0].title
    assert (texts.CONTINUE_BUTTON.format(title=title), GoItem(item_id=target).pack()) in buttons
    async with container() as request:
        assert await (await request.get(AttemptRepository)).count(learner.id) == before


async def test_voice_after_opening_a_card_is_assessed(
    app: tuple[Dispatcher, AsyncContainer],
) -> None:
    dp, _ = app
    ali = _person(dp)
    await ali.write("/start")
    await ali.press(Opening(act="skip"))
    await ali.press(GoItem(item_id="L006-02"))
    await ali.voice()
    assert texts.VERDICT_EXCELLENT in ali.tg.texts()[-1]
    assert texts.VOICE_ON_HOME not in ali.tg.texts()


async def test_yesterdays_unfinished_opening_does_not_take_todays_voice(
    app: tuple[Dispatcher, AsyncContainer], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Начало занятия помнит дату (по часам бота, Clock): вчерашнее сегодня уже не действует."""
    dp, container = app
    ali = _person(dp)
    await ali.write("/start")
    await ali.press(Opening(act="start"))  # открыл истиазу и не прочитал
    real_now = SystemClock.now
    monkeypatch.setattr(SystemClock, "now", lambda self: real_now(self) + timedelta(days=1))
    await ali.voice()  # на следующий день, карточка истиазы всё ещё на экране
    assert len(await _opening_attempts(container)) == 2  # только вчерашние из _seed
    assert await _current_item(container) == RESUME


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
    await ali.press(Opening(act="skip"))
    await ali.press(GoItem(item_id="L006-02"))  # карточка открыта
    await ali.write("/abc")  # неизвестная команда — главная
    before = await _attempt_count(container)
    await ali.voice()
    assert texts.VOICE_ON_HOME in ali.tg.texts()
    assert await _attempt_count(container) == before


async def test_lesson_chosen_from_list_during_opening_moves_cursor(
    app: tuple[Dispatcher, AsyncContainer], curriculum: Curriculum
) -> None:
    """TD-FN-90 п. 3 (FR-49): выбор урока из «📚 Уроки» посреди начала занятия — сознательный.

    Он завершает начало занятия, и карточка урока двигает «Продолжить».
    """
    from muallim.presentation.telegram.callbacks import Lessons  # noqa: PLC0415
    from muallim.presentation.telegram.screens import LESSONS_PER_PAGE  # noqa: PLC0415

    dp, container = app
    ali = _person(dp)
    await ali.write("/start")
    await ali.press(Opening(act="start"))  # истиаза на экране, начало занятия идёт
    part = next(
        k for k, (_, ls) in enumerate(curriculum.parts()) if any(x.id == "L007" for x in ls)
    )
    index = [x.id for x in curriculum.parts()[part][1]].index("L007")
    await ali.press(Lessons(part=part, page=index // LESSONS_PER_PAGE))
    target = GoItem(item_id="L007-01").pack()
    assert target in [data for _, data in _labels(ali)], _labels(ali)
    await ali.press(target)
    assert await _current_item(container) == "L007-01"
    assert await _home_continue(ali) == target


# басмала — последний шаг: «Продолжить» ведёт в урок 2 (FR-49), круга нет
@pytest.mark.parametrize("cursor", [OPENING_ITEMS[0]])
async def test_no_opening_when_cursor_is_on_opening_card(
    app: tuple[Dispatcher, AsyncContainer], cursor: str
) -> None:
    """TD-FN-90 п. 5 (ADR-0050, ADR-0058): урок 1 пройден, ученик вернулся повторить истиазу или
    басмалу — курсор на L001-02/03. Начало занятия не предлагается: иначе «Продолжить» после
    басмалы снова открывает его по кругу."""
    dp, container = app
    async with container() as request:
        session = await request.get(AsyncSession)
        repo = SqlLearnerRepository(session)
        learner = await repo.get_by_telegram_id(TG)
        assert learner is not None
        learner.current_item_id = cursor
        await repo.save(learner)
        await session.commit()
    ali = _person(dp)
    await ali.write("/start")  # новый день: сегодня ещё не занимался
    assert texts.OPENING_TITLE not in ali.tg.texts()[-1]
    assert ali.button(GoItem) == GoItem(item_id=cursor).pack()


async def test_voice_on_menu_is_not_downloaded(app: tuple[Dispatcher, AsyncContainer]) -> None:
    """TD-FN-90 п. 6 (FR-50): на экране меню голосовое не оценивается — и не скачивается."""
    from aiogram.methods import GetFile  # noqa: PLC0415

    dp, _ = app
    ali = _person(dp)
    await ali.write("/start")
    await ali.press(Opening(act="skip"))  # главная
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
    await ali.press(Opening(act="skip"))
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
