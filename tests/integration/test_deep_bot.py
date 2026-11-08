"""FR-66, FR-67 (ADR-0082, срез 1): «📖 Углублённо», «⋯ Ещё» и упрощённые экраны через бота.

Настоящие обработчики, DI и SQLite (окружение — как в test_settings_bot); распознавание — заглушка.
Открытие «Углублённо» пишет событие ``deep_opened`` {item_id} (схема БД не меняется). Старые
кнопки (``Help``, ``Privacy``, ``Me``, ``ShowSettings``, ``ShowProgress``, ``Signs``, ``SuraList``,
``LettersSheet``) из прежних сообщений продолжают отвечать. Переключателя «Данные для
исследования» нет, а учитель и разметчик по-прежнему видят блок «Для исследования».
"""

from pathlib import Path
from typing import Any

import pytest
from aiogram import Dispatcher
from dishka import AsyncContainer

from muallim.application.ports.repositories import LearnerRepository
from muallim.presentation.telegram import callbacks as cb
from muallim.presentation.telegram import texts
from muallim.presentation.telegram.callbacks import (
    GoItem,
    Home,
    Privacy,
    ShowSettings,
)
from tests.conftest import CURRICULUM_DIR
from tests.integration import test_settings_bot as settings_bot
from tests.integration.test_bot_flow import Learner
from tests.integration.test_settings_bot import (
    ISTI_ADHA,
    PUPIL,
    WITH_REFERENCE,
    _buttons,
    _events,
    _on_home,
    _read_isti_adha,
    _set,
    _view,
)

app = settings_bot.app  # окружение бота — та же фикстура (SQLite, DI, эталоны в tmp_path)

pytestmark = pytest.mark.integration

DEEP = "📖 Подробнее"
STUB = "https://www.youtube.com/"
MIM_STEP = "L006-03"


def _urls(person: Learner) -> list[tuple[str, str]]:
    markup = person.last_screen().reply_markup
    assert markup is not None
    return [(b.text, b.url) for row in markup.inline_keyboard for b in row if b.url]


async def test_deep_opened_event_recorded(app: tuple[Dispatcher, AsyncContainer]) -> None:
    dp, container = app
    ali = await _on_home(dp)
    await ali.press(GoItem(item_id=WITH_REFERENCE))
    assert await _events(container, "deep_opened") == []
    await ali.press(cb.Deep(item_id=WITH_REFERENCE))
    events = await _events(container, "deep_opened")
    assert [e["item_id"] for e in events] == [WITH_REFERENCE]


async def test_deep_screen_replaces_card_in_place_and_goes_back(
    app: tuple[Dispatcher, AsyncContainer],
) -> None:
    dp, _ = app
    ali = await _on_home(dp)
    await ali.press(GoItem(item_id=WITH_REFERENCE))
    card = _view(ali)
    screen_id = ali.last_screen().message_id
    had_photo = bool(ali.last_screen().photo)
    await ali.press(cb.Deep(item_id=WITH_REFERENCE))
    assert _view(ali)[0] != card[0]
    # без картинки экран меняется на месте (ADR-0024); фото в текст правкой не превратить —
    # тогда старое сообщение заменяется новым (Display.show)
    assert (ali.last_screen().message_id == screen_id) is not had_photo
    assert "◀️ К уроку" in _view(ali)[1]
    await ali.press(GoItem(item_id=WITH_REFERENCE))
    assert _view(ali) == card


async def test_deep_video_button_is_url_from_links_file(
    app: tuple[Dispatcher, AsyncContainer],
) -> None:
    from muallim.infrastructure.curriculum.lesson_links import YamlLessonLinks  # noqa: PLC0415

    dp, _ = app
    expected = YamlLessonLinks.load(CURRICULUM_DIR / "lesson_links.yaml").for_lesson("L006")
    assert expected is not None and expected.startswith("https://")
    ali = await _on_home(dp)
    await ali.press(cb.Deep(item_id=WITH_REFERENCE))
    assert _urls(ali) == [("🎥 Видеоурок на YouTube", expected)]


