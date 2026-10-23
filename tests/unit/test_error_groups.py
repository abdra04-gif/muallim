"""FR-54 (этап 1): разбор попытки группами — ``muallim.application.breakdown.build_breakdown``.

Решения автора 2026-10-23/24: одинаковые ошибки — одна группа «N раз» со словами, где они
случились. Ключ согласной — нужная → прозвучавшая буква; ключ огласовки — нужный → прозвучавший
знак (Р7: «дамма → фатха» на разных буквах — одна группа; «фа→фи» и «фа→фу» — разные). Число раз —
число разных мест (две одинаковые ошибки в одном слове — 2 раза, слово одно). Буква урока —
первой (каждая её путаница — своя группа, все впереди), затем явные ошибки, затем мадд, внутри —
по строке. Ошибки после «не дочитал» в группы не входят; до этого места ни одна ошибка не
теряется (кроме огласовки и мадда пропущенной буквы — они уходят вместе с ней). Подписи — простой
кириллицей из ``Lexicon.sounds`` («ха» горлом / «ха» легко — Р8), без значков х̣ с̣ һ ħ θ ʿ ð ’ ‘;
без подписи — буква и название.

Строки — из curriculum/course.ru.yaml; «услышано» — та же строка с заменой букв. Эталон — текст
строки или фонемы, как у Muaalem (без сукуна и пробелов). Распознавание не нужно: ``assess``.
"""

from dataclasses import replace
from typing import Any

import pytest

from muallim.application.breakdown import Breakdown, ErrorGroup, build_breakdown
from muallim.domain.assessment import Assessment, ErrorKind, assess, unread_from
from muallim.domain.curriculum import Curriculum, Lexicon
from muallim.domain.phonetics import syllables

L020_06 = "صُمْ صِفْ فَصْ صَرَفَ صَبَرَ بَصَرَ"  # урок ص, с. 18
L020_06_PHONEMES = "صُمصِففَصصَرَفَصَبَرَبَصَرَ"
L024_07 = "مُحْسِنُ مَحْشَرُ مِنْحَرُ مَحْفَلُ أَحْسَنَ"  # урок ح, с. 21
L024_07_PHONEMES = "مُحسِنُمَحشَرُمِنحَرُمَحفَلُءَحسَنَ"
L006_06 = "أَمْ إِمْ أُمْ مُرْ مُزْ رُمْ أَمَرَ أُمِرَ أَمْرُ"  # урок م, с. 12
L006_07 = "إِمْرُ رَمْزُ اِرْمِ مَرْمَرُ رَمْرَمُ زَمْزَمُ"  # урок م
L031_LINE = "بَا بِي بُو"  # «Долгие гласные (мадд)»
L031_PHONEMES = "بَاابِۦۦبُۥۥ"  # мадд на два счёта — две фонемы
RABBA = "رَبَّ"  # урок ташдида
RABBA_PHONEMES = "رَببَ"

# Подписи звуков — решение автора 2026-10-23 (раздел ``sounds:`` lexicon.ru.yaml)
SOUNDS = {"ح": ("ха", "горлом"), "ه": ("ха", "легко"), "ص": ("со", "")}  # Р8: ه — «легко»
MARKS = ("х̣", "с̣", "һ", "ħ", "θ", "ʿ", "ð", "’", "‘", "̣", "̱")  # и точка/черта снизу
FOLLOW_MISSING = (ErrorKind.VOWEL_MISSING, ErrorKind.MADD_TOO_SHORT)


@pytest.fixture(scope="module")
def lexicon(curriculum: Curriculum) -> Lexicon:
    return replace(curriculum.lexicon, sounds=SOUNDS)


def _assess(text: str, heard: str, reference: str = "") -> tuple[Assessment, int | None]:
    a = assess(reference or text, heard)
    return a, unread_from(a.reference, heard)


def _review(
    lexicon: Lexicon, text: str, heard: str, letter: str | None = None, reference: str = ""
) -> Breakdown:
    a, unread = _assess(text, heard, reference)
    return build_breakdown(a, text, lexicon, unread=unread, lesson_letter=letter)


def _words(g: ErrorGroup) -> list[int]:
    return [p.word_index for p in g.places]


def _no_marks(label: str) -> None:
    assert label, "пустая подпись"
    assert not [m for m in MARKS if m in label], label


