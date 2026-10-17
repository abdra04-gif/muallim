"""Начальная схема: ученики, согласия, попытки, ошибки, разметка, журнал событий.

Описание полей: docs/data/data-dictionary.md. Решение о составе таблиц: ADR-0004.

Revision ID: 0001
Revises:
Create Date: 2026-10-16 19:38:32.931599+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "learners",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("pseudonym", sa.String(length=16), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("current_item_id", sa.String(length=32), nullable=True),
        sa.Column("research_consent", sa.Boolean(), nullable=False),
        sa.Column("blocked_bot", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_learners")),
        sa.UniqueConstraint("pseudonym", name=op.f("uq_learners_pseudonym")),
        sa.UniqueConstraint("telegram_user_id", name=op.f("uq_learners_telegram_user_id")),
    )
    op.create_table(
        "attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("learner_id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.String(length=32), nullable=False),
        sa.Column("curriculum_version", sa.String(length=32), nullable=False),
        sa.Column("model_version", sa.String(length=128), nullable=False),
        sa.Column("reference_phonemes", sa.Text(), nullable=False),
        sa.Column("heard_phonemes", sa.Text(), nullable=False),
        sa.Column("score", sa.SmallInteger(), nullable=False),
        sa.Column("verdict", sa.String(length=16), nullable=False),
        sa.Column("audio_sha256", sa.String(length=64), nullable=True),
        sa.Column("audio_duration_ms", sa.Integer(), nullable=True),
        sa.Column("processing_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("score BETWEEN 0 AND 100", name=op.f("ck_attempts_score_range")),
        sa.ForeignKeyConstraint(
            ["learner_id"],
            ["learners.id"],
            name=op.f("fk_attempts_learner_id_learners"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_attempts")),
    )
    with op.batch_alter_table("attempts", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_attempts_created_at"), ["created_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_attempts_item_id"), ["item_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_attempts_learner_id"), ["learner_id"], unique=False)
        batch_op.create_index("ix_attempts_learner_item", ["learner_id", "item_id"], unique=False)

    op.create_table(
        "consents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("learner_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("granted", sa.Boolean(), nullable=False),
        sa.Column("text_version", sa.String(length=32), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["learner_id"],
            ["learners.id"],
            name=op.f("fk_consents_learner_id_learners"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_consents")),
    )
    with op.batch_alter_table("consents", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_consents_learner_id"), ["learner_id"], unique=False)

    op.create_table(
        "interaction_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("learner_id", sa.Uuid(), nullable=True),
        sa.Column("event", sa.String(length=48), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["learner_id"],
            ["learners.id"],
            name=op.f("fk_interaction_events_learner_id_learners"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_interaction_events")),
    )
    with op.batch_alter_table("interaction_events", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_interaction_events_created_at"), ["created_at"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_interaction_events_event"), ["event"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_interaction_events_learner_id"), ["learner_id"], unique=False
        )

    op.create_table(
        "detected_errors",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.SmallInteger(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("syllable", sa.SmallInteger(), nullable=True),
        sa.Column("expected", sa.String(length=16), nullable=False),
        sa.Column("heard", sa.String(length=16), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["attempts.id"],
            name=op.f("fk_detected_errors_attempt_id_attempts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_detected_errors")),
    )
    with op.batch_alter_table("detected_errors", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_detected_errors_attempt_id"), ["attempt_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_detected_errors_kind"), ["kind"], unique=False)

    op.create_table(
        "annotations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("detected_error_id", sa.Integer(), nullable=True),
        sa.Column("annotator", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=32), nullable=False),
        sa.Column("corrected_phonemes", sa.Text(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("guide_version", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["attempts.id"],
            name=op.f("fk_annotations_attempt_id_attempts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["detected_error_id"],
            ["detected_errors.id"],
            name=op.f("fk_annotations_detected_error_id_detected_errors"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_annotations")),
    )
    with op.batch_alter_table("annotations", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_annotations_attempt_id"), ["attempt_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_annotations_label"), ["label"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("annotations", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_annotations_label"))
        batch_op.drop_index(batch_op.f("ix_annotations_attempt_id"))

    op.drop_table("annotations")
    with op.batch_alter_table("detected_errors", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_detected_errors_kind"))
        batch_op.drop_index(batch_op.f("ix_detected_errors_attempt_id"))

    op.drop_table("detected_errors")
    with op.batch_alter_table("interaction_events", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_interaction_events_learner_id"))
        batch_op.drop_index(batch_op.f("ix_interaction_events_event"))
        batch_op.drop_index(batch_op.f("ix_interaction_events_created_at"))

    op.drop_table("interaction_events")
    with op.batch_alter_table("consents", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_consents_learner_id"))

    op.drop_table("consents")
    with op.batch_alter_table("attempts", schema=None) as batch_op:
        batch_op.drop_index("ix_attempts_learner_item")
        batch_op.drop_index(batch_op.f("ix_attempts_learner_id"))
        batch_op.drop_index(batch_op.f("ix_attempts_item_id"))
        batch_op.drop_index(batch_op.f("ix_attempts_created_at"))

    op.drop_table("attempts")
    op.drop_table("learners")
