"""Фильтры логов (ADR-0027): секреты вычищаются, шум библиотеки модели отбрасывается."""

import io
import logging
import sys
from collections.abc import Iterator
from pathlib import Path

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


def test_log_file_keeps_records_after_the_terminal_is_closed(
    restore_root: None, tmp_path: Path
) -> None:
    """ADR-0048: логи пишутся и в файл — с теми же фильтрами, что и в консоль."""
    log_file = tmp_path / "logs" / "bot.log"
    configure_logging("INFO", [TOKEN], stream=io.StringIO(), file=log_file)
    logging.getLogger("muallim.test").info("запуск, токен %s", TOKEN)
    for handler in logging.getLogger().handlers:
        handler.flush()
    written = log_file.read_text(encoding="utf-8")
    assert "запуск, токен ***" in written
    assert TOKEN not in written


def test_log_file_is_rotated(restore_root: None, tmp_path: Path) -> None:
    """Срок хранения ограничен объёмом: не больше backups + 1 файлов по max_bytes."""
    log_file = tmp_path / "bot.log"
    configure_logging("INFO", [], stream=io.StringIO(), file=log_file, max_bytes=2_000, backups=2)
    for i in range(200):
        logging.getLogger("muallim.test").info("строка %03d %s", i, "x" * 40)
    files = sorted(p.name for p in tmp_path.iterdir())
    assert files == ["bot.log", "bot.log.1", "bot.log.2"]


def test_no_log_file_when_disabled(restore_root: None, tmp_path: Path) -> None:
    configure_logging("INFO", [], stream=io.StringIO(), file=None)
    logging.getLogger("muallim.test").info("только в консоль")
    assert not any(isinstance(h, logging.FileHandler) for h in logging.getLogger().handlers)
    assert list(tmp_path.iterdir()) == []


def test_empty_log_file_setting_means_console_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """``LOG_FILE=`` (пусто, как в .env.example и Docker) — без файла, а не файл с путём «.»."""
    from muallim.bootstrap.config import Settings  # noqa: PLC0415

    monkeypatch.setenv("BOT_TOKEN", "x")
    monkeypatch.setenv("LOG_FILE", "")
    assert Settings().log_file is None