# ---------- одинаковые ошибки — одна группа ----------
def test_same_swap_in_three_words_is_one_group_three_times(lexicon: Lexicon) -> None:
    """Баг: «ص→س» в трёх словах — третья пропадала. Теперь одна группа, 3 места, слова названы."""
    review = _review(lexicon, L020_06, "سُمْ صِفْ فَصْ سَرَفَ صَبَرَ بَسَرَ")
    (g,) = review.groups
    assert (g.kind, g.expected, g.heard) == (ErrorKind.LETTER_SUBSTITUTION, "ص", "س")
    assert _words(g) == [0, 3, 5]
    assert [p.word_text for p in g.places] == ["صُمْ", "صَرَفَ", "بَصَرَ"]


def test_place_marks_only_the_wrong_letter_not_the_whole_word(lexicon: Lexicon) -> None:
    """На картинке красная сама буква: место хранит кластер буквы ص, а не всё слово."""
    review = _review(lexicon, L020_06, "سُمْ صِفْ فَصْ سَرَفَ صَبَرَ بَسَرَ")
    (g,) = review.groups
    # кластеры строки: صُ0 مْ1 | صِ2 فْ3 | فَ4 صْ5 | صَ6 رَ7 فَ8 | صَ9 بَ10 رَ11 | بَ12 صَ13 رَ14
    assert [set(p.clusters) for p in g.places] == [{0}, {6}, {13}]


def test_same_swap_twice_in_one_word_is_two_places_of_one_word(lexicon: Lexicon) -> None:
    """Р4: «مَرْمَرُ» → «نَرْنَرُ» — 2 раза (два места), но слово одно."""
    review = _review(lexicon, L006_07, "إِمْرُ رَمْزُ اِرْمِ نَرْنَرُ رَمْرَمُ زَمْزَمُ")
    (g,) = review.groups
    assert (g.expected, g.heard) == ("م", "ن")
    assert len(g.places) == 2 and _words(g) == [3, 3]
    assert len({frozenset(p.clusters) for p in g.places}) == 2


def test_different_heard_letters_are_different_groups(lexicon: Lexicon) -> None:
    """ص→س и ص→ز — разные путаницы, разные пункты."""
    review = _review(lexicon, L020_06, "سُمْ صِفْ فَصْ زَرَفَ صَبَرَ بَصَرَ")
    assert [(g.expected, g.heard) for g in review.groups] == [("ص", "س"), ("ص", "ز")]


def test_lesson_letter_group_comes_first_then_vowel_group(lexicon: Lexicon) -> None:
    """Баг 2 (L024-07): ح→ه дважды (буква урока, первая) и огласовка над ف один раз."""
    review = _review(lexicon, L024_07, "مُهْسِنُ مَحْشَرُ مِنْهَرُ مَحْفِلُ أَحْسَنَ", letter="ح")
    first, second = review.groups
    assert (first.expected, first.heard, first.lesson_letter) == ("ح", "ه", True)
    assert _words(first) == [0, 2]
    assert second.kind is ErrorKind.VOWEL_SUBSTITUTION and not second.lesson_letter
    assert _words(second) == [3]
    assert "фа" in second.need_label and "фи" in second.heard_label  # «над ف: фа, у тебя фи»


def test_same_vowel_swap_on_same_letter_in_two_words_is_one_group(lexicon: Lexicon) -> None:
    """Р2: «صَ→صِ» в «صَرَفَ» и «صَبَرَ» — одна группа ×2."""
    review = _review(lexicon, L020_06, "صُمْ صِفْ فَصْ صِرَفَ صِبَرَ بَصَرَ")
    (g,) = review.groups
    assert g.kind is ErrorKind.VOWEL_SUBSTITUTION and _words(g) == [3, 4]


def test_different_heard_vowels_on_same_letter_are_different_groups(lexicon: Lexicon) -> None:
    """Р2 (вариант А): «со→сы» и «со→су» — две группы, подписи «у тебя» разные."""
    review = _review(lexicon, L020_06, "صُمْ صِفْ فَصْ صِرَفَ صُبَرَ بَصَرَ")
    first, second = review.groups
    assert first.kind is second.kind is ErrorKind.VOWEL_SUBSTITUTION
    assert first.need_label == second.need_label and first.heard_label != second.heard_label


