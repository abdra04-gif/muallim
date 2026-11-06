"""FR-62 (ADR-0079 п. 5): точность бота по клеткам — отдельный блок рядом с фонемными цифрами RQ-1.

Исход клетки — та же схема MDD (SRC-064), но единица крупнее фонемы: модель отметила клетку ×
учитель отметил клетку. TA — никто, FR — только модель, FA — только учитель, TR — оба.
Precision/recall/F1 — те же формулы (``mdd_quality``); recall по виду ошибки учителя; α
Криппендорфа (SRC-065) — по клеткам «ошибка / нет» и по виду. Данные синтетические.
"""

from typing import Any
from uuid import UUID

import pytest

from muallim.research import metrics

A, B = UUID(int=1), UUID(int=2)  # ученики


def _labels() -> list[Any]:
    """Аят из 12 клеток. 1/T1: бот и учитель — клетка 9 (TR). 2/T1: бот — 7, учитель — ничего
    (FR). 3/T1 и 3/T2: бот — ничего, учителя — 2 и 5 (FA); в клетке 5 T1 слышит ещё и таджвид."""
    label = metrics.CellLabel
    return [
        label(learner=A, attempt=UUID(int=11), annotator="T1", cells=12,
              model=frozenset({9}), teacher={9: frozenset({"letter"})}),
        label(learner=A, attempt=UUID(int=12), annotator="T1", cells=12,
              model=frozenset({7}), teacher={}),
        label(learner=B, attempt=UUID(int=13), annotator="T1", cells=12, model=frozenset(),
              teacher={2: frozenset({"missing"}), 5: frozenset({"vowel", "tafkhim"})}),
        label(learner=B, attempt=UUID(int=13), annotator="T2", cells=12, model=frozenset(),
              teacher={2: frozenset({"missing"}), 5: frozenset({"vowel"})}),
    ]  # fmt: skip


def test_cell_outcomes_are_counted_per_cell_of_every_label() -> None:
    c = metrics.cell_metrics(_labels())
    assert (c.labels, c.counts.ta, c.counts.fr, c.counts.fa, c.counts.tr) == (4, 42, 1, 4, 1)


def test_cell_precision_recall_and_f1_use_mdd_formulas() -> None:
    q = metrics.cell_metrics(_labels()).quality
    assert q.precision == pytest.approx(1 / 2)  # TR / (TR + FR)
    assert q.recall == pytest.approx(1 / 5)  # TR / (TR + FA)
    assert q.f1 == pytest.approx(2 * 0.5 * 0.2 / 0.7)


def test_cell_recall_by_kind_of_teacher_mark() -> None:
    """Сколько клеток с этим видом ошибки учителя отметила и модель."""
    by_kind = metrics.cell_metrics(_labels()).recall_by_kind
    assert by_kind["letter"] == pytest.approx(1.0)
    assert by_kind["missing"] == pytest.approx(0.0)
    assert by_kind["vowel"] == pytest.approx(0.0)
    assert by_kind["tafkhim"] == pytest.approx(0.0)
    assert set(by_kind) == {"letter", "missing", "vowel", "tafkhim"}  # только отмеченные учителем


def test_teachers_agreement_by_cells_and_by_kind() -> None:
    """3/T1 и 3/T2 согласны, где ошибка, но расходятся в виде (таджвид в клетке 5).

    α по клеткам: единица — клетка, значение «ошибка / нет». α по виду: единица — пара
    (клетка, вид) для каждого из 13 видов (FR-63: добавлены «shadda» и «sukun»), значение
    «отмечен / нет»: 12 × 13 = 156 единиц, одно расхождение. Обе — ``krippendorff_alpha_nominal``
    по попыткам с двумя и более разметчиками.
    """
    c = metrics.cell_metrics(_labels())
    assert c.alpha_cells == pytest.approx(1.0)
    assert c.alpha_kinds == pytest.approx(0.7973941368078176)
    assert (c.alpha_units, c.alpha_kind_units) == (12, 156)


def test_cell_confidence_intervals_bootstrap_by_learner() -> None:
    """95 % ДИ — тот же ``cluster_bootstrap`` по ученикам, что у фонемных цифр."""
    c = metrics.cell_metrics(_labels())
    for name in ("precision", "recall", "F1"):
        interval = c.ci[name]
        assert interval is not None, name
        low, high = interval
        assert 0.0 <= low <= high <= 1.0, name
    one = metrics.cell_metrics([lb for lb in _labels() if lb.learner == A])
    assert one.ci["recall"] is None  # один ученик — интервала нет


def test_cell_metrics_without_labels_are_undefined() -> None:
    c = metrics.cell_metrics([])
    assert c.labels == 0
    assert (c.quality.precision, c.quality.recall, c.quality.f1) == (None, None, None)
    assert c.alpha_cells is None
