"""FR-54: разбор арабского текста — чистые функции домена (``muallim.domain.arabic``).

Группы ошибок нужны в application (какие слова задеты), а картинка — в presentation. Поэтому разбор
строки на буквы (кластеры) и сопоставление согласных эталона с буквами текста переезжают из
``render.py`` в домен; ``render`` их реэкспортирует (старые тесты test_render.py не меняются).
Строки — из curriculum/course.ru.yaml.
"""

from muallim.domain import arabic
from muallim.presentation.telegram import render

L024_07 = "مُحْسِنُ مَحْشَرُ مِنْحَرُ مَحْفَلُ أَحْسَنَ"  # урок ح, с. 21
# Эталон в фонемах (как у Muaalem): хамза вместо «أ», без сукуна и пробелов
L024_07_PHONEMES = "مُحسِنُمَحشَرُمِنحَرُمَحفَلُءَحسَنَ"
FATIHA_2 = "ٱلْحَمْدُ لِلَّهِ رَبِّ ٱلْعَـٰلَمِينَ"
# Настоящий выход фонетизатора quran-transcript (external/obadx_quran-transcript/tests/
# phonetics_pytest.py:3257) без пробелов: шадда удвоена, «ٱ» внутри фразы не читается.
FATIHA_2_PHONEMES = "ءَلحَمدُلِللَااهِرَببِلعَاالَمِۦۦن"


def test_text_parsing_lives_in_domain_and_render_reexports_it() -> None:
    """Одна реализация на оба слоя: render берёт кластеры из домена, а не держит копию."""
    assert render.clusters is arabic.clusters
    assert render.Cluster is arabic.Cluster
    assert render.consonant_clusters is arabic.consonant_clusters
    assert render.error_clusters is arabic.error_clusters
    assert render.unread_clusters is arabic.unread_clusters
    assert render.word_states is arabic.word_states
    assert render.WordState is arabic.WordState


def test_domain_clusters_keep_marks_with_their_letter() -> None:
    cs = arabic.clusters("مَرْ مُ")
    assert [(c.base, c.marks) for c in cs] == [("م", "َ"), ("ر", "ْ"), ("م", "ُ")]


def test_each_reference_consonant_knows_its_word() -> None:
    """FR-54: ошибка в согласной эталона → слово строки, где она случилась («в каких словах»)."""
    assert (
        arabic.consonant_words(L024_07, L024_07_PHONEMES)
        == [0] * 4 + [1] * 4 + [2] * 4 + [3] * 4 + [4] * 4
    )


def test_consonant_words_work_when_reference_is_the_text_itself() -> None:
    """В тестах экранов эталон — сам текст (с пробелами и сукуном): слова те же."""
    words = arabic.consonant_words(L024_07, L024_07)
    # «أ» в эталоне-тексте — не фонема: 19 согласных, последние — ل слова 3 и ح س ن слова 4
    assert len(words) == 19
    assert words[:4] == [0, 0, 0, 0] and words[-4:] == [3, 4, 4, 4]


def test_consonant_words_count_shadda_and_silent_alif_wasl() -> None:
    """Шадда — две согласные одного слова; «ٱ» внутри фразы не читается и слово не сдвигает."""
    assert arabic.consonant_words("رَبَّ", "رَببَ") == [0, 0, 0]
    # ء ل ح م د | ل ل ل ه | ر ب ب | ل ع ل م ن — 17 согласных
    assert arabic.consonant_words(FATIHA_2, FATIHA_2_PHONEMES) == (
        [0] * 5 + [1] * 4 + [2] * 3 + [3] * 5
    )


def test_hamza_on_tatweel_belongs_to_its_own_letter() -> None:
    """I7: «يَنْـَٔوْنَ» (L046-06) — хамза ء эталона принадлежит кластеру татвиля с хамзой «ـَٔ»
    (U+0654), а не букве ن: иначе на картинке красным красится не та буква."""
    text, reference = "يَنْـَٔوْنَ", "يَنءَونَ"
    letters = arabic.clusters(text)
    seat = next(n for n, c in enumerate(letters) if "ٔ" in c.marks)
    assert arabic.owners(text, reference) == [0, 1, seat, 3, 4]
