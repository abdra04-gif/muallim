"""FR-52 (пакет В, круг 1, ADR-0062): шпаргалка букв через бота.

Карточка урока → «шпаргалка» (буквы по книге до урока) → 🔊 буквы → «◀️ Назад» на ту же карточку;
«🔤 Знаки» → шпаргалка до урока, где ученик остановился → «◀️ Назад» на «Знаки».
Настоящие обработчики, DI и SQLite (окружение — как в test_settings_bot); распознавание — заглушка.
"""

from pathlib import Path

import pytest
from aiogram import Dispatcher
from dishka import AsyncContainer

from muallim.presentation.telegram import texts
from muallim.presentation.telegram.callbacks import GoItem, Home, Signs
from tests.integration import test_settings_bot as settings_bot
from tests.integration.test_settings_bot import VoiceTelegram, _find, _on_home, _view

app = settings_bot.app  # окружение бота — та же фикстура (SQLite, DI, эталоны в tmp_path)

pytestmark = pytest.mark.integration

MIM_STEP = "L006-03"  # «مِ», урок 6 · Мим: до него по книге — ء ر ز
RA_HEAD = "L004-05"  # «رَ رِ رُ» — головная карточка урока ر


async def test_sheet_from_card_shows_known_letters_and_returns_to_card(
    app: tuple[Dispatcher, AsyncContainer],
) -> None:
    dp, _ = app
    person = await _on_home(dp)
    await person.press(GoItem(item_id=MIM_STEP))
    card_caption, _ = _view(person)
    await person.press(_find(person, texts.SHEET_BUTTON))
    caption, _ = _view(person)
    for letter, name in (("أ", "Элиф с хэмзэ"), ("ر", "Ра"), ("ز", "Зэй")):
        assert letter in caption and name in caption
    assert "Мим" not in caption
    await person.press(_find(person, texts.BACK_BUTTON))
    assert _view(person)[0] == card_caption


async def test_sheet_listen_sends_the_letter_reference(
    app: tuple[Dispatcher, AsyncContainer], tmp_path: Path
) -> None:
    dp, _ = app
    (tmp_path / "reference" / f"{RA_HEAD}.ogg").write_bytes(b"OggS-ra-reference")
    person = await _on_home(dp)
    await person.press(GoItem(item_id=MIM_STEP))
    await person.press(_find(person, texts.SHEET_BUTTON))
    listen = [t for t in _view(person)[1] if "🔊" in t and "ر" in t]
    assert len(listen) == 1, _view(person)[1]
    await person.press(_find(person, listen[0]))
    assert isinstance(person.tg, VoiceTelegram)
    assert person.tg.sound_ids  # эталон пришёл голосовым


async def test_sheet_from_signs_follows_learner_lesson_and_returns_to_signs(
    app: tuple[Dispatcher, AsyncContainer],
) -> None:
    dp, _ = app
    person = await _on_home(dp)
    await person.press(GoItem(item_id=MIM_STEP))  # курсор — урок 6
    await person.press(Home())
    await person.press(Signs())
    signs_caption, _ = _view(person)
    await person.press(_find(person, texts.SHEET_BUTTON))
    caption, _ = _view(person)
    assert "Зэй" in caption and "Мим" not in caption
    await person.press(_find(person, texts.BACK_BUTTON))
    assert _view(person)[0] == signs_caption


async def test_new_learner_signs_have_no_sheet(app: tuple[Dispatcher, AsyncContainer]) -> None:
    dp, _ = app
    person = await _on_home(dp)
    await person.press(Signs())
    assert all(not t.startswith(texts.SHEET_BUTTON) for t in _view(person)[1])