def test_same_vowel_swap_on_different_letters_is_one_group(lexicon: Lexicon) -> None:
    """Р7: «фатха → кясра» над م и над ف — одна путаница знака, одна группа ×2."""
    review = _review(lexicon, L024_07, "مُحْسِنُ مَحْشَرُ مِنْحَرُ مِحْفِلُ أَحْسَنَ")
    (g,) = review.groups
    assert g.kind is ErrorKind.VOWEL_SUBSTITUTION and g.times == 2 and _words(g) == [3, 3]


def test_different_swaps_are_different_groups_in_line_order(lexicon: Lexicon) -> None:
    """Баг 3: три разные замены согласных — три группы (раньше на картинке была одна)."""
    review = _review(lexicon, L020_06, "سُمْ صِفْ فَصْ صَلَفَ صَبَرَ مَصَرَ")
    pairs = [(g.expected, g.heard) for g in review.groups]
    assert pairs == [("ص", "س"), ("ر", "ل"), ("ب", "م")]
    assert not any(g.lesson_letter for g in review.groups)


# ---------- буква урока ----------
def test_lesson_letter_moves_its_group_first(lexicon: Lexicon) -> None:
    heard = "أَمْ إِمْ أُمْ مُرْ مُزْ لُمْ أَنَرَ أُمِرَ أَمْرُ"  # ر→ل, затем م→ن
    plain = _review(lexicon, L006_06, heard)
    assert [g.expected for g in plain.groups] == ["ر", "م"]
    starred = _review(lexicon, L006_06, heard, letter="م")
    assert [(g.expected, g.lesson_letter) for g in starred.groups] == [("م", True), ("ر", False)]


def test_two_confusions_of_lesson_letter_are_two_starred_groups_first(lexicon: Lexicon) -> None:
    """Р4: م→ن и م→ب — две группы буквы урока, обе впереди ر→ل (хотя ر→ل раньше в строке)."""
    review = _review(lexicon, L006_07, "إِمْرُ لَمْزُ اِرْمِ نَرْمَرُ رَبْرَمُ زَمْزَمُ", "م")
    got = [(g.expected, g.heard, g.lesson_letter) for g in review.groups]
    assert got == [("م", "ن", True), ("م", "ب", True), ("ر", "ل", False)]


def test_missing_lesson_letter_is_its_group(lexicon: Lexicon) -> None:
    """«мур» → «р»: буква урока пропущена — группа буквы урока, её огласовка отдельно не пункт."""
    review = _review(lexicon, L006_06, "أَمْ إِمْ أُمْ رْ مُزْ رُمْ أَمَرَ أُمِرَ أَمْرُ", "م")
    first = review.groups[0]
    assert (first.kind, first.expected, first.lesson_letter) == (ErrorKind.SOUND_MISSING, "م", True)
    assert not any(g.kind is ErrorKind.VOWEL_MISSING for g in review.groups)


def test_vowel_error_on_lesson_letter_is_not_the_lesson_letter(lexicon: Lexicon) -> None:
    """Огласовка над буквой урока — не «буква прозвучала иначе» (ADR-0062, В3 (а))."""
    review = _review(lexicon, L024_07, "مُحْسِنُ مَحْشَرُ مِنْحِرُ مَحْفَلُ أَحْسَنَ", letter="ح")
    (g,) = review.groups
    assert g.kind is ErrorKind.VOWEL_SUBSTITUTION and not g.lesson_letter


def test_fragment_is_grouped_by_its_first_wrong_letter(lexicon: Lexicon) -> None:
    """«صُ» → «سِ» (замена куска) — та же группа ص→س, что и простая замена."""
    review = _review(lexicon, L020_06, "سِمْ صِفْ فَصْ صَرَفَ صَبَرَ بَسَرَ")
    (g,) = review.groups
    assert (g.kind, g.expected, g.heard) == (ErrorKind.LETTER_SUBSTITUTION, "ص", "س")
    assert _words(g) == [0, 5]


