"""Аят по слогам на карточке суры (FR-61, ADR-0077). Только правила.

Аят — кортеж слов, слово — кортеж клеток-слогов: кусочек текста аята и как он звучит. Разбор
делается заранее (``curriculum/syllables/ayat.yaml``), здесь — только тип и правило номера аята.
"""

from dataclasses import dataclass

from muallim.domain.curriculum import Lesson, LessonItem


@dataclass(frozen=True, slots=True)
class SyllableCell:
    """Клетка аята: кусочек слова (буквы с огласовками) и его звучание простой кириллицей."""

    text: str
    sound: str


type Word = tuple[SyllableCell, ...]
type Ayah = tuple[Word, ...]


def _reference(quran: str) -> tuple[str, int] | None:
    """«сура:аят» → (сура, номер); иначе None."""
    sura, _, ayah = quran.partition(":")
    if not sura or not ayah.isdigit():
        return None
    return sura, int(ayah)


def ayah_number(lesson: Lesson, item: LessonItem) -> int | None:
    """Номер аята в кружке после последнего слова.

    None — у пункта нет ``quran`` или его сура не совпадает с сурой остальных аятов урока
    (басмала перед сурой: номера у неё нет, кроме аль-Фатихи, где она — первый аят).
    """
    ref = _reference(item.quran)
    if ref is None:
        return None
    others = {
        other[0]
        for i in lesson.items
        if i.id != item.id and (other := _reference(i.quran)) is not None
    }
    if others and ref[0] not in others:
        return None
    return ref[1]
