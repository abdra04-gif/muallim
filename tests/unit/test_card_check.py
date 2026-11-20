"""Решение по «вариантам карточки» без модели (FR-70 п. 2, 3, 5; ADR-0087 п. 4, 9; ADR-0088 п. 3).

Модель заменена таблицей баллов: log P(вариант | запись) для нескольких строк записи бота, у всех
остальных вариантов балл ничтожный. Ожидаемое поведение сверено с прототипом
`docs/research/phase3/library_check.py::answer` (правило последнего слога `--last clear`).
Карточки — из `curriculum/course.ru.yaml` («بُ», «دَ», «رَ رِ رُ», «رَبَ», «رَبَّ», «بَا»), строки — их
запись фонетизатором бота.
"""

import math
from collections.abc import Callable, Mapping, Sequence

import pytest

from muallim.domain.policy import CardPolicy

UNHEARD = -1000.0  # балл варианта, которого нет в таблице: модель его «не слышала»

from muallim.domain.card_check import LOOKALIKE, CardDecision, decide  # noqa: E402


def _score(table: Mapping[str, float], unheard: float = UNHEARD) -> Callable[[str], float]:
    return lambda variant: table.get(variant, unheard)


def _decide(
    accepted: Sequence[str],
    table: Mapping[str, float],
    *,
    separate_syllables: bool = True,
    policy: CardPolicy | None = None,
    **kwargs: frozenset[str],
) -> CardDecision:
    return decide(
        accepted,
        _score(table),
        policy or CardPolicy(),
        separate_syllables=separate_syllables,
        **kwargs,
    )


# --- засчитано / ещё раз / ошибка (пороги 0 и −4) ---------------------------------------------


def test_correct_reading_ahead_of_every_error_is_passed() -> None:
    d = _decide(["بُ"], {"بُ": -1.0, "بَ": -5.0})
    assert d.outcome == "passed"
    assert d.kind is None
    assert d.winner == "بُ"
    assert d.margin == pytest.approx(4.0)


def test_margin_exactly_zero_is_passed() -> None:
    assert _decide(["بُ"], {"بُ": -5.0, "بَ": -5.0}).outcome == "passed"


def test_error_slightly_ahead_asks_to_read_again() -> None:
    d = _decide(["بُ"], {"بُ": -5.0, "بَ": -3.0})
    assert d.outcome == "again"
    assert d.margin == pytest.approx(-2.0)


def test_margin_exactly_minus_four_is_still_again() -> None:
    assert _decide(["بُ"], {"بُ": -10.0, "بَ": -6.0}).outcome == "again"


def test_error_clearly_ahead_is_an_error_with_its_kind_and_reading() -> None:
    d = _decide(["بُ"], {"بُ": -10.0, "بِ": -2.0})
    assert d.outcome == "error"
    assert d.kind == "vowel"
    assert d.winner == "بِ"
    assert d.margin == pytest.approx(-8.0)


def test_no_vowel_on_a_single_syllable_card_is_an_error() -> None:
    d = _decide(["بُ"], {"بُ": -10.0, "ب": -2.0})
    assert d.outcome == "error"
    assert d.kind == "no_vowel"
    assert d.winner == "ب"


def test_lookalike_letter_is_a_typical_error_not_another_syllable() -> None:
    d = _decide(["دَ"], {"دَ": -10.0, "تَ": -2.0})
    assert d.outcome == "error"
    assert d.kind == "lookalike"
    assert d.winner == "تَ"
    assert not d.other_syllable


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("ص", "س"),
        ("ض", "د"),
        ("ط", "ت"),
        ("ظ", "ز"),
        ("ح", "ه"),
        ("ع", "ء"),
        ("ق", "ك"),
        ("ث", "س"),
    ],
)
def test_lookalike_table_has_the_pairs_of_the_letter_tests(a: str, b: str) -> None:
    """Пары — как `U_LOOK` в `docs/research/phase3/compare_models.py`; утверждает человек."""
    assert LOOKALIKE
    assert b in LOOKALIKE.get(a, "")


def test_lookalike_table_is_symmetric() -> None:
    """«Похожи» — отношение пары: если د похожа на ت, то и ت на د (как `near` в прототипе)."""
    for letter, others in LOOKALIKE.items():
        for other in others:
            assert letter in LOOKALIKE.get(other, ""), (letter, other)