# ---------- другие виды ошибок не теряются ----------
@pytest.mark.parametrize(
    ("text", "reference", "heard", "kind", "word"),
    [
        (RABBA, RABBA_PHONEMES, "رَبَ", ErrorKind.SHADDA_MISSING, 0),
        (L024_07, L024_07_PHONEMES, "مُحسِنُمَاحشَرُمِنحَرُمَحفَلُءَحسَنَ", ErrorKind.MADD_TOO_LONG, 1),
        (L024_07, L024_07_PHONEMES, "مُحسِنُمَحشَرُمِنحَرُمَحفَلُءَحسَنَن", ErrorKind.EXTRA_SOUND, 4),
        (L024_07, L024_07_PHONEMES, "مُحسِنُمَاشَرُمِنحَرُمَحفَلُءَحسَنَ", ErrorKind.SOUND_SUBSTITUTION, 1),
    ],
    ids=["shadda_missing", "madd_too_long", "extra_sound", "sound_substitution"],
)  # fmt: skip
def test_every_error_kind_becomes_a_group(  # noqa: PLR0917
    lexicon: Lexicon, text: str, reference: str, heard: str, kind: ErrorKind, word: int
) -> None:
    (g,) = _review(lexicon, text, heard, reference=reference).groups
    assert g.kind is kind and _words(g) == [word]


@pytest.mark.parametrize(
    ("text", "reference", "heard"),
    [
        (L020_06, L020_06_PHONEMES, "سِمصِففَصسَرَفَصَبَرَبَسَرَ"),  # фрагмент + замены
        (L020_06, L020_06_PHONEMES, "سُمصِفَصسَرَفَ"),  # шадда + остановка
        (L031_LINE, L031_PHONEMES, "بَبِۦۦتُۥۥ"),  # мадд из двух фонем + замена
        (L024_07, L024_07_PHONEMES, "مُحسِنُمَرُمِنحَرُمَحفِلُءَحسَنَ"),  # пропуск + огласовка
        (RABBA, RABBA_PHONEMES, "رَبَ"),
    ],
    ids=["fragment", "stopped", "madd", "missing", "shadda"],
)
def test_no_error_before_the_stop_is_lost(
    lexicon: Lexicon, text: str, reference: str, heard: str
) -> None:
    """Каждая ошибка ``assess`` до «не дочитал» — ровно в одном месте одной группы. Исключение:
    огласовка и мадд пропущенной буквы (уходят вместе с ней, ADR-0031)."""
    a, unread = _assess(text, heard, reference)
    review = build_breakdown(a, text, lexicon, unread=unread)
    assert review.groups
    cut = syllables(a.reference)[unread][0] if unread is not None else len(a.reference) + 1
    placed = [e for g in review.groups for p in g.places for e in p.errors]
    for e in a.errors:
        if e.position >= cut:
            assert e not in placed, e
            continue
        n = placed.count(e)
        missing_letter = any(
            m.kind is ErrorKind.SOUND_MISSING and m.position < e.position <= m.position + 2
            for m in a.errors
        )
        if n == 0 and e.kind in FOLLOW_MISSING and missing_letter:
            continue
        assert n == 1, (e, n)


# ---------- мадд, порядок, «не дочитано» ----------
def test_two_madd_phonemes_in_one_place_count_once(lexicon: Lexicon) -> None:
    """Мадд на два счёта — две фонемы; не дотянул в одном месте — «1 раз», а не 2."""
    review = _review(lexicon, L031_LINE, "بَبِۦۦبُۥۥ", reference=L031_PHONEMES)
    (g,) = review.groups
    assert g.kind is ErrorKind.MADD_TOO_SHORT and _words(g) == [0]


def test_madd_goes_after_explicit_errors(lexicon: Lexicon) -> None:
    """Порядок как в разборе (ADR-0031): явная ошибка (буква) раньше мадда, хотя мадд левее."""
    review = _review(lexicon, L031_LINE, "بَبِۦۦتُۥۥ", reference=L031_PHONEMES)
    kinds = [g.kind for g in review.groups]
    assert kinds == [ErrorKind.LETTER_SUBSTITUTION, ErrorKind.MADD_TOO_SHORT]


def test_errors_after_unread_point_are_not_grouped(lexicon: Lexicon) -> None:
    """Остановился на 4-м слове: ص→س — 2 раза (а не 3), конец строки — «не дочитано»."""
    review = _review(lexicon, L020_06, "سُمْ صِفْ فَصْ سَرَفَ")
    (g,) = review.groups
    assert (g.expected, g.heard) == ("ص", "س") and _words(g) == [0, 3]
    assert review.unread == (4, 5)


def test_only_errors_after_the_stop_give_no_groups(lexicon: Lexicon) -> None:
    """Верно прочитал три слова и остановился: групп нет, есть только «не дочитано»."""
    review = _review(lexicon, L020_06, "صُمصِففَص", reference=L020_06_PHONEMES)
    assert review.groups == ()
    assert review.unread == (3, 4, 5)
    assert (review.words_ok, review.words_total) == (3, 6)


