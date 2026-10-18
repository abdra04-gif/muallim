"""Сквозной путь ученика через настоящие обработчики aiogram (TD-FN-06, R-15).

Всё настоящее, кроме Telegram: диспетчер, роутер, DI-контейнер, сценарии, SQLite, заглушка
распознавания (ADR-0006). Вместо серверов Telegram — сессия, которая записывает вызовы API и
отвечает правдоподобными объектами. Так проверяется то, что раньше проверялось только руками
в Telegram: апдейт → обработчик → сценарий → БД → экран.
"""

from collections.abc import AsyncGenerator, AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.filters.callback_data import CallbackData
from aiogram.methods import (
    EditMessageMedia,
    EditMessageText,
    GetFile,
    GetMe,
    SendMessage,
    SendPhoto,
    TelegramMethod,
)
from aiogram.types import (
    CallbackQuery,
    Chat,
    File,
    InlineKeyboardMarkup,
    Message,
    PhotoSize,
    Update,
    User,
    Voice,
)
from dishka import AsyncContainer
from dishka.integrations.aiogram import setup_dishka
from pydantic import SecretStr

from muallim.application.ports.repositories import (
    AttemptRepository,
    LearnerProfileRepository,
    LearnerRepository,
)
from muallim.application.use_cases.curriculum import PublishCurriculum
from muallim.bootstrap.config import Settings
from muallim.bootstrap.di import create_container
from muallim.domain.curriculum import Curriculum
from muallim.infrastructure.db.engine import create_engine
from muallim.infrastructure.db.tables import metadata
from muallim.infrastructure.db.views import create_views
from muallim.presentation.telegram import texts
from muallim.presentation.telegram.callbacks import (
    Consent,
    DeleteData,
    Dispute,
    DisputeReason,
    GoItem,
    Profile,
)
from muallim.presentation.telegram.handlers import router

pytestmark = pytest.mark.integration

BOT_USER = User(id=1, is_bot=True, first_name="Muallim", username="muallim_bot")
NOW = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)


