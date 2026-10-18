"""Проверка бота из терминала: ``uv run muallim --test "/start" "✅ Да, разрешаю" "🎤"``.

Каждый шаг — сообщение, нажатие кнопки по её надписи или голосовое («🎤»). Работают настоящие
обработчики, DI и экраны; вместо Telegram — сессия в памяти, которая печатает ответы бота;
вместо базы — временная SQLite; вместо модели — заглушка (засчитывает любое голосовое).
`.env` не читается: настоящий токен и данные учеников этому режиму не нужны (TD-FN-61, SRC-072).
"""

import html
import re
import tempfile
from collections.abc import AsyncGenerator, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.base import BaseSession
from aiogram.enums import ParseMode
from aiogram.methods import (
    AnswerCallbackQuery,
    DeleteMessage,
    EditMessageMedia,
    EditMessageReplyMarkup,
    EditMessageText,
    GetFile,
    GetMe,
    SendAudio,
    SendMessage,
    SendPhoto,
    SendVoice,
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
from dishka.integrations.aiogram import setup_dishka
from pydantic import SecretStr

from muallim.application.use_cases.curriculum import PublishCurriculum
from muallim.bootstrap.config import Settings
from muallim.bootstrap.di import create_container
from muallim.bootstrap.main import routers
from muallim.infrastructure.db.engine import create_engine
from muallim.infrastructure.db.tables import metadata
from muallim.infrastructure.db.views import create_views

VOICE_STEPS = frozenset({"🎤", "/voice"})
_BOT = User(id=1, is_bot=True, first_name="Muallim", username="muallim_console_bot")
_ME = User(id=1000, is_bot=False, first_name="Ученик", language_code="ru")
_TAG = re.compile(r"<[^>]+>")
NOTICE = (
    "Режим проверки: временная база, без Telegram; распознавание — ЗАГЛУШКА "
    "(любое голосовое засчитывается, ошибки чтения не ищутся)."
)


def plain(text: str) -> str:
    """HTML Telegram → текст для терминала: теги убраны, &lt; и подобные раскрыты."""
    return html.unescape(_TAG.sub("", text))


class _Session(BaseSession):
    """Сессия Telegram в памяти: запоминает, что бот показал, и печатает это в журнал."""

    def __init__(self, log: list[str]) -> None:
        super().__init__()
        self.log = log
        self.shown: list[Message] = []
        self._next_id = 100

    async def close(self) -> None:
        return None

    async def make_request(
        self,
        bot: Bot,
        method: TelegramMethod[Any],
        timeout: int | None = None,  # noqa: ASYNC109 — сигнатура BaseSession aiogram
    ) -> Any:
        if isinstance(method, GetMe):
            return _BOT
        if isinstance(method, GetFile):
            return File(file_id=method.file_id, file_unique_id="f", file_path="voice/1.oga")
        if isinstance(method, SendMessage | SendPhoto | EditMessageText | EditMessageMedia):
            return self._show(bot, method)
        if isinstance(method, SendVoice | SendAudio):
            self.log.append("🤖 [голосовое]" if isinstance(method, SendVoice) else "🤖 [аудио]")
            return self._message(bot, self._new_id(), None, None, None)
        if isinstance(method, EditMessageReplyMarkup):
            self._replace_markup(bot, method)
        elif isinstance(method, DeleteMessage):
            self.shown = [m for m in self.shown if m.message_id != method.message_id]
        elif isinstance(method, AnswerCallbackQuery) and method.text:
            self.log.append(f"🤖 (всплывающее) {method.text}")
        return True

    async def stream_content(
        self,
        url: str,
        headers: dict[str, Any] | None = None,
        timeout: int = 30,  # noqa: ASYNC109 — сигнатура BaseSession aiogram
        chunk_size: int = 65536,
        raise_for_status: bool = True,
    ) -> AsyncGenerator[bytes, None]:
        yield b"OggS-console-voice"  # заглушке распознавания байты не важны

    def _new_id(self) -> int:
        self._next_id += 1
        return self._next_id

    def _show(
        self, bot: Bot, method: SendMessage | SendPhoto | EditMessageText | EditMessageMedia
    ) -> Message:
        edited = isinstance(method, EditMessageText | EditMessageMedia)
        if isinstance(method, EditMessageText | EditMessageMedia):
            if not isinstance(method.message_id, int):  # бот правит свои сообщения в личке
                raise TypeError("правка без message_id — в личном чате так не бывает")
            message_id = method.message_id
        else:
            message_id = self._new_id()
        text = method.text if isinstance(method, SendMessage | EditMessageText) else None
        caption = (
            method.caption if isinstance(method, SendPhoto)
            else method.media.caption if isinstance(method, EditMessageMedia)
            else None
        )  # fmt: skip
        photo = isinstance(method, SendPhoto | EditMessageMedia)
        markup = (
            method.reply_markup if isinstance(method.reply_markup, InlineKeyboardMarkup) else None
        )
        message = self._message(bot, message_id, text, caption, markup, photo=photo)
        self.shown = [m for m in self.shown if m.message_id != message_id] + [message]
        body = plain(text or caption or "")
        head = ("✏️ " if edited else "") + ("[картинка] " if photo else "")
        self.log.append(f"🤖 {head}{body}".rstrip())
        if markup:
            for row in markup.inline_keyboard:
                self.log.append("   " + " ".join(f"[{b.text}]" for b in row))
        return message

    def _replace_markup(self, bot: Bot, method: EditMessageReplyMarkup) -> None:
        markup = (
            method.reply_markup if isinstance(method.reply_markup, InlineKeyboardMarkup) else None
        )
        for k, old in enumerate(self.shown):
            if old.message_id == method.message_id:
                self.shown[k] = old.model_copy(update={"reply_markup": markup}).as_(bot)

    @staticmethod
    def _message(
        bot: Bot,
        message_id: int,
        text: str | None,
        caption: str | None,
        markup: InlineKeyboardMarkup | None,
        *,
        photo: bool = False,
    ) -> Message:
        sizes = [PhotoSize(file_id=f"p{message_id}", file_unique_id="p", width=1, height=1)]
        return Message(
            message_id=message_id, date=datetime.now(UTC), chat=Chat(id=_ME.id, type="private"),
            from_user=_BOT, text=text, caption=caption, photo=sizes if photo else None,
            reply_markup=markup,
        ).as_(bot)  # fmt: skip

    def button(self, label: str) -> tuple[Message, str] | None:
        """Кнопка на последнем экране: точная надпись, иначе — надпись, содержащая шаг."""
        screens = [m for m in self.shown if m.reply_markup is not None]
        if not screens:
            return None
        screen = screens[-1]
        rows = screen.reply_markup.inline_keyboard if screen.reply_markup else []
        buttons = [b for row in rows for b in row if b.callback_data]
        wanted = label.casefold()
        for match in (lambda t: t == wanted, lambda t: wanted in t):
            for b in buttons:
                if match(b.text.casefold()) and b.callback_data:
                    return screen, b.callback_data
        return None


def _settings(folder: Path) -> Settings:
    return Settings(
        _env_file=None,  # pydantic-settings: не читать .env
        bot_token=SecretStr("1:console"),
        database_url=SecretStr(f"sqlite+aiosqlite:///{folder / 'console.sqlite3'}"),
        asr_backend="stub",
        audio_dir=folder / "audio",
        recitations_dir=folder / "recitations",
        teacher_ids="",
        annotator_ids="",
        log_level="WARNING",
    )


async def run_console(steps: Sequence[str]) -> str:
    """Прогоняет шаги через бота и возвращает, что он показал, — по шагам."""
    log: list[str] = [NOTICE, ""]
    with tempfile.TemporaryDirectory(prefix="muallim-console-") as tmp:
        settings = _settings(Path(tmp))
        engine = create_engine(settings.database_url.get_secret_value())
        async with engine.begin() as conn:
            await conn.run_sync(metadata.create_all)
            await conn.run_sync(create_views)
        await engine.dispose()
        container = create_container(settings)
        async with container() as request:
            await (await request.get(PublishCurriculum)).execute()
        session = _Session(log)
        bot = Bot(
            "1:console", session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )
        dp = Dispatcher()
        used = routers()
        dp.include_routers(*used)
        setup_dishka(container=container, router=dp, auto_inject=True)
        await dp.emit_startup()  # dishka внедряет зависимости в обработчики при старте
        try:
            for n, step in enumerate(steps, start=1):
                await _step(dp, bot, session, n=n, step=step)
        finally:
            await dp.emit_shutdown()
            for r in used:  # роутеры — модульные: отцепить, чтобы бот можно было собрать снова
                dp.sub_routers.remove(r)
                r._parent_router = None  # noqa: SLF001 — у aiogram нет публичного «отцепить»
            await container.close()
    return "\n".join(log)


async def _step(dp: Dispatcher, bot: Bot, session: _Session, *, n: int, step: str) -> None:
    log = session.log
    chat = Chat(id=_ME.id, type="private")
    now = datetime.now(UTC)
    if step in VOICE_STEPS:
        log.append("\n▶ 🎤 голосовое")
        voice = Voice(file_id="v", file_unique_id="v", duration=2)
        message = Message(message_id=n, date=now, chat=chat, from_user=_ME, voice=voice)
        await dp.feed_update(bot, Update(update_id=n, message=message))
        return
    pressed = session.button(step)
    if pressed is not None:
        screen, data = pressed
        log.append(f"\n▶ [{step}]")
        query = CallbackQuery(
            id=str(n), from_user=_ME, chat_instance="console", data=data, message=screen
        )
        await dp.feed_update(bot, Update(update_id=n, callback_query=query))
        return
    log.append(f"\n▶ {step}")
    message = Message(message_id=n, date=now, chat=chat, from_user=_ME, text=step)
    await dp.feed_update(bot, Update(update_id=n, message=message))
