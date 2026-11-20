"""Фонетизатор бота (quran-transcript): текст карточки → звуки по Хафсу (ADR-0007, ADR-0088).

Общий для обеих моделей: Muaalem получает эталон прямо в этой записи, MostafaMaroof — после
перевода в свой алфавит (`maroof_script.to_maroof`). quran-transcript ставится с extra ``ml`` и
импортируется лениво.
"""

from dataclasses import fields
from functools import lru_cache
from typing import Any

from muallim.infrastructure.asr.script import for_phonetizer

# Параметры чтения: риваят Хафс, все мадды по 4 харакята. Методическое решение — менять
# только человеку. Строка входит в model_version, поэтому видна в каждой попытке в БД.
MOSHAF_PARAMS: dict[str, Any] = {
    "rewaya": "hafs",
    "madd_monfasel_len": 4,
    "madd_mottasel_len": 4,
    "madd_mottasel_waqf": 4,
    "madd_aared_len": 4,
}

# Слог, который дописываем, чтобы получить чтение без остановки (васл) — см. ADR-0007.
_WASL_SUFFIX = " مَ"


@lru_cache(maxsize=1024)
def _references(text: str) -> tuple[Any, tuple[tuple[str, str], tuple[str, str]]]:
    """Эталон для модели и два допустимых варианта: со слитным чтением (васл) и с остановкой.

    Варианты — только из звуков, которые модель умеет выдать: знак мадда «ٓ» над словом, вырезанным
    из аята, фонетизатор оставляет как есть (в аяте за ним шла хамза), а это письмо, не звук.
    """
    from quran_transcript import MoshafAttributes, quran_phonetizer  # noqa: PLC0415

    moshaf = MoshafAttributes(**MOSHAF_PARAMS)
    text = for_phonetizer(text)
    waqf = quran_phonetizer(text, moshaf, remove_spaces=True)
    wasl = quran_phonetizer(text + _WASL_SUFFIX, moshaf, remove_spaces=True).phonemes[:-1]
    sounds = _model_sounds()
    return waqf, (
        ("wasl", "".join(ch for ch in wasl if ch in sounds)),
        ("waqf", "".join(ch for ch in waqf.phonemes if ch in sounds)),
    )


@lru_cache(maxsize=1)
def _model_sounds() -> frozenset[str]:
    """Алфавит фонем модели (quran-transcript): буквы, огласовки, мадд, калькаля, ихфа…"""
    from quran_transcript import alphabet  # noqa: PLC0415

    ph = alphabet.phonetics
    return frozenset("".join(getattr(ph, f.name) for f in fields(ph)))
