"""Слоги эталона для показа ученику: «в слоге «та»» вместо «во 2-м слоге» (FR-43)."""

import pytest

from muallim.domain.phonetics import syllable_index, syllables


def _parts(phonemes: str) -> list[str]:
    return [phonemes[a:b] for a, b in syllables(phonemes)]


def test_open_syllables_split_by_consonant() -> None:
    assert _parts("كَتَبَ") == ["كَ", "تَ", "بَ"]


def test_consonant_without_vowel_closes_previous_syllable() -> None:
    assert _parts("بَب") == ["بَب"]  # «баб», а не «ба» + «б»


def test_shadda_is_split_between_syllables() -> None:
    assert _parts("رَببَ") == ["رَب", "بَ"]  # «раб-ба»


def test_long_vowel_and_qalqala_stay_in_syllable() -> None:
    assert _parts("بَاڇ") == ["بَاڇ"]


def test_lonely_consonant_is_its_own_syllable() -> None:
    assert _parts("ب") == ["ب"]
    assert syllables("") == ()


@pytest.mark.parametrize(
    ("phonemes", "consonant", "index"),
    [("كَتَبَ", 2, 1), ("رَببَ", 2, 0), ("رَببَ", 3, 1), ("كَتَبَ", None, 0), ("كَتَبَ", 9, 2)],
)
def test_error_syllable_maps_to_shown_syllable(
    phonemes: str, consonant: int | None, index: int
) -> None:
    """``PronunciationError.syllable`` считает согласные; показываем слог, где эта согласная."""
    assert syllable_index(phonemes, consonant) == index
