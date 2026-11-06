"""Разметка 3.0: виды «shadda» и «sukun», откуда строка «что прозвучало» (FR-63, ADR-0080).

В ``annotation_marks.kind`` добавлены ``shadda`` и ``sukun`` (прежний ``shadda_sukun`` остаётся
допустимым для прежних меток). В ``annotations`` — ``phonemes_source``: ``typed`` (введена
учителем) | ``marks`` (из отметок) | ``confirmed`` («Бот прав») | ``reference`` («Чисто»); у
прежних меток NULL. Откат: ``shadda`` и ``sukun`` становятся ``shadda_sukun`` (если в клетке были
оба, остаётся один), столбец удаляется. Перед миграцией make migrate делает копию БД.

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-07 12:00:00.000000+00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Копия значений кода на момент миграции (MarkKind, PhonemesSource): новое — только новой миграцией.
OLD_KINDS = (
    "letter", "vowel", "madd", "shadda_sukun", "missing", "extra",
    "tafkhim", "ghunna", "qalqala", "halting", "wrong_stop",
)  # fmt: skip
KINDS = (*OLD_KINDS, "shadda", "sukun")
SOURCES = ("typed", "marks", "confirmed", "reference")

KIND_CHECK = "ck_annotation_marks_kind_values"
SOURCE_CHECK = "ck_annotations_phonemes_source_values"


def _one_of(column: str, values: Sequence[str]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _swap_kind_check(values: Sequence[str]) -> None:
    # annotation_marks не входит ни в одно представление (v_*): пересоздание таблицы в SQLite
    # безопасно; в PostgreSQL batch просто меняет ограничение.
    with op.batch_alter_table("annotation_marks") as batch:
        batch.drop_constraint(op.f(KIND_CHECK), type_="check")
        batch.create_check_constraint(op.f(KIND_CHECK), _one_of("kind", values))


def upgrade() -> None:
    # Простой ADD COLUMN с CHECK, как в 0011: таблица не пересоздаётся, представления целы.
    op.execute(
        "ALTER TABLE annotations ADD COLUMN phonemes_source VARCHAR(16) "
        f"CONSTRAINT {SOURCE_CHECK} CHECK (phonemes_source IS NULL OR "
        f"{_one_of('phonemes_source', SOURCES)})"
    )
    _swap_kind_check(KINDS)


def downgrade() -> None:
    # В клетке были и «shadda», и «sukun»: UNIQUE (annotation_id, cell, kind) не даст обоим стать
    # «shadda_sukun» — лишний убираем.
    op.execute(
        "DELETE FROM annotation_marks WHERE kind = 'sukun' AND EXISTS ("
        "SELECT 1 FROM annotation_marks m WHERE m.annotation_id = annotation_marks.annotation_id "
        "AND m.cell = annotation_marks.cell AND m.kind = 'shadda')"
    )
    op.execute(
        "UPDATE annotation_marks SET kind = 'shadda_sukun' WHERE kind IN ('shadda', 'sukun')"
    )
    _swap_kind_check(OLD_KINDS)
    if op.get_bind().dialect.name != "sqlite":
        op.drop_constraint(SOURCE_CHECK, "annotations", type_="check")
    # SQLite ≥ 3.35 удаляет столбец сам; CHECK столбца уходит вместе с ним.
    op.execute("ALTER TABLE annotations DROP COLUMN phonemes_source")
