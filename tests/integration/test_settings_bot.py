"""⚙️ Настройки ученика через бота (FR-51, ADR-0061, пакет Б, круг 3).

Главная: Продолжить / Уроки, Закрепление / Знаки, Прогресс / ⚙️ Настройки; «Как заниматься»,
«Мои данные» и ID — внутри настроек. Экран настроек — одно окно (ADR-0024): нажатие меняет
значение в `learner_settings`, пишет `setting_changed` и перерисовывает экран на месте.
Настройки действуют: «Как читается» (Закрыта / Видна сразу / Не показывать — подписи утвердил
автор 2026-10-21), блок исследования (ADR-0057), начало занятия (ADR-0050), крупный шрифт
(ADR-0059), автозвук эталона (В5: по умолчанию выключен).

Круг 4: напоминание (В1–В3: раз в день в выбранный час, по умолчанию выключено; при включении —
«который у тебя час?» кнопками, хранится только смещение от UTC) и доводка TD-FN-93 пп. 1–5.

Настоящие обработчики, DI и SQLite; распознавание — заглушка, фонетизатор «Как читается» —
подменён (как ``ScriptedReadingGuide``): в CI нет extra ``ml``.
"""

import re
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import (
    AnswerCallbackQuery,
    DeleteMessage,
    EditMessageMedia,
    SendAudio,
    SendMessage,
    SendPhoto,
    SendVoice,
    TelegramMethod,
)
from aiogram.types import BufferedInputFile, Chat, Message, User
from dishka import AsyncContainer
from dishka.integrations.aiogram import setup_dishka
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from muallim.application.ports.repositories import (
    LearnerRepository,
    LearnerSettingsRepository,
    UnitOfWork,
)
from muallim.application.use_cases.curriculum import PublishCurriculum
from muallim.bootstrap.config import Settings
from muallim.bootstrap.di import create_container
from muallim.domain.settings import HowToRead, LearnerSettings
from muallim.infrastructure.asr.reading import QuranReadingGuide
from muallim.infrastructure.db.engine import create_engine
from muallim.infrastructure.db.tables import interaction_events, metadata
from muallim.infrastructure.db.views import create_views
from muallim.infrastructure.system import SystemClock
from muallim.presentation.telegram import render, texts
from muallim.presentation.telegram.callbacks import ChangeSetting as ChangeSettingCallback
from muallim.presentation.telegram.callbacks import (
    Consent,
    GoItem,
    Home,
    Lessons,
    Listen,
    Opening,
    ShowSettings,
)
from muallim.presentation.telegram.handlers import router
from tests.fakes import ScriptedReadingGuide
from tests.integration.test_bot_flow import BOT_USER, NOW, FakeTelegram, Learner
from tests.integration.test_opening_bot import RESUME, _seed
from tests.integration.test_opening_bot import TG as SEEDED_TG
from tests.unit.test_readable_images import MAX_WIDTH, _on_phone

pytestmark = pytest.mark.integration

TEACHER, PUPIL = 7201, 7202
WITH_REFERENCE = "L006-02"  # «مَ» — слог, не аят: эталон — файл учителя из tmp
WITHOUT_REFERENCE = "L006-03"  # «مِ» — эталона нет
ISTI_ADHA = "L001-02"
CALLBACK_LIMIT = 64  # байт, Telegram Bot API
REMINDER_ICON = "🔔"  # «🔔 Напоминание: выкл.» / «🔔 Напоминание: 19:00»
EVENING = 19 * 60  # 19:00 — минута местных суток
UTC_PLUS_5 = 5 * 60  # Алматы

HOW_TO_READ_LABELS = {  # подписи утвердил автор 2026-10-21
    HowToRead.SPOILER: "Закрыта",
    HowToRead.SHOWN: "Видна сразу",
    HowToRead.HIDDEN: "Не показывать",
}
# переключатель → (значок на кнопке, умолчание)
TOGGLES = {
    "auto_reference": ("🔊", False),
    "daily_opening": ("🌙", True),
    "large_font": ("🔎", False),
    "research_block": ("🔬", False),
}