def test_empty_heard_still_gives_a_review(lexicon: Lexicon) -> None:
    """Ничего не услышано — разбор строится и не падает; верных слов нет."""
    review = _review(lexicon, L020_06, "", reference=L020_06_PHONEMES)
    assert review.groups and review.words_ok == 0 and review.words_total == 6


def test_finished_line_has_no_unread(lexicon: Lexicon) -> None:
    assert _review(lexicon, L020_06, "سُمْ صِفْ فَصْ صَرَفَ صَبَرَ بَصَرَ").unread == ()


# ---------- счётчик слов ----------
def test_words_counter_counts_whole_words(lexicon: Lexicon) -> None:
    """Один счётчик «верно N слов из M»: ошибка в слове — слово неверно."""
    review = _review(lexicon, L024_07, "مُهْسِنُ مَحْشَرُ مِنْهَرُ مَحْفِلُ أَحْسَنَ")
    assert (review.words_ok, review.words_total) == (2, 5)


def test_unread_words_are_not_counted_as_right(lexicon: Lexicon) -> None:
    review = _review(lexicon, L020_06, "سُمْ صِفْ فَصْ سَرَفَ")
    assert (review.words_ok, review.words_total) == (2, 6)


def test_correct_reading_has_no_groups(lexicon: Lexicon) -> None:
    review = _review(lexicon, L020_06, L020_06)
    assert review.groups == () and (review.words_ok, review.words_total) == (6, 6)


# ---------- подписи звуков и чтение слова — простой кириллицей ----------
def test_throat_sounds_are_told_apart_by_word_not_by_marks(lexicon: Lexicon) -> None:
    """«ха» горлом / «ха» легко — без значков х̣ һ ħ: новичок их не читает (audience.md)."""
    review = _review(lexicon, L024_07, "مُهْسِنُ مَحْشَرُ مِنْحَرُ مَحْفَلُ أَحْسَنَ", letter="ح")
    g = review.groups[0]
    assert "ха" in g.need_label and "горлом" in g.need_label
    assert "ха" in g.heard_label and "легко" in g.heard_label
    assert "ح" not in g.need_label  # буква — в начале пункта («Буква урока ح (Хэ): …»)
    _no_marks(g.need_label)
    _no_marks(g.heard_label)


def test_vowel_labels_are_syllables_as_on_course_cards(curriculum: Curriculum) -> None:
    """Слоги огласовки — как в карточках курса (ل: «ля · ли · лю»): над ل дамма → кясра —
    нужно «лю», у тебя «ли». Проверяет и черновик ``sounds`` автора в lexicon.ru.yaml."""
    review = _review(curriculum.lexicon, L024_07, "مُحْسِنُ مَحْشَرُ مِنْحَرُ مَحْفَلِ أَحْسَنَ")
    (g,) = review.groups
    assert g.kind is ErrorKind.VOWEL_SUBSTITUTION
    assert "лю" in g.need_label and "ли" in g.heard_label
    _no_marks(g.need_label)
    _no_marks(g.heard_label)


def test_vowel_label_over_marked_letter_keeps_its_note(lexicon: Lexicon) -> None:
    """Р2: огласовка над ح — «ха» → «хи», обе с пометкой «горлом», без значков."""
    review = _review(lexicon, L024_07, "مُحْسِنُ مَحْشَرُ مِنْحِرُ مَحْفَلُ أَحْسَنَ")
    (g,) = review.groups
    assert "ха" in g.need_label and "хи" in g.heard_label
    assert "горлом" in g.need_label and "горлом" in g.heard_label
    _no_marks(g.need_label)
    _no_marks(g.heard_label)


@pytest.mark.parametrize(
    ("text", "heard"),
    [
        (L024_07, "مُحْسِنُ مَحْشَرُ مِنْحِرُ مَحْفَلُ أَحْسَنَ"),  # над ح
        (L020_06, "صُمْ صِفْ فَصْ صِرَفَ صُبَرَ بَصَرَ"),  # над ص
    ],
    ids=["ha", "sad"],
)
def test_vowel_labels_have_no_marks(lexicon: Lexicon, text: str, heard: str) -> None:
    """Р2: подпись огласовки — слог как в карточке, простой кириллицей (со/сы/су, ха/хи/ху)."""
    review = _review(lexicon, text, heard)
    assert review.groups
    for g in review.groups:
        _no_marks(g.need_label)
        _no_marks(g.heard_label)


