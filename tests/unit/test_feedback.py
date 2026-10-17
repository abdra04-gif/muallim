"""Объяснения ошибок для новичка (FR-05, FR-43): что не так, в каком слоге, как сказать."""

import pytest

from muallim.application.feedback import Explanation, FeedbackRenderer
from muallim.domain.assessment import assess, unread_from
from muallim.domain.curriculum import Curriculum

HOW = "👄"


def msgs(renderer: FeedbackRenderer, reference: str, heard: str) -> tuple[str, ...]:
    return renderer.render(assess(reference, heard).errors, reference)


def test_letter_substitution_names_both_letters_and_gives_pair_tip(
    renderer: FeedbackRenderer, curriculum: Curriculum
) -> None:
    (m,) = msgs(renderer, "صَ", "سَ")
    assert "ص" in m and "س" in m and "«с̣а»" in m
    assert curriculum.lexicon.pair_tips[frozenset("صس")] in m and HOW in m


def test_substitution_without_pair_tip_falls_back_to_letter_tip(
    renderer: FeedbackRenderer, curriculum: Curriculum
) -> None:
    (m,) = msgs(renderer, "بَ", "مَ")
    assert curriculum.lexicon.letter_tips["ب"] in m


def test_error_points_to_the_syllable_not_its_number(renderer: FeedbackRenderer) -> None:
    (m,) = msgs(renderer, "كَتَبَ", "كَطَبَ")
    assert "«та»" in m and "слоге" in m and "2-м" not in m


def test_vowel_substitution_says_how_to_hold_the_mouth(
    renderer: FeedbackRenderer, curriculum: Curriculum
) -> None:
    (m,) = msgs(renderer, "بَ", "بِ")
    assert "фатха" in m and "кясра" in m
    assert curriculum.lexicon.vowel_tips["َ"] in m


def test_missing_short_vowel_gives_vowel_tip(
    renderer: FeedbackRenderer, curriculum: Curriculum
) -> None:
    (m,) = msgs(renderer, "بَ", "ب")
    assert "«ба»" in m and curriculum.lexicon.vowel_tips["َ"] in m


def test_vowel_stretched_into_madd(renderer: FeedbackRenderer) -> None:
    (m,) = msgs(renderer, "بَ", "بَا")
    assert "растянут" in m and HOW in m


def test_missing_shadda_explains_doubling(renderer: FeedbackRenderer) -> None:
    (m,) = msgs(renderer, "رَببَ", "رَبَ")
    assert "ташдид" in m.lower() and HOW in m


@pytest.mark.parametrize(
    ("reference", "heard"),
    [("صَ", "سَ"), ("بَ", "بِ"), ("بَ", "بx"), ("بَتَ", "سِ"), ("بَا", "بَ"), ("بَ", "ب"),
     ("رَببَ", "رَبَ"), ("كَتَبَ", "كَتَ"), ("بَ", "بَا"), ("بَ", "بَس")],
)  # fmt: skip
def test_every_error_kind_says_what_and_how(
    renderer: FeedbackRenderer, reference: str, heard: str
) -> None:
    """Каждый тип ошибки (10 из 10) — с подсказкой, как исправить, а не только что не так."""
    found = msgs(renderer, reference, heard)
    assert found and all(m.strip() and HOW in m for m in found)


def test_unknown_symbol_is_quoted(renderer: FeedbackRenderer) -> None:
    assert renderer.describe("x") == "«x»"


def test_old_style_call_without_reference_still_works(renderer: FeedbackRenderer) -> None:
    """Черновики kk/en и старые вызовы: без эталона слог не показываем, но и не падаем."""
    (m,) = renderer.render(assess("صَ", "سَ").errors)
    assert "ص" in m


def explain(renderer: FeedbackRenderer, reference: str, heard: str) -> tuple[Explanation, ...]:
    a = assess(reference, heard)
    return renderer.explain(a.errors, reference, unread_from(reference, heard))