def test_thresholds_come_from_the_policy() -> None:
    strict = CardPolicy(error_margin=-1.0)
    assert _decide(["بُ"], {"بُ": -10.0, "بَ": -8.0}, policy=strict).outcome == "error"


def test_own_policy_changes_the_outcome_for_the_same_scores() -> None:
    own = CardPolicy(error_margin=-2.0, other_error=-5.0)
    typical = {"بُ": -10.0, "بَ": -7.0}  # маржа −3
    assert _decide(["بُ"], typical).outcome == "again"
    assert _decide(["بُ"], typical, policy=own).outcome == "error"
    other = {"بُ": -10.0, "زُ": -4.5}  # «другой слог» −5,5
    assert _decide(["بُ"], other).outcome == "again"
    d = _decide(["بُ"], other, policy=own)
    assert d.outcome == "error"
    assert d.other_syllable


# --- тихая запись и неверный вызов ---------------------------------------------------------------


def test_silent_recording_asks_to_read_again() -> None:
    """Модель не слышит ничего (все баллы −inf): не nan и не «ошибка» — бот не расслышал."""
    d = decide(["بُ"], _score({}, unheard=-math.inf), CardPolicy(), separate_syllables=True)
    assert d.outcome == "again"
    assert not math.isnan(d.margin)
    assert not math.isnan(d.margin_other)


def test_impossible_correct_reading_with_a_heard_error_is_an_error() -> None:
    d = decide(["بُ"], _score({"بِ": -5.0}, unheard=-math.inf), CardPolicy(), separate_syllables=True)
    assert d.outcome == "error"
    assert d.winner == "بِ"


def test_card_without_accepted_reading_is_rejected() -> None:
    with pytest.raises(ValueError):
        _decide([], {})


# --- соперник «другой слог» (пороги −6 и −3) ------------------------------------------------


def test_another_syllable_far_ahead_is_an_other_syllable_error() -> None:
    d = _decide(["بُ"], {"بُ": -10.0, "زُ": -3.0})
    assert d.outcome == "error"
    assert d.other_syllable
    assert d.winner == "زُ"
    assert d.margin_other == pytest.approx(-7.0)


def test_another_syllable_rule_overrides_a_passed_typical_margin() -> None:
    """Типичные ошибки позади (маржа ≥ 0 — «засчитано»), но чужой слог впереди больше чем на 6."""
    d = _decide(["بُ"], {"بُ": -10.0, "بَ": -10.0, "زِ": -3.5})
    assert d.margin == pytest.approx(0.0)
    assert d.outcome == "error"
    assert d.other_syllable
    assert d.winner == "زِ"


def test_another_syllable_exactly_minus_six_is_only_again() -> None:
    d = _decide(["بُ"], {"بُ": -10.0, "زَ": -4.0})
    assert d.outcome == "again"
    assert not d.other_syllable


def test_another_syllable_exactly_minus_three_does_not_ask_again() -> None:
    assert _decide(["بُ"], {"بُ": -10.0, "زِ": -7.0}).outcome == "passed"


def test_another_syllable_close_with_close_typical_error_is_again() -> None:
    """Без правила «другой слог» маржа +2 дала бы «засчитано»."""
    assert _decide(["بُ"], {"بُ": -10.0, "زُ": -5.5, "بَ": -12.0}).outcome == "again"


def test_another_syllable_close_with_clear_typical_error_is_error() -> None:
    """Полоса −6…−3 даёт «ещё раз» только при марже ≥ −4; при марже −5 — ошибка, а не «ещё раз»."""
    d = _decide(["بُ"], {"بُ": -10.0, "زُ": -5.5, "بَ": -5.0})
    assert d.margin_other == pytest.approx(-4.5)
    assert d.outcome == "error"
    assert d.kind == "vowel"


# --- несколько верных чтений ------------------------------------------------------------------


def test_score_of_correct_combines_every_accepted_reading() -> None:
    """Верное = logaddexp по чтениям (слитно и с остановкой); принятое чтение — не ошибка."""
    d = _decide(["رَبَ", "رَب"], {"رَبَ": -2.0, "رَب": -2.0, "رِبَ": -3.0}, separate_syllables=False)
    assert d.outcome == "passed"
    assert d.margin == pytest.approx(1.0 + math.log(2.0))