def test_letter_without_sound_falls_back_to_letter_and_name(curriculum: Curriculum) -> None:
    """Подписи нет в ``sounds`` — буква и название из словаря: «ح (Хэ)»."""
    bare = replace(curriculum.lexicon, sounds={})
    review = _review(bare, L024_07, "مُهْسِنُ مَحْشَرُ مِنْحَرُ مَحْفَلُ أَحْسَنَ")
    g = review.groups[0]
    assert "ح" in g.need_label and "Хэ" in g.need_label
    assert "ه" in g.heard_label and curriculum.lexicon.consonants["ه"][0] in g.heard_label


def test_lexicon_sounds_are_empty_by_default() -> None:
    """Раздел ``sounds:`` необязателен: словарь других языков работает без него."""
    assert Lexicon({}, {}, {}, {}).sounds == {}


def test_word_reading_is_plain_cyrillic(lexicon: Lexicon) -> None:
    """Р1: чтение слова — простая кириллица по слогам: «мух-си-ну», «ах-са-на» (без х̣ и ’)."""
    review = _review(lexicon, L024_07, "مُهْسِنُ مَحْشَرُ مِنْحَرُ مَحْفَلُ أَهْسَنَ")
    (g,) = review.groups
    assert [p.word_reading for p in g.places] == ["мух-си-ну", "ах-са-на"]


def test_word_reading_with_phoneme_reference_is_the_same(lexicon: Lexicon) -> None:
    """Эталон-фонемы (как в работе) дают те же слова и то же чтение, что эталон-текст."""
    heard = "مُهسِنُمَحشَرُمِنحَرُمَحفَلُءَهسَنَ"
    review = _review(lexicon, L024_07, heard, reference=L024_07_PHONEMES)
    (g,) = review.groups
    assert _words(g) == [0, 4]
    assert [p.word_text for p in g.places] == ["مُحْسِنُ", "أَحْسَنَ"]
    assert [p.word_reading for p in g.places] == ["мух-си-ну", "ах-са-на"]


# ---------- раунд 2 (ревью 2026-10-24) ----------
# Эталоны — выход quran-transcript с MOSHAF_PARAMS бота (``muaalem._references``), без модели
BASMALA = "بِسْمِ ٱللَّهِ ٱلرَّحْمَـٰنِ ٱلرَّحِيمِ"  # L001-03
BASMALA_PHONEMES = "بِسمِللَااهِررَحمَاانِررَحِۦۦۦۦم"  # waqf
L031_03 = "بَا بِي بُو تَا تِي تُو ثَا ثِي ثُو"
L031_03_PHONEMES = "بَاابِۦۦبُۥۥتَااتِۦۦتُۥۥثَااثِۦۦثُۥۥ"
L040_01 = "ذُكِّرَ عُلِّمَ كُمِّلَ شُمِّرَ صُنِّفَ صُوِّرَ غُيِّرَ"  # урок ташдида
L040_01_PHONEMES = "ذُككِرَعُللِمَكُممممِلَشُممممِرَصُننننِفَصُووِرَغُييِر"
L043_08 = "دَلْوٍ شَرْهٌ مَقْتًا نِعْمَةٍ شُكُورًا"  # танвин и ة
L043_08_PHONEMES = "دَلوِنشَرهُنمَقڇتَننِعمَتِنشُكُۥۥرَن"  # wasl
AHAD = "أَحَدٌ"  # L086-05, Коран 112:1
AHAD_PHONEMES = "ءَحَدُن"  # wasl


@pytest.mark.parametrize("stop", [24, 14], ids=["in_last_word", "in_third_word"])
def test_stopping_inside_a_word_leaves_it_unread(lexicon: Lexicon, stop: int) -> None:
    """B1: басмала оборвана посреди слова — это слово не «верно»: верных слов меньше, чем слов,
    и конец строки — «не дочитано» (или ошибки)."""
    b = _review(lexicon, BASMALA, BASMALA_PHONEMES[:stop], reference=BASMALA_PHONEMES)
    assert b.unread or b.groups
    assert b.words_ok < b.words_total