class VoiceTelegram(FakeTelegram):
    """Ещё и голосовые/аудио: эталон приходит отдельным сообщением."""

    fail_sound = False  # Telegram отказал в звуке (сеть, слишком большой файл)

    def __init__(self) -> None:
        super().__init__()
        self.sound_ids: list[int] = []  # номера сообщений со звуком — по порядку отправки

    async def make_request(
        self, bot: Bot, method: TelegramMethod[Any], timeout: int | None = None
    ) -> Any:
        if isinstance(method, SendVoice | SendAudio):
            if self.fail_sound:
                raise TelegramBadRequest(method=method, message="Bad Request: file is too big")
            self.calls.append(method)
            self._next_id += 1
            self.sound_ids.append(self._next_id)
            assert isinstance(method.chat_id, int)
            return Message(
                message_id=self._next_id, date=NOW, chat=Chat(id=method.chat_id, type="private"),
                from_user=BOT_USER,
            ).as_(bot)  # fmt: skip
        return await super().make_request(bot, method, timeout)


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
    (reference / f"{WITH_REFERENCE}.ogg").write_bytes(b"OggS-teacher-reference")
    settings = Settings(
        bot_token=SecretStr("1:test"), database_url=SecretStr(url), asr_backend="stub",
        audio_dir=tmp_path / "audio", reference_audio_dir=reference,
        recitations_dir=tmp_path / "recitations", teacher_ids=str(TEACHER), log_file=None,
        video_dir=tmp_path / "video",  # без роликов FR-56: здесь проверяется звук FR-20/FR-52
    )  # fmt: skip
    container = create_container(settings)
    async with container() as request:
        await (await request.get(PublishCurriculum)).execute()
        await _seed(await request.get(AsyncSession))  # урок 1 пройден вчера (SEEDED_TG)
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
    fake = VoiceTelegram()
    user = User(id=tg, is_bot=False, first_name="Ученик", language_code="ru")
    return Learner(dp, Bot("1:test", session=fake), fake, user)


async def _on_home(dp: Dispatcher, tg: int = PUPIL) -> Learner:
    """Новый ученик: /start → согласие «нет» → главная."""
    person = _person(dp, tg)
    await person.write("/start")
    await person.press(Consent(granted=False))
    return person


def _buttons(person: Learner) -> list[tuple[str, str]]:
    markup = person.last_screen().reply_markup
    assert markup is not None
    return [(b.text, b.callback_data or "") for row in markup.inline_keyboard for b in row]


def _find(person: Learner, part: str) -> str:
    found = [data for text, data in _buttons(person) if part in text]
    assert len(found) == 1, f"кнопка с «{part}»: {_buttons(person)}"
    return found[0]


async def _press_text(person: Learner, part: str) -> None:
    await person.press(_find(person, part))


async def _open_settings(person: Learner) -> None:
    await _press_text(person, texts.SETTINGS_BUTTON)


def _view(person: Learner) -> tuple[str, list[str]]:
    """Что ученик видит на экране: подпись и надписи кнопок."""
    screen = person.last_screen()
    return screen.text or screen.caption or "", [text for text, _ in _buttons(person)]


async def _learner_id(container: AsyncContainer, tg: int) -> UUID:
    async with container() as request:
        learner = await (await request.get(LearnerRepository)).get_by_telegram_id(tg)
    assert learner is not None
    learner_id: UUID = learner.id
    return learner_id


async def _settings(container: AsyncContainer, tg: int = PUPIL) -> LearnerSettings:
    learner_id = await _learner_id(container, tg)
    async with container() as request:
        found: LearnerSettings = await (await request.get(LearnerSettingsRepository)).get(
            learner_id
        )
    return found


async def _set(container: AsyncContainer, tg: int, **fields: Any) -> None:
    learner_id = await _learner_id(container, tg)
    async with container() as request:
        await (await request.get(LearnerSettingsRepository)).change(learner_id, fields)
        await (await request.get(UnitOfWork)).commit()


async def _events(container: AsyncContainer, event: str) -> list[dict[str, Any]]:
    async with container() as request:
        session = await request.get(AsyncSession)
        rows = await session.execute(
            select(interaction_events.c.payload)
            .where(interaction_events.c.event == event)
            .order_by(interaction_events.c.id)
        )
        return [dict(r[0]) for r in rows]


# ---------- 1. главная ----------
async def test_home_has_settings_instead_of_help_and_privacy(
    app: tuple[Dispatcher, AsyncContainer],
) -> None:
    dp, _ = app
    ali = await _on_home(dp)
    labels = [text for text, _ in _buttons(ali)]
    assert "⚙️" in texts.SETTINGS_BUTTON and "Настройки" in texts.SETTINGS_BUTTON
    assert labels[1:] == [
        texts.LESSONS_BUTTON,
        texts.QUIZ_BUTTON,
        texts.SIGNS_BUTTON,
        texts.PROGRESS_BUTTON,
        texts.SETTINGS_BUTTON,
    ], labels
    assert labels[0].startswith("▶️")  # «Начать первый урок» / «Продолжить: …»
    assert texts.HELP_BUTTON not in labels and texts.PRIVACY_BUTTON not in labels