def test_winner_of_a_passed_card_is_the_best_accepted_reading() -> None:
    d = _decide(["رَبَ", "رَب"], {"رَبَ": -10.0, "رَب": -1.0}, separate_syllables=False)
    assert d.outcome == "passed"
    assert d.winner == "رَب"
    assert d.kind is None


# --- мягкие виды: короткий мадд и нет шадды -----------------------------------------------------


def test_missing_shadda_ahead_only_gives_a_hint() -> None:
    d = _decide(
        ["رَببَ", "رَببڇ"],
        {"رَببَ": -10.0, "رَببڇ": -11.0, "رَبَ": -2.0},
        separate_syllables=False,
    )
    assert d.outcome == "passed"
    assert d.kind is None
    assert "no_shadda" in d.hints


def test_missing_shadda_behind_gives_no_hint() -> None:
    d = _decide(["رَببَ"], {"رَببَ": -2.0, "رَبَ": -10.0}, separate_syllables=False)
    assert d.outcome == "passed"
    assert d.hints == ()


def test_short_madd_ahead_only_gives_a_hint() -> None:
    d = _decide(["بَاا"], {"بَاا": -10.0, "بَ": -1.0})
    assert d.outcome == "passed"
    assert "short_madd" in d.hints


def test_soft_hint_is_kept_when_the_card_is_read_again() -> None:
    d = _decide(["رَببَ"], {"رَببَ": -10.0, "رَببِ": -8.0, "رَبَ": -2.0}, separate_syllables=False)
    assert d.outcome == "again"
    assert "no_shadda" in d.hints


def test_soft_kind_is_an_error_where_it_is_not_soft() -> None:
    d = _decide(
        ["رَببَ"],
        {"رَببَ": -10.0, "رَبَ": -2.0},
        separate_syllables=False,
        soft_kinds=frozenset(),
    )
    assert d.outcome == "error"
    assert d.kind == "no_shadda"
    assert d.winner == "رَبَ"


# --- последний слог карточки из отдельных слогов: «ясная гласная» -------------------------------

TRIPLE = ["رَرِرُ"]  # «رَ رِ رُ»: слоги отдельно, читаются все с гласной


def test_last_vowel_clearly_other_is_an_error() -> None:
    d = _decide(TRIPLE, {"رَرِرُ": -10.0, "رَرِرَ": -3.0})
    assert d.outcome == "error"
    assert d.kind == "vowel"
    assert d.winner == "رَرِرَ"


def test_last_vowel_other_exactly_minus_four_is_again() -> None:
    assert _decide(TRIPLE, {"رَرِرُ": -10.0, "رَرِرِ": -6.0}).outcome == "again"


def test_last_vowel_slightly_other_is_again() -> None:
    assert _decide(TRIPLE, {"رَرِرُ": -10.0, "رَرِرَ": -8.0}).outcome == "again"


def test_last_vowel_other_exactly_zero_is_passed() -> None:
    assert _decide(TRIPLE, {"رَرِرُ": -5.0, "رَرِرَ": -5.0}).outcome == "passed"


def test_last_vowel_hardly_heard_asks_again_with_last_vowel_hint() -> None:
    d = _decide(TRIPLE, {"رَرِرُ": -10.0, "رَرِر": -8.0})
    assert d.outcome == "again"
    assert "last_vowel" in d.hints


def test_no_vowel_on_the_last_syllable_is_never_an_error() -> None:
    d = _decide(TRIPLE, {"رَرِرُ": -10.0, "رَرِر": -1.0})
    assert d.outcome == "again"
    assert "last_vowel" in d.hints


def test_last_syllable_rule_does_not_soften_the_middle_syllable() -> None:
    assert _decide(TRIPLE, {"رَرِرُ": -10.0, "رَرَرُ": -3.0}).outcome == "error"
    d = _decide(TRIPLE, {"رَرِرُ": -10.0, "رَررُ": -3.0})
    assert d.outcome == "error"
    assert d.kind == "no_vowel"


def test_last_syllable_of_a_word_is_checked_like_the_others() -> None:
    d = _decide(["رَبَ"], {"رَبَ": -10.0, "رَب": -2.0}, separate_syllables=False)
    assert d.outcome == "error"
    assert d.kind == "no_vowel"


# --- исправления по ревью (FR-70; ADR-0088 п. 3, 8) -------------------------------------------