def test_word_cut_in_the_middle_is_not_counted_as_right(lexicon: Lexicon) -> None:
    """B1: остановка в «ٱلرَّحْمَـٰنِ» (3-е слово) — верны только первые два слова."""
    b = _review(lexicon, BASMALA, BASMALA_PHONEMES[:14], reference=BASMALA_PHONEMES)
    assert b.words_ok <= 2
    assert 2 in b.unread or any(2 in [p.word_index for p in g.places] for g in b.groups)


def test_missing_syllable_with_madd_has_no_separate_madd_group(lexicon: Lexicon) -> None:
    """I1: пропущен слог «بِي» целиком — одна группа пропуска, без отдельного «мадд не дотянут»."""
    heard = L031_03_PHONEMES.replace("بِۦۦ", "", 1)
    b = _review(lexicon, L031_03, heard, reference=L031_03_PHONEMES)
    assert b.groups
    assert not [g for g in b.groups if g.kind is ErrorKind.MADD_TOO_SHORT]


@pytest.mark.parametrize(
    ("text", "reference", "heard"),
    [
        (L031_03, L031_03_PHONEMES, L031_03_PHONEMES.replace("اا", "ا", 1)),  # мадд недотянут
        (BASMALA, BASMALA_PHONEMES, ""),  # ничего не услышано
        (L040_01, L040_01_PHONEMES, L040_01_PHONEMES.replace("كك", "ك", 1)),  # нет шадды
        (L024_07, L024_07_PHONEMES, "مُحسِنُمَحشَرُمِنحَرُمَحفَلُءَحسَنَن"),  # лишний звук
    ],
    ids=["madd_short", "empty", "shadda", "extra"],
)
def test_need_and_heard_labels_always_differ(
    lexicon: Lexicon, text: str, reference: str, heard: str
) -> None:
    """I2: «нужно «баа», у тебя «баа»» — бессмыслица: у любой группы подписи разные; «у тебя» —
    не «—» и не пусто (пропуск называется словом «пропущено»)."""
    b = _review(lexicon, text, heard, reference=reference)
    assert b.groups
    for g in b.groups:
        assert g.need_label != g.heard_label, g
        assert g.heard_label.strip() not in ("", "—"), g


def test_missing_shadda_is_one_place_per_letter(lexicon: Lexicon) -> None:
    """I3: буква с шаддой — одно место: «كُمِّلَ» без удвоения — 1 раз, не 2."""
    for heard in (
        L040_01_PHONEMES.replace("كك", "ك", 1),
        L040_01_PHONEMES.replace("ممممِ", "مِ", 1),
    ):
        b = _review(lexicon, L040_01, heard, reference=L040_01_PHONEMES)
        (g,) = b.groups
        assert g.kind is ErrorKind.SHADDA_MISSING
        assert g.times == len({p.clusters for p in g.places}) == 1


def test_same_vowel_swap_on_many_letters_is_one_group(lexicon: Lexicon) -> None:
    """Р7: систематическая «дамма → фатха» во всей строке L040-01 — одна группа, а не по букве."""
    heard = L040_01_PHONEMES.replace("ُ", "َ")
    b = _review(lexicon, L040_01, heard, reference=L040_01_PHONEMES)
    (g,) = b.groups
    assert g.kind is ErrorKind.VOWEL_SUBSTITUTION
    assert g.times == L040_01_PHONEMES.count("ُ")
    assert g.need_label != g.heard_label
    _no_marks(g.need_label)
    _no_marks(g.heard_label)


def test_single_letter_line_with_hamza_seat_does_not_fail(lexicon: Lexicon) -> None:
    """M1: «أَ» прочитано «أُ» — разбор строится (раньше — исключение)."""
    b = build_breakdown(assess("أَ", "أُ"), "أَ", lexicon)
    assert b.groups and b.words_total == 1


def test_missing_tanwin_does_not_name_a_letter_absent_from_the_word(lexicon: Lexicon) -> None:
    """M3: «دَلْوٍ» без «н» танвина — в слове нет буквы ن: подписи не называют ن (Нун)."""
    heard = L043_08_PHONEMES.replace("دَلوِن", "دَلوِ", 1)
    b = _review(lexicon, L043_08, heard, reference=L043_08_PHONEMES)
    (g,) = b.groups
    assert [p.word_index for p in g.places] == [0]
    for label in (g.need_label, g.heard_label):
        assert "ن" not in label and "Нун" not in label, label


