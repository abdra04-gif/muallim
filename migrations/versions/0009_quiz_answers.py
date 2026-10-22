"""Ответы «🧠 Закрепления»: таблица quiz_answers (FR-53, ADR-0066).

Одна строка — один показанный вопрос: пишется при показе, ответ дописывается в неё же один раз.
Удаляется вместе с учеником (ON DELETE CASCADE). Одно место раунда — один вопрос (UNIQUE).
Права ролям бота и просмотра выдаются сами (ALTER DEFAULT PRIVILEGES в scripts/db/roles.sql), make db-roles повторять не нужно.
Описание полей: docs/data/data-dictionary.md. Перед миграцией make migrate делает копию БД.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-23 06:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "quiz_answers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("learner_id", sa.Uuid(), nullable=False),
        sa.Column("round_no", sa.Integer(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("step", sa.SmallInteger(), nullable=False),
        sa.Column("letter_id", sa.String(32), nullable=False),
        sa.Column("item_id", sa.String(32), nullable=False),
        sa.Column("vowel", sa.SmallInteger(), nullable=False),
        sa.Column("options", sa.JSON(), nullable=False),
        sa.Column("answer", sa.SmallInteger(), nullable=False),
        sa.Column("picked", sa.SmallInteger(), nullable=True),
        sa.Column("correct", sa.Boolean(), nullable=True),
        sa.Column("attempt_id", sa.Uuid(), nullable=True),
        sa.Column("reason", sa.String(16), nullable=False, server_default=""),
        sa.Column("shown_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("curriculum_version", sa.String(32), nullable=False),
        sa.Column("rule", sa.String(8), nullable=False),
        sa.CheckConstraint("step BETWEEN 1 AND 3", name=op.f("ck_quiz_answers_step_range")),
        sa.CheckConstraint("vowel BETWEEN 0 AND 2", name=op.f("ck_quiz_answers_vowel_range")),
        sa.CheckConstraint("position >= 1", name=op.f("ck_quiz_answers_position_positive")),
        sa.CheckConstraint(
            "picked IS NULL OR picked BETWEEN 0 AND 3",
            name=op.f("ck_quiz_answers_picked_range"),
        ),
        sa.ForeignKeyConstraint(
            ["learner_id"],
            ["learners.id"],
            name=op.f("fk_quiz_answers_learner_id_learners"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["attempts.id"],
            name=op.f("fk_quiz_answers_attempt_id_attempts"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_quiz_answers")),
        # одно место раунда — один вопрос (двойное нажатие); он же индекс по ученику
        sa.UniqueConstraint(
            "learner_id", "round_no", "position", name=op.f("uq_quiz_answers_learner_id")
        ),
    )


def downgrade() -> None:
    op.drop_table("quiz_answers")
