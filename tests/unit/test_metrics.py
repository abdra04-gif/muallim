"""Формулы метрик GQM (docs/research/metrics-gqm.md): G1 — точность, G4 — возврат, G5 — система."""

from datetime import date

import pytest

from muallim.domain.assessment import ErrorKind
from muallim.research.metrics import (
    COMPARISON_VERSION,
    Outcome,
    PhonemeCounts,
    PhonemeOutcome,
    Retention,
    cohen_kappa,
    krippendorff_alpha_nominal,
    mdd_quality,
    nearest_rank,
    phoneme_decisions,
    phoneme_outcomes,
    retention,
)


# Эталон «صَ» = [ص, фатха]. Человек (разметчик) и модель сравниваются с эталоном по каждой
# фонеме — схема MDD: TA, FR, FA, TR (SRC-064), как в L2-ARCTIC (SRC-063) и Iqra'Eval.
@pytest.mark.parametrize(
    ("model", "human", "expected"),
    [
        ("صَ", "صَ", PhonemeCounts(ta=2)),  # оба: прочитано верно
        ("سَ", "سَ", PhonemeCounts(ta=1, tr=1, correct_diagnosis=1)),  # ошибку нашли и назвали
        ("ثَ", "سَ", PhonemeCounts(ta=1, tr=1)),  # ошибку нашли, но назвали не ту букву
        ("سَ", "صَ", PhonemeCounts(ta=1, fr=1)),  # ложная тревога: ученик прочитал верно
        ("صَ", "سَ", PhonemeCounts(ta=1, fa=1)),  # пропуск: модель не заметила ошибку
        ("صِ", "صُ", PhonemeCounts(ta=1, tr=1)),  # огласовка: обе не фатха, но разные
        ("ص", "ص", PhonemeCounts(ta=1, tr=1, correct_diagnosis=1)),  # оба: огласовка пропущена
        ("صَا", "صَ", PhonemeCounts(ta=1, fr=1)),  # лишний мадд в конце — к последней фонеме
        ("صَڇ", "صَ", PhonemeCounts(ta=2)),  # калькаля при остановке — не ошибка (методика)
    ],
)
def test_phoneme_decisions(model: str, human: str, expected: PhonemeCounts) -> None:
    assert phoneme_decisions("صَ", model, human) == expected


def test_phoneme_outcomes_say_where_and_how_the_model_was_wrong() -> None:
    """Разбор по каждому звуку эталона: что ждали, что услышала модель, что — учитель."""
    assert phoneme_outcomes("صَ", "سَ", "صَ") == (
        PhonemeOutcome(
            0, "ص", "س", "ص", Outcome.FALSE_REJECTION, None, ErrorKind.LETTER_SUBSTITUTION, None
        ),  # ученик прав
        PhonemeOutcome(1, "َ", "َ", "َ", Outcome.CORRECT_ACCEPT, None, None, None),
    )
    assert phoneme_outcomes("صَ", "صَ", "سَ")[0] == PhonemeOutcome(
        0,
        "ص",
        "ص",
        "س",
        Outcome.FALSE_ACCEPT,
        None,
        None,
        ErrorKind.LETTER_SUBSTITUTION,  # модель пропустила ошибку
    )
    assert phoneme_outcomes("صَ", "ثَ", "سَ")[0] == PhonemeOutcome(
        0,
        "ص",
        "ث",
        "س",
        Outcome.TRUE_REJECTION,
        False,
        ErrorKind.LETTER_SUBSTITUTION,
        ErrorKind.LETTER_SUBSTITUTION,  # нашла, но не ту букву
    )
    assert phoneme_outcomes("صَ", "سَ", "سَ")[0].same_diagnosis is True


def test_phoneme_outcomes_mark_a_missing_sound_as_empty() -> None:
    first = phoneme_outcomes("صَ", "صَ", "ص")[1]  # учитель: огласовка не прозвучала
    assert (first.expected, first.model_heard, first.human_heard) == ("َ", "َ", "")
    assert first.outcome is Outcome.FALSE_ACCEPT and first.human_kind is ErrorKind.VOWEL_MISSING


def test_phoneme_outcomes_show_extra_sound_after_the_phoneme() -> None:
    last = phoneme_outcomes("صَ", "صَا", "صَ")[1]  # лишний мадд в конце
    assert (last.model_heard, last.outcome) == ("َا", Outcome.FALSE_REJECTION)


@pytest.mark.parametrize(
    ("reference", "human", "position", "shown"),
    [
        ("بَتَ", "بَاتَ", 2, "ات"),  # вставка внутри — перед фонемой, к которой отнесена
        ("بَ", "ءبَ", 0, "ءب"),  # вставка в начале строки
        ("بَتَ", "بَتءَا", 3, "ءَا"),  # две вставки у последней фонемы: перед и после — обе видны
    ],
)
def test_phoneme_outcomes_show_inserted_sounds_where_they_were_heard(
    reference: str, human: str, position: int, shown: str
) -> None:
    assert phoneme_outcomes(reference, reference, human)[position].human_heard == shown


def test_phoneme_outcomes_of_empty_reference_are_empty() -> None:
    assert phoneme_outcomes("", "بَ", "بَ") == ()