def test_lexicon_syllables_give_vowel_labels() -> None:
    """Слоги огласовки — из словаря (``sounds.<буква>.syllables``: фатха, кясра, дамма), а не из
    правила в коде: на своём словаре подписи — ровно эти слоги."""
    small = Lexicon(
        consonants={"ص": ("Сад", "с"), "م": ("Мим", "м")},
        vowels={"َ": "фатха", "ِ": "кясра", "ُ": "дамма"},
        letter_tips={},
        pair_tips={},
        transcription={"ص": "с", "م": "м", "َ": "а", "ِ": "и", "ُ": "у"},
        sounds={"ص": ("со", "")},
        syllables={"ص": ("so", "si", "su")},
    )
    b = build_breakdown(assess("صَمْ", "صِمْ"), "صَمْ", small)
    (g,) = b.groups
    assert "so" in g.need_label and "si" in g.heard_label


# ---------- раунд 3 (повторное ревью 2026-10-24) ----------
# Эталоны (wasl) — quran-transcript с MOSHAF_PARAMS бота, без модели
SWEEP = {
    "L026-06": ("بِعْ عَنْ عَمْ سَعْ مَعَ عَرَبُ عَجَمُ", "بِععَنعَمسَعمَعَعَرَبُعَجَمُ"),
    "L031-03": (L031_03, L031_03_PHONEMES),
    "L031-04": ("جَا جِي جُو حَا حِي حُو خَا خِي خُو", "جَااجِۦۦجُۥۥحَااحِۦۦحُۥۥخَااخِۦۦخُۥۥ"),
    "L032-01": ("فَا فِي فُو قَا قِي قُو كَا كِي كُو", "فَاافِۦۦفُۥۥقَااقِۦۦقُۥۥكَااكِۦۦكُۥۥ"),
    "L032-02": ("لَا لِي لُو مَا مِي مُو نَا نِي نُو", "لَاالِۦۦلُۥۥمَاامِۦۦمُۥۥنَاانِۦۦنُۥۥ"),
    "L032-03": ("وَا وِي وُو هَا هِي هُو يَا يِي يُو", "وَااوِۦۦوُۥۥهَااهِۦۦهُۥۥيَاايِۦۦيُۥۥ"),
}


def _sweep() -> list[Any]:
    """Ничего не услышано и «пропущена одна короткая огласовка перед долгой» (каждая из трёх)."""
    cases = []
    for item, (text, ref) in SWEEP.items():
        cases.append(pytest.param(text, ref, "", id=f"{item}-empty"))
        for name, short, long_ in (("a", "َ", "ا"), ("i", "ِ", "ۦ"), ("u", "ُ", "ۥ")):
            k = ref.rfind(short + long_)
            if k >= 0:
                heard = ref[:k] + ref[k + 1 :]
                cases.append(pytest.param(text, ref, heard, id=f"{item}-no_short_{name}"))
    return cases


@pytest.mark.parametrize(("text", "reference", "heard"), _sweep())
def test_need_and_heard_labels_differ_on_sweep(
    lexicon: Lexicon, text: str, reference: str, heard: str
) -> None:
    """I2 (повторное ревью): «нужно «суу», у тебя «суу»» оставалось при пропуске короткой огласовки
    перед долгой (L031-03 «ثُۥۥ» → «ثۥۥ») и у шадды на ع (L026-06, ничего не услышано)."""
    b = _review(lexicon, text, heard, reference=reference)
    assert b.groups
    for g in b.groups:
        assert g.need_label != g.heard_label, g


def test_missing_tanwin_n_is_named_as_n() -> None:
    """Танвин: в «ثَوْبًا» (L043-03) пропущено «н» — «нужно «н»», а не «на» (огласовки у «н»
    танвина нет)."""
    from muallim.infrastructure.curriculum.yaml_loader import load_lexicon  # noqa: PLC0415
    from tests.conftest import CURRICULUM_DIR  # noqa: PLC0415

    lexicon = load_lexicon(CURRICULUM_DIR / "lexicon.ru.yaml")
    text = "ثَوْبًا ثَوْبٍ ثَوْبٌ فَوْتًا فَوْتٍ فَوْتٌ"
    ref = "ثَوبَنثَوبِنثَوبُنفَوتَنفَوتِنفَوتُن"
    (g,) = _review(lexicon, text, ref.replace("بَن", "بَ", 1), reference=ref).groups
    assert [p.word_index for p in g.places] == [0]
    assert "«н»" in g.need_label and "на" not in g.need_label
