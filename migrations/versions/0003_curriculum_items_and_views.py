"""Снимок учебной программы и представления для просмотра данных.

ADR-0023. Описание: docs/data/data-dictionary.md. VIEWS — замороженная копия
src/muallim/infrastructure/db/views.py на момент миграции (тест сверяет).

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-17 08:14:49.128971+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VIEWS: dict[str, str] = {
    "v_attempts": """
SELECT
    a.id AS attempt_id,
    a.created_at,
    l.pseudonym,
    a.item_id,
    ci.lesson_id,
    ci.lesson_title,
    ci.page,
    ci.line,
    ci.text AS item_text,
    ci.note AS item_note,
    a.score,
    a.verdict,
    a.reference_phonemes,
    a.heard_phonemes,
    a.reference_variant,
    (SELECT COUNT(*) FROM detected_errors e WHERE e.attempt_id = a.id) AS errors,
    (SELECT COUNT(*) FROM learner_reports r WHERE r.attempt_id = a.id) AS disputed,
    (SELECT COUNT(*) FROM annotations an WHERE an.attempt_id = a.id) AS annotations,
    a.audio_sha256,
    a.audio_duration_ms,
    a.model_version,
    a.curriculum_version,
    a.app_version
FROM attempts a
JOIN learners l ON l.id = a.learner_id
LEFT JOIN curriculum_items ci
    ON ci.item_id = a.item_id AND ci.curriculum_version = a.curriculum_version
""",
    "v_errors": """
SELECT
    e.id AS error_id,
    e.attempt_id,
    a.created_at,
    l.pseudonym,
    a.item_id,
    ci.lesson_id,
    ci.lesson_title,
    ci.page,
    ci.line,
    ci.text AS item_text,
    ci.note AS item_note,
    e.kind,
    e.expected,
    e.heard,
    e.position,
    e.syllable,
    e.message,
    a.score,
    a.verdict,
    a.audio_sha256,
    a.model_version,
    a.curriculum_version,
    (SELECT COUNT(*) FROM learner_reports r WHERE r.attempt_id = a.id) AS disputed,
    (
        SELECT an.label FROM annotations an
        WHERE an.attempt_id = a.id
            AND (an.detected_error_id = e.id OR an.detected_error_id IS NULL)
        ORDER BY an.created_at DESC
        LIMIT 1
    ) AS label
FROM detected_errors e
JOIN attempts a ON a.id = e.attempt_id
JOIN learners l ON l.id = a.learner_id
LEFT JOIN curriculum_items ci
    ON ci.item_id = a.item_id AND ci.curriculum_version = a.curriculum_version
""",
}


def upgrade() -> None:
    op.create_table(
        "curriculum_items",
        sa.Column("curriculum_version", sa.String(length=32), nullable=False),
        sa.Column("item_id", sa.String(length=32), nullable=False),
        sa.Column("lesson_id", sa.String(length=16), nullable=False),
        sa.Column("lesson_number", sa.SmallInteger(), nullable=False),
        sa.Column("lesson_title", sa.String(length=128), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("source_id", sa.String(length=16), nullable=True),
        sa.Column("page", sa.SmallInteger(), nullable=True),
        sa.Column("line", sa.SmallInteger(), nullable=True),
        sa.Column("verified", sa.Boolean(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("curriculum_version", "item_id", name=op.f("pk_curriculum_items")),
    )
    for name, sql in VIEWS.items():
        op.execute(f"CREATE VIEW {name} AS {sql}")


def downgrade() -> None:
    for name in reversed(VIEWS):
        op.execute(f"DROP VIEW IF EXISTS {name}")
    op.drop_table("curriculum_items")
