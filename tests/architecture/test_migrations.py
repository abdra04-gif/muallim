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


SETTINGS_COLUMNS = {
    "learner_id", "how_to_read", "auto_reference", "daily_opening", "large_font",
    "research_block", "reminder_minute", "utc_offset_min",
    "screen_item_id", "screen_opening", "opening_resume_item", "opening_day",
    "opening_skipped_on", "reminder_sent_on", "updated_at",
}  # fmt: skip


def test_migration_0008_adds_learner_settings_one_to_one(tmp_path: Path) -> None:
    """ADR-0061: настройки и экран — строка на ученика, без Telegram ID, удаляется с ним."""
    from sqlalchemy import inspect  # noqa: PLC0415

    db = tmp_path / "s.sqlite3"
    cfg = _config(f"sqlite+aiosqlite:///{db}")
    command.upgrade(cfg, "0008")
    with create_engine(f"sqlite:///{db}").connect() as conn:
        info = inspect(conn)
        columns = {c["name"]: c for c in info.get_columns("learner_settings")}
        (fk,) = info.get_foreign_keys("learner_settings")
        pk = info.get_pk_constraint("learner_settings")["constrained_columns"]
    assert set(columns) == SETTINGS_COLUMNS
    assert not [c for c in columns if "telegram" in c], "роль просмотра видит таблицу целиком"
    assert pk == ["learner_id"]
    assert (fk["referred_table"], fk["referred_columns"]) == ("learners", ["id"])
    assert fk["options"].get("ondelete") == "CASCADE"
    nullable = {name for name, c in columns.items() if c["nullable"]}
    assert nullable == {
        "reminder_minute", "screen_item_id", "opening_resume_item", "opening_day",
        "opening_skipped_on", "reminder_sent_on",
    }  # fmt: skip

    command.downgrade(cfg, "0007")
    with create_engine(f"sqlite:///{db}").connect() as conn:
        assert not inspect(conn).has_table("learner_settings")


# ---------- FR-62 (ADR-0079 п. 3): клетки меток учителя ----------
MARK_COLUMNS = {
    "id", "annotation_id", "cell", "layout", "char_start", "char_end", "piece", "kind",
    "heard_letter", "bot_flagged",
}  # fmt: skip
_INSERT_MARK = (
    "INSERT INTO annotation_marks (annotation_id, cell, layout, char_start, char_end, piece,"
    " kind, heard_letter, bot_flagged) VALUES (1, ?, ?, 0, 3, 'x', ?, NULL, 0)"
)


def _seed_annotation(conn: Any) -> None:
    """Ученик, попытка и одна метка — как до миграции 0011 (без ``entry``)."""
    conn.exec_driver_sql(
        "INSERT INTO learners (id, telegram_user_id, pseudonym, language, research_consent,"
        " blocked_bot, created_at) VALUES ('00000000000000000000000000000001', 5, 'L-1', 'ru',"
        " 1, 0, '2026-10-31 12:00:00')"
    )
    conn.exec_driver_sql(
        "INSERT INTO attempts (id, learner_id, item_id, curriculum_version, model_version,"
        " reference_phonemes, heard_phonemes, score, verdict, processing_ms, created_at) VALUES"
        " ('00000000000000000000000000000002', '00000000000000000000000000000001', 'L097-03',"
        " 'v1', 'm', 'a', 'a', 100, 'excellent', 1, '2026-10-31 12:00:00')"
    )
    conn.exec_driver_sql(
        "INSERT INTO annotations (id, attempt_id, annotator, label, corrected_phonemes, comment,"
        " guide_version, created_at, source) VALUES (1, '00000000000000000000000000000002', 'A1',"
        " 'agree', 'a', '', '2.1', '2026-10-31 12:00:00', 'telegram')"
    )