def test_every_error_keeps_its_own_message_for_research(renderer: FeedbackRenderer) -> None:
    """В БД у каждой ошибки — свой текст (detected_errors.message), даже если они совпадают."""
    errors = assess("بَلَاا", "بَلَ").errors
    assert len(renderer.render(errors, "بَلَاا")) == len(errors) == 2


def test_same_explanation_is_not_repeated(renderer: FeedbackRenderer) -> None:
    """Мадд из двух «ا» не дотянут — две ошибки в одном слоге, но пункт один."""
    (m,) = explain(renderer, "بَلَاا", "بَلَ")
    assert m.text.startswith("«лаа» → у тебя «ла»")


# ---------- коротко + «подробнее» (ADR-0031) ----------
def test_item_is_syllable_as_needed_and_as_heard_plus_short_hint(
    renderer: FeedbackRenderer, curriculum: Curriculum
) -> None:
    """Слог «как надо → как у тебя» и полфразы подсказки; без названий букв и «+»."""
    (m,) = explain(renderer, "صَبَرَ", "سَبَرَ")
    first, hint = m.text.split("\n")
    assert first == "«с̣а» → у тебя «са»"
    assert "с̣" in hint and len(hint) < 60
    assert "(Сод" not in m.text and "+" not in m.text and HOW not in m.text
    assert curriculum.lexicon.pair_tips[frozenset("صس")] in m.more


def test_several_sounds_read_otherwise_are_shown_as_syllables(renderer: FeedbackRenderer) -> None:
    (m,) = explain(renderer, "كَتَبَ", "كَطِبَ")
    assert m.text.startswith("«та» → у тебя «т̣и»") and "+" not in m.text


def test_mixed_up_place_names_the_mixed_up_letter(
    renderer: FeedbackRenderer, curriculum: Curriculum
) -> None:
    """«х̣ии» → «һа»: главное — «х̣», а не «һ»; подсказка к этой паре букв — в «подробнее»."""
    (m,) = explain(renderer, "رَحِۦۦمِ", "رَهَمِ")
    assert m.text == "«х̣ии» → у тебя «һа»\nНужен звук «х̣», а не «һ»."
    assert curriculum.lexicon.pair_tips[frozenset("حه")] in m.more


def test_mixed_up_vowel_is_named_when_letters_are_right(renderer: FeedbackRenderer) -> None:
    (m,) = explain(renderer, "بَاتَ", "بُۥتَ")
    assert "«а»" in m.text and "«у»" in m.text


def test_skipped_syllable_is_shown_as_missing(renderer: FeedbackRenderer) -> None:
    (m,) = explain(renderer, "كَتَبَ", "كَبَ")
    assert m.text.startswith("«та» → у тебя пропущено")


def test_one_item_per_syllable(renderer: FeedbackRenderer) -> None:
    """Пропущена буква — не перечислять ещё и её огласовку и мадд."""
    (m,) = explain(renderer, "بَلَاكَ", "بَكَ")
    assert m.text.startswith("«лаа» → у тебя пропущено") and m.text.count("\n") == 1


def test_clear_errors_come_before_madd(renderer: FeedbackRenderer) -> None:
    """Лахн джали (буква, огласовка) — раньше лахн хафи (мадд): сначала то, что меняет слово."""
    found = explain(renderer, "بَاكَتَ", "بَكَطَ")
    assert len(found) == 2
    assert "т̣" in found[0].text and "«баа»" in found[1].text


def test_unread_tail_is_one_short_item(renderer: FeedbackRenderer) -> None:
    reference = "ءَلحَمدُلِلََهِرَبِِلعَاالَمِۦۦنَ"
    (m,) = explain(renderer, reference, reference[:15])
    assert m.text.startswith("📖") and "«һи»" in m.text and "«ра" in m.text
    assert "до конца" in m.more


def test_errors_before_the_stop_are_still_explained(renderer: FeedbackRenderer) -> None:
    reference = "ءَلحَمدُلِلََهِرَبِِلعَاالَمِۦۦنَ"
    found = explain(renderer, reference, reference[:15].replace("ح", "ه"))
    assert len(found) == 2 and found[0].text.startswith("«х̣ам» → у тебя «һам»")
    assert found[1].text.startswith("📖")
