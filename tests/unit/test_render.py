"""Картинки карточек: разбор арабского текста на буквы, подсветка (ADR-0024)."""

import pytest

from muallim.presentation.telegram import render


def test_clusters_keep_marks_with_their_letter() -> None:
    cs = render.clusters("مَرْ مُ")
    assert [(c.base, c.marks) for c in cs] == [("م", "َ"), ("ر", "ْ"), ("م", "ُ")]


def test_accent_marks_every_lesson_letter() -> None:
    assert render.accent_clusters("مَرْمَرُ", {"م"}) == {0, 2}


def test_error_syllable_maps_to_letter_with_shadda_counted_twice() -> None:
    text = "صَبَرَ"
    assert render.error_clusters(text, [1, 3]) == {0, 2}
    assert render.error_clusters("رَبَّ", [3]) == {1}  # بّ — два согласных: слоги 2 и 3
    assert render.error_clusters("صَ", [None, 9]) == set()


def test_unread_tail_is_highlighted_to_the_end_of_the_line() -> None:
    """Прочитана половина строки — красным весь непрочитанный конец, а не сдвинутый кусок.

    В фонемах шадда — одна согласная, а «ٱ» в середине фразы не читается: по номеру согласной
    подсветка уезжала к началу строки.
    """
    text = "ٱلْحَمْدُ لِلَّهِ رَبِّ ٱلْعَـٰلَمِينَ"
    reference = "ءَلحَمدُلِلََهِرَبِِلعَاالَمِۦۦنَ"
    wrong = render.error_clusters(text, [10, 11, 12, 13, 14, 15], reference)
    letters = render.clusters(text)
    shown = "".join(letters[n].base for n in sorted(wrong))
    assert shown == "بٱلعـلمين"


def test_shadda_doubled_in_phonemes_maps_to_one_letter() -> None:
    assert render.error_clusters("رَبَّ", [2, 3], "رَببَ") == {1}
    assert render.error_clusters("صَبَرَ", [1, 3], "صَبَرَ") == {0, 2}


def test_unread_clusters_are_from_a_consonant_to_the_end() -> None:
    text = "ٱلْحَمْدُ لِلَّهِ رَبِّ ٱلْعَـٰلَمِينَ"
    reference = "ءَلحَمدُلِلََهِرَبِِلعَاالَمِۦۦنَ"
    unread = render.unread_clusters(text, reference, 9)  # с «ر» (9-я согласная)
    letters = render.clusters(text)
    assert "".join(letters[n].base for n in sorted(unread)) == "ربٱلعـلمين"


def test_madd_letters_without_marks_are_not_consonants() -> None:
    assert render.consonant_clusters("بَا بُو") == [0, 2]


needs_raqm = pytest.mark.skipif(not render.available(), reason="нет libraqm (brew install fribidi)")


@needs_raqm
@pytest.mark.parametrize(
    "png",
    [
        lambda: render.card("رَ رِ رُ", {"ر"}, (0, 2)),
        lambda: render.result("صُمْ صِفْ", {0}, 70),
        lambda: render.result("صُمْ صِفْ", {0}, 40, unread={2, 3}),
        lambda: render.result(" ".join(["ٱلْحَمْدُ لِلَّهِ رَبِّ ٱلْعَـٰلَمِينَ"] * 3), {1}, 50, {40}),
        lambda: render.alphabet([[("ا", render.Mark.DONE), ("ب", render.Mark.CURRENT)]]),
        lambda: render.letters("ا ب ت ث ج ح خ"),
        render.signs,
        lambda: render.rule("بَ بِ بُ"),
        lambda: render.card("بِسْمِ ٱللَّهِ ٱلرَّحْمَـٰنِ ٱلرَّحِيمِ", set(), (0, 3)),
    ],
)
def test_images_are_png(png) -> None:  # type: ignore[no-untyped-def]
    data = png()
    assert data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) > 5000
