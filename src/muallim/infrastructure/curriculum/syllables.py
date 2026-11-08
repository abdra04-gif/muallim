"""Аяты по слогам (FR-61, ADR-0077): curriculum/syllables/ayat.yaml.

Устроено как ``VideoLibrary`` (ADR-0074): поиск по точному тексту пункта; отдаётся любой статус:
``unchecked`` и ``bad`` тоже — ``bad`` только пометка «поправить разбор», карточку по слогам она
не прячет (FR-62, ADR-0079 п. 7, решение автора 2026-10-31). Нет файла — пустая библиотека.
Строка, чьи кусочки не складываются ровно в ``text`` (файл устарел или правлен руками), —
пропускается: бот покажет прежнюю карточку. Файл собирает ``scripts/syllables/build.py``.
"""

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from muallim.application.ports.reading import AyahSyllables
from muallim.domain.syllables import Ayah, SyllableCell

logger = logging.getLogger(__name__)


def _ayah(row: Mapping[str, Any]) -> Ayah | None:
    """Слова строки файла; None — строка битая или кусочки не складываются в текст."""
    words = row.get("words")
    if not isinstance(words, list):
        return None
    try:
        ayah = tuple(
            tuple(SyllableCell(str(piece), str(sound)) for piece, sound in word) for word in words
        )
    except (TypeError, ValueError):
        return None
    joined = " ".join("".join(cell.text for cell in word) for word in ayah)
    return ayah if ayah and joined == str(row.get("text", "")) else None


@dataclass(frozen=True, slots=True)
class SuraSyllables(AyahSyllables):
    """Слоги только аятов уроков «Суры» — для разметки: клетки строк из книги в ней остаются
    буквами, как до слогов на всех карточках (автор 2026-11-08: разметку пока не трогать)."""

    inner: AyahSyllables
    texts: frozenset[str]

    def for_text(self, text: str) -> Ayah | None:
        return self.inner.for_text(text) if text in self.texts else None


@dataclass(frozen=True, slots=True)
class SyllableLibrary(AyahSyllables):
    ayat: Mapping[str, Ayah] = field(default_factory=dict)  # текст пункта → слова

    @classmethod
    def load(cls, path: Path) -> "SyllableLibrary":
        if not path.is_file():
            return cls()
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            logger.warning("Файл слогов %s не читается — карточки сур без слогов", path)
            return cls()
        rows = (data.get("ayat") or []) if isinstance(data, dict) else []
        ayat: dict[str, Ayah] = {}
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict) or not isinstance(row.get("text"), str):
                continue  # строка испорчена ручной правкой — пропуск
            ayah = _ayah(row)
            if ayah is not None:
                ayat[str(row["text"])] = ayah
        return cls(ayat)

    def for_text(self, text: str) -> Ayah | None:
        return self.ayat.get(text)