# ---------- 2. экран настроек ----------
async def test_settings_screen_offers_every_option_and_inner_screens(
    app: tuple[Dispatcher, AsyncContainer],
) -> None:
    dp, _ = app
    ali = await _on_home(dp)
    await _open_settings(ali)
    labels = [text for text, _ in _buttons(ali)]
    for label in HOW_TO_READ_LABELS.values():
        assert any(label in text for text in labels), (label, labels)
    for icon, _ in TOGGLES.values():
        assert sum(icon in text for text in labels) == 1, (icon, labels)
    for inner in (texts.HELP_BUTTON, texts.PRIVACY_BUTTON, texts.HOME_BUTTON):
        assert inner in labels, (inner, labels)
    assert sum("🪪" in text for text in labels) == 1, labels


async def test_settings_screen_shows_reminder_switched_off_by_default(
    app: tuple[Dispatcher, AsyncContainer],
) -> None:
    """В1–В2: напоминание — в настройках, по умолчанию выключено (круг 3 его ещё не показывал)."""
    dp, container = app
    ali = await _on_home(dp)
    await _open_settings(ali)
    reminder = [text for text in _view(ali)[1] if REMINDER_ICON in text]
    assert len(reminder) == 1, _view(ali)[1]
    assert "выкл." in reminder[0], reminder
    assert (await _settings(container)).reminder_minute is None


async def test_settings_buttons_fit_telegram_callback_limit(
    app: tuple[Dispatcher, AsyncContainer],
) -> None:
    dp, _ = app
    ali = await _on_home(dp)
    await _open_settings(ali)
    for text, data in _buttons(ali):
        assert data, f"у кнопки «{text}» нет callback_data"
        assert len(data.encode()) <= CALLBACK_LIMIT, (text, data)


@pytest.mark.parametrize("choice", [HowToRead.SHOWN, HowToRead.HIDDEN])
async def test_choosing_how_to_read_is_saved_and_redrawn_in_place(
    app: tuple[Dispatcher, AsyncContainer], choice: HowToRead
) -> None:
    dp, container = app
    ali = await _on_home(dp)
    await _open_settings(ali)
    before, screen_id = _view(ali), ali.last_screen().message_id
    await _press_text(ali, HOW_TO_READ_LABELS[choice])
    assert (await _settings(container)).how_to_read is choice
    assert _view(ali) != before, "экран показывает новое значение"
    assert ali.last_screen().message_id == screen_id, "экран меняется на месте (ADR-0024)"
    assert await _events(container, "setting_changed") == [
        {"name": "how_to_read", "value": str(choice)}
    ]


async def test_how_to_read_can_be_closed_again(app: tuple[Dispatcher, AsyncContainer]) -> None:
    dp, container = app
    ali = await _on_home(dp)
    await _open_settings(ali)
    default = _view(ali)
    await _press_text(ali, HOW_TO_READ_LABELS[HowToRead.SHOWN])
    await _press_text(ali, HOW_TO_READ_LABELS[HowToRead.SPOILER])
    assert (await _settings(container)).how_to_read is HowToRead.SPOILER
    assert _view(ali) == default


@pytest.mark.parametrize("name", sorted(TOGGLES))
async def test_toggle_is_saved_logged_and_redrawn(
    app: tuple[Dispatcher, AsyncContainer], name: str
) -> None:
    dp, container = app
    icon, default = TOGGLES[name]
    ali = await _on_home(dp)
    await _open_settings(ali)
    assert getattr(await _settings(container), name) is default
    before, screen_id = _view(ali), ali.last_screen().message_id

    await _press_text(ali, icon)
    assert getattr(await _settings(container), name) is (not default)
    assert _view(ali) != before, "экран показывает новое значение"
    assert ali.last_screen().message_id == screen_id, "экран меняется на месте (ADR-0024)"

    await _press_text(ali, icon)  # ещё раз — обратно
    assert getattr(await _settings(container), name) is default
    assert _view(ali) == before
    assert await _events(container, "setting_changed") == [
        {"name": name, "value": not default},
        {"name": name, "value": default},
    ]


