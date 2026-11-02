"""Слияние статусов ayat.yaml при пересборке (FR-61, ADR-0077) — без quran_transcript и torch.

Пересборка ``build.py`` не должна терять решения человека: тот же текст и те же ``words`` —
статус человека (``ok``/``bad``) сохраняется; разбор изменился или строка новая — ``unchecked``;
строк, которых нет в новом разборе, больше нет. Порядок — по новому разбору.
"""

from collections.abc import Iterable
from typing import Any

Row = dict[str, Any]
UNCHECKED = "unchecked"


def merge_status(old_rows: Iterable[Row], new_rows: Iterable[Row]) -> list[Row]:
    """Новые строки в их порядке со статусом человека, если разбор не изменился."""
    old = {r["text"]: r for r in old_rows}
    merged = []
    for row in new_rows:
        before = old.get(row["text"])
        same = before is not None and before.get("words") == row["words"]
        status = before.get("status", UNCHECKED) if before is not None and same else UNCHECKED
        merged.append({**row, "status": status})
    return merged
