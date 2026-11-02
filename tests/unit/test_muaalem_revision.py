"""Версия модели Muaalem видна в каждой попытке; смена версии — предупреждение в лог (TD-FN-121).

Модель в тестах не нужна: подделка повторяет то, что отдаёт transformers —
``Muaalem().model.config._commit_hash``.
"""

import logging
from types import SimpleNamespace

import pytest
from sqlalchemy import String

from muallim.infrastructure.asr import muaalem
from muallim.infrastructure.asr.muaalem import (
    EXPECTED_MODEL_REVISION,
    MuaalemRecognizer,
    _loaded_revision,
)
from muallim.infrastructure.db.tables import attempts


def fake_model(commit_hash: str | None) -> SimpleNamespace:
    return SimpleNamespace(model=SimpleNamespace(config=SimpleNamespace(_commit_hash=commit_hash)))


def test_expected_revision_is_logged_quietly(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        assert _loaded_revision(fake_model(EXPECTED_MODEL_REVISION)) == EXPECTED_MODEL_REVISION
    assert not caplog.records


def test_other_revision_warns(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        assert _loaded_revision(fake_model("f" * 40)) == "f" * 40
    assert "f" * 40 in caplog.text
    assert EXPECTED_MODEL_REVISION in caplog.text


def test_unknown_revision_warns(caplog: pytest.LogCaptureFixture) -> None:
    """Модель из локальной папки: transformers не знает коммит."""
    with caplog.at_level(logging.WARNING):
        assert _loaded_revision(fake_model(None)) == "unknown"
    assert caplog.records


def test_model_version_includes_revision(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(muaalem, "_library_version", lambda: "0.2.2")
    recognizer = MuaalemRecognizer()
    recognizer._revision = "0123456789abcdef"
    version = recognizer.model_version
    assert version.startswith("quran-muaalem==0.2.2@0123456;")
    assert "rewaya=hafs" in version


def test_model_version_fits_db_column(monkeypatch: pytest.MonkeyPatch) -> None:
    """Длиннее колонки attempts.model_version — попытка не сохранится в PostgreSQL."""
    monkeypatch.setattr(muaalem, "_library_version", lambda: "10.20.300")
    recognizer = MuaalemRecognizer()
    recognizer._revision = EXPECTED_MODEL_REVISION
    column = attempts.c.model_version.type
    assert isinstance(column, String) and column.length is not None
    assert len(recognizer.model_version) <= column.length


def test_model_version_before_load_has_no_revision(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(muaalem, "_library_version", lambda: "0.2.2")
    assert MuaalemRecognizer().model_version.startswith("quran-muaalem==0.2.2;rewaya=")