async def test_help_privacy_and_id_open_from_settings(
    app: tuple[Dispatcher, AsyncContainer],
) -> None:
    dp, _ = app
    ali = await _on_home(dp)
    await _open_settings(ali)
    await _press_text(ali, texts.HELP_BUTTON)
    assert _view(ali)[0] == texts.HELP

    await ali.press(Home())
    await _open_settings(ali)
    await _press_text(ali, texts.PRIVACY_BUTTON)
    assert _view(ali)[0].startswith(texts.PRIVACY_STATUS.split("\n")[0])

    await ali.press(Home())
    await _open_settings(ali)
    await _press_text(ali, "🪪")
    assert any(t.startswith(texts.ME_TEXT.split("{")[0]) for t in ali.tg.texts())


async def test_settings_screen_leads_home(app: tuple[Dispatcher, AsyncContainer]) -> None:
    dp, _ = app
    ali = await _on_home(dp)
    await _open_settings(ali)
    await _press_text(ali, texts.HOME_BUTTON)
    assert texts.SETTINGS_BUTTON in [text for text, _ in _buttons(ali)]


# ---------- 3. настройки действуют ----------
def _card_caption(person: Learner) -> str:
    return _view(person)[0]


async def test_how_to_read_is_under_spoiler_by_default(
    app: tuple[Dispatcher, AsyncContainer],
) -> None:
    dp, _ = app
    ali = await _on_home(dp)
    await ali.press(GoItem(item_id=WITH_REFERENCE))
    assert texts.CARD_HOW_TO_READ.split("{")[0] in _card_caption(ali)


async def test_how_to_read_shown_has_no_spoiler(app: tuple[Dispatcher, AsyncContainer]) -> None:
    dp, container = app
    ali = await _on_home(dp)
    await _set(container, PUPIL, how_to_read=HowToRead.SHOWN)
    await ali.press(GoItem(item_id=WITH_REFERENCE))
    caption = _card_caption(ali)
    assert "Как читается" in caption, caption
    assert "tg-spoiler" not in caption


async def test_how_to_read_hidden_removes_the_line(
    app: tuple[Dispatcher, AsyncContainer],
) -> None:
    dp, container = app
    ali = await _on_home(dp)
    await _set(container, PUPIL, how_to_read=HowToRead.HIDDEN)
    await ali.press(GoItem(item_id=WITH_REFERENCE))
    caption = _card_caption(ali)
    assert "Как читается" not in caption and "tg-spoiler" not in caption


def _result_text(person: Learner) -> str:
    """Подпись результата и разбор — всё, что пришло после «Слушаю…»."""
    shown = person.tg.texts()
    start = max(i for i, t in enumerate(shown) if t.startswith(texts.LISTENING.split("{")[0]))
    return "\n".join(shown[start + 1 :])


async def _read_isti_adha(person: Learner) -> str:
    await person.press(GoItem(item_id=ISTI_ADHA))
    await person.voice()
    return _result_text(person)


async def test_pupil_with_research_block_sees_it(app: tuple[Dispatcher, AsyncContainer]) -> None:
    dp, container = app
    ali = await _on_home(dp)
    await _set(container, PUPIL, research_block=True)
    result = await _read_isti_adha(ali)
    assert texts.VERDICT_EXCELLENT in result
    assert "Для исследования" in result and "Попытка №" in result


async def test_pupil_without_research_block_does_not_see_it(
    app: tuple[Dispatcher, AsyncContainer],
) -> None:
    dp, _ = app
    result = await _read_isti_adha(await _on_home(dp))
    assert "Для исследования" not in result and "Попытка №" not in result


async def test_staff_sees_research_block_even_when_switched_off(
    app: tuple[Dispatcher, AsyncContainer],
) -> None:
    dp, container = app
    teacher = await _on_home(dp, TEACHER)
    await _set(container, TEACHER, research_block=False)
    result = await _read_isti_adha(teacher)
    assert "Для исследования" in result and "Попытка №" in result


async def test_research_block_switched_on_in_settings_reaches_result(
    app: tuple[Dispatcher, AsyncContainer],
) -> None:
    """Сквозь экран: ⚙️ → 🔬 → урок → голосовое — блок виден."""
    dp, _ = app
    ali = await _on_home(dp)
    await _open_settings(ali)
    await _press_text(ali, TOGGLES["research_block"][0])
    result = await _read_isti_adha(ali)
    assert "Для исследования" in result


