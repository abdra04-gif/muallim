"""Транскрипция фонем алфавитом языка ученика (FR-21, FR-43, M-10).

Таблица — по научной русской транскрипции Крачковского (SRC-051), упрощённой для новичка:
долгий гласный — двумя буквами, без надстрочной черты.
"""

import pytest

from muallim.application.transcription import as_text, legend, reading, transcribe
from muallim.domain.curriculum import Curriculum, Lexicon
from muallim.domain.phonetics import CONSONANTS, SPECIAL, VOWELS


def test_letter_with_fatha(curriculum: Curriculum) -> None:
    assert transcribe("بَ", curriculum.lexicon) == "ба"


def test_word_reads_as_syllables(curriculum: Curriculum) -> None:
    assert transcribe("كَتَبَ", curriculum.lexicon) == "катаба"


def test_long_vowel_doubles(curriculum: Curriculum) -> None:
    assert transcribe("بَا", curriculum.lexicon) == "баа"


def test_madd_of_any_length_is_two_letters(curriculum: Curriculum) -> None:
    """Мадд на 4–6 счётов не превращается в «ииииии»: длину объясняет подсказка."""
    assert transcribe("بَاا", curriculum.lexicon) == "баа"
    assert transcribe("رِۦۦۦۦم", curriculum.lexicon) == "риим"


def test_qalqala_is_silent_in_transcription(curriculum: Curriculum) -> None:
    assert transcribe("بَڇ", curriculum.lexicon) == "ба"


@pytest.mark.parametrize(
    ("phoneme", "expected"),
    [
        ("ص", "с̣а"), ("ض", "д̣а"), ("ط", "т̣а"), ("ظ", "з̣а"),  # твёрдые — точка снизу
        ("ث", "с̱а"), ("ذ", "з̱а"),  # межзубные — черта снизу
        ("ح", "х̣а"), ("ع", "‘а"), ("ق", "к̣а"), ("غ", "г̣а"),  # горловые и глубокие
        ("ه", "һа"), ("ء", "’а"), ("و", "ўа"), ("خ", "ха"), ("س", "са"),
    ],
)  # fmt: skip
def test_krachkovsky_style_letters(curriculum: Curriculum, phoneme: str, expected: str) -> None:
    assert transcribe(phoneme + "َ", curriculum.lexicon) == expected


def test_every_phoneme_of_the_model_has_transcription(curriculum: Curriculum) -> None:
    """Иначе в транскрипцию попадают арабские символы (было: ں ۾ ۪ ـ ٲ ۜ)."""
    missing = (CONSONANTS | VOWELS | SPECIAL) - set(curriculum.lexicon.transcription)
    assert not missing, sorted(missing)


def test_hidden_noon_is_nasal(curriculum: Curriculum) -> None:
    assert transcribe("ں", curriculum.lexicon) == "н̃"


def test_unknown_symbol_is_kept(curriculum: Curriculum) -> None:
    assert transcribe("x", curriculum.lexicon) == "x"


def test_empty_heard_is_marked() -> None:
    assert transcribe("", Lexicon({}, {}, {}, {})) == "—"


# ---------- слоги и отметка ошибок ----------
def test_reading_splits_syllables_and_marks_wrong_one(curriculum: Curriculum) -> None:
    r = reading("كَتَبَ", curriculum.lexicon, wrong=[2])
    assert r == (("ка", False), ("та", True), ("ба", False))
    assert as_text(r) == "ка-та-ба"


def test_reading_of_single_syllable_marks_it_for_none(curriculum: Curriculum) -> None:
    assert reading("صَ", curriculum.lexicon, wrong=[None]) == (("с̣а", True),)


def test_reading_of_empty_is_empty(curriculum: Curriculum) -> None:
    assert reading("", curriculum.lexicon) == ()
    assert as_text(()) == "—"


# ---------- подсказка к значкам ----------
def test_legend_explains_only_marks_present(curriculum: Curriculum) -> None:
    assert legend("ка-та-ба", curriculum.lexicon) == ()
    lines = legend("с̣а-‘а", curriculum.lexicon)
    assert len(lines) == 2
    assert any("твёрд" in line for line in lines) and any("горл" in line for line in lines)


def test_legend_names_only_letters_present(curriculum: Curriculum) -> None:
    lines = legend("’ал-х̣ам-ду-лил-лаа-һи-раб-бил-‘аа-ла-мии-на", curriculum.lexicon)
    dotted = [line for line in lines if "точка снизу" in line]
    assert dotted == ["х̣ — из горла, глубоко (точка снизу)"]
    assert not any("твёрд" in line for line in lines)
