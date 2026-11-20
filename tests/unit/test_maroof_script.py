"""Запись фонетизатора бота → символы модели MostafaMaroof (FR-70 п. 1, ADR-0087 п. 8, ADR-0088).

Ожидаемое поведение сверено с прототипом `docs/research/phase3/to_maroof.py`. Строки — запись
фонетизатора бота (quran-transcript) для карточек из `curriculum/course.ru.yaml`: «بُ», «رَبَّ»,
«بَا», «قِيلَ», «لَوْ», «دَ»; повторы и знаки ихфа — короткие куски той же записи.
"""

import pytest

# шадда и сукун письма, латиница — не знаки записи фонетизатора
NOT_PHONETIC = ["بّ", "بْ", "b"]

from muallim.infrastructure.asr.maroof_script import to_maroof  # noqa: E402


def test_letter_with_vowel_becomes_two_sounds() -> None:
    assert to_maroof("بُ") == ("b", "u")  # «بُ», wasl


def test_repeated_letter_becomes_doubled_symbol() -> None:
    assert to_maroof("رَببَ") == ("r", "a", "bb", "a")  # «رَبَّ», wasl


def test_letter_repeated_many_times_is_still_one_doubled_symbol() -> None:
    assert to_maroof("ننننَ") == ("nn", "a")


def test_hidden_nun_held_long_is_one_plain_n() -> None:
    assert to_maroof("ںںں") == ("n",)


def test_waw_without_vowel_after_it_at_a_stop_is_single() -> None:
    assert to_maroof("لَووو") == ("l", "a", "w")  # «لَوْ», waqf
    assert to_maroof("لَوو") == ("l", "a", "w")


def test_vowel_with_madd_signs_is_long_whatever_their_count() -> None:
    assert to_maroof("بَاا") == ("b", "aa")  # «بَا»
    assert to_maroof("قِۦۦ") == ("q", "ii")
    assert to_maroof("قِۦۦۦۦل") == ("q", "ii", "l")  # «قِيلَ», waqf


def test_madd_sign_without_vowel_before_it_is_long() -> None:
    assert to_maroof("بۥۥ") == ("b", "uu")


def test_qalqala_and_sakt_are_dropped() -> None:
    assert to_maroof("بڇ") == ("b",)  # «بُ», waqf
    assert to_maroof("بَۜ") == ("b", "a")


def test_emphatic_letter_keeps_plain_vowel() -> None:
    assert to_maroof("صَ") == ("S", "a")


def test_hamza_has_its_own_symbol() -> None:
    assert to_maroof("ءَنتَ") == ("<", "a", "n", "t", "a")


@pytest.mark.parametrize("phonetic", NOT_PHONETIC)
def test_unknown_symbol_is_rejected(phonetic: str) -> None:
    with pytest.raises(ValueError):
        to_maroof(phonetic)
