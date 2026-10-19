"""Защита в самой БД: допустимые значения, одна жалоба на попытку, без detected_error_id.

TD-DB-02, TD-DB-04, ADR-0055. Описание полей: docs/data/data-dictionary.md. VIEWS — замороженная
копия src/muallim/infrastructure/db/views.py (тест сверяет); OLD_VIEWS — как было до 0007.
Двойные жалобы «Бот ошибся» (двойное нажатие) сливаются в первую — иначе UNIQUE не встанет;
откат их не вернёт. Перед миграцией make migrate делает копию БД.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-20 06:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Замороженные значения (тест сверяет с перечислениями в коде).
VERDICTS = ("excellent", "passed", "failed")
REPORT_REASONS = ("read_correctly", "wrong_error", "other")
LABELS = (
    "agree", "fix", "audio_unusable", "off_task",
    "correct", "false_alarm", "missed_error", "wrong_error",  # руководство 1.0
)  # fmt: skip
SOURCES = ("excel", "telegram")

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
        ORDER BY an.created_at DESC, an.id DESC
        LIMIT 1
    ) AS label
FROM detected_errors e
JOIN attempts a ON a.id = e.attempt_id
JOIN learners l ON l.id = a.learner_id
LEFT JOIN curriculum_items ci
    ON ci.item_id = a.item_id AND ci.curriculum_version = a.curriculum_version
""",
}

OLD_VIEWS: dict[str, str] = {
    "v_attempts": VIEWS["v_attempts"],
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


def _one_of(column: str, values: Sequence[str]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _drop_views() -> None:
    for name in ("v_errors", "v_attempts"):
        op.execute(f"DROP VIEW IF EXISTS {name}")


def _create_views(views: dict[str, str]) -> None:
    for name, sql in views.items():
        op.execute(f"CREATE VIEW {name} AS {sql}")


def upgrade() -> None:
    _drop_views()  # представления держат таблицы: SQLite пересоздаёт их, PostgreSQL — DROP COLUMN
    op.execute(
        "DELETE FROM learner_reports WHERE id NOT IN "
        "(SELECT MIN(id) FROM learner_reports GROUP BY attempt_id, learner_id)"
    )
    with op.batch_alter_table("attempts") as batch:  # SQLite переносит прежние CHECK сам
        batch.create_check_constraint(
            op.f("ck_attempts_verdict_values"), _one_of("verdict", VERDICTS)
        )
    with op.batch_alter_table("learner_reports") as batch:
        batch.create_check_constraint(
            op.f("ck_learner_reports_reason_values"), _one_of("reason", REPORT_REASONS)
        )
        batch.create_unique_constraint(
            op.f("uq_learner_reports_attempt_id"), ["attempt_id", "learner_id"]
        )
    with op.batch_alter_table("detected_errors") as batch:
        batch.create_unique_constraint(
            op.f("uq_detected_errors_attempt_id"), ["attempt_id", "ordinal"]
        )
    with op.batch_alter_table("annotations") as batch:
        batch.drop_constraint(
            op.f("fk_annotations_detected_error_id_detected_errors"), type_="foreignkey"
        )
        batch.drop_column("detected_error_id")
        batch.create_check_constraint(op.f("ck_annotations_label_values"), _one_of("label", LABELS))
        batch.create_check_constraint(
            op.f("ck_annotations_source_values"), "source IS NULL OR " + _one_of("source", SOURCES)
        )
    _create_views(VIEWS)


def downgrade() -> None:
    _drop_views()
    with op.batch_alter_table("annotations") as batch:
        batch.drop_constraint(op.f("ck_annotations_source_values"), type_="check")
        batch.drop_constraint(op.f("ck_annotations_label_values"), type_="check")
        batch.add_column(sa.Column("detected_error_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            op.f("fk_annotations_detected_error_id_detected_errors"),
            "detected_errors", ["detected_error_id"], ["id"], ondelete="CASCADE",
        )  # fmt: skip
    with op.batch_alter_table("detected_errors") as batch:
        batch.drop_constraint(op.f("uq_detected_errors_attempt_id"), type_="unique")
    with op.batch_alter_table("learner_reports") as batch:
        batch.drop_constraint(op.f("uq_learner_reports_attempt_id"), type_="unique")
        batch.drop_constraint(op.f("ck_learner_reports_reason_values"), type_="check")
    with op.batch_alter_table("attempts") as batch:
        batch.drop_constraint(op.f("ck_attempts_verdict_values"), type_="check")
    _create_views(OLD_VIEWS)
