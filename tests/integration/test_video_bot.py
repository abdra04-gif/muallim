"""FR-56 (ADR-0074): ролик «🎬 Как произносить» через настоящие обработчики aiogram.

Решения автора 2026-10-25: где для текста карточки есть ролик — только ролик: на карточке нет 🔊,
есть «🎬 Как произносить»; автозвук над карточкой (настройка 🔊, ADR-0061) заменяется автороликом,
голосовое не уходит; после попытки — ролик. Где ролика нет — всё как было (FR-20). Ролик уходит
``send_video`` (``supports_streaming``, размеры и длительность); второй раз — по ``file_id`` из
памяти ``Display`` (ключ ``video:<ключ ролика>``); устаревший ``file_id`` — загрузить файлом
заново. Авторолик — при каждом открытии карточки, как автозвук. Сбой отправки — карточка всё равно
показана, в лог — предупреждение, события нет. Каждый успешный показ — событие ``video_played``
{video, item_id | letter, from}.

Настоящие DI и SQLite; ролики — временная папка с фальшивым mp4 (``Settings.video_dir``),
распознавание — заглушка, «Как читается» — подменён (как в test_settings_bot.py).
"""

import logging
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import pytest
from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import (
    AnswerCallbackQuery,
    SendAudio,
    SendVideo,
    SendVoice,
    TelegramMethod,
)
from aiogram.types import BufferedInputFile, Chat, Message, Video
from dishka import AsyncContainer
from dishka.integrations.aiogram import setup_dishka
from pydantic import SecretStr

from muallim.application.ports.recognition import Recognition
from muallim.application.use_cases.curriculum import PublishCurriculum
from muallim.bootstrap.config import PROJECT_ROOT, Settings
from muallim.bootstrap.di import create_container
from muallim.infrastructure.asr.reading import QuranReadingGuide
from muallim.infrastructure.asr.stub import StubRecognizer
from muallim.infrastructure.db.engine import create_engine
from muallim.infrastructure.db.tables import metadata
from muallim.infrastructure.db.views import create_views
from muallim.presentation.telegram import texts
from muallim.presentation.telegram.callbacks import GoItem, Home, LettersSheet
from muallim.presentation.telegram.display import Display
from muallim.presentation.telegram.handlers import router
from tests.fakes import ScriptedReadingGuide
from tests.integration.test_bot_flow import BOT_USER, NOW, Learner
from tests.integration.test_settings_bot import (
    CARD_MARK,
    PUPIL,
    VoiceTelegram,
    _buttons,
    _card_caption,
    _deleted,
    _events,
    _on_home,
    _set,
)

pytestmark = pytest.mark.integration

RA = "L004-02"  # رَ — эталон есть (файл учителя), ролик есть
RI = "L004-03"  # رِ — эталона нет, ролик есть
RA_LINE = "L004-06"  # رَرْ رِرْ رُرْ أَرْ إِرْ أُرْ — у строки ролика нет
MA = "L006-02"  # مَ — эталон есть, ролика нет
MIM = "L006"
SECONDS = 4.29
FAKE_MP4 = b"\x00\x00\x00\x18ftypmp42-fake"


class VideoTelegram(VoiceTelegram):
    """Ещё и ролики: ответ — сообщение с ``video.file_id``; ``fail_video`` — Telegram отказал."""

    fail_video = False
    stale_file_ids = False  # Telegram не узнаёт file_id (сменился бот, файл удалён)

    def __init__(self) -> None:
        super().__init__()
        self.video_ids: list[int] = []  # номера сообщений с роликом
        self.rejected: list[SendVideo] = []  # отклонённые отправки

    async def make_request(
        self, bot: Bot, method: TelegramMethod[Any], timeout: int | None = None
    ) -> Any:
        if isinstance(method, SendVideo):
            if self.stale_file_ids and isinstance(method.video, str):
                self.rejected.append(method)
                raise TelegramBadRequest(
                    method=method, message="Bad Request: wrong file identifier/HTTP URL specified"
                )
            if self.fail_video:
                self.rejected.append(method)
                raise TelegramBadRequest(method=method, message="Bad Request: file is too big")
            self.calls.append(method)
            self._next_id += 1
            self.video_ids.append(self._next_id)
            assert isinstance(method.chat_id, int)
            video = Video(
                file_id=f"vid{self._next_id}", file_unique_id="u", width=1280, height=720,
                duration=4,
            )  # fmt: skip
            return Message(
                message_id=self._next_id, date=NOW, chat=Chat(id=method.chat_id, type="private"),
                from_user=BOT_USER, video=video,
            ).as_(bot)  # fmt: skip
        return await super().make_request(bot, method, timeout)


