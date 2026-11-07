"""Представления для просмотра данных в DBeaver/psql и для отчётов (ADR-0023).

SQL переносимый (PostgreSQL и SQLite). Telegram ID в представления не попадает — только псевдоним.
Последняя миграция с представлениями (сейчас 0013) хранит их замороженную копию; тест сверяет.
Изменили SQL здесь — добавьте миграцию, которая пересоздаёт представление.
"""

from sqlalchemy import Connection

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
    # Ученик под псевдонимом: ковариаты анкеты и итоги попыток (FR-65). Имени и Telegram ID нет.
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


def create_views(conn: Connection) -> None:
    for name, sql in VIEWS.items():
        conn.exec_driver_sql(f"CREATE VIEW {name} AS {sql}")


def drop_views(conn: Connection) -> None:
    for name in reversed(VIEWS):
        conn.exec_driver_sql(f"DROP VIEW IF EXISTS {name}")
