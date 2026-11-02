"""«Как читается» строка (FR-43) и аят по слогам (FR-61): чтение без модели распознавания."""

from typing import Protocol

from muallim.domain.syllables import Ayah


class ReadingGuide(Protocol):
    def phonemes(self, text: str) -> str | None:
        """Фонемы чтения без остановки (васл) — со всеми огласовками, как написано в книге.

        Чтение с остановкой (вакф) бот тоже принимает, но на карточке показываем полное.
        None — фонетизатор недоступен или не разобрал строку.
        """


class AyahSyllables(Protocol):
    """Аят по слогам для карточки суры (FR-61, ADR-0077): разбор сделан заранее."""

    def for_text(self, text: str) -> Ayah | None:
        """Слова аята из клеток-слогов по точному тексту пункта; None — разбора нет или он
        отклонён человеком (``status: bad``)."""