def _video_dir(root: Path) -> Path:
    """Ролики слогов رَ, رِ и тройка буквы ر (тексты — curriculum/course.ru.yaml)."""
    root.mkdir()
    rows = []
    for text, letter, name in (
        ("رَ", "", "ra.mp4"),
        ("رِ", "", "ri.mp4"),
        ("رَ رِ رُ", "ر", "ra3.mp4"),
    ):
        (root / name).write_bytes(FAKE_MP4 + name.encode())
        rows.append(
            f"- text: {text}\n" + (f"  letter: {letter}\n" if letter else "")
            + f"  file: {name}\n  seconds: {SECONDS}\n  width: 1280\n  height: 720\n"
            "  status: ok\n  source: SRC-144\n  picture: SRC-148\n"
            "  origin: curriculum/audio/library/1e3d7cd47ac8f84d.ogg\n"
        )  # fmt: skip
    (root / "videos.yaml").write_text("".join(rows), encoding="utf-8")
    return root


@pytest.fixture
async def app(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[tuple[Dispatcher, AsyncContainer]]:
    monkeypatch.setattr(
        QuranReadingGuide, "phonemes", lambda self, text: ScriptedReadingGuide().phonemes(text)
    )
    url = f"sqlite+aiosqlite:///{tmp_path / 'bot.sqlite3'}"
    engine = create_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)
        await conn.run_sync(create_views)
    await engine.dispose()
    reference = tmp_path / "reference"
    reference.mkdir()
    for item_id in (RA, MA):  # у обеих карточек есть звук «как правильно»
        (reference / f"{item_id}.ogg").write_bytes(b"OggS-teacher-reference")
    settings = Settings(
        bot_token=SecretStr("1:test"), database_url=SecretStr(url), asr_backend="stub",
        audio_dir=tmp_path / "audio", reference_audio_dir=reference,
        recitations_dir=tmp_path / "recitations", video_dir=_video_dir(tmp_path / "video"),
        log_file=None,
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


@pytest.fixture(autouse=True)
def _videos_in_fake_telegram(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ученики из test_settings_bot (``_on_home``) получают Telegram, который принимает ролики."""
    import tests.integration.test_settings_bot as settings_bot  # noqa: PLC0415

    monkeypatch.setattr(settings_bot, "VoiceTelegram", VideoTelegram)


@pytest.fixture
def key(tmp_path: Path) -> Callable[[str], str]:
    """Ключ ролика по тексту — как его выдаёт библиотека роликов бота."""
    from muallim.infrastructure.video.library import VideoLibrary  # noqa: PLC0415

    library = VideoLibrary.load(tmp_path / "video")

    def of(text: str) -> str:
        found = library.for_text(text)
        assert found is not None, text
        return found

    return of


def _videos(person: Learner) -> list[SendVideo]:
    return [c for c in person.tg.calls if isinstance(c, SendVideo)]


def _sounds(person: Learner) -> list[TelegramMethod[Any]]:
    return [c for c in person.tg.calls if isinstance(c, SendVoice | SendAudio)]


def _labels(person: Learner) -> list[str]:
    return [t for t, _ in _buttons(person)]


async def _press_label(person: Learner, label: str) -> None:
    found = [d for t, d in _buttons(person) if t == label]
    assert len(found) == 1, f"кнопка «{label}»: {_buttons(person)}"
    await person.press(found[0])


def test_videos_are_read_from_curriculum_video_by_default() -> None:
    assert Settings.model_fields["video_dir"].default == PROJECT_ROOT / "curriculum" / "video"


# ---------- карточка ----------
async def test_card_with_video_has_video_button_and_no_listen(
    app: tuple[Dispatcher, AsyncContainer],
) -> None:
    dp, _ = app
    ali = await _on_home(dp)
    await ali.press(GoItem(item_id=RA))
    assert texts.VIDEO_BUTTON in _labels(ali)
    assert texts.LISTEN_BUTTON not in _labels(ali)


async def test_video_button_sends_streaming_video_not_voice_and_logs_it(
    app: tuple[Dispatcher, AsyncContainer],
    key: Callable[[str], str],
) -> None:
    dp, container = app
    ali = await _on_home(dp)
    await ali.press(GoItem(item_id=RA))
    await _press_label(ali, texts.VIDEO_BUTTON)
    [sent] = _videos(ali)
    assert sent.supports_streaming is True
    assert (sent.width, sent.height, sent.duration) == (1280, 720, round(SECONDS))
    assert isinstance(sent.video, BufferedInputFile)  # первый раз — файлом
    assert sent.video.data == FAKE_MP4 + b"ra.mp4"
    assert _sounds(ali) == []
    assert await _events(container, "video_played") == [
        {"video": key("رَ"), "item_id": RA, "from": "card"}
    ]
    assert await _events(container, "reference_played") == []


async def test_second_showing_reuses_telegram_file_id(
    app: tuple[Dispatcher, AsyncContainer],
    key: Callable[[str], str],
) -> None:
    dp, container = app
    ali = await _on_home(dp)
    await ali.press(GoItem(item_id=RA))
    await _press_label(ali, texts.VIDEO_BUTTON)
    await ali.press(GoItem(item_id=RA))
    await _press_label(ali, texts.VIDEO_BUTTON)
    first, second = _videos(ali)
    assert isinstance(first.video, BufferedInputFile)
    file_id = f"vid{ali.tg.video_ids[0]}"  # type: ignore[attr-defined]
    assert second.video == file_id, "второй раз — по file_id, без загрузки файла"
    display = await container.get(Display)
    assert display.file_ids[f"video:{key('رَ')}"] == file_id


async def test_auto_reference_sends_video_above_card_instead_of_voice(
    app: tuple[Dispatcher, AsyncContainer],
    key: Callable[[str], str],
) -> None:
    dp, container = app
    ali = await _on_home(dp)
    await _set(container, PUPIL, auto_reference=True)
    await ali.press(GoItem(item_id=RA))
    [sent] = _videos(ali)
    assert sent.supports_streaming is True
    assert _sounds(ali) == [], "у ролика свой звук — голосового нет"
    index = ali.tg.calls.index(sent)
    assert any(
        CARD_MARK in (getattr(c, "caption", None) or getattr(c, "text", None) or "")
        for c in ali.tg.calls[index + 1 :]
    ), "карточка — под роликом"
    assert CARD_MARK in _card_caption(ali)
    assert await _events(container, "video_played") == [
        {"video": key("رَ"), "item_id": RA, "from": "auto"}
    ]
    assert await _events(container, "reference_played") == []


async def test_auto_video_comes_every_time_the_card_opens(
    app: tuple[Dispatcher, AsyncContainer],
    key: Callable[[str], str],
) -> None:
    """Как автозвук — без «уже видел»: второе открытие — снова ролик, уже по file_id."""
    dp, container = app
    ali = await _on_home(dp)
    await _set(container, PUPIL, auto_reference=True)
    await ali.press(GoItem(item_id=RA))
    await ali.press(GoItem(item_id=RA))
    first, second = _videos(ali)
    assert isinstance(first.video, BufferedInputFile)
    assert isinstance(ali.tg, VideoTelegram)
    assert second.video == f"vid{ali.tg.video_ids[0]}"
    played = {"video": key("رَ"), "item_id": RA, "from": "auto"}
    assert await _events(container, "video_played") == [played, played]


async def test_card_with_video_but_without_reference_sound_gets_auto_video(
    app: tuple[Dispatcher, AsyncContainer],
    key: Callable[[str], str],
) -> None:
    """У «رِ» нет записи «как правильно», но есть ролик: 🎬 на карточке, авторолик приходит."""
    dp, container = app
    ali = await _on_home(dp)
    await _set(container, PUPIL, auto_reference=True)
    await ali.press(GoItem(item_id=RI))
    [sent] = _videos(ali)
    assert isinstance(sent.video, BufferedInputFile) and sent.video.data == FAKE_MP4 + b"ri.mp4"
    assert texts.VIDEO_BUTTON in _labels(ali)
    assert await _events(container, "video_played") == [
        {"video": key("رِ"), "item_id": RI, "from": "auto"}
    ]


async def test_auto_video_is_removed_when_leaving_card_like_auto_sound(
    app: tuple[Dispatcher, AsyncContainer],
) -> None:
    dp, container = app
    ali = await _on_home(dp)
    await _set(container, PUPIL, auto_reference=True)
    await ali.press(GoItem(item_id=RA))
    [video_id] = ali.tg.video_ids  # type: ignore[attr-defined]
    await ali.press(Home())
    assert video_id in _deleted(ali)


async def test_auto_off_sends_no_video(app: tuple[Dispatcher, AsyncContainer]) -> None:
    dp, container = app
    ali = await _on_home(dp)
    await ali.press(GoItem(item_id=RA))
    assert _videos(ali) == [] and _sounds(ali) == []
    assert await _events(container, "video_played") == []


async def test_card_still_comes_when_video_fails(
    app: tuple[Dispatcher, AsyncContainer],
    key: Callable[[str], str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Авторолик не ушёл — карточка показана, предупреждение нашего логгера с ключом ролика,
    ``video_played`` нет (решение автора D)."""
    dp, container = app
    ali = await _on_home(dp)
    await _set(container, PUPIL, auto_reference=True)
    assert isinstance(ali.tg, VideoTelegram)
    ali.tg.fail_video = True
    with caplog.at_level(logging.WARNING):
        await ali.press(GoItem(item_id=RA))
    assert ali.tg.rejected, "отправка ролика была"
    assert CARD_MARK in _card_caption(ali), "карточка показана"
    assert texts.VIDEO_BUTTON in _labels(ali)
    warnings = [
        r for r in caplog.records
        if r.levelno == logging.WARNING and r.name.startswith("muallim")
    ]  # fmt: skip
    assert any(key("رَ") in r.getMessage() for r in warnings), [r.getMessage() for r in warnings]
    assert await _events(container, "video_played") == []


async def test_failed_video_button_answers_and_logs_nothing(
    app: tuple[Dispatcher, AsyncContainer],
) -> None:
    """Сбой по нажатию 🎬 (не авто): нажатие получает ответ, исключения нет, события нет."""
    dp, container = app
    ali = await _on_home(dp)
    await ali.press(GoItem(item_id=RA))
    assert isinstance(ali.tg, VideoTelegram)
    ali.tg.fail_video = True
    answered = sum(isinstance(c, AnswerCallbackQuery) for c in ali.tg.calls)
    await _press_label(ali, texts.VIDEO_BUTTON)  # не бросает исключение
    assert ali.tg.rejected
    assert sum(isinstance(c, AnswerCallbackQuery) for c in ali.tg.calls) == answered + 1
    assert await _events(container, "video_played") == []


async def test_stale_file_id_is_replaced_by_a_new_upload(
    app: tuple[Dispatcher, AsyncContainer],
    key: Callable[[str], str],
) -> None:
    """Telegram не узнал сохранённый file_id — ролик загружается файлом, file_id обновляется."""
    dp, container = app
    ali = await _on_home(dp)
    await ali.press(GoItem(item_id=RA))
    await _press_label(ali, texts.VIDEO_BUTTON)
    assert isinstance(ali.tg, VideoTelegram)
    ali.tg.stale_file_ids = True
    await ali.press(GoItem(item_id=RA))
    await _press_label(ali, texts.VIDEO_BUTTON)
    [rejected] = ali.tg.rejected
    assert isinstance(rejected.video, str)
    first, second = _videos(ali)
    assert isinstance(first.video, BufferedInputFile)
    assert isinstance(second.video, BufferedInputFile), "второй раз — снова файлом"
    display = await container.get(Display)
    assert display.file_ids[f"video:{key('رَ')}"] == f"vid{ali.tg.video_ids[-1]}"
    assert len(await _events(container, "video_played")) == 2


async def test_card_without_video_keeps_listen_and_auto_voice(
    app: tuple[Dispatcher, AsyncContainer],
) -> None:
    """Регрессия FR-20: у «مَ» ролика нет — 🔊 и автоголосовое как раньше."""
    dp, container = app
    ali = await _on_home(dp)
    await _set(container, PUPIL, auto_reference=True)
    await ali.press(GoItem(item_id=MA))
    assert len(_sounds(ali)) == 1 and _videos(ali) == []
    assert texts.LISTEN_BUTTON in _labels(ali)
    assert texts.VIDEO_BUTTON not in _labels(ali)
    assert await _events(container, "video_played") == []


# ---------- после попытки ----------
async def test_result_after_attempt_offers_video_instead_of_listen(
    app: tuple[Dispatcher, AsyncContainer],
    key: Callable[[str], str],
) -> None:
    dp, container = app
    ali = await _on_home(dp)
    await ali.press(GoItem(item_id=RA))
    await ali.voice()
    assert texts.VIDEO_BUTTON in _labels(ali)
    assert texts.LISTEN_BUTTON not in _labels(ali)
    await _press_label(ali, texts.VIDEO_BUTTON)
    assert len(_videos(ali)) == 1 and _sounds(ali) == []
    assert await _events(container, "video_played") == [
        {"video": key("رَ"), "item_id": RA, "from": "after"}
    ]


# ---------- шпаргалка ----------
async def test_sheet_has_no_video_buttons(app: tuple[Dispatcher, AsyncContainer]) -> None:
    """Решение автора 2026-10-25 (уточнение): в шпаргалке роликов нет."""
    dp, _ = app
    ali = await _on_home(dp)
    await ali.press(LettersSheet(lesson_id=MIM))
    assert not [t for t, _ in _buttons(ali) if "🎬" in t], _buttons(ali)


# ---------- устаревшая кнопка ----------
async def test_button_of_removed_video_sends_nothing_and_logs_nothing(
    app: tuple[Dispatcher, AsyncContainer],
) -> None:
    """Ролика с таким ключом больше нет (``bad`` после перезапуска): «кнопка устарела»."""
    from muallim.presentation.telegram.callbacks import Watch  # noqa: PLC0415

    dp, container = app
    ali = await _on_home(dp)
    await ali.press(GoItem(item_id=RA))
    data = next(d for t, d in _buttons(ali) if t == texts.VIDEO_BUTTON)
    forged = Watch.unpack(data).model_copy(update={"v": "0" * 16}).pack()
    await ali.press(forged)
    assert _videos(ali) == []
    assert await _events(container, "video_played") == []
    answers = [c for c in ali.tg.calls if isinstance(c, AnswerCallbackQuery)]
    assert answers[-1].show_alert is True
    assert answers[-1].text == texts.STALE_BUTTON


# ---------- разбор ошибки (FR-54) ----------
async def test_breakdown_of_line_has_no_video_button(
    app: tuple[Dispatcher, AsyncContainer], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ошибка ر → ل в строке книги: в разборе 🎬 нет — ролики только на карточках алфавита."""
    heard = "رَرْ لِرْ رُرْ أَرْ إِرْ أُرْ"

    async def recognize(self: StubRecognizer, audio: bytes, text: str) -> Recognition:
        return Recognition(
            heard=heard, references=(("waqf", text),), model_version="stub", audio_duration_ms=0
        )

    monkeypatch.setattr(StubRecognizer, "recognize", recognize)
    dp, _ = app
    ali = await _on_home(dp)
    await ali.press(GoItem(item_id=RA_LINE))
    await ali.voice()
    assert not [t for t, _ in _buttons(ali) if "🎬" in t], _buttons(ali)
