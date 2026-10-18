"""Разметка: «сам исправился» — отдельная категория чтения (руководство 2.1, ADR-0043).

Описание полей: docs/data/data-dictionary.md.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-18 12:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Простой ADD COLUMN: таблица не пересоздаётся, представления (v_*) не ломаются.
    # Прежние метки остаются NULL: тогда отметки не было, «нет» о них сказать нельзя.
    op.add_column("annotations", sa.Column("self_corrected", sa.Boolean(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.drop_column("annotations", "self_corrected")
        return
    # SQLite пересоздаёт таблицу и проверяет представления — снять их на время и вернуть как были.
    views = bind.execute(sa.text("SELECT name, sql FROM sqlite_master WHERE type = 'view'")).all()
    for name, _ in views:
        op.execute(f"DROP VIEW {name}")
    with op.batch_alter_table("annotations") as batch:
        batch.drop_column("self_corrected")
    for _, sql in views:
        op.execute(sql)