async def test_daily_opening_off_is_not_offered(app: tuple[Dispatcher, AsyncContainer]) -> None:
    """Урок 1 пройден вчера, сегодня не занимался — но начало занятия выключено."""
    dp, container = app
    await _set(container, SEEDED_TG, daily_opening=False)
    ali = _person(dp, SEEDED_TG)
    await ali.write("/start")
    assert texts.OPENING_TITLE not in ali.tg.texts()[-1]
    assert ali.button(GoItem) == GoItem(item_id=RESUME).pack()
    await ali.press(Home())
    assert texts.OPENING_TITLE not in ali.tg.texts()[-1]


async def test_daily_opening_on_is_offered(app: tuple[Dispatcher, AsyncContainer]) -> None:
    dp, _ = app
    ali = _person(dp, SEEDED_TG)
    await ali.write("/start")
    assert texts.OPENING_TITLE in ali.tg.texts()[-1]
    assert ali.button(Opening)


# --- крупный шрифт ---
needs_raqm = pytest.mark.skipif(not render.available(), reason="нет libraqm (brew install fribidi)")


def _last_photo(person: Learner) -> bytes:
    """Картинка последнего показанного экрана — байты, а не file_id из кэша."""
    calls = [c for c in person.tg.calls if isinstance(c, SendPhoto | EditMessageMedia)]
    assert calls, "картинку не отправляли"
    last = calls[-1]
    media = last.photo if isinstance(last, SendPhoto) else last.media.media
    assert isinstance(media, BufferedInputFile), (
        "картинка взята из кэша file_id: ключ кэша не различает крупный и обычный шрифт"
    )
    return media.data


async def _card_photo(person: Learner) -> bytes:
    await person.press(Home())
    await person.press(GoItem(item_id=WITH_REFERENCE))
    return _last_photo(person)


@needs_raqm
async def test_large_font_makes_letters_bigger_within_900_px(
    app: tuple[Dispatcher, AsyncContainer],
) -> None:
    dp, container = app
    ali = await _on_home(dp)
    normal = await _card_photo(ali)
    await _set(container, PUPIL, large_font=True)
    large = await _card_photo(ali)  # та же карточка: из кэша нельзя — другой размер
    from tests.unit.test_readable_images import _image  # noqa: PLC0415

    assert _image(large).width <= MAX_WIDTH
    assert _on_phone(large, render.ACCENT) > _on_phone(normal, render.ACCENT), (
        "буквы на телефоне крупнее"
    )


@needs_raqm
async def test_back_to_normal_font_shows_normal_card(
    app: tuple[Dispatcher, AsyncContainer],
) -> None:
    dp, container = app
    ali = await _on_home(dp)
    await _set(container, PUPIL, large_font=True)
    large = await _card_photo(ali)
    await _set(container, PUPIL, large_font=False)
    normal = await _card_photo(ali)
    assert _on_phone(normal, render.ACCENT) < _on_phone(large, render.ACCENT)


# --- автозвук эталона ---
def _sounds(person: Learner) -> list[int]:
    """Номера вызовов API, которыми прислан эталон (голосовое или аудио)."""
    return [i for i, c in enumerate(person.tg.calls) if isinstance(c, SendVoice | SendAudio)]


CARD_MARK = " · шаг "  # из texts.CARD_HEAD: «<урок> · шаг N из M»


def _text_of(call: TelegramMethod[Any]) -> str:
    if isinstance(call, SendPhoto):
        return call.caption or ""
    if isinstance(call, SendMessage):
        return call.text
    return ""


def _card_sent_after(person: Learner, index: int) -> bool:
    """После звука карточка пришла новым сообщением — звук над ней в чате."""
    return any(CARD_MARK in _text_of(c) for c in person.tg.calls[index + 1 :])


async def test_auto_reference_sends_reference_above_the_card(
    app: tuple[Dispatcher, AsyncContainer],
) -> None:
    dp, container = app
    ali = await _on_home(dp)
    await _set(container, PUPIL, auto_reference=True)
    await ali.press(GoItem(item_id=WITH_REFERENCE))
    sounds = _sounds(ali)
    assert len(sounds) == 1, "эталон прислан сам, без нажатия 🔊"
    assert _card_sent_after(ali, sounds[0]), "карточка — под голосовым"
    assert CARD_MARK in _card_caption(ali)
    assert await _events(container, "reference_played") == [
        {"item_id": WITH_REFERENCE, "auto": True}
    ]


async def test_auto_reference_off_sends_nothing(app: tuple[Dispatcher, AsyncContainer]) -> None:
    dp, container = app
    ali = await _on_home(dp)
    await ali.press(GoItem(item_id=WITH_REFERENCE))
    assert _sounds(ali) == []
    assert await _events(container, "reference_played") == []


