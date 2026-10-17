"""«Как читается» от фонетизатора quran-transcript: правила чтения без модели (FR-43).

Те же параметры чтения, что у распознавания (``MOSHAF_PARAMS``), — транскрипция на карточке
совпадает с эталоном, по которому потом проверяется голосовое. Без extra ``ml`` — None.
"""

import logging
from dataclasses import dataclass
from typing import Final

from muallim.application.ports.reading import ReadingGuide

logger: Final = logging.getLogger(__name__)


@dataclass
class QuranReadingGuide(ReadingGuide):
    def phonemes(self, text: str) -> str | None:
        try:
            from muallim.infrastructure.asr.muaalem import _references  # noqa: PLC0415

            _, variants = _references(text)
        except ImportError:
            return None
        except Exception:  # фонетизатор не разбирает некоторые строки (например, с алифа)
            logger.info("Фонетизатор не разобрал строку карточки", exc_info=True)
            return None
        return dict(variants).get("wasl")
