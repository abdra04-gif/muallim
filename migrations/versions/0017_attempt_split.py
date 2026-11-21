"""Часть попытки и чтения суры: учёба или тест (TD-FN-174, ADR-0090, предрегистрация 0.7).

Столбец ``split`` (``train`` / ``test``) в ``attempts`` и ``sura_readings``, по умолчанию ``train``:
все старые строки — учёба, пока их не разложит по соли отдельная команда (шаг 3; сами голоса в
закрытую часть тоже переносит она). Других значений БД не принимает. Откат: столбцы удаляются —
часть восстановима по соли. Описание полей: docs/data/data-dictionary.md. Перед миграцией
make migrate делает копию БД.

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-21 20:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Замороженные значения (тест сверяет с перечислением Part в коде).
PARTS = ("train", "test")
TABLES = ("attempts", "sura_readings")


def _check(table: str) -> str:
    return f"ck_{table}_split_values"


def _views_off() -> list[tuple[str, str]]:
    """SQLite пересоздаёт таблицу: представления (v_*) снимаем и ставим обратно тем же текстом."""
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        return []
    saved = bind.exec_driver_sql(
        "SELECT name, sql FROM sqlite_master WHERE type = 'view' ORDER BY name"
    ).all()
    for name, _ in saved:
        op.execute(f'DROP VIEW "{name}"')
    return [(str(name), str(sql)) for name, sql in saved]


def upgrade() -> None:
    saved = _views_off()
    values = ", ".join(repr(v) for v in PARTS)
    for table in TABLES:
        with op.batch_alter_table(table) as batch:
            batch.add_column(
                sa.Column("split", sa.String(8), nullable=False, server_default="train")
            )
            batch.create_check_constraint(op.f(_check(table)), f"split IN ({values})")
    for _, sql in saved:
        op.execute(sql)


# Таблицы с фильтром строк для входа агента (scripts/db/roles.sql): его политики зависят от split.
RLS_TABLES = (
    "attempts", "sura_readings", "detected_errors", "annotations", "learner_reports",
    "quiz_answers", "annotation_marks", "sura_reading_ayahs", "sura_reading_chunks",
    "sura_reading_events",
)  # fmt: skip


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        # без split фильтр «только учёба» невозможен: политики и сам фильтр снимаем (после
        # повторного upgrade их вернёт make db-roles)
        for table in RLS_TABLES:
            op.execute(f'DROP POLICY IF EXISTS agent_train ON "{table}"')
            op.execute(f'DROP POLICY IF EXISTS everyone ON "{table}"')
            op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')
    saved = _views_off()
    for table in TABLES:
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(op.f(_check(table)), type_="check")
            batch.drop_column("split")
    for _, sql in saved:
        op.execute(sql)