async def test_auto_reference_on_card_without_reference_sends_nothing(
    app: tuple[Dispatcher, AsyncContainer],
) -> None:
    dp, container = app
    ali = await _on_home(dp)
    await _set(container, PUPIL, auto_reference=True)
    await ali.press(GoItem(item_id=WITHOUT_REFERENCE))
    assert _sounds(ali) == []
    assert await _events(container, "reference_played") == []
    assert CARD_MARK in _card_caption(ali)  # карточка показана


async def test_auto_reference_switched_on_in_settings_plays_on_next_card(
    app: tuple[Dispatcher, AsyncContainer],
) -> None:
    """Сквозь экран: ⚙️ → 🔊 → урок — эталон пришёл сам."""
    dp, _ = app
    ali = await _on_home(dp)
    await _open_settings(ali)
    await _press_text(ali, TOGGLES["auto_reference"][0])
    await ali.press(Home())
    await ali.press(GoItem(item_id=WITH_REFERENCE))
    assert len(_sounds(ali)) == 1


async def test_card_still_comes_when_auto_reference_fails(
    app: tuple[Dispatcher, AsyncContainer],
) -> None:
    """Звук не ушёл — карточка всё равно приходит: ученик не остаётся без экрана (ревью круга 3)."""
    dp, container = app
    ali = await _on_home(dp)
    await _set(container, PUPIL, auto_reference=True)
    assert isinstance(ali.tg, VoiceTelegram)
    ali.tg.fail_sound = True
    await ali.press(GoItem(item_id=WITH_REFERENCE))
    assert _sounds(ali) == []
    assert CARD_MARK in _card_caption(ali)


# ---------- 4. напоминание: час и «который у тебя час?» (круг 4, В1–В3) ----------
BOT_NOW = datetime(2026, 10, 21, 16, 5, tzinfo=UTC)  # часы бота; в UTC+8…+12 — уже завтра
_TIME = re.compile(r"(?<!\d)(\d{1,2}):(\d{2})(?!\d)")


@pytest.fixture
def bot_clock(monkeypatch: pytest.MonkeyPatch) -> datetime:
    """Часы бота стоят: подписи «который час» вычисляются от них, а не от настоящего времени."""
    monkeypatch.setattr(SystemClock, "now", lambda self: BOT_NOW)
    return BOT_NOW


def _times(person: Learner) -> dict[tuple[int, int], str]:
    """Кнопки-времена на экране: (часы, минуты) → callback_data."""
    found: dict[tuple[int, int], str] = {}
    for text, data in _buttons(person):
        if m := _TIME.search(text):
            key = (int(m[1]), int(m[2]))
            assert key not in found, f"две кнопки с временем {key}: {_buttons(person)}"
            found[key] = data
    return found


async def _open_reminder(person: Learner) -> None:
    await _open_settings(person)
    await _press_text(person, REMINDER_ICON)