def test_migration_0011_adds_annotation_marks_and_entry(tmp_path: Path) -> None:
    """Клетки метки — отдельная таблица со ссылкой на метку; прежние метки не трогаются."""
    from sqlalchemy import inspect  # noqa: PLC0415

    db = tmp_path / "marks.sqlite3"
    cfg = _config(f"sqlite+aiosqlite:///{db}")
    command.upgrade(cfg, "0010")
    with create_engine(f"sqlite:///{db}").begin() as conn:
        _seed_annotation(conn)
    command.upgrade(cfg, "0011")
    with create_engine(f"sqlite:///{db}").connect() as conn:
        info = inspect(conn)
        columns = {c["name"]: c for c in info.get_columns("annotation_marks")}
        (fk,) = info.get_foreign_keys("annotation_marks")
        uniques = [u["column_names"] for u in info.get_unique_constraints("annotation_marks")]
        entry = {c["name"]: c for c in info.get_columns("annotations")}["entry"]
        old = conn.exec_driver_sql("SELECT label, entry FROM annotations").all()
    assert set(columns) == MARK_COLUMNS
    assert not [c for c in columns if "telegram" in c]
    assert (fk["referred_table"], fk["referred_columns"]) == ("annotations", ["id"])
    assert fk["constrained_columns"] == ["annotation_id"]
    assert fk["options"].get("ondelete") == "CASCADE"
    assert ["annotation_id", "cell", "kind"] in uniques
    assert {name for name, c in columns.items() if c["nullable"]} == {"heard_letter"}
    assert entry["nullable"] is True
    assert old == [("agree", None)]  # entry у прежних меток — NULL

    command.downgrade(cfg, "0010")
    with create_engine(f"sqlite:///{db}").connect() as conn:
        info = inspect(conn)
        assert not info.has_table("annotation_marks")
        assert "entry" not in {c["name"] for c in info.get_columns("annotations")}
        assert conn.exec_driver_sql("SELECT count(*) FROM annotations").scalar() == 1


@pytest.mark.parametrize(
    ("sql", "params"),
    [
        (_INSERT_MARK, (20, "syllables", "unsure")),  # «не уверен» отклонён автором
        (_INSERT_MARK, (20, "words", "vowel")),  # раскладки: syllables | letters
        (_INSERT_MARK, (30, "syllables", "letter")),  # UNIQUE (annotation_id, cell, kind)
        ("UPDATE annotations SET entry = 'buttons'", ()),  # entry: cells | phonemes | NULL
    ],
)
def test_migration_0011_rejects_values_outside_the_code(
    tmp_path: Path, sql: str, params: tuple[object, ...]
) -> None:
    """CHECK — те же 11 видов (``MarkKind``), две раскладки и два способа ввода, что в коде."""
    from sqlalchemy.exc import IntegrityError  # noqa: PLC0415

    import muallim.domain.annotation as ann  # noqa: PLC0415

    db = tmp_path / "check.sqlite3"
    cfg = _config(f"sqlite+aiosqlite:///{db}")
    command.upgrade(cfg, "0011")
    with create_engine(f"sqlite:///{db}").begin() as conn:
        _seed_annotation(conn)
        for cell, kind in enumerate(ann.MarkKind):  # каждый вид из кода проходит CHECK
            conn.exec_driver_sql(_INSERT_MARK, (cell, "syllables", str(kind)))
        conn.exec_driver_sql(_INSERT_MARK, (30, "letters", "letter"))
        for entry in ("cells", "phonemes"):
            conn.exec_driver_sql("UPDATE annotations SET entry = ?", (entry,))
    with pytest.raises(IntegrityError), create_engine(f"sqlite:///{db}").begin() as conn:
        conn.exec_driver_sql(sql, params)


def test_annotation_marks_go_away_with_their_annotation(tmp_path: Path) -> None:
    """ON DELETE CASCADE: метку удалили (и при /delete ученика) — её клеток не осталось."""
    from sqlalchemy import event  # noqa: PLC0415

    db = tmp_path / "cascade.sqlite3"
    command.upgrade(_config(f"sqlite+aiosqlite:///{db}"), "head")
    engine = create_engine(f"sqlite:///{db}")
    event.listen(engine, "connect", lambda dbapi, _: dbapi.execute("PRAGMA foreign_keys=ON"))
    with engine.begin() as conn:
        _seed_annotation(conn)
        conn.exec_driver_sql(_INSERT_MARK, (0, "syllables", "letter"))
        conn.exec_driver_sql(_INSERT_MARK, (1, "syllables", "missing"))
        conn.exec_driver_sql("DELETE FROM annotations WHERE id = 1")
        assert conn.exec_driver_sql("SELECT count(*) FROM annotation_marks").scalar() == 0
