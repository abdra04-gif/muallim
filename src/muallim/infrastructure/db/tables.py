"""Схема БД. Описание каждой таблицы и поля — docs/data/data-dictionary.md (держать в синхроне).

Типы переносимые (PostgreSQL в работе, SQLite в тестах) — ADR-0004.
Любое изменение схемы — только через миграцию Alembic (migrations/versions).
"""

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    SmallInteger,
    String,
    Table,
    Text,
    Uuid,
)
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator


class UtcDateTime(TypeDecorator[datetime]):
    """Время всегда в UTC и всегда с часовым поясом — и в PostgreSQL, и в SQLite."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("Нужна дата с часовым поясом (UTC)")
        return value.astimezone(UTC) if value is not None else None

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


metadata = MetaData(
    naming_convention={
        "ix": "ix_%(column_0_label)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }
)

learners = Table(
    "learners",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("telegram_user_id", BigInteger, nullable=False, unique=True),
    Column("pseudonym", String(16), nullable=False, unique=True),
    Column("language", String(8), nullable=False),
    Column("current_item_id", String(32)),
    Column("research_consent", Boolean, nullable=False, default=False),
    Column("blocked_bot", Boolean, nullable=False, default=False),
    Column("feedback_language", String(8)),
    Column("created_at", UtcDateTime(), nullable=False),
)

consents = Table(
    "consents",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column(
        "learner_id",
        Uuid,
        ForeignKey("learners.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("kind", String(32), nullable=False),
    Column("granted", Boolean, nullable=False),
    Column("text_version", String(32), nullable=False),
    Column("at", UtcDateTime(), nullable=False),
)

learner_profiles = Table(
    "learner_profiles",
    metadata,
    Column("learner_id", Uuid, ForeignKey("learners.id", ondelete="CASCADE"), primary_key=True),
    Column("adult", Boolean, nullable=False),
    Column("native_language", String(8)),
    Column("arabic_reading", String(16)),
    Column("questionnaire_version", String(16), nullable=False),
    Column("answered_at", UtcDateTime(), nullable=False),
)

attempts = Table(
    "attempts",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column(
        "learner_id",
        Uuid,
        ForeignKey("learners.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("item_id", String(32), nullable=False, index=True),
    Column("curriculum_version", String(32), nullable=False),
    Column("model_version", String(128), nullable=False),
    Column("reference_phonemes", Text, nullable=False),
    Column("heard_phonemes", Text, nullable=False),
    Column("score", SmallInteger, nullable=False),
    Column("verdict", String(16), nullable=False),
    Column("audio_sha256", String(64)),
    Column("audio_duration_ms", Integer),
    Column("processing_ms", Integer, nullable=False),
    Column("created_at", UtcDateTime(), nullable=False, index=True),
    # След решения (ADR-0019): пустые у попыток, сохранённых до миграции 0002.
    Column("reference_variant", String(16)),
    Column("candidates", JSON),
    Column("model_output", JSON),
    Column("policy", JSON),
    Column("app_version", String(64)),
    Column("feedback_language", String(8)),
    CheckConstraint("score BETWEEN 0 AND 100", name="score_range"),
)

curriculum_items = Table(
    # Снимок учебной программы (ADR-0023): по item_id + curriculum_version попытку можно связать
    # со страницей и строкой книги и с текстом, который видел ученик, даже после правок контента.
    "curriculum_items",
    metadata,
    Column("curriculum_version", String(32), primary_key=True),
    Column("item_id", String(32), primary_key=True),
    Column("lesson_id", String(16), nullable=False),
    Column("lesson_number", SmallInteger, nullable=False),
    Column("lesson_title", String(128), nullable=False),
    Column("position", SmallInteger, nullable=False),  # номер карточки в уроке, с 1
    Column("kind", String(16), nullable=False),
    Column("text", Text, nullable=False),
    Column("note", Text, nullable=False, default=""),
    Column("source_id", String(16)),
    Column("page", SmallInteger),
    Column("line", SmallInteger),
    Column("verified", Boolean, nullable=False, default=False),
    Column("published_at", UtcDateTime(), nullable=False),
)

detected_errors = Table(
    "detected_errors",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column(
        "attempt_id",
        Uuid,
        ForeignKey("attempts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("ordinal", SmallInteger, nullable=False),  # порядок в ответе ученику
    Column("kind", String(32), nullable=False, index=True),
    Column("position", SmallInteger, nullable=False),
    Column("syllable", SmallInteger),
    Column("expected", String(16), nullable=False),
    Column("heard", String(16), nullable=False),
    Column("message", Text, nullable=False),  # что именно увидел ученик
)

annotations = Table(
    "annotations",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column(
        "attempt_id",
        Uuid,
        ForeignKey("attempts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("detected_error_id", Integer, ForeignKey("detected_errors.id", ondelete="CASCADE")),
    Column("annotator", String(64), nullable=False),  # код разметчика, не имя
    Column("label", String(32), nullable=False, index=True),
    Column("corrected_phonemes", Text),  # что на самом деле прочитано (эталон разметчика)
    Column("comment", Text, nullable=False, default=""),
    Column("guide_version", String(16), nullable=False),  # версия docs/data/annotation-guide.md
    Column("created_at", UtcDateTime(), nullable=False),
)

learner_reports = Table(
    "learner_reports",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column(
        "attempt_id",
        Uuid,
        ForeignKey("attempts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column(
        "learner_id",
        Uuid,
        ForeignKey("learners.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("reason", String(32), nullable=False),
    Column("created_at", UtcDateTime(), nullable=False),
)

interaction_events = Table(
    "interaction_events",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("learner_id", Uuid, ForeignKey("learners.id", ondelete="SET NULL"), index=True),
    Column("event", String(48), nullable=False, index=True),
    Column("payload", JSON, nullable=False),
    Column("created_at", UtcDateTime(), nullable=False, index=True),
)

Index("ix_attempts_learner_item", attempts.c.learner_id, attempts.c.item_id)
