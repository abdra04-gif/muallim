"""Анкета ученика: 18+, родной язык, опыт чтения (FR-44, ADR-0038).

Описание полей: docs/data/data-dictionary.md.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-18 01:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "learner_profiles",
        sa.Column("learner_id", sa.Uuid(), nullable=False),
        sa.Column("adult", sa.Boolean(), nullable=False),
        sa.Column("native_language", sa.String(length=8), nullable=True),
        sa.Column("arabic_reading", sa.String(length=16), nullable=True),
        sa.Column("questionnaire_version", sa.String(length=16), nullable=False),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["learner_id"],
            ["learners.id"],
            name=op.f("fk_learner_profiles_learner_id_learners"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("learner_id", name=op.f("pk_learner_profiles")),
    )


def downgrade() -> None:
    op.drop_table("learner_profiles")
