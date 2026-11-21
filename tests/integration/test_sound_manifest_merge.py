"""Пересборка манифеста готовых записей не теряет ручные и отклонённые строки (FR-49).

Готовые записи лежат в ``curriculum/audio/library`` и описаны в ``sounds.yaml``. Строку,
добавленную вручную (``manual: true``), пересборка ``scripts/audio/library_sounds.py`` не теряет.
Проверки записи истиазы убраны вместе с карточкой (автор 2026-11-21: истиазы в книге нет).
"""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
AUDIO = ROOT / "curriculum" / "audio"
LIBRARY = AUDIO / "library"


# ---------- пересборка манифеста не теряет ручные строки ----------
def _manifest_module() -> ModuleType:
    """Слияние манифеста — отдельный модуль без модели и torch (scripts/audio/cuts_manifest.py)."""
    path = ROOT / "scripts" / "audio" / "cuts_manifest.py"
    assert path.is_file(), "нет scripts/audio/cuts_manifest.py с merge_manifest"
    spec = importlib.util.spec_from_file_location("cuts_manifest", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MANUAL = {"text": "истиаза", "file": "manual.ogg", "status": "ok", "manual": True, "parts": []}
BAD = {"text": "плохая", "file": "bad.ogg", "status": "bad", "parts": []}
OLD_AUTO = {"text": "старая", "file": "old.ogg", "status": "ok", "parts": []}
NEW = {"text": "новая", "file": "new.ogg", "status": "unchecked", "parts": []}


def test_merge_keeps_manual_rows_not_found_again() -> None:
    merged = _manifest_module().merge_manifest([MANUAL, OLD_AUTO], [NEW])
    assert MANUAL in merged and NEW in merged
    assert OLD_AUTO not in merged  # обычная строка, которой нет в новой сборке, уходит


def test_merge_does_not_overwrite_manual_row() -> None:
    rebuilt = {**MANUAL, "file": "auto.ogg", "status": "unchecked", "manual": False}
    merged = _manifest_module().merge_manifest([MANUAL], [rebuilt])
    assert [r for r in merged if r["text"] == MANUAL["text"]] == [MANUAL]


def test_merge_keeps_rejected_rows() -> None:
    """Отклонённое человеком (status: bad) не теряем — как и раньше."""
    merged = _manifest_module().merge_manifest([BAD], [NEW])
    assert BAD in merged and NEW in merged
