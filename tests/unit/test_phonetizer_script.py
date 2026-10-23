"""Текст карточки → запись, которую понимает фонетизатор quran-transcript (аудит 2026-10-23).

Программа собрана с нормализацией Unicode NFC: она ставит огласовку перед шаддой, огласовку перед
хамзой над татвилем и склеивает «ا + ٓ» в «آ». Шрифт рисует оба порядка одинаково, а фонетизатор
ждёт порядок мусхафа: иначе шадда теряется («рабара» вместо «рабба») или он падает.
"""

from muallim.infrastructure.asr.script import for_phonetizer

FATHA, KASRA, DAMMA, SUKUN = "َ", "ِ", "ُ", "ْ"
FATHATAN, SHADDA, HAMZA_ABOVE, MADDA = "ً", "ّ", "ٔ", "ٓ"
TATWEEL = "ـ"


def test_shadda_goes_before_its_vowel() -> None:
    nfc = "ر" + FATHA + "ب" + FATHA + SHADDA  # رَبَّ после NFC
    assert for_phonetizer(nfc) == "ر" + FATHA + "ب" + SHADDA + FATHA


def test_shadda_goes_before_tanween() -> None:
    nfc = "ر" + FATHA + "ب" + FATHATAN + SHADDA + "ا"  # رَبًّا после NFC
    assert for_phonetizer(nfc) == "ر" + FATHA + "ب" + SHADDA + FATHATAN + "ا"


def test_hamza_above_goes_before_its_vowel() -> None:
    nfc = "م" + FATHA + TATWEEL + FATHA + HAMZA_ABOVE + "اب"  # مَـَٔاب после NFC
    assert for_phonetizer(nfc) == "م" + FATHA + TATWEEL + HAMZA_ABOVE + FATHA + "اب"


def test_alif_madda_is_split_into_alif_and_madd_sign() -> None:
    assert for_phonetizer("ج" + FATHA + "آ" + "ء" + FATHA) == (
        "ج" + FATHA + "ا" + MADDA + "ء" + FATHA
    )


def test_bare_alif_with_vowel_at_word_start_is_read_with_hamza() -> None:
    """Книга пишет «اِسْتَغْفَرَ», «اَلْ»: начиная слово, такой алиф читают хамзой."""
    text = "ا" + KASRA + "ر" + SUKUN + "م" + KASRA + " " + "ا" + FATHA + "ل" + SUKUN
    assert for_phonetizer(text) == (
        "إ" + KASRA + "ر" + SUKUN + "م" + KASRA + " " + "أ" + FATHA + "ل" + SUKUN
    )
    assert for_phonetizer("ا" + DAMMA + "ك") == "أ" + DAMMA + "ك"


def test_alif_inside_a_word_and_wasla_are_not_touched() -> None:
    for text in ("ق" + FATHA + "ال" + FATHA, "ٱ" + "ل" + SUKUN + "ح" + FATHA, "ب" + FATHA + "ا"):
        assert for_phonetizer(text) == text


def test_text_already_in_mushaf_order_is_unchanged() -> None:
    mushaf = "إ" + KASRA + "ل" + SHADDA + FATHA + "ا"  # إِلَّا из мусхафа
    assert for_phonetizer(mushaf) == mushaf
    assert for_phonetizer(for_phonetizer(mushaf)) == mushaf
