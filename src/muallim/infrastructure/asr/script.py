"""Текст карточки → запись мусхафа, которую понимает фонетизатор quran-transcript.

Программа хранит текст после нормализации Unicode NFC. Шрифт рисует его так же, а фонетизатор —
нет: огласовка перед шаддой теряет удвоение («рабара» вместо «рабба»), огласовка перед хамзой над
татвилем и склеенная «آ» ломают разбор. Здесь — обратно к порядку мусхафа (аудит 2026-10-23).
"""

import re
from typing import Final

_VOWELS: Final = "ً-ِْ"  # танвины, фатха, дамма, кясра, сукун
_SHADDA_AFTER_VOWEL: Final = re.compile(f"([{_VOWELS}]+)ّ")
_HAMZA_AFTER_VOWEL: Final = re.compile(f"([{_VOWELS}]+)ٔ")
_ALIF_MADDA: Final = "آ"
# Книга пишет начальный алиф с огласовкой («اِسْتَغْفَرَ», «اَلْ»): начиная слово, его читают хамзой.
_WORD_START_ALIF: Final = re.compile("(?<!\\S)ا([َُِ])")
_HAMZA_SEAT: Final = {"َ": "أ", "ُ": "أ", "ِ": "إ"}


def for_phonetizer(text: str) -> str:
    text = _SHADDA_AFTER_VOWEL.sub("ّ\\1", text)
    text = _HAMZA_AFTER_VOWEL.sub("ٔ\\1", text)
    text = text.replace(_ALIF_MADDA, "آ")
    return _WORD_START_ALIF.sub(lambda m: _HAMZA_SEAT[m[1]] + m[1], text)
