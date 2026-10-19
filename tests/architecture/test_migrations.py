"""Миграции Alembic совпадают со схемой в коде и откатываются (NFR-MNT-03)."""

import importlib.util
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine

from muallim.domain.annotation import AnnotationSource, AnnotationStatus
from muallim.domain.policy import Verdict
from muallim.domain.report import ReportReason
from muallim.infrastructure.db.tables import LEGACY_LABELS, metadata
from muallim.infrastructure.db.views import VIEWS

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.architecture


def _config(url: str) -> Config:
    cfg = Config(ROOT / "alembic.ini")
    cfg.attributes["url"] = url
    cfg.attributes["configure_logger"] = False
    return cfg


def test_migrations_match_metadata_and_downgrade(tmp_path: Path) -> None:
    db = tmp_path / "m.sqlite3"
    cfg = _config(f"sqlite+aiosqlite:///{db}")
    command.upgrade(cfg, "head")  # синхронный тест: env.py сам запускает asyncio.run

    with create_engine(f"sqlite:///{db}").connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), metadata)
        views = conn.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='view'").all()
    assert diff == [], f"Схема в коде и миграции разошлись — нужна новая миграция: {diff}"
    assert sorted(v for (v,) in views) == sorted(VIEWS), "представления не совпадают с views.py"

    command.downgrade(cfg, "base")
    with create_engine(f"sqlite:///{db}").connect() as conn:
        tables = conn.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
        ).all()
    assert [t for (t,) in tables if t != "alembic_version"] == []


def _migration(prefix: str) -> Any:
    (path,) = (ROOT / "migrations" / "versions").glob(f"{prefix}_*.py")
    spec = importlib.util.spec_from_file_location(f"m{prefix}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_latest_migration_creates_views_exactly_as_in_code() -> None:
    """Последняя миграция с представлениями хранит их копию — она совпадает с views.py."""
    with_views = sorted(
        p.name[:4] for p in (ROOT / "migrations" / "versions").glob("0*.py")
        if "VIEWS" in p.read_text(encoding="utf-8")
    )  # fmt: skip
    assert _migration(with_views[-1]).VIEWS == VIEWS


def test_check_constraints_in_migration_match_code() -> None:
    """Значения в CHECK миграции 0007 — те же, что в коде: новое значение — только с миграцией."""
    m = _migration("0007")
    assert set(m.VERDICTS) == {str(v) for v in Verdict}
    assert set(m.REPORT_REASONS) == {str(r) for r in ReportReason}
    assert set(m.LABELS) == {str(s) for s in AnnotationStatus} | set(LEGACY_LABELS)
    assert set(m.SOURCES) == {str(s) for s in AnnotationSource}


def test_migration_0007_keeps_first_of_duplicate_reports(tmp_path: Path) -> None:
    """Двойные жалобы (двойное нажатие до 0007) сливаются в первую — иначе UNIQUE не встанет."""
    db = tmp_path / "d.sqlite3"
    cfg = _config(f"sqlite+aiosqlite:///{db}")
    command.upgrade(cfg, "0006")
    with create_engine(f"sqlite:///{db}").begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO learners (id, telegram_user_id, pseudonym, language, research_consent,"
            " blocked_bot, created_at) VALUES ('00000000000000000000000000000001', 5, 'L-1', 'ru',"
            " 0, 0, '2026-10-20 12:00:00')"
        )
        conn.exec_driver_sql(
            "INSERT INTO attempts (id, learner_id, item_id, curriculum_version, model_version,"
            " reference_phonemes, heard_phonemes, score, verdict, processing_ms, created_at) VALUES"
            " ('00000000000000000000000000000002', '00000000000000000000000000000001', 'L01-14',"
            " 'v1', 'm', 'a', 'a', 100, 'excellent', 1, '2026-10-20 12:00:00')"
        )
        for n, reason in enumerate(["read_correctly", "other"], start=1):
            conn.exec_driver_sql(
                "INSERT INTO learner_reports (id, attempt_id, learner_id, reason, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (n, "0" * 31 + "2", "0" * 31 + "1", reason, f"2026-10-20 12:0{n}:00"),
            )
    command.upgrade(cfg, "head")
    with create_engine(f"sqlite:///{db}").connect() as conn:
        rows = conn.exec_driver_sql("SELECT reason FROM learner_reports").all()
    assert rows == [("read_correctly",)]