def _local(offset_hours: int) -> tuple[int, int]:
    local = BOT_NOW.hour * 60 + BOT_NOW.minute + offset_hours * 60
    return (local // 60) % 24, local % 60


async def test_reminder_button_opens_hour_grid_in_place(
    app: tuple[Dispatcher, AsyncContainer],
) -> None:
    dp, _ = app
    ali = await _on_home(dp)
    await _open_settings(ali)
    screen_id = ali.last_screen().message_id
    await _press_text(ali, REMINDER_ICON)
    assert ali.last_screen().message_id == screen_id, "выбор часа — на месте экрана (ADR-0024)"
    hours = _times(ali)
    assert {(h, 0) for h in range(7, 23)} <= set(hours), sorted(hours)
    assert all(minute == 0 for _, minute in hours), "сетка — целые часы"


async def test_choosing_hour_asks_what_time_it_is_for_utc_plus_2_to_12(
    app: tuple[Dispatcher, AsyncContainer], bot_clock: datetime
) -> None:
    """В3: «который у тебя час?» — кнопки с текущим временем для UTC+2…UTC+12."""
    dp, _ = app
    ali = await _on_home(dp)
    await _open_reminder(ali)
    await ali.press(_times(ali)[(19, 0)])
    caption = _view(ali)[0].casefold()
    assert "который" in caption and "час" in caption, caption
    assert set(_times(ali)) == {_local(h) for h in range(2, 13)}, sorted(_times(ali))


async def test_reminder_hour_and_offset_are_saved_and_shown_in_settings(
    app: tuple[Dispatcher, AsyncContainer], bot_clock: datetime
) -> None:
    dp, container = app
    ali = await _on_home(dp)
    await _open_reminder(ali)
    screen_id = ali.last_screen().message_id
    await ali.press(_times(ali)[(19, 0)])
    await ali.press(_times(ali)[_local(5)])  # у ученика 21:05 — Алматы, UTC+5
    saved = await _settings(container)
    assert (saved.reminder_minute, saved.utc_offset_min) == (EVENING, UTC_PLUS_5)
    assert ali.last_screen().message_id == screen_id, "всё — в одном окне"
    reminder = [text for text in _view(ali)[1] if REMINDER_ICON in text]
    assert len(reminder) == 1 and "19:00" in reminder[0], _view(ali)[1]


async def test_offset_is_logged_without_value_and_hour_with_value(
    app: tuple[Dispatcher, AsyncContainer], bot_clock: datetime
) -> None:
    """Смещение — данные работы сервиса: в журнал без значения (ADR-0061, круг 2)."""
    dp, container = app
    ali = await _on_home(dp)
    await _open_reminder(ali)
    await ali.press(_times(ali)[(19, 0)])
    await ali.press(_times(ali)[_local(5)])
    assert await _events(container, "setting_changed") == [
        {"name": "reminder_minute", "value": EVENING},
        {"name": "utc_offset_min"},
    ]


async def test_reminder_can_be_switched_off(app: tuple[Dispatcher, AsyncContainer]) -> None:
    dp, container = app
    ali = await _on_home(dp)
    await _set(container, PUPIL, reminder_minute=EVENING, utc_offset_min=UTC_PLUS_5)
    await _open_reminder(ali)
    await _press_text(ali, "ыключ")  # «Выключить» / «выключить»
    saved = await _settings(container)
    assert saved.reminder_minute is None
    assert saved.utc_offset_min == UTC_PLUS_5, "смещение остаётся — спрашивать заново не нужно"
    reminder = [text for text in _view(ali)[1] if REMINDER_ICON in text]
    assert len(reminder) == 1 and "выкл." in reminder[0], _view(ali)[1]
    assert await _events(container, "setting_changed") == [
        {"name": "reminder_minute", "value": None}
    ]


async def test_reminder_screens_fit_telegram_callback_limit(
    app: tuple[Dispatcher, AsyncContainer], bot_clock: datetime
) -> None:
    dp, _ = app
    ali = await _on_home(dp)
    await _open_reminder(ali)
    hour_screen = _buttons(ali)
    await ali.press(_times(ali)[(19, 0)])
    for text, data in hour_screen + _buttons(ali):
        assert data, f"у кнопки «{text}» нет callback_data"
        assert len(data.encode()) <= CALLBACK_LIMIT, (text, data)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("reminder_minute", "1440"),  # вне CHECK 0…1439
        ("reminder_minute", "-1"),
        ("reminder_minute", "1145"),  # 19:05 — не на сетке целых часов
        ("reminder_minute", "abc"),
        ("utc_offset_min", "841"),  # вне CHECK −720…840
        ("utc_offset_min", "-721"),
        ("utc_offset_min", "330"),  # UTC+5:30 — не на сетке
        ("utc_offset_min", "60"),  # UTC+1 — вне UTC+2…+12
        ("utc_offset_min", "x"),
    ],
)
async def test_forged_reminder_button_is_stale_and_changes_nothing(
    app: tuple[Dispatcher, AsyncContainer], name: str, value: str
) -> None:
    dp, container = app
    ali = await _on_home(dp)
    await _open_settings(ali)
    before = await _settings(container)
    await ali.press(ChangeSettingCallback(name=name, value=value))
    assert texts.STALE_BUTTON in ali.tg.alerts()
    assert await _settings(container) == before
    assert await _events(container, "setting_changed") == []


# ---------- 5. доводка настроек (TD-FN-93 пп. 1–5) ----------
def _deleted(person: Learner) -> set[int]:
    return {c.message_id for c in person.tg.calls if isinstance(c, DeleteMessage)}


def _sound_ids(person: Learner) -> list[int]:
    assert isinstance(person.tg, VoiceTelegram)
    return person.tg.sound_ids


