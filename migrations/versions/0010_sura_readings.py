"""Чтения сур целиком и наизусть: sura_readings и три таблицы подробностей (FR-60, ADR-0076).

Одно голосовое со всей сурой — строка sura_readings; по аятам, кускам записи 6–10 с и событиям
(ошибка, заминка, самоисправление) — sura_reading_ayahs, sura_reading_chunks, sura_reading_events.
Старые таблицы не меняются. Удаляется вместе с учеником (ON DELETE CASCADE).
Права ролям бота и просмотра выдаются сами (ALTER DEFAULT PRIVILEGES в scripts/db/roles.sql).
Описание полей: docs/data/data-dictionary.md. Перед миграцией make migrate делает копию БД.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-31 12:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MODES = "mode IN ('text', 'memory')"
_OUTCOMES = "outcome IN ('clean', 'pronunciation', 'forgot_part', 'skipped', 'not_reached')"
_KINDS = "kind IN ('pronunciation', 'forgot_word', 'extra', 'self_corrected', 'pause')"


def _reading_fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["reading_id"],
        ["sura_readings.id"],
        name=op.f(f"fk_{table}_reading_id_sura_readings"),
        ondelete="CASCADE",
    )


def upgrade() -> None:
    op.create_table(
        "sura_readings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("learner_id", sa.Uuid(), nullable=False),
        sa.Column("sura", sa.SmallInteger(), nullable=False),
        sa.Column("mode", sa.String(8), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("days_since_last", sa.Integer(), nullable=True),
        sa.Column("studied_by_text", sa.Boolean(), nullable=False),
        sa.Column("clean_ayahs", sa.SmallInteger(), nullable=False),
        sa.Column("total_ayahs", sa.SmallInteger(), nullable=False),
        sa.Column("score", sa.SmallInteger(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("credited", sa.JSON(), nullable=False),
        sa.Column("reference_phonemes", sa.Text(), nullable=False),
        sa.Column("heard_phonemes", sa.Text(), nullable=False),
        sa.Column("audio_sha256", sa.String(64), nullable=True),
        sa.Column("audio_duration_ms", sa.Integer(), nullable=False),
        sa.Column("processing_ms", sa.Integer(), nullable=False),
        sa.Column("model_version", sa.String(128), nullable=False),
        sa.Column("curriculum_version", sa.String(32), nullable=False),
        sa.Column("app_version", sa.String(64), nullable=False),
        sa.Column("policy", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(_MODES, name=op.f("ck_sura_readings_mode_values")),
        sa.CheckConstraint("score BETWEEN 0 AND 100", name=op.f("ck_sura_readings_score_range")),
        sa.CheckConstraint(
            "attempt_number >= 1", name=op.f("ck_sura_readings_attempt_number_positive")
        ),
        sa.ForeignKeyConstraint(
            ["learner_id"],
            ["learners.id"],
            name=op.f("fk_sura_readings_learner_id_learners"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sura_readings")),
    )
    op.create_index(op.f("ix_sura_readings_learner_id"), "sura_readings", ["learner_id"])
    op.create_index(op.f("ix_sura_readings_created_at"), "sura_readings", ["created_at"])

    op.create_table(
        "sura_reading_ayahs",
        sa.Column("reading_id", sa.Uuid(), nullable=False),
        sa.Column("ayah", sa.SmallInteger(), nullable=False),
        sa.Column("item_id", sa.String(32), nullable=False),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("score", sa.SmallInteger(), nullable=False),
        sa.Column("forgotten_words", sa.SmallInteger(), nullable=False),
        sa.Column("extra_words", sa.SmallInteger(), nullable=False),
        sa.Column("pronunciation_errors", sa.SmallInteger(), nullable=False),
        sa.Column("reference_phonemes", sa.Text(), nullable=False),
        sa.Column("heard_phonemes", sa.Text(), nullable=False),
        sa.CheckConstraint(_OUTCOMES, name=op.f("ck_sura_reading_ayahs_outcome_values")),
        sa.CheckConstraint(
            "score BETWEEN 0 AND 100", name=op.f("ck_sura_reading_ayahs_score_range")
        ),
        _reading_fk("sura_reading_ayahs"),
        sa.PrimaryKeyConstraint("reading_id", "ayah", name=op.f("pk_sura_reading_ayahs")),
    )
    op.create_index(op.f("ix_sura_reading_ayahs_item_id"), "sura_reading_ayahs", ["item_id"])

    op.create_table(
        "sura_reading_chunks",
        sa.Column("reading_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.SmallInteger(), nullable=False),
        sa.Column("start_ms", sa.Integer(), nullable=False),
        sa.Column("end_ms", sa.Integer(), nullable=False),
        sa.Column("first_ayah", sa.SmallInteger(), nullable=True),
        sa.Column("last_ayah", sa.SmallInteger(), nullable=True),
        sa.Column("heard_phonemes", sa.Text(), nullable=False),
        sa.CheckConstraint("end_ms >= start_ms", name=op.f("ck_sura_reading_chunks_span_order")),
        _reading_fk("sura_reading_chunks"),
        sa.PrimaryKeyConstraint("reading_id", "ordinal", name=op.f("pk_sura_reading_chunks")),
    )

    op.create_table(
        "sura_reading_events",
        sa.Column("reading_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.SmallInteger(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("ayah", sa.SmallInteger(), nullable=False),
        sa.Column("word", sa.SmallInteger(), nullable=True),
        sa.Column("expected", sa.Text(), nullable=False),
        sa.Column("heard", sa.Text(), nullable=False),
        sa.Column("error_kind", sa.String(32), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.CheckConstraint(_KINDS, name=op.f("ck_sura_reading_events_kind_values")),
        _reading_fk("sura_reading_events"),
        sa.PrimaryKeyConstraint("reading_id", "ordinal", name=op.f("pk_sura_reading_events")),
    )
    op.create_index(op.f("ix_sura_reading_events_kind"), "sura_reading_events", ["kind"])


def downgrade() -> None:
    op.drop_table("sura_reading_events")
    op.drop_table("sura_reading_chunks")
    op.drop_table("sura_reading_ayahs")
    op.drop_table("sura_readings")
