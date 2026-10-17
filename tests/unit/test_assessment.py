"""Классификация ошибок произношения (FR-04). Перенесено из прототипа и расширено."""

import pytest

from muallim.domain.assessment import ErrorKind, assess, assess_best, unread_from
from muallim.domain.phonetics import syllables

FATHA, KASRA = "َ", "ِ"


@pytest.mark.parametrize("item", ["بَ", "كَتَبَ", "خَلَقَ"])
def test_exact_match_scores_100_without_errors(item: str) -> None:
    result = assess(item, item)
    assert (result.score, result.errors) == (100, ())


def test_qalqala_at_stop_is_not_an_error() -> None:
    result = assess("بَ", "بَڇ")
    assert result.errors == ()
    assert result.score < 100  # точность честно ниже, но ошибкой новичку не считается


def test_deleted_qalqala_is_not_an_error() -> None:
    assert assess("بَڇ", "بَ").errors == ()


@pytest.mark.parametrize(
    ("reference", "heard", "kind"),
    [
        ("صَ", "سَ", ErrorKind.LETTER_SUBSTITUTION),
        ("بَ", "بِ", ErrorKind.VOWEL_SUBSTITUTION),
        ("بَ", "بx", ErrorKind.SOUND_SUBSTITUTION),
        ("بَتَ", "سِ", ErrorKind.FRAGMENT_SUBSTITUTION),
        ("بَا", "بَ", ErrorKind.MADD_TOO_SHORT),
        ("بَ", "ب", ErrorKind.VOWEL_MISSING),
        ("بَ", "بَا", ErrorKind.MADD_TOO_LONG),
        ("بَ", "بَس", ErrorKind.EXTRA_SOUND),
    ],
)
def test_error_kind(reference: str, heard: str, kind: ErrorKind) -> None:
    assert [e.kind for e in assess(reference, heard).errors][:1] == [kind]


def test_missing_doubled_consonant_is_shadda_error() -> None:
    # В фонетическом письме Muaalem ташдид — это удвоенная согласная подряд.
    errors = assess("رَببَ", "رَبَ").errors
    assert any(e.kind is ErrorKind.SHADDA_MISSING and e.expected == "ب" for e in errors)


def test_missing_single_consonant_is_sound_missing() -> None:
    assert assess("كَتَبَ", "كَتَ").errors[0].kind is ErrorKind.SOUND_MISSING


def test_syllable_position_reported_in_multi_syllable_word() -> None:
    (error,) = assess("كَتَبَ", "كَطَبَ").errors
    assert error.syllable == 2


def test_single_letter_has_no_syllable_position() -> None:
    (error,) = assess("صَ", "سَ").errors
    assert error.syllable is None


def test_empty_recognition_gives_zero_and_errors() -> None:
    result = assess("بَ", "")
    assert result.score == 0 and result.errors


def test_assess_best_picks_closest_reference() -> None:
    result = assess_best(["بَ", "بَڇ"], "بَڇ")
    assert result.reference == "بَڇ" and result.score == 100


def test_assess_best_requires_reference() -> None:
    with pytest.raises(ValueError, match="эталон"):
        assess_best([], "بَ")


def test_skipped_syllable_is_blamed_on_itself_not_on_its_neighbour() -> None:
    """Пропущено «تَ» в «كَتَبَ»: «ка» прочитано верно — ошибка только в слоге «та»."""
    errors = assess("كَتَبَ", "كَبَ").errors
    assert {e.syllable for e in errors} == {2}
    assert ErrorKind.SOUND_MISSING in {e.kind for e in errors}


# ---------- строка не дочитана ----------
FATIHA = "ءَلحَمدُلِلََهِرَبِِلعَاالَمِۦۦنَ"  # ٱلْحَمْدُ لِلَّهِ رَبِّ ٱلْعَـٰلَمِينَ


def test_unread_tail_starts_at_first_unread_syllable() -> None:
    # прочитано «’ал-х̣ам-ду-лил-лаа-һи-ра», дальше тишина: с «раб» и до конца не прочитано
    k = unread_from(FATIHA, FATIHA[:15])
    assert k is not None
    assert FATIHA[syllables(FATIHA)[k][0] :].startswith("رَب")


def test_whole_line_read_with_mistakes_is_not_unread() -> None:
    assert unread_from(FATIHA, FATIHA) is None
    assert unread_from(FATIHA, FATIHA.replace("ح", "ه")) is None
    assert unread_from(FATIHA, FATIHA[:-2]) is None  # проглочен последний слог — обычная ошибка


def test_nothing_read_is_not_a_tail() -> None:
    assert unread_from(FATIHA, "") is None


def test_noise_after_stop_still_counts_as_unread() -> None:
    assert unread_from(FATIHA, FATIHA[:15] + "م") is not None
