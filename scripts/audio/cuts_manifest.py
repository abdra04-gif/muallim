"""Слияние манифеста нарезок Хусари (cuts.yaml) при пересборке — без модели и torch.

Пересборка ``husary_cuts.py`` не должна терять решения человека:
- строка, собранная вручную (``manual: true``), остаётся как есть и не перезаписывается;
- отклонённая (``status: bad``) остаётся, даже если заново не нашлась;
- обычная строка, которой нет в новой сборке, уходит.
"""

from collections.abc import Iterable
from typing import Any

Row = dict[str, Any]


def is_manual(row: Row) -> bool:
    return row.get("manual") is True


def merge_manifest(old_rows: Iterable[Row], new_rows: Iterable[Row]) -> list[Row]:
    """Новые строки в их порядке; ручные — вместо пересобранных; затем ручные и bad из старых."""
    old = list(old_rows)
    manual = {r["text"]: r for r in old if is_manual(r)}
    merged = [manual.get(row["text"], row) for row in new_rows]
    seen = {r["text"] for r in merged}
    for row in old:
        if row["text"] not in seen and (is_manual(row) or row.get("status") == "bad"):
            merged.append(row)
            seen.add(row["text"])
    return merged