class FakeTelegram(BaseSession):
    """Сервер Telegram в памяти: каждый вызов API записывается, ответы — минимальные объекты."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[TelegramMethod[Any]] = []
        self.shown: list[Message] = []  # все сообщения бота по порядку (новые и изменённые)
        self._next_id = 1000

    async def close(self) -> None:
        return None

    async def make_request(
        self, bot: Bot, method: TelegramMethod[Any], timeout: int | None = None
    ) -> Any:
        self.calls.append(method)
        if isinstance(method, GetMe):
            return BOT_USER
        if isinstance(method, GetFile):
            return File(file_id=method.file_id, file_unique_id="f", file_path="voice/1.oga")
        if isinstance(method, SendMessage | SendPhoto | EditMessageText | EditMessageMedia):
            message = self._message(method).as_(bot)
            self.shown.append(message)
            return message
        return True  # answerCallbackQuery, deleteMessage, editMessageReplyMarkup …

    async def stream_content(
        self,
        url: str,
        headers: dict[str, Any] | None = None,
        timeout: int = 30,
        chunk_size: int = 65536,
        raise_for_status: bool = True,
    ) -> AsyncGenerator[bytes, None]:
        yield b"OggS-fake-voice"  # декодирование — в адаптере модели; заглушке байты не важны

    def _message(
        self, method: SendMessage | SendPhoto | EditMessageText | EditMessageMedia
    ) -> Message:
        if isinstance(method, SendMessage | SendPhoto):
            self._next_id += 1
            message_id = self._next_id
        else:
            assert isinstance(method.message_id, int)
            message_id = method.message_id
        assert isinstance(method.chat_id, int)
        photo = None
        if isinstance(method, SendPhoto | EditMessageMedia):
            photo = [PhotoSize(file_id=f"p{message_id}", file_unique_id="p", width=1, height=1)]
        text = method.text if isinstance(method, SendMessage | EditMessageText) else None
        caption = (
            method.caption if isinstance(method, SendPhoto) else None
        ) or (
            method.media.caption if isinstance(method, EditMessageMedia) else None
        )  # fmt: skip
        markup = (
            method.reply_markup if isinstance(method.reply_markup, InlineKeyboardMarkup) else None
        )
        return Message(
            message_id=message_id,
            date=NOW,
            chat=Chat(id=method.chat_id, type="private"),
            from_user=BOT_USER,
            text=text,
            caption=caption,
            photo=photo,
            reply_markup=markup,
        )

    # --- что увидел ученик ---
    def texts(self) -> list[str]:
        return [m.text or m.caption or "" for m in self.shown]

    def alerts(self) -> list[str]:
        return [
            str(c.text) for c in self.calls if type(c).__name__ == "AnswerCallbackQuery" and c.text
        ]


@dataclass
class Learner:
    """Ученик в чате: пишет, присылает голосовые, нажимает кнопки на последнем экране бота."""

    dp: Dispatcher
    bot: Bot
    tg: FakeTelegram
    user: User
    sent: list[Message] = field(default_factory=list)
    _update_id: int = 0

    async def _feed(self, **payload: Any) -> None:
        self._update_id += 1
        await self.dp.feed_update(self.bot, Update(update_id=self._update_id, **payload))

    def _incoming(self, **content: Any) -> Message:
        self._update_id += 1
        chat = Chat(id=self.user.id, type="private")
        return Message(
            message_id=self._update_id, date=NOW, chat=chat, from_user=self.user, **content
        )

    async def write(self, text: str) -> None:
        await self._feed(message=self._incoming(text=text))

    async def voice(self, duration: int = 2) -> None:
        voice = Voice(file_id="v", file_unique_id="v", duration=duration)
        await self._feed(message=self._incoming(voice=voice))

    def last_screen(self) -> Message:
        """Последнее сообщение бота с кнопками — на нём ученик и нажимает."""
        with_buttons = [m for m in self.tg.shown if m.reply_markup is not None]
        assert with_buttons, "у бота нет ни одного экрана с кнопками"
        return with_buttons[-1].as_(self.bot)

    def button(self, kind: type[CallbackData]) -> str:
        markup = self.last_screen().reply_markup
        assert markup is not None
        prefix = kind.__prefix__ + ":"
        for row in markup.inline_keyboard:
            for b in row:
                if b.callback_data and b.callback_data.startswith(prefix):
                    return b.callback_data
        raise AssertionError(f"на экране нет кнопки {kind.__name__}")

    async def press(self, data: CallbackData | str) -> None:
        packed = data if isinstance(data, str) else data.pack()
        query = CallbackQuery(
            id=str(self._update_id),
            from_user=self.user,
            chat_instance="ci",
            data=packed,
            message=self.last_screen(),
        )
        await self._feed(callback_query=query)


@pytest.fixture
async def bot_app(tmp_path: Path) -> AsyncIterator[tuple[Dispatcher, AsyncContainer]]:
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
        teacher_ids="",
    )
    container = create_container(settings)
    async with container() as request:  # как при старте бота (main.py)
        await (await request.get(PublishCurriculum)).execute()
    dp = Dispatcher()
    dp.include_router(router)
    setup_dishka(container=container, router=dp, auto_inject=True)
    await (
        dp.emit_startup()
    )  # dishka внедряет зависимости в обработчики на старте (как start_polling)
    try:
        yield dp, container
    finally:
        await dp.emit_shutdown()
        await container.close()
        dp.sub_routers.remove(router)  # роутер модульный: отцепить для следующего теста
        router._parent_router = None


@pytest.fixture
def learner_factory(
    bot_app: tuple[Dispatcher, AsyncContainer],
) -> Callable[[int], Learner]:
    dp, _ = bot_app

    def make(telegram_id: int) -> Learner:
        tg = FakeTelegram()
        bot = Bot("1:test", session=tg)
        user = User(id=telegram_id, is_bot=False, first_name="Ученик", language_code="ru")
        return Learner(dp, bot, tg, user)

    return make


def _first_practice_item(curriculum: Curriculum) -> str:
    return next(i.id for lesson in curriculum.lessons for i in lesson.items if i.is_practice)


async def test_new_learner_consents_reads_disputes_and_deletes_data(
    bot_app: tuple[Dispatcher, AsyncContainer],
    learner_factory: Callable[[int], Learner],
    curriculum: Curriculum,
) -> None:
    _, container = bot_app
    ali = learner_factory(5001)

    # 1. /start: приветствие и согласие — до любой записи голоса (FR-09)
    await ali.write("/start")
    assert ali.tg.texts()[:2] == [texts.WELCOME, texts.CONSENT_TEXT]

    # 2. Согласие → анкета один раз (FR-44): 18+ → родной язык → опыт чтения → главный экран
    await ali.press(Consent(granted=True))
    assert texts.CONSENT_SAVED_YES in ali.tg.alerts()
    assert ali.tg.texts()[-1] == texts.PROFILE_ADULT
    await ali.press(Profile(adult=True))
    assert ali.tg.texts()[-1] == texts.PROFILE_LANGUAGE
    await ali.press(Profile(adult=True, lang="kk"))
    assert ali.tg.texts()[-1] == texts.PROFILE_READING
    await ali.press(Profile(adult=True, lang="kk", read="none"))
    assert ali.button(GoItem)  # на главном есть «Начать»/«Продолжить»

    # 3. Открыть строку для чтения и прочитать её голосовым
    await ali.press(GoItem(item_id=_first_practice_item(curriculum)))
    await ali.voice()
    shown = ali.tg.texts()
    assert any(t.startswith(texts.LISTENING.split("{")[0]) for t in shown)
    assert texts.VERDICT_EXCELLENT in shown[-1]  # заглушка «слышит» ровно эталон

    async with container() as request:
        learners = await request.get(LearnerRepository)
        attempts = await request.get(AttemptRepository)
        saved = await learners.get_by_telegram_id(5001)
        assert saved is not None and saved.research_consent
        assert await attempts.count(saved.id) == 1  # попытка в БД (FR-06)

    # 4. «Бот ошибся» → причина → спасибо (FR-23)
    await ali.press(ali.button(Dispute))
    await ali.press(ali.button(DisputeReason))
    assert ali.tg.texts()[-1] == texts.DISPUTE_THANKS

    # 5. Удалить все данные (FR-10)
    await ali.press(DeleteData(confirmed=True))
    assert ali.tg.texts()[-1] == texts.DELETE_DONE
    async with container() as request:
        assert await (await request.get(LearnerRepository)).get_by_telegram_id(5001) is None


async def test_too_short_voice_is_rejected_without_attempt(
    bot_app: tuple[Dispatcher, AsyncContainer],
    learner_factory: Callable[[int], Learner],
) -> None:
    _, container = bot_app
    ali = learner_factory(5002)
    await ali.write("/start")
    await ali.voice(duration=0)
    replies = [c for c in ali.tg.calls if isinstance(c, SendMessage)]
    assert replies[-1].text == texts.VOICE_TOO_SHORT
    async with container() as request:
        saved = await (await request.get(LearnerRepository)).get_by_telegram_id(5002)
        assert saved is not None
        assert await (await request.get(AttemptRepository)).count(saved.id) == 0


async def test_text_instead_of_voice_shows_hint_and_home(
    learner_factory: Callable[[int], Learner],
) -> None:
    ali = learner_factory(5003)
    await ali.write("/start")
    await ali.press(Consent(granted=False))
    await ali.write("салам")
    shown = ali.tg.texts()
    assert texts.SEND_VOICE in shown
    assert ali.button(GoItem)  # после подсказки — главный экран с кнопками


async def test_questionnaire_is_asked_only_once(
    bot_app: tuple[Dispatcher, AsyncContainer], learner_factory: Callable[[int], Learner]
) -> None:
    _, container = bot_app
    ali = learner_factory(5101)
    await ali.write("/start")
    await ali.press(Consent(granted=True))
    await ali.press(Profile(adult=True, lang="ru", read="some_letters"))
    asked = ali.tg.texts().count(texts.PROFILE_ADULT)

    await ali.write("/start")  # вернулся — анкеты больше нет, сразу главный экран
    assert ali.tg.texts().count(texts.PROFILE_ADULT) == asked == 1
    assert ali.button(GoItem)
    async with container() as request:
        learner = await (await request.get(LearnerRepository)).get_by_telegram_id(5101)
        assert learner is not None
        profile = await (await request.get(LearnerProfileRepository)).get(learner.id)
        assert profile is not None and profile.native_language == "ru"


async def test_unfinished_questionnaire_is_asked_on_next_start(
    learner_factory: Callable[[int], Learner],
) -> None:
    ali = learner_factory(5102)
    await ali.write("/start")
    await ali.press(Consent(granted=True))
    await ali.press(Profile(adult=True))  # ушёл, не ответив на язык
    await ali.write("/start")
    assert ali.tg.texts()[-1] == texts.PROFILE_ADULT


async def test_minor_learns_without_research_and_is_not_asked_more(
    bot_app: tuple[Dispatcher, AsyncContainer], learner_factory: Callable[[int], Learner]
) -> None:
    _, container = bot_app
    kid = learner_factory(5103)
    await kid.write("/start")
    await kid.press(Consent(granted=True))
    await kid.press(Profile(adult=False))
    assert texts.PROFILE_MINOR in kid.tg.alerts()
    assert kid.button(GoItem)  # учиться можно
    assert texts.PROFILE_LANGUAGE not in kid.tg.texts()  # остальное у младших не спрашиваем
    async with container() as request:
        learner = await (await request.get(LearnerRepository)).get_by_telegram_id(5103)
        assert learner is not None and not learner.research_consent  # голос не сохраняется


async def test_declined_consent_skips_questionnaire(
    learner_factory: Callable[[int], Learner],
) -> None:
    ali = learner_factory(5104)
    await ali.write("/start")
    await ali.press(Consent(granted=False))
    assert texts.PROFILE_ADULT not in ali.tg.texts()
    assert ali.button(GoItem)
