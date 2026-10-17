"""След решения в попытке, жалобы учеников, язык объяснений.

ADR-0017 (язык), ADR-0019 (след решения), ADR-0020 (жалобы). Описание полей: docs/data/data-dictionary.md.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-16 20:39:26.768887+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "learner_reports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("learner_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["attempts.id"],
            name=op.f("fk_learner_reports_attempt_id_attempts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["learner_id"],
            ["learners.id"],
            name=op.f("fk_learner_reports_learner_id_learners"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_learner_reports")),
    )
    with op.batch_alter_table("learner_reports", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_learner_reports_attempt_id"), ["attempt_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_learner_reports_learner_id"), ["learner_id"], unique=False
        )

    with op.batch_alter_table("attempts", schema=None) as batch_op:
        batch_op.add_column(sa.Column("reference_variant", sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column("candidates", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("model_output", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("policy", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("app_version", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("feedback_language", sa.String(length=8), nullable=True))

    with op.batch_alter_table("learners", schema=None) as batch_op:
        batch_op.add_column(sa.Column("feedback_language", sa.String(length=8), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("learners", schema=None) as batch_op:
        batch_op.drop_column("feedback_language")

    with op.batch_alter_table("attempts", schema=None) as batch_op:
        batch_op.drop_column("feedback_language")
        batch_op.drop_column("app_version")
        batch_op.drop_column("policy")
        batch_op.drop_column("model_output")
        batch_op.drop_column("candidates")
        batch_op.drop_column("reference_variant")

    with op.batch_alter_table("learner_reports", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_learner_reports_learner_id"))
        batch_op.drop_index(batch_op.f("ix_learner_reports_attempt_id"))

    op.drop_table("learner_reports")
