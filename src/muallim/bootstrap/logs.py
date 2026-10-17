"""Логи процесса (ADR-0027): stdout → Docker с ротацией; без секретов и шума библиотеки модели.

Логи — для диагностики, не для исследования: события ученика пишутся в ``interaction_events``.
Что можно и нельзя писать в лог, проверяет ``tests/architecture/test_logging.py``.
"""

import logging
import re
import sys
from collections.abc import Iterable
from typing import TextIO

FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
MASK = "***"
_BOT_TOKEN = re.compile(r"(?<!\d)\d{6,}:[A-Za-z0-9_-]{30,}")  # и внутри URL: /bot<токен>/
_URL_PASSWORD = re.compile(r"(\b[\w+.-]+://[^:/\s@]+:)[^@\s]+@")


class RedactSecrets(logging.Filter):
    """Маскирует токен бота, пароли в URL и явно переданные секреты — в тексте и в traceback.

    Страховка на случай DEBUG или чужой библиотеки, которая напечатает URL запроса к Telegram.
    """

    def __init__(self, secrets: Iterable[str] = ()) -> None:
        super().__init__()
        self._secrets = tuple(s for s in secrets if s)

    def redact(self, text: str) -> str:
        for secret in self._secrets:
            text = text.replace(secret, MASK)
        text = _BOT_TOKEN.sub(MASK, text)
        return _URL_PASSWORD.sub(rf"\1{MASK}@", text)

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        clean = self.redact(message)
        if clean != message:
            record.msg, record.args = clean, None
        if record.exc_info and not record.exc_text:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = self.redact(record.exc_text)
        return True


class DropLibraryNoise(logging.Filter):
    """Quran Muaalem пишет INFO в корневой логгер на каждую запись (TD-FN-21).

    Предупреждения и ошибки библиотеки остаются.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        noisy = record.name == "root" and "quran_muaalem" in record.pathname
        return not (noisy and record.levelno < logging.WARNING)


def configure_logging(level: str, secrets: Iterable[str], stream: TextIO | None = None) -> None:
    """Единственное место настройки логов.

    Фильтры стоят на обработчике, а не на логгере, поэтому видят и логи чужих библиотек.
    """
    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(logging.Formatter(FORMAT))
    handler.addFilter(RedactSecrets(secrets))
    handler.addFilter(DropLibraryNoise())
    logging.basicConfig(level=level, handlers=[handler], force=True)
