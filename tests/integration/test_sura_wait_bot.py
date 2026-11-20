"""Сура — сколько ждать (FR-70 ч. 7, FR-57; ADR-0088 «Порог времени для суры»: цель 30 с на 2 мин
записи, предел 60 с): бот сразу, до результата, пишет «проверяю, займёт ~N с», N — по длине записи.

Текст — ключ ``texts.SURA_CHECKING`` с местом ``{seconds}``; содержание утверждает автор. Настоящие
обработчики aiogram, DI и SQLite, распознавание — заглушка (как `test_sura_bot.py`).
"""

import re
from typing import Any

import pytest
from aiogram import Dispatcher
from dishka import AsyncContainer

from muallim.application.ports.recognition import RecognitionError
from muallim.presentation.telegram import texts
from muallim.presentation.telegram.callbacks import SuraOpen
from tests.integration import test_settings_bot
from tests.integration.test_bot_flow import Learner
from tests.integration.test_settings_bot import _events, _on_home

app = test_settings_bot.app

pytestmark = pytest.mark.integration

IKHLAS = 112


def _checking() -> re.Pattern[str]:
    template: str = texts.SURA_CHECKING
    assert "{seconds}" in template
    return re.compile(re.escape(template).replace(re.escape("{seconds}"), r"(\d+)"))


async def _read(dp: Dispatcher, seconds: int, tg: int) -> tuple[Learner, list[str]]:
    ali = await _on_home(dp, tg)
    await ali.press(SuraOpen(n=IKHLAS, m="t"))
    before = len(ali.tg.texts())
    await ali.voice(duration=seconds)
    return ali, ali.tg.texts()[before:]


def _estimate(shown: list[str]) -> tuple[int, int]:
    """(номер сообщения «проверяю…», N)."""
    pattern = _checking()
    found = [(k, m) for k, t in enumerate(shown) if (m := pattern.fullmatch(t))]
    assert found, f"нет сообщения «проверяю…»: {shown}"
    k, match = found[0]
    return k, int(match[1])


async def test_estimate_is_sent_before_the_result(app: tuple[Dispatcher, AsyncContainer]) -> None:
    dp, _ = app
    _, shown = await _read(dp, 20, 501)
    k, seconds = _estimate(shown)
    result = next(i for i, t in enumerate(shown) if texts.SURA_PASSED_TEXT in t)
    assert k < result
    assert seconds >= 1


async def test_estimate_is_already_sent_when_the_check_starts(
    app: tuple[Dispatcher, AsyncContainer], monkeypatch: pytest.MonkeyPatch
) -> None:
    """В момент вызова проверки суры (``ReadSura.execute``) «проверяю…» уже у ученика, а не
    отправляется вместе с результатом."""
    from muallim.application.use_cases.sura import ReadSura  # noqa: PLC0415

    dp, _ = app
    ali = await _on_home(dp, 504)
    await ali.press(SuraOpen(n=IKHLAS, m="t"))
    before = len(ali.tg.texts())
    seen: list[list[str]] = []
    original = ReadSura.execute

    async def execute(self: ReadSura, *args: Any, **kwargs: Any) -> Any:
        seen.append(ali.tg.texts()[before:])
        return await original(self, *args, **kwargs)

    monkeypatch.setattr(ReadSura, "execute", execute)
    await ali.voice(duration=20)
    assert len(seen) == 1
    pattern = _checking()
    assert any(pattern.fullmatch(t) for t in seen[0]), seen[0]


async def test_longer_recording_gets_a_longer_estimate(
    app: tuple[Dispatcher, AsyncContainer],
) -> None:
    dp, _ = app
    _, short = await _read(dp, 20, 502)
    _, long = await _read(dp, 120, 503)
    assert _estimate(short)[1] < _estimate(long)[1]


# ---------- сбой проверки: «не получилось», «проверяю…» убрано (ревью FR-70) ----------
@pytest.mark.parametrize(
    "error",
    [KeyError("sh"), ValueError("operands could not be broadcast"), RecognitionError("битая")],
)
async def test_failure_inside_the_check_shows_cant_process_and_removes_the_wait_message(
    app: tuple[Dispatcher, AsyncContainer], monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    """Любой сбой внутри проверки суры: ученик видит «не получилось обработать», а не «кнопка
    устарела»; сообщение «🎧 Проверяю…» удалено (не висит); сбой — в журнале с этапом."""
    from aiogram.methods import DeleteMessage  # noqa: PLC0415

    from muallim.infrastructure.asr.stub import StubRecognizer  # noqa: PLC0415

    async def broken(*args: Any, **kwargs: Any) -> Any:
        raise error

    monkeypatch.setattr(StubRecognizer, "recognize_sura", broken)
    dp, container = app
    ali = await _on_home(dp, 505)
    await ali.press(SuraOpen(n=IKHLAS, m="t"))
    before = len(ali.tg.shown)
    await ali.voice(duration=20)
    shown = ali.tg.shown[before:]
    texts_after = [m.text or m.caption or "" for m in shown]
    assert texts.CANT_PROCESS in texts_after
    assert texts.STALE_BUTTON not in texts_after
    pattern = _checking()
    waits = [m.message_id for m in shown if pattern.fullmatch(m.text or "")]
    assert waits, texts_after
    deleted = {c.message_id for c in ali.tg.calls if isinstance(c, DeleteMessage)}
    assert set(waits) <= deleted
    events = await _events(container, "sura_recognition_failed")
    assert [e["stage"] for e in events] == [getattr(error, "stage", "model")]
