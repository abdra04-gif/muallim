"""Разметка в Telegram (FR-17): разметчики, приглашения, источник метки и время ответа.

Описание полей: docs/data/data-dictionary.md.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-18 09:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Простой ADD COLUMN: таблица не пересоздаётся, представления (v_*) не ломаются.
    op.add_column("annotations", sa.Column("source", sa.String(length=16), nullable=True))
    op.add_column("annotations", sa.Column("seconds_spent", sa.Integer(), nullable=True))
    op.create_table(
        "annotators",
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("code", name=op.f("pk_annotators")),
        sa.UniqueConstraint("telegram_user_id", name=op.f("uq_annotators_telegram_user_id")),
    )
    op.create_table(
        "annotator_invites",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code_digest", sa.String(length=64), nullable=False),
        sa.Column("annotator", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_annotator_invites")),
        sa.UniqueConstraint("code_digest", name=op.f("uq_annotator_invites_code_digest")),
    )


def downgrade() -> None:
    op.drop_table("annotator_invites")
    op.drop_table("annotators")
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.drop_column("annotations", "seconds_spent")
        op.drop_column("annotations", "source")
        return
    # SQLite пересоздаёт таблицу и проверяет представления — снять их на время и вернуть как были.
    views = bind.execute(sa.text("SELECT name, sql FROM sqlite_master WHERE type = 'view'")).all()
    for name, _ in views:
        op.execute(f"DROP VIEW {name}")
    with op.batch_alter_table("annotations") as batch:
        batch.drop_column("seconds_spent")
        batch.drop_column("source")
    for _, sql in views:
        op.execute(sql)