@pytest.mark.parametrize(
    "away", [Home(), Lessons(part=-1), ShowSettings()], ids=["home", "lessons", "settings"]
)
async def test_auto_reference_is_removed_when_leaving_card_for_a_menu(
    app: tuple[Dispatcher, AsyncContainer], away: Any
) -> None:
    """П. 1: автоголосовое не остаётся висеть над главной, уроками и настройками."""
    dp, container = app
    ali = await _on_home(dp)
    await _set(container, PUPIL, auto_reference=True)
    await ali.press(GoItem(item_id=WITH_REFERENCE))
    [sound] = _sound_ids(ali)
    await ali.press(away)
    assert sound in _deleted(ali)


async def test_manual_listen_replaces_auto_reference_instead_of_adding_second(
    app: tuple[Dispatcher, AsyncContainer],
) -> None:
    """П. 2: «🔊 Как правильно» при автозвуке — эталон в чате один (старый заменяется новым)."""
    dp, container = app
    ali = await _on_home(dp)
    await _set(container, PUPIL, auto_reference=True)
    await ali.press(GoItem(item_id=WITH_REFERENCE))
    await ali.press(Listen(item_id=WITH_REFERENCE))
    auto, manual = _sound_ids(ali)
    assert auto in _deleted(ali), "автоэталон убран — второго эталона над карточкой нет"
    await ali.press(Home())
    assert manual in _deleted(ali), "и новый убирается, когда ученик уходит с карточки"


@pytest.mark.parametrize("inner", [texts.HELP_BUTTON, texts.PRIVACY_BUTTON])
async def test_help_and_privacy_from_settings_lead_back_to_settings(
    app: tuple[Dispatcher, AsyncContainer], inner: str
) -> None:
    """П. 3: из «Как заниматься» и «Мои данные» — «◀️ Настройки», на месте экрана."""
    dp, _ = app
    ali = await _on_home(dp)
    await _open_settings(ali)
    screen_id = ali.last_screen().message_id
    await _press_text(ali, inner)
    assert texts.BACK_TO_SETTINGS in _view(ali)[1], _view(ali)[1]
    await _press_text(ali, texts.BACK_TO_SETTINGS)
    assert _view(ali)[0] == texts.SETTINGS
    assert ali.last_screen().message_id == screen_id


async def test_my_id_replaces_settings_screen_and_leads_back(
    app: tuple[Dispatcher, AsyncContainer],
) -> None:
    """П. 4: «🪪 Мой ID» — на месте экрана, не новым сообщением."""
    dp, _ = app
    ali = await _on_home(dp)
    await _open_settings(ali)
    screen_id = ali.last_screen().message_id
    sent_before = sum(isinstance(c, SendMessage) for c in ali.tg.calls)
    await _press_text(ali, "🪪")
    caption, labels = _view(ali)
    assert caption.startswith(texts.ME_TEXT.split("{")[0]), caption
    assert ali.last_screen().message_id == screen_id
    assert sum(isinstance(c, SendMessage) for c in ali.tg.calls) == sent_before
    assert texts.BACK_TO_SETTINGS in labels, labels
    await _press_text(ali, texts.BACK_TO_SETTINGS)
    assert _view(ali)[0] == texts.SETTINGS


async def test_how_to_read_header_explains_itself_in_a_popup(
    app: tuple[Dispatcher, AsyncContainer],
) -> None:
    """П. 5: заголовок «🔤 Как читается:» выглядит кнопкой — отвечает подсказкой."""
    dp, container = app
    ali = await _on_home(dp)
    await _open_settings(ali)
    before = _view(ali)
    calls_before = len(ali.tg.calls)  # всплывающее «Понял…» из согласия — не в счёт
    await _press_text(ali, texts.SETTING_HOW_TO_READ)
    answers = [
        c for c in ali.tg.calls[calls_before:] if isinstance(c, AnswerCallbackQuery) and c.text
    ]
    assert [c.text for c in answers] == [texts.HOW_TO_READ_HINT]
    assert answers[0].show_alert, "всплывающее окно, а не исчезающая строка"
    assert _view(ali) == before
    assert await _events(container, "setting_changed") == []


async def test_old_settings_button_without_page_opens_settings(
    app: tuple[Dispatcher, AsyncContainer],
) -> None:
    """Кнопка ⚙️ из сообщений до выкладки поля ``page`` — callback_data ровно «settings»."""
    dp, _ = app
    ali = await _on_home(dp)
    assert ShowSettings().pack() != "settings"  # иначе проверка ничего не проверяет
    await ali.press("settings")
    assert texts.STALE_BUTTON not in ali.tg.alerts()
    assert _view(ali)[0] == texts.SETTINGS