def _numbers_are_finite(d: CardDecision) -> None:
    """Решение уходит в ``attempts.model_output`` (JSON PostgreSQL): inf и nan там нельзя."""
    import dataclasses  # noqa: PLC0415
    import json  # noqa: PLC0415

    json.dumps(dataclasses.asdict(d), allow_nan=False)
    for value in (d.margin, d.margin_other):
        assert value is None or math.isfinite(value), d


def test_decision_without_hard_rivals_has_no_infinite_margin() -> None:
    """Ни одной жёсткой ошибки (все виды — мягкие): маржа не +inf, а None или число."""
    d = _decide(["بُ"], {"بُ": -1.0}, soft_kinds=frozenset({"vowel", "lookalike", "no_vowel"}))
    assert d.outcome == "passed"
    _numbers_are_finite(d)


@pytest.mark.parametrize(
    "table",
    [
        {},  # тишина
        {"بُ": -1.0},  # слышно только верное
        {"بِ": -5.0},  # верное невозможно, ошибка слышна
        {"بُ": -10.0, "زُ": -3.0},  # другой слог
        {"ب": -2.0},  # слишком короткая запись
    ],
)
def test_every_decision_is_json_safe(table: dict[str, float]) -> None:
    d = decide(["بُ"], _score(table, unheard=-math.inf), CardPolicy(), separate_syllables=True)
    _numbers_are_finite(d)


def test_too_short_recording_asks_to_read_again_not_an_error() -> None:
    """Кадров меньше, чем звуков верного чтения: верное −inf, а «нет гласной» (короче) — число.
    Это не ошибка ученика — бот не расслышал."""
    d = decide(["بُ"], _score({"ب": -2.0}, unheard=-math.inf), CardPolicy(), separate_syllables=True)
    assert d.outcome == "again"
    assert d.kind is None


# ималя (۪ + ـ, `quran_transcript.phonetics.operations`, مَجْر۪ىٰهَا — L096-02) и краткая дамма
# (ؙ, `process_uthmani_alphabet.py`, تَأْمَ۫نَّا — L096-03) — гласные фонетизатора бота
@pytest.mark.parametrize(("syllable", "bare"), [("ر۪ــ", "ر"), ("نؙ", "ن")])
def test_imala_and_shortened_damma_are_vowels(syllable: str, bare: str) -> None:
    """Без гласной вместо ималя / краткой даммы — ошибка «нет гласной», как у обычной огласовки."""
    d = _decide([syllable], {syllable: -10.0, bare: -2.0})
    assert d.outcome == "error"
    assert d.kind == "no_vowel"
    assert d.winner == bare


RABBA = ("رَببَ", "رَببڇ")  # «رَبَّ» L038-01: слитно и с остановкой (фикстура maroof_cards.json)


def test_order_of_accepted_readings_does_not_change_the_decision() -> None:
    """Варианты ошибок строятся от чтения со всеми гласными (слитно), где бы оно ни стояло:
    у чтения с остановкой у последней буквы гласной нет, и ошибку в её огласовке не построить."""
    table = {"رَببَ": -10.0, "رَببڇ": -11.0, "رَببِ": -3.0}
    wasl_first = _decide(RABBA, table, separate_syllables=False)
    waqf_first = _decide(RABBA[::-1], table, separate_syllables=False)
    assert wasl_first.outcome == "error"
    assert wasl_first.winner == "رَببِ"
    assert waqf_first == wasl_first


KALAM = ("كَلَاامُ", "كَلَاااام")  # «كَلَامُ» L034-01: мадд 2 и 4 знака — для модели один звук aa


def test_variant_that_sounds_like_an_accepted_reading_is_not_an_error() -> None:
    """«Нет гласной» у كَلَاامُ — كَلَاام: в записи бота это не чтение с остановкой (там мадд
    длиннее), а для модели — те же звуки. Дубликат отсеивается по звукам (``sounds``), и маржа
    считается против настоящей ошибки, а не против самого верного чтения (было ≈ 0)."""
    from muallim.infrastructure.asr.maroof_script import to_maroof  # noqa: PLC0415

    by_sounds = {to_maroof(KALAM[1]): -1.0, to_maroof("كَلَاامِ"): -6.0}

    def score(variant: str) -> float:
        return by_sounds.get(to_maroof(variant), UNHEARD)

    d = decide(KALAM, score, CardPolicy(), separate_syllables=False, sounds=to_maroof)
    assert d.outcome == "passed"
    assert d.margin == pytest.approx(5.0, abs=1e-3)
    assert d.hints == ()