async def test_deep_video_link_override_by_lesson_via_di(
    app: tuple[Dispatcher, AsyncContainer], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from muallim.infrastructure.curriculum.lesson_links import YamlLessonLinks  # noqa: PLC0415

    own, other = "https://example.org/own", "https://example.org/default"
    links = tmp_path / "links" / "lesson_links.yaml"
    links.parent.mkdir()
    links.write_text(f"default: {other}\nlessons:\n  L006: {own}\n", encoding="utf-8")
    original = YamlLessonLinks.load
    monkeypatch.setattr(YamlLessonLinks, "load", classmethod(lambda cls, _p: original(links)))
    dp, _ = app
    ali = await _on_home(dp)
    await ali.press(cb.Deep(item_id=WITH_REFERENCE))  # урок 6
    assert _urls(ali) == [("🎥 Видеоурок на YouTube", own)]
    await ali.press(cb.Deep(item_id=ISTI_ADHA))  # урок 1 — default
    assert _urls(ali) == [("🎥 Видеоурок на YouTube", other)]


async def test_deep_card_button_opens_deep_from_card(
    app: tuple[Dispatcher, AsyncContainer],
) -> None:
    dp, _ = app
    ali = await _on_home(dp)
    await ali.press(GoItem(item_id=MIM_STEP))
    assert (DEEP, cb.Deep(item_id=MIM_STEP).pack()) in _buttons(ali)
    await ali.press(cb.Deep(item_id=MIM_STEP))
    assert texts.SHEET_BUTTON in _view(ali)[1]


async def test_container_resolves_lesson_links(app: tuple[Dispatcher, AsyncContainer]) -> None:
    """Порт ``LessonLinks`` зарегистрирован в bootstrap/di.py (curriculum/lesson_links.yaml)."""
    from muallim.application.ports.storage import LessonLinks  # noqa: PLC0415

    _, container = app
    links = await container.get(LessonLinks)
    link = links.for_lesson("L006")
    assert link is not None and link.startswith("https://")


async def test_home_more_and_lessons_flow(app: tuple[Dispatcher, AsyncContainer]) -> None:
    dp, _ = app
    ali = await _on_home(dp)
    labels = [t for t, _ in _buttons(ali)]
    assert labels[1:] == [texts.LESSONS_BUTTON, texts.QUIZ_BUTTON, "⋯ Ещё"], labels
    lessons = [d for t, d in _buttons(ali) if t == texts.LESSONS_BUTTON]
    await ali.press(lessons[0])
    assert texts.PARTS.split("\n")[0] not in _view(ali)[0]  # сразу часть, а не список частей
    assert texts.PARTS_BUTTON in _view(ali)[1]
    await ali.press(Home())
    more = [d for t, d in _buttons(ali) if t == "⋯ Ещё"]
    await ali.press(more[0])
    assert _view(ali)[1] == [
        texts.PROGRESS_BUTTON, texts.SIGNS_BUTTON, texts.MEMORY_BUTTON, texts.SETTINGS_BUTTON,
        texts.HELP_BUTTON, texts.HOME_BUTTON,
    ]  # fmt: skip


async def test_help_opened_from_more_returns_to_more(
    app: tuple[Dispatcher, AsyncContainer],
) -> None:
    dp, _ = app
    ali = await _on_home(dp)
    await ali.press(cb.More())
    more_view = _view(ali)
    help_data = [d for t, d in _buttons(ali) if t == texts.HELP_BUTTON]
    await ali.press(help_data[0])
    assert _view(ali)[0] == texts.HELP
    await ali.press(cb.More())
    assert _view(ali) == more_view


async def test_settings_screen_has_no_research_toggle_or_my_id(
    app: tuple[Dispatcher, AsyncContainer],
) -> None:
    dp, _ = app
    ali = await _on_home(dp)
    await ali.press(ShowSettings())
    labels = _view(ali)[1]
    assert not [t for t in labels if "🔬" in t or "🪪" in t]
    assert texts.HELP_BUTTON not in labels and texts.PRIVACY_BUTTON in labels


async def test_privacy_screen_contains_my_id(app: tuple[Dispatcher, AsyncContainer]) -> None:
    dp, container = app
    ali = await _on_home(dp)
    async with container() as request:
        learner = await (await request.get(LearnerRepository)).get_by_telegram_id(PUPIL)
    assert learner is not None
    await ali.press(Privacy())
    assert learner.pseudonym in _view(ali)[0]


def _answers(person: Learner, since: int) -> list[str]:
    """Тексты и подписи сообщений бота после ``since``-го (новые и изменённые экраны)."""
    return [m.text or m.caption or "" for m in person.tg.shown[since:]]


async def test_old_help_privacy_me_buttons_still_answer(
    app: tuple[Dispatcher, AsyncContainer],
) -> None:
    """Кнопки из старых сообщений в чатах не «умирают» (ADR-0082, Б): каждая даёт текст."""
    dp, container = app
    ali = await _on_home(dp)
    async with container() as request:
        learner = await (await request.get(LearnerRepository)).get_by_telegram_id(PUPIL)
    assert learner is not None
    old: list[Any] = [
        cb.Help(), cb.Privacy(), cb.Me(), cb.ShowSettings(), cb.ShowProgress(), cb.Signs(),
        cb.SuraList(), cb.LettersSheet(lesson_id="L006", item_id=MIM_STEP), cb.Lessons(part=-1),
    ]  # fmt: skip
    for data in old:
        before = len(ali.tg.shown)
        await ali.press(data)
        shown = _answers(ali, before)
        assert shown and all(t.strip() for t in shown), data
        if isinstance(data, cb.Help):
            assert texts.HELP in shown[-1]
        if isinstance(data, cb.Me):
            assert any(learner.pseudonym in t for t in shown)
        await ali.press(cb.Home())


async def test_pupil_does_not_see_research_block_even_if_old_flag_is_set(
    app: tuple[Dispatcher, AsyncContainer],
) -> None:
    """Колонка ``research_block`` остаётся в БД, но ничего не включает (ADR-0082 п. 6)."""
    dp, container = app
    ali = await _on_home(dp)
    await _set(container, PUPIL, research_block=True)
    result = await _read_isti_adha(ali)
    assert texts.VERDICT_EXCELLENT in result
    assert "Для исследования" not in result and "Попытка №" not in result


async def test_more_leads_to_settings(app: tuple[Dispatcher, AsyncContainer]) -> None:
    dp, _ = app
    ali = await _on_home(dp)
    await ali.press(cb.More())
    settings = [d for t, d in _buttons(ali) if t == texts.SETTINGS_BUTTON]
    assert len(settings) == 1
    await ali.press(settings[0])
    assert _view(ali)[0] == texts.SETTINGS
    assert cb.More().pack() in [d for _, d in _buttons(ali)]


async def test_lessons_command_opens_learner_part(app: tuple[Dispatcher, AsyncContainer]) -> None:
    """``/lessons`` — по тому же правилу, что «📚 Уроки» с главной: сразу часть ученика."""
    dp, _ = app
    ali = await _on_home(dp)
    await ali.press(GoItem(item_id=MIM_STEP))  # курсор — урок 6
    await ali.write("/lessons")
    caption, labels = _view(ali)
    assert texts.PARTS.split("\n")[0] not in caption
    assert texts.PARTS_BUTTON in labels
    assert any("Мим" in t or "م" in t for t in labels)  # урок ученика виден на странице части


async def test_deep_opened_not_written_on_back(app: tuple[Dispatcher, AsyncContainer]) -> None:
    dp, container = app
    ali = await _on_home(dp)
    await ali.press(GoItem(item_id=WITH_REFERENCE))
    await ali.press(cb.Deep(item_id=WITH_REFERENCE))
    await ali.press(GoItem(item_id=WITH_REFERENCE))  # «◀️ К уроку»
    assert len(await _events(container, "deep_opened")) == 1


async def test_deep_opened_from_result_with_errors(
    app: tuple[Dispatcher, AsyncContainer], monkeypatch: pytest.MonkeyPatch
) -> None:
    from muallim.application.ports.recognition import Recognition  # noqa: PLC0415
    from muallim.infrastructure.asr.stub import StubRecognizer  # noqa: PLC0415

    async def recognize(self: StubRecognizer, audio: bytes, text: str) -> Recognition:
        return Recognition(
            heard="سَ", references=(("waqf", text),), model_version="stub", audio_duration_ms=0
        )

    monkeypatch.setattr(StubRecognizer, "recognize", recognize)
    dp, container = app
    ali = await _on_home(dp)
    await ali.press(GoItem(item_id=WITH_REFERENCE))
    await ali.voice()
    await ali.press(cb.Deep(item_id=WITH_REFERENCE))
    assert [e["item_id"] for e in await _events(container, "deep_opened")] == [WITH_REFERENCE]


async def test_stale_deep_does_not_crash_and_writes_no_event(
    app: tuple[Dispatcher, AsyncContainer],
) -> None:
    dp, container = app
    ali = await _on_home(dp)
    await ali.press(cb.Deep(item_id="нет-такого"))
    assert await _events(container, "deep_opened") == []
