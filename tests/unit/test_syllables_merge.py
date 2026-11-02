"""FR-61 (ADR-0077 п. 1, 4): пересборка ayat.yaml не теряет решения человека о статусе.

Слияние — отдельный модуль без ``quran_transcript`` (scripts/syllables/merge.py, stdlib), как
``merge_manifest`` в scripts/audio/cuts_manifest.py. ``merge_status(old_rows, new_rows)``: порядок и
состав — по новому разбору; тот же текст и те же ``words`` — статус человека (``ok``/``bad``)
сохраняется; ``words`` изменились или строки раньше не было — ``unchecked``; строк, которых нет в
новом разборе, больше нет. Тексты — из curriculum/course.ru.yaml.
"""

import copy
import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from muallim.domain.curriculum import Curriculum

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def merge() -> Any:
    path = ROOT / "scripts" / "syllables" / "merge.py"
    assert path.is_file(), "нет scripts/syllables/merge.py с merge_status"
    spec = importlib.util.spec_from_file_location("syllables_merge", path)
    assert spec is not None and spec.loader is not None
    module: ModuleType = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.merge_status


def _row(text: str, status: str, sound: str = "звук") -> dict[str, Any]:
    return {"text": text, "status": status, "words": [[[w, sound]] for w in text.split(" ")]}


@pytest.fixture
def ayat(curriculum: Curriculum) -> list[str]:
    return [curriculum.item(i).text for i in ("L097-02", "L097-03", "L097-04", "L098-02")]


def _status(rows: list[dict[str, Any]]) -> dict[str, str]:
    return {r["text"]: r["status"] for r in rows}


@pytest.mark.parametrize("status", ["ok", "bad"])
def test_same_split_keeps_human_status(merge: Any, ayat: list[str], status: str) -> None:
    old = [_row(ayat[0], status)]
    merged = merge(old, [_row(ayat[0], "unchecked")])
    assert _status(merged) == {ayat[0]: status}
    assert merged[0]["words"] == old[0]["words"]


def test_changed_words_become_unchecked(merge: Any, ayat: list[str]) -> None:
    new = _row(ayat[1], "unchecked", sound="другой звук")
    merged = merge([_row(ayat[1], "ok")], [new])
    assert _status(merged) == {ayat[1]: "unchecked"}
    assert merged[0]["words"] == new["words"], "в файл идёт новый разбор"


def test_new_row_is_unchecked(merge: Any, ayat: list[str]) -> None:
    merged = merge([_row(ayat[0], "ok")], [_row(ayat[0], "unchecked"), _row(ayat[2], "unchecked")])
    assert _status(merged) == {ayat[0]: "ok", ayat[2]: "unchecked"}


def test_rows_missing_from_new_split_are_dropped(merge: Any, ayat: list[str]) -> None:
    old = [_row(ayat[0], "ok"), _row(ayat[3], "bad")]
    merged = merge(old, [_row(ayat[0], "unchecked")])
    assert [r["text"] for r in merged] == [ayat[0]]


def test_order_follows_new_split_and_inputs_are_not_changed(merge: Any, ayat: list[str]) -> None:
    old = [_row(ayat[2], "ok"), _row(ayat[0], "bad")]
    new = [_row(t, "unchecked") for t in ayat]
    old_copy, new_copy = copy.deepcopy(old), copy.deepcopy(new)
    merged = merge(old, new)
    assert [r["text"] for r in merged] == ayat
    assert [r["status"] for r in merged] == ["bad", "unchecked", "ok", "unchecked"]
    assert (old, new) == (old_copy, new_copy)
