"""Миграции Alembic совпадают со схемой в коде и откатываются (NFR-MNT-03)."""

import importlib.util
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine

from muallim.infrastructure.db.tables import metadata
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


def test_latest_migration_creates_views_exactly_as_in_code() -> None:
    """Миграция хранит замороженную копию SQL представлений — она должна совпадать с views.py."""
    spec = importlib.util.spec_from_file_location(
        "m0003", ROOT / "migrations" / "versions" / "0003_curriculum_items_and_views.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.VIEWS == VIEWS
