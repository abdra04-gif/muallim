"""«📖 Вся сура» и «Наизусть» через настоящие обработчики aiogram (FR-57…FR-59, ADR-0076).

Настоящие DI и SQLite, распознавание — заглушка: «читает» суру без ошибок. Голосовое уходит в
проверку суры, только пока на экране сура (как карточка: решение автора 2026-10-20); наизусть —
только после «Готов», когда текст уже скрыт.
"""

from typing import Any

import pytest
from aiogram import Dispatcher
from aiogram.methods import SendMessage
from dishka import AsyncContainer

from muallim.application.ports.repositories import AttemptRepository, SuraReadingRepository
from muallim.infrastructure.curriculum.yaml_loader import load_curriculum
from muallim.presentation.telegram import texts
from muallim.presentation.telegram.callbacks import GoItem, Home, SuraList, SuraOpen, SuraReady
from tests.conftest import CURRICULUM_DIR
from tests.integration import test_settings_bot
from tests.integration.test_bot_flow import Learner
from tests.integration.test_settings_bot import (
    PUPIL,
    _buttons,
    _events,
    _learner_id,
    _on_home,
    _view,
)

app = test_settings_bot.app  # та же фикстура бота: настоящие DI, SQLite, заглушка модели

pytestmark = pytest.mark.integration

IKHLAS = 112  # аль-Ихлас: урок L123, басмала L123-01, аяты L123-02…05
# аят 2 аль-Ихлас — есть ли текст на экране; текст — из программы, не по памяти (CLAUDE.md)
FIRST_AYAH = (
    load_curriculum(CURRICULUM_DIR / "course.ru.yaml", CURRICULUM_DIR / "lexicon.ru.yaml")
    .item("L123-03")
    .text
)


def _replies(person: Learner) -> list[str]:
    return [c.text for c in person.tg.calls if isinstance(c, SendMessage)]


async def test_memory_from_home_hides_text_after_ready_and_gives_the_mark(
    app: tuple[Dispatcher, AsyncContainer],
) -> None:
    dp, container = app
    ali = await _on_home(dp)
    await ali.press(SuraList())
    await ali.press(SuraOpen(n=IKHLAS, m="m"))
    assert FIRST_AYAH in _view(ali)[0]  # сначала текст виден
    await ali.press(SuraReady(n=IKHLAS))
    assert FIRST_AYAH not in _view(ali)[0]  # «Готов» — текст пропал
    await ali.voice(duration=20)
    assert texts.SURA_PASSED_MEMORY in _view(ali)[0]
    [event] = await _events(container, "sura_read")
    assert event["mode"] == "memory" and event["passed"] == 1
    async with container() as request:
        repo = await request.get(SuraReadingRepository)
        assert await repo.memorized(await _learner_id(container, PUPIL)) == {IKHLAS}
    await ali.press(Home())
    await ali.press(SuraList())
    [mark] = [t for t, d in _buttons(ali) if d == SuraOpen(n=IKHLAS, m="m").pack()]
    assert "✅" in mark


async def test_voice_before_ready_is_not_checked(app: tuple[Dispatcher, AsyncContainer]) -> None:
    dp, container = app
    ali = await _on_home(dp)
    await ali.press(SuraList())
    await ali.press(SuraOpen(n=IKHLAS, m="m"))
    await ali.voice(duration=20)
    assert texts.SURA_PRESS_READY in _replies(ali)
    assert await _events(container, "sura_read") == []


async def test_whole_sura_from_card_counts_the_lessons(
    app: tuple[Dispatcher, AsyncContainer],
) -> None:
    dp, container = app
    ali = await _on_home(dp)
    await ali.press(GoItem(item_id="L123-03"))
    await ali.press(SuraOpen(n=IKHLAS, m="t"))
    assert FIRST_AYAH in _view(ali)[0]
    await ali.voice(duration=20)
    assert texts.SURA_PASSED_TEXT in _view(ali)[0]
    async with container() as request:
        best = await (await request.get(AttemptRepository)).best_scores(
            await _learner_id(container, PUPIL)
        )
    assert all(best.get(f"L123-0{n}") == 100 for n in range(1, 6))


async def test_voice_after_leaving_the_sura_is_not_a_sura_reading(
    app: tuple[Dispatcher, AsyncContainer],
) -> None:
    dp, container = app
    ali = await _on_home(dp)
    await ali.press(SuraOpen(n=IKHLAS, m="t"))
    await ali.press(Home())
    await ali.voice(duration=20)
    assert await _events(container, "sura_read") == []
    assert texts.VOICE_ON_HOME in [*_replies(ali), _view(ali)[0]]


async def test_result_offers_to_read_again(app: tuple[Dispatcher, AsyncContainer]) -> None:
    dp, _ = app
    ali = await _on_home(dp)
    await ali.press(SuraOpen(n=IKHLAS, m="t"))
    await ali.voice(duration=20)
    data: list[Any] = [d for _, d in _buttons(ali)]
    assert SuraOpen(n=IKHLAS, m="t").pack() in data
