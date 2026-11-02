"""Еженедельная сверка версии модели на Hugging Face (TD-FN-121, workflow model-revision).

Сеть не нужна: история коммитов — подделка в формате API Hugging Face.
"""

import importlib.util
import urllib.error
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from muallim.infrastructure.asr.muaalem import EXPECTED_MODEL_REVISION

ROOT = Path(__file__).resolve().parents[2]


def load() -> ModuleType:
    path = ROOT / "scripts" / "model" / "check_revision.py"
    spec = importlib.util.spec_from_file_location("check_revision", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def commit(sha: str, date: str, title: str) -> dict[str, str]:
    return {"id": sha, "date": date, "title": title}


def test_reads_expected_revision_from_bot_code() -> None:
    """Одно место правды — константа в адаптере, скрипт её не дублирует."""
    assert load().expected_revision() == EXPECTED_MODEL_REVISION


def test_same_revision_is_ok() -> None:
    history = [commit("a" * 40, "2025-09-04T17:02:48.000Z", "add: docs")]
    ok, text = load().compare(history, "a" * 40)
    assert ok
    assert "2025-09-04" in text


def test_new_commits_are_listed_newest_first() -> None:
    old = "a" * 40
    history = [
        commit("c" * 40, "2026-11-02T10:00:00.000Z", "Upload model v3.3"),
        commit("b" * 40, "2026-11-01T10:00:00.000Z", "fix tokenizer"),
        commit(old, "2025-09-04T17:02:48.000Z", "add: docs"),
    ]
    ok, text = load().compare(history, old)
    assert not ok
    assert text.index("Upload model v3.3") < text.index("fix tokenizer")
    assert "add: docs" not in text  # то, что уже было, не повторяем
    assert "2026-11-02" in text


def test_expected_revision_missing_from_history() -> None:
    """Ожидаемой ревизии нет в истории — тоже тревога, со всеми коммитами."""
    history = [commit("c" * 40, "2026-11-02T10:00:00.000Z", "rewrite")]
    ok, text = load().compare(history, "a" * 40)
    assert ok is False
    assert "rewrite" in text


def test_network_error_is_not_an_update(monkeypatch: pytest.MonkeyPatch, capsys: Any) -> None:
    """Hugging Face лежит — не тревога «модель обновилась»: свой код выхода и понятная строка."""
    module = load()

    def down(*_: object, **__: object) -> None:
        raise urllib.error.URLError("timed out")

    monkeypatch.setattr(module.urllib.request, "urlopen", down)
    assert module.main() == 2
    out = capsys.readouterr().out
    assert "не состоялась" in out
    assert "обновилась" not in out


def test_empty_history_is_not_an_update() -> None:
    ok, text = load().compare([], "a" * 40)
    assert ok is None
    assert "не состоялась" in text


def test_missing_revision_does_not_claim_rewrite() -> None:
    """API отдаёт историю страницами: ревизии может просто не быть на первой."""
    history = [commit("c" * 40, "2026-11-02T10:00:00.000Z", "new")]
    _, text = load().compare(history, "a" * 40)
    assert "первой странице" in text
