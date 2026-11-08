"""Ссылки на видеоурок (ADR-0082): ``curriculum/lesson_links.yaml``.

Ссылка урока главнее ``default``; годна только строка ``https://хост…`` (иначе Telegram отклонит
всю клавиатуру: ``BUTTON_URL_INVALID``). Плохая ссылка урока — ``None`` для него, без подмены на
``default``. Нет файла или он битый — ссылок нет, бот не падает.
"""

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml

from muallim.application.ports.storage import LessonLinks

logger = logging.getLogger(__name__)
MAX_LINK = 2048  # длиннее Telegram не принимает


def _https(value: Any) -> str | None:
    """Обрезанная ссылка, если это https с хостом; иначе None."""
    if not isinstance(value, str):
        return None
    link = value.strip()
    if len(link) > MAX_LINK or any(c.isspace() or not c.isprintable() for c in link):
        return None  # Telegram отклонит всю клавиатуру (BUTTON_URL_INVALID)
    parts = urlsplit(link)
    return link if parts.scheme.lower() == "https" and parts.netloc else None


@dataclass(frozen=True, slots=True)
class YamlLessonLinks(LessonLinks):
    default: str | None = None
    lessons: Mapping[str, str | None] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "YamlLessonLinks":
        if not path.is_file():
            return cls()
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            logger.warning("Файл ссылок %s не читается — кнопки видеоурока не будет", path)
            return cls()
        if not isinstance(data, dict):
            return cls()
        own = data.get("lessons")
        return cls(
            _https(data.get("default")),
            {str(k): _https(v) for k, v in own.items()} if isinstance(own, dict) else {},
        )

    def for_lesson(self, lesson_id: str) -> str | None:
        return self.lessons.get(lesson_id, self.default)
