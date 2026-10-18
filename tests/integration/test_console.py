"""Проверка бота из терминала (TD-FN-61, SRC-072): `uv run muallim --test "/start" "кнопка" "🎤"`.

Настоящие обработчики, DI и экраны; вместо Telegram — сессия в памяти, вместо базы учеников —
временная SQLite, вместо модели — заглушка. `.env` не читается: настоящий токен и данные
учеников этому режиму не нужны и недоступны.
"""

import sys

import pytest

from muallim.bootstrap import console, main
from muallim.presentation.telegram import texts

pytestmark = pytest.mark.integration


def _plain(html: str) -> str:
    return console.plain(html)


async def test_start_shows_welcome_and_consent_buttons() -> None:
    out = await console.run_console(["/start"])
    assert "▶ /start" in out
    assert _plain(texts.WELCOME).splitlines()[0] in out
    assert f"[{texts.CONSENT_YES_BUTTON}]" in out and f"[{texts.CONSENT_NO_BUTTON}]" in out
    assert "заглушка" in out.lower()  # человек должен знать, что модель не настоящая


async def test_button_is_pressed_by_its_label() -> None:
    out = await console.run_console(["/start", texts.CONSENT_YES_BUTTON])
    assert _plain(texts.CONSENT_SAVED_YES) in out
    assert _plain(texts.PROFILE_ADULT).splitlines()[-1] in out  # дальше — анкета
    assert f"[{texts.PROFILE_ADULT_YES}]" in out


async def test_unknown_label_is_sent_as_text() -> None:
    out = await console.run_console(["/start", "привет"])
    assert _plain(texts.SEND_VOICE) in out


async def test_voice_goes_through_recognition_stub() -> None:
    out = await console.run_console(["/start", texts.CONSENT_NO_BUTTON, "🎤"])
    assert "▶ 🎤 голосовое" in out
    assert "Traceback" not in out


async def test_does_not_touch_real_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Даже если в окружении настоящая база и токен — режим проверки их не использует."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://real:secret@prod:5432/muallim")
    monkeypatch.setenv("BOT_TOKEN", "123:real-token")
    monkeypatch.setenv("ASR_BACKEND", "muaalem")
    out = await console.run_console(["/start"])
    assert "real-token" not in out and "prod" not in out
    assert f"[{texts.CONSENT_YES_BUTTON}]" in out


def test_command_line(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(sys, "argv", ["muallim", "--test", "/start"])
    main.run()
    assert f"[{texts.CONSENT_YES_BUTTON}]" in capsys.readouterr().out


def test_plain_text_drops_html_and_keeps_arabic() -> None:
    assert console.plain("<b>صَ</b> &lt;3 <i>урок</i>") == "صَ <3 урок"
