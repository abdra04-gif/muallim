"""Схема БД. Описание каждой таблицы и поля — docs/data/data-dictionary.md (держать в синхроне).

Типы переносимые (PostgreSQL в работе, SQLite в тестах) — ADR-0004.
Любое изменение схемы — только через миграцию Alembic (migrations/versions).
"""

from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    SmallInteger,
    String,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.engine import Dialect
from sqlalchemy.sql.expression import false, true
from sqlalchemy.types import TypeDecorator

from muallim.domain.annotation import AnnotationSource, AnnotationStatus
from muallim.domain.policy import Verdict
from muallim.domain.report import ReportReason
from muallim.domain.settings import (
    DEFAULT_UTC_OFFSET_MIN,
    MAX_UTC_OFFSET_MIN,
    MIN_UTC_OFFSET_MIN,
    MINUTES_PER_DAY,
    HowToRead,
)

# Метки руководства 1.0 (ADR-0040): больше не ставятся, но могли остаться в БД — CHECK их пускает.
LEGACY_LABELS = ("correct", "false_alarm", "missed_error", "wrong_error")


def _one_of(column: str, values: Iterable[object]) -> str:
    """CHECK «значение из списка» (TD-DB-02): новое значение — только вместе с миграцией."""
    return f"{column} IN ({', '.join(repr(str(v)) for v in values)})"


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
    CheckConstraint(_one_of("verdict", Verdict), name="verdict_values"),
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
    UniqueConstraint("attempt_id", "ordinal"),  # один номер ошибки на попытку
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
    Column("annotator", String(64), nullable=False),  # код разметчика, не имя
    Column("label", String(32), nullable=False, index=True),
    Column("corrected_phonemes", Text),  # что на самом деле прочитано (эталон разметчика)
    Column("comment", Text, nullable=False, default=""),
    Column("guide_version", String(16), nullable=False),  # версия docs/data/annotation-guide.md
    Column("created_at", UtcDateTime(), nullable=False),
    Column("source", String(16)),  # excel | telegram (FR-17); NULL — до миграции 0005
    Column("seconds_spent", Integer),  # от показа записи до ответа; только Telegram
    # ученик ошибся и сам перечитал верно — отдельная категория; NULL — до руководства 2.1
    Column("self_corrected", Boolean),
    CheckConstraint(_one_of("label", [*AnnotationStatus, *LEGACY_LABELS]), name="label_values"),
    CheckConstraint(
        "source IS NULL OR " + _one_of("source", AnnotationSource), name="source_values"
    ),
)

# Разметчики по приглашению и отозванные (FR-17). Разметчики из ANNOTATOR_IDS живут в настройках;
# строка появляется, когда их отзывают. Имени нет — только код (A1…), Telegram ID — отдельно.
annotators = Table(
    "annotators",
    metadata,
    Column("code", String(64), primary_key=True),
    Column("telegram_user_id", BigInteger, unique=True),  # привязан приглашением; NULL — нет
    Column("created_at", UtcDateTime(), nullable=False),
    Column("revoked_at", UtcDateTime()),  # NULL — доступ открыт
)

annotator_invites = Table(
    "annotator_invites",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("code_digest", String(64), nullable=False, unique=True),  # SHA-256 кода, не сам код
    Column("annotator", String(64), nullable=False),
    Column("created_at", UtcDateTime(), nullable=False),
    Column("expires_at", UtcDateTime(), nullable=False),
    Column("used_at", UtcDateTime()),  # одноразовое: после входа — время
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
    CheckConstraint(_one_of("reason", ReportReason), name="reason_values"),
    UniqueConstraint("attempt_id", "learner_id"),  # «Бот ошибся» — одна жалоба на попытку
)

# Настройки ученика и состояние его экрана (FR-51, TD-FN-90, ADR-0061): строка на ученика, нет
# строки — умолчания. Telegram ID нет: роль просмотра видит таблицу целиком. Даты — местные.
learner_settings = Table(
    "learner_settings",
    metadata,
    Column("learner_id", Uuid, ForeignKey("learners.id", ondelete="CASCADE"), primary_key=True),
    Column("how_to_read", String(16), nullable=False, server_default=str(HowToRead.SPOILER)),
    Column("auto_reference", Boolean, nullable=False, server_default=false()),
    Column("daily_opening", Boolean, nullable=False, server_default=true()),
    Column("large_font", Boolean, nullable=False, server_default=false()),
    Column("research_block", Boolean, nullable=False, server_default=false()),
    Column("reminder_minute", SmallInteger),  # минута местных суток; NULL — выключено
    Column(
        "utc_offset_min",
        SmallInteger,
        nullable=False,
        server_default=str(DEFAULT_UTC_OFFSET_MIN),
    ),
    Column("screen_item_id", String(32)),  # NULL — на экране меню
    Column("screen_opening", Boolean, nullable=False, server_default=false()),
    Column("opening_resume_item", String(32)),
    Column("opening_day", Date),
    Column("opening_skipped_on", Date),
    Column("reminder_sent_on", Date),
    Column("updated_at", UtcDateTime(), nullable=False),
    CheckConstraint(_one_of("how_to_read", HowToRead), name="how_to_read_values"),
    CheckConstraint(
        f"reminder_minute IS NULL OR reminder_minute BETWEEN 0 AND {MINUTES_PER_DAY - 1}",
        name="reminder_minute_range",
    ),
    CheckConstraint(
        f"utc_offset_min BETWEEN {MIN_UTC_OFFSET_MIN} AND {MAX_UTC_OFFSET_MIN}",
        name="utc_offset_range",
    ),
)

# «🧠 Закрепление» (FR-53, ADR-0066): одна строка — один показанный вопрос; ответ дописывается в
# неё же один раз. Буква — для модели усвоения (RQ-3), слог — что было на экране.
quiz_answers = Table(
    "quiz_answers",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column(
        "learner_id",
        Uuid,
        ForeignKey("learners.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("round_no", Integer, nullable=False),
    Column("position", SmallInteger, nullable=False),
    Column("step", SmallInteger, nullable=False),
    Column("letter_id", String(32), nullable=False),
    Column("item_id", String(32), nullable=False),
    Column("vowel", SmallInteger, nullable=False),
    Column("options", JSON, nullable=False),
    Column("answer", SmallInteger, nullable=False),
    Column("picked", SmallInteger),
    Column("correct", Boolean),
    Column("attempt_id", Uuid, ForeignKey("attempts.id", ondelete="SET NULL")),
    Column("reason", String(16), nullable=False, server_default=""),
    Column("shown_at", UtcDateTime(), nullable=False),
    Column("answered_at", UtcDateTime()),
    Column("curriculum_version", String(32), nullable=False),
    Column("rule", String(8), nullable=False),
    CheckConstraint("step BETWEEN 1 AND 3", name="step_range"),
    CheckConstraint("vowel BETWEEN 0 AND 2", name="vowel_range"),
    CheckConstraint("position >= 1", name="position_positive"),
    CheckConstraint("picked IS NULL OR picked BETWEEN 0 AND 3", name="picked_range"),
    # одно место раунда — один вопрос: двойное нажатие не даёт раунд из 11 (автор 2026-10-23)
    UniqueConstraint("learner_id", "round_no", "position"),
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