@pytest.mark.parametrize(
    ("model", "human"),
    [("صَ", "صَ"), ("سَ", "سَ"), ("ثَ", "سَ"), ("سَ", "صَ"), ("صَ", "سَ"), ("ص", "ص"), ("صَا", "صَ")],
)
def test_phoneme_outcomes_add_up_to_the_metric(model: str, human: str) -> None:
    """Файл «по звукам» и цифры метрики считаются одним правилом — не могут разойтись."""
    rows = phoneme_outcomes("صَ", model, human)
    counts = phoneme_decisions("صَ", model, human)
    by_kind = {kind: sum(r.outcome is kind for r in rows) for kind in Outcome}
    assert (counts.ta, counts.fr, counts.fa, counts.tr) == (
        by_kind[Outcome.CORRECT_ACCEPT], by_kind[Outcome.FALSE_REJECTION],
        by_kind[Outcome.FALSE_ACCEPT], by_kind[Outcome.TRUE_REJECTION],
    )  # fmt: skip
    assert counts.correct_diagnosis == sum(r.same_diagnosis is True for r in rows)


def test_comparison_version_is_declared() -> None:
    assert COMPARISON_VERSION  # меняется вместе с правилом сравнения — видно в выгрузке


def test_phoneme_counts_add_up() -> None:
    total = PhonemeCounts(ta=1, fr=1) + PhonemeCounts(ta=2, tr=1, correct_diagnosis=1)
    assert total == PhonemeCounts(ta=3, fr=1, tr=1, correct_diagnosis=1)


def test_mdd_quality_formulas() -> None:
    # TR — найденные ошибки, FR — ложные тревоги, FA — пропущенные, TA — верно принятые
    q = mdd_quality(PhonemeCounts(ta=80, fr=4, fa=4, tr=12, correct_diagnosis=9))
    assert q.precision == pytest.approx(12 / 16)  # TR / (TR + FR)
    assert q.recall == pytest.approx(12 / 16)  # TR / (TR + FA)
    assert q.f1 == pytest.approx(0.75)
    assert q.far == pytest.approx(4 / 16)  # FA / (FA + TR): пропущено из ошибок
    assert q.frr == pytest.approx(4 / 84)  # FR / (TA + FR): забраковано из верного
    assert q.diagnosis == pytest.approx(9 / 12)  # верно названа ошибка среди найденных


def test_mdd_quality_without_data_is_undefined() -> None:
    q = mdd_quality(PhonemeCounts())
    assert (q.precision, q.recall, q.f1, q.far, q.frr, q.diagnosis) == (None,) * 6


def test_krippendorff_alpha_nominal_reference_example() -> None:
    """Пример Krippendorff (2011) «Computing Krippendorff's Alpha-Reliability»: α = 0,743.

    Строка — единица (что оценивали), столбцы — 4 оценщика, None — не оценивал. То же значение
    даёт библиотека fast-krippendorff (external/), сверено 2026-10-18.
    """
    n = None
    coders = [
        [1, 2, 3, 3, 2, 1, 4, 1, 2, n, n, n],
        [1, 2, 3, 3, 2, 2, 4, 1, 2, 5, n, 3],
        [n, 3, 3, 3, 2, 3, 4, 2, 2, 5, 1, n],
        [1, 2, 3, 3, 2, 4, 4, 1, 2, 5, 1, n],
    ]
    units = [list(values) for values in zip(*coders, strict=True)]
    assert krippendorff_alpha_nominal(units) == pytest.approx(0.743421, abs=1e-6)


def test_krippendorff_alpha_perfect_and_undefined() -> None:
    assert krippendorff_alpha_nominal([["ok", "ok"], ["err", "err"]]) == pytest.approx(1.0)
    assert krippendorff_alpha_nominal([]) is None
    assert krippendorff_alpha_nominal([["ok", "ok"], ["ok", "ok"]]) is None  # нет разброса
    assert krippendorff_alpha_nominal([["ok", None]]) is None  # одна оценка — не пара


def test_cohen_kappa_known_value() -> None:
    # 4 оба «да», 1 «да/нет», 2 «нет/да», 3 оба «нет»: po = 0,7, pe = 0,5 → κ = 0,4
    pairs = [(True, True)] * 4 + [(True, False)] + [(False, True)] * 2 + [(False, False)] * 3
    assert cohen_kappa(pairs) == pytest.approx(0.4)


def test_cohen_kappa_perfect_agreement() -> None:
    assert cohen_kappa([(True, True), (False, False)]) == pytest.approx(1.0)


def test_cohen_kappa_undefined_without_variation_or_data() -> None:
    assert cohen_kappa([]) is None
    assert cohen_kappa([(True, True), (True, True)]) is None  # pe = 1


def test_nearest_rank_percentiles() -> None:
    values = [100 * i for i in range(10, 0, -1)]  # порядок не важен
    assert nearest_rank(values, 50) == 500
    assert nearest_rank(values, 90) == 900
    assert nearest_rank(values, 100) == 1000
    assert nearest_rank([], 90) is None


def test_retention_counts_returns_and_seven_day_cohort() -> None:
    today = date(2026, 10, 17)
    days = {
        "L-a": {date(2026, 10, 1), date(2026, 10, 9)},  # вернулся, и через ≥ 7 дней
        "L-b": {date(2026, 10, 2), date(2026, 10, 3)},  # вернулся, но не через 7 дней
        "L-c": {date(2026, 10, 15), date(2026, 10, 16)},  # слишком новый для 7-дневной когорты
        "L-d": {date(2026, 10, 5)},  # не вернулся
    }
    assert retention(days, today) == Retention(learners=4, returned=3, cohort_7d=3, returned_7d=1)
