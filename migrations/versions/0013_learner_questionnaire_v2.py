"""Анкета 2.0: возраст, пол, намаз, пропуски; имя отдельно; представление когорт (FR-65, ADR-0081).

``learner_profiles``: добавлены ``age_group``, ``gender``, ``prayer``, ``skipped``; ``adult``
удалён (прежнее «нет 18» становится ``age_group = 'u18'``, прежнее «да» — возраст неизвестен).
``arabic_reading`` получил значение ``fluent``. Имя — в новой таблице ``learner_names`` (прямое ПДн,
роль просмотра её не читает). Новое представление ``v_learner_cohorts``: ученик под псевдонимом,
ковариаты анкеты и итоги попыток.

Откат: ``adult`` восстанавливается из возраста (``u18`` → нет, остальное → да), столбцы и
представление удаляются, **имена теряются**. Перед миграцией make migrate делает копию БД.

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-07 15:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Копия значений кода на момент миграции (AgeGroup, Gender, NativeLanguage, ArabicReading, Prayer).
AGE = ("u18", "18_24", "25_34", "35_44", "45_54", "55_plus")
GENDER = ("m", "f")
NATIVE = ("ru", "kk", "tt", "other")
READING = ("none", "some_letters", "slow_syllables", "fluent")
PRAYER = ("no", "sometimes", "regular")

# Копия представлений на момент миграции (src/muallim/infrastructure/db/views.py): последняя
# миграция с представлениями хранит их целиком, тест сверяет с кодом. Создаётся только новое.
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
    "v_learner_cohorts": """
SELECT
    l.pseudonym,
    l.created_at,
    l.research_consent,
    p.age_group,
    p.gender,
    p.native_language,
    p.arabic_reading,
    p.prayer,
    (SELECT COUNT(*) FROM attempts a
        WHERE a.learner_id = l.id AND a.model_version <> 'stub') AS attempts,
    (SELECT COUNT(*) FROM detected_errors e JOIN attempts a ON a.id = e.attempt_id
        WHERE a.learner_id = l.id AND a.model_version <> 'stub') AS errors,
    (SELECT ROUND(AVG(a.score), 1) FROM attempts a
        WHERE a.learner_id = l.id AND a.model_version <> 'stub') AS avg_score,
    (SELECT MIN(a.created_at) FROM attempts a
        WHERE a.learner_id = l.id AND a.model_version <> 'stub') AS first_attempt_at,
    (SELECT MAX(a.created_at) FROM attempts a
        WHERE a.learner_id = l.id AND a.model_version <> 'stub') AS last_attempt_at
FROM learners l
LEFT JOIN learner_profiles p ON p.learner_id = l.id
""",
}


def _one_of_or_null(column: str, values: Sequence[str]) -> str:
    return f"{column} IS NULL OR {column} IN ({', '.join(repr(v) for v in values)})"


def upgrade() -> None:
    with op.batch_alter_table("learner_profiles") as batch:
        batch.add_column(sa.Column("age_group", sa.String(8), nullable=True))
        batch.add_column(sa.Column("gender", sa.String(1), nullable=True))
        batch.add_column(sa.Column("prayer", sa.String(16), nullable=True))
        batch.add_column(sa.Column("skipped", sa.JSON(), nullable=False, server_default="[]"))
    # Прежнее «нет 18» → «до 18»; прежнее «да» — возраст неизвестен (анкета спросит ещё раз).
    op.execute("UPDATE learner_profiles SET age_group = 'u18' WHERE adult = false")
    with op.batch_alter_table("learner_profiles") as batch:
        batch.drop_column("adult")
        batch.create_check_constraint(
            op.f("ck_learner_profiles_age_group_values"), _one_of_or_null("age_group", AGE)
        )
        batch.create_check_constraint(
            op.f("ck_learner_profiles_gender_values"), _one_of_or_null("gender", GENDER)
        )
        batch.create_check_constraint(
            op.f("ck_learner_profiles_native_values"), _one_of_or_null("native_language", NATIVE)
        )
        batch.create_check_constraint(
            op.f("ck_learner_profiles_reading_values"), _one_of_or_null("arabic_reading", READING)
        )
        batch.create_check_constraint(
            op.f("ck_learner_profiles_prayer_values"), _one_of_or_null("prayer", PRAYER)
        )
    op.create_table(
        "learner_names",
        sa.Column("learner_id", sa.Uuid(), nullable=False),
        sa.Column("display_name", sa.String(40), nullable=False),
        sa.ForeignKeyConstraint(
            ["learner_id"],
            ["learners.id"],
            name=op.f("fk_learner_names_learner_id_learners"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("learner_id", name=op.f("pk_learner_names")),
    )
    op.execute(f"CREATE VIEW v_learner_cohorts AS {VIEWS['v_learner_cohorts']}")


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_learner_cohorts")
    op.drop_table("learner_names")
    with op.batch_alter_table("learner_profiles") as batch:
        batch.add_column(sa.Column("adult", sa.Boolean(), nullable=True))
    op.execute("UPDATE learner_profiles SET adult = (age_group IS NULL OR age_group <> 'u18')")
    with op.batch_alter_table("learner_profiles") as batch:
        for name in ("age_group", "gender", "native", "reading", "prayer"):
            batch.drop_constraint(op.f(f"ck_learner_profiles_{name}_values"), type_="check")
        batch.alter_column("adult", existing_type=sa.Boolean(), nullable=False)
        batch.drop_column("skipped")
        batch.drop_column("prayer")
        batch.drop_column("gender")
        batch.drop_column("age_group")
