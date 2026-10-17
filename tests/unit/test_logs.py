"""Фильтры логов (ADR-0027): секреты вычищаются, шум библиотеки модели отбрасывается."""

import io
import logging
import sys
from collections.abc import Iterator

import pytest

from muallim.bootstrap.logs import DropLibraryNoise, RedactSecrets, configure_logging

TOKEN = "1234567890:" + "x" * 35  # формат токена бота; собран в коде, чтобы не ловил gitleaks


def _record(
    msg: str, *args: object, name: str = "muallim", path: str = "x.py"
) -> logging.LogRecord:
    return logging.LogRecord(name, logging.INFO, path, 1, msg, args, None)


def test_bot_token_is_masked_even_if_not_configured() -> None:
    record = _record("GET https://api.telegram.org/bot%s/getUpdates", TOKEN)
    RedactSecrets().filter(record)
    assert TOKEN not in record.getMessage()
    assert "***" in record.getMessage()


def test_configured_secret_and_url_password_are_masked() -> None:
    record = _record(
        "connect postgresql+asyncpg://muallim:s3cret-pass@db:5432/muallim and %s", "k3y"
    )
    RedactSecrets(["k3y"]).filter(record)
    message = record.getMessage()
    assert "s3cret-pass" not in message and "k3y" not in message
    assert "postgresql+asyncpg://muallim:***@db" in message


def test_traceback_is_masked() -> None:
    try:
        raise RuntimeError(f"bad token {TOKEN}")
    except RuntimeError:
        record = logging.LogRecord("m", logging.ERROR, "x.py", 1, "сбой", None, sys.exc_info())
    RedactSecrets().filter(record)
    assert record.exc_text is not None and TOKEN not in record.exc_text


def test_filter_never_drops_records() -> None:
    assert RedactSecrets().filter(_record("обычное сообщение")) is True


def test_muaalem_info_noise_dropped_but_warnings_kept() -> None:
    noisy = "/site-packages/quran_muaalem/decode.py"
    drop = DropLibraryNoise()
    assert drop.filter(_record("mismatch Level: 2", name="root", path=noisy)) is False
    warning = _record("model failed", name="root", path=noisy)
    warning.levelno = logging.WARNING
    assert drop.filter(warning) is True
    assert drop.filter(_record("Программа в БД", name="muallim.bootstrap.main")) is True


@pytest.fixture
def restore_root() -> Iterator[None]:
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    yield
    root.handlers, root.level = handlers, level


def test_configure_logging_installs_filters_on_the_handler(restore_root: None) -> None:
    stream = io.StringIO()
    configure_logging("INFO", [TOKEN], stream=stream)
    logging.getLogger("aiogram.event").info("token %s", TOKEN)
    logging.getLogger("muallim.test").debug("не видно на INFO")
    output = stream.getvalue()
    assert "token ***" in output
    assert TOKEN not in output and "не видно" not in output
