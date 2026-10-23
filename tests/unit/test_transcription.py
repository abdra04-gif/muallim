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


# ---------- FR-54: слоги без арабских букв и пробелов ----------
def _arabic(text: str) -> list[str]:
    return [ch for ch in text if "\u0600" <= ch <= "\u06ff"]


@pytest.mark.parametrize(
    ("text", "count"),
    [("أَحْسَنَ", 3), ("أَمْ إِمْ أُمْ", 3), ("مُؤْمِنُ", 3), ("بِئْرُ", 2)],
    ids=["ahsana", "am_im_um", "mumin", "bir"],
)  # L024-07, L006-06, строки урока хамзы
def test_hamza_seats_do_not_leak_into_syllables(
    curriculum: Curriculum, text: str, count: int
) -> None:
    """FR-54: опоры хамзы أ إ ؤ ئ читаются как ء — в слоге нет арабской буквы, слоги делятся
    как у хамзы (транскрипция хамзы та же, что сейчас у ء)."""
    shown = reading(text, curriculum.lexicon)
    assert len(shown) == count, shown
    assert not [s for s, _ in shown if _arabic(s)], shown


def test_hamza_seat_reads_like_hamza(curriculum: Curriculum) -> None:
    lex = curriculum.lexicon
    assert reading("أَحْسَنَ", lex)[0][0] == reading("ءَحسَنَ", lex)[0][0]


def test_syllables_have_no_spaces_inside(curriculum: Curriculum) -> None:
    """FR-54: эталон-текст с пробелами (L020-06) — слоги «с̣ум», «с̣иф», без «с̣ум »."""
    assert [t for t, _ in reading("صُمْ صِفْ", curriculum.lexicon)] == ["с̣ум", "с̣иф"]


# ---------- FR-54, Р1: простая запись для экрана результата ----------
def plain(text: str, lexicon: Lexicon) -> str:
    from muallim.application.transcription import plain as plain_reading  # noqa: PLC0415

    return plain_reading(text, lexicon)


PLAIN_MARKS = ("х̣", "с̣", "һ", "ħ", "θ", "ʿ", "ð", "’", "‘", "\u0323", "\u0331")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("مُحْسِنُ", "мух-си-ну"),  # L024-07, текст карточки
        ("مُحسِنُ", "мух-си-ну"),  # то же в фонемах
        ("أَحْسَنَ", "ах-са-на"),  # хамза без знака
        ("صُمْ", "сум"),  # L020-06: твёрдое без точки
    ],
    ids=["muhsinu_text", "muhsinu_phonemes", "ahsana", "sum"],
)
def test_plain_reading_is_simple_cyrillic(curriculum: Curriculum, text: str, expected: str) -> None:
    """Р1 (автор 2026-10-23): на экране результата — простая кириллица без значков и апострофа:
    ح→х, ص→с, ع/ء без знака; разницу звуков несёт подпись группы («ха» горлом)."""
    assert plain(text, curriculum.lexicon) == expected


def test_plain_reading_of_any_letter_has_no_marks(curriculum: Curriculum) -> None:
    for ch in sorted(CONSONANTS):
        out = plain(ch + "َ", curriculum.lexicon)
        assert out and not [m for m in PLAIN_MARKS if m in out], (ch, out)
        assert not _arabic(out), (ch, out)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("صَ", "со"), ("صِ", "сы"), ("خَ", "хо"), ("قَ", "ко"), ("طَ", "то"),  # как в карточках
        ("ٱلرَّحِيمِ", "ар-ра-хии-ми"), ("ٱلشَّيْطَانِ", "аш-шай-таа-ни"),  # солнечная ل
        ("ٱلْحَمْدُ", "ал-хам-ду"),  # лунная ل
        ("ثَوْبًا", "сау-бан"), ("هُدًى", "ху-дан"), ("رَحْمَةً", "рах-ма-тан"),  # танвин, ة
        ("يَنْـَٔوْنَ", "йан-ау-на"),  # хамза на татвиле — без «э»
        ("قَالُوا", "каа-луу"),  # алиф после و мн. ч. не читается
    ],
    ids=[
        "sad_fatha", "sad_kasra", "kha", "qaf", "ta", "sun_lam_ra", "sun_lam_shin", "moon_lam",
        "tanwin_alif", "tanwin_maqsura", "ta_marbuta", "hamza_on_tatweel", "alif_after_waw",
    ],
)  # fmt: skip
def test_plain_reading_follows_the_cards_and_tajwid(
    curriculum: Curriculum, text: str, expected: str
) -> None:
    """I5 (ревью 2026-10-24): простое чтение экрана результата — твёрдые буквы как в карточках
    (со · сы, хо, ко, то), солнечная ل уподобляется, танвин — «н» в конце, ة — «т».

    Ожидаемые чтения — ПРЕДЛОЖЕНИЕ агента (близко к таджвиду), проверит автор (TD-FN-30).
    """
    assert plain(text, curriculum.lexicon) == expected


def test_alif_maqsura_with_dagger_alif_is_a_long_a(curriculum: Curriculum) -> None:
    """«عَلَىٰ» (L06x/Коран): «ىٰ» — долгое «аа», не «йа»: два слога, без «й».

    Ожидаемое «а-лаа» — ПРЕДЛОЖЕНИЕ агента, сверить с преподавателем (TD-FN-30); тест держит
    правило (долгий гласный, не согласная), а не мягкость «л»."""
    out = plain("عَلَىٰ", curriculum.lexicon)
    assert "й" not in out and out.count("-") == 1, out
    assert out.startswith("а-") and out.endswith(("аа", "яа", "яя")), out


@pytest.mark.parametrize(
    ("doubled", "spelled"),
    [("رَبِّ", "رَبْبِ"), ("صُوِّرَ", "صُوْوِرَ"), ("ذُكِّرَ", "ذُكْكِرَ")],
    ids=["rabbi", "suwwira", "dhukkira"],
)
def test_shadda_reads_as_the_letter_twice(
    curriculum: Curriculum, doubled: str, spelled: str
) -> None:
    """Шадда — та же буква дважды: с сукуном (закрывает слог) и с огласовкой (раб-би). Для «صُوِّرَ»
    (L040-01) правило даёт то же, что «صُوْوِرَ»; что именно писать для و — ПРЕДЛОЖЕНИЕ агента,
    сверить с преподавателем (TD-FN-30)."""
    assert plain(doubled, curriculum.lexicon) == plain(spelled, curriculum.lexicon)
