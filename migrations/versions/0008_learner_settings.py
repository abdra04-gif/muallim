"""Настройки ученика и состояние его экрана: таблица learner_settings (FR-51, TD-FN-90, ADR-0061).

Строка на ученика (learner_id — PK и FK с ON DELETE CASCADE), нет строки — умолчания, как бот
работал до настроек. Telegram ID в таблице нет: роль просмотра видит её целиком, make db-roles
повторять не нужно. Даты — местные (смещение utc_offset_min, до ответа ученика — UTC+3).
Описание полей: docs/data/data-dictionary.md. Перед миграцией make migrate делает копию БД.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-21 06:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Замороженные значения (как в domain/settings.py на момент миграции).
HOW_TO_READ = ("spoiler", "shown", "hidden")
DEFAULT_UTC_OFFSET_MIN = 180


def _one_of(column: str, values: Sequence[str]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def upgrade() -> None:
    op.create_table(
        "learner_settings",
        sa.Column("learner_id", sa.Uuid(), nullable=False),
        sa.Column("how_to_read", sa.String(16), nullable=False, server_default="spoiler"),
        sa.Column("auto_reference", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("daily_opening", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("large_font", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("research_block", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("reminder_minute", sa.SmallInteger(), nullable=True),
        sa.Column(
            "utc_offset_min",
            sa.SmallInteger(),
            nullable=False,
            server_default=str(DEFAULT_UTC_OFFSET_MIN),
        ),
        sa.Column("screen_item_id", sa.String(32), nullable=True),
        sa.Column("screen_opening", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("opening_resume_item", sa.String(32), nullable=True),
        sa.Column("opening_day", sa.Date(), nullable=True),
        sa.Column("opening_skipped_on", sa.Date(), nullable=True),
        sa.Column("reminder_sent_on", sa.Date(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            _one_of("how_to_read", HOW_TO_READ),
            name=op.f("ck_learner_settings_how_to_read_values"),
        ),
        sa.CheckConstraint(
            "reminder_minute IS NULL OR reminder_minute BETWEEN 0 AND 1439",
            name=op.f("ck_learner_settings_reminder_minute_range"),
        ),
        sa.CheckConstraint(
            "utc_offset_min BETWEEN -720 AND 840",
            name=op.f("ck_learner_settings_utc_offset_range"),
        ),
        sa.ForeignKeyConstraint(
            ["learner_id"],
            ["learners.id"],
            name=op.f("fk_learner_settings_learner_id_learners"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("learner_id", name=op.f("pk_learner_settings")),
    )


def downgrade() -> None:
    op.drop_table("learner_settings")
