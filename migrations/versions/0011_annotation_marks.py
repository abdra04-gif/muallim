"""Разметка по клеткам: таблица annotation_marks и annotations.entry (FR-62, ADR-0079).

Учитель отмечает клетки (слоги аята суры или буквы строки) и вид ошибки — строка на отметку
«клетка × вид». Позиция кусочка — в символах текста пункта. Клетки уходят вместе с меткой
(ON DELETE CASCADE) — и при /delete ученика. ``annotations.entry`` — как введено «что прозвучало»:
cells | phonemes; у прежних меток NULL. Описание полей: docs/data/data-dictionary.md.
Права ролям бота и просмотра выдаются сами (ALTER DEFAULT PRIVILEGES в scripts/db/roles.sql).
Перед миграцией make migrate делает копию БД.

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-31 18:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Копия значений кода на момент миграции (MarkKind, Layout, Entry): новое — только новой миграцией.
KINDS = (
    "letter", "vowel", "madd", "shadda_sukun", "missing", "extra",
    "tafkhim", "ghunna", "qalqala", "halting", "wrong_stop",
)  # fmt: skip
LAYOUTS = ("syllables", "letters")
ENTRIES = ("cells", "phonemes")


def _one_of(column: str, values: Sequence[str]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


_ENTRY_CHECK = "entry IS NULL OR " + _one_of("entry", ENTRIES)


def upgrade() -> None:
    # Простой ADD COLUMN с CHECK (и в PostgreSQL, и в SQLite): таблица не пересоздаётся,
    # представления (v_*) не ломаются. Прежние метки — NULL: способ ввода тогда не записывали.
    op.execute(
        "ALTER TABLE annotations ADD COLUMN entry VARCHAR(16) "
        f"CONSTRAINT ck_annotations_entry_values CHECK ({_ENTRY_CHECK})"
    )
    op.create_table(
        "annotation_marks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("annotation_id", sa.Integer(), nullable=False),
        sa.Column("cell", sa.SmallInteger(), nullable=False),
        sa.Column("layout", sa.String(16), nullable=False),
        sa.Column("char_start", sa.SmallInteger(), nullable=False),
        sa.Column("char_end", sa.SmallInteger(), nullable=False),
        sa.Column("piece", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("heard_letter", sa.String(4), nullable=True),
        sa.Column("bot_flagged", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            _one_of("layout", LAYOUTS), name=op.f("ck_annotation_marks_layout_values")
        ),
        sa.CheckConstraint(_one_of("kind", KINDS), name=op.f("ck_annotation_marks_kind_values")),
        sa.ForeignKeyConstraint(
            ["annotation_id"],
            ["annotations.id"],
            name=op.f("fk_annotation_marks_annotation_id_annotations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_annotation_marks")),
        sa.UniqueConstraint(
            "annotation_id", "cell", "kind", name=op.f("uq_annotation_marks_annotation_id")
        ),
    )
    op.create_index(
        op.f("ix_annotation_marks_annotation_id"), "annotation_marks", ["annotation_id"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_annotation_marks_annotation_id"), table_name="annotation_marks")
    op.drop_table("annotation_marks")
    if op.get_bind().dialect.name != "sqlite":
        op.drop_constraint("ck_annotations_entry_values", "annotations", type_="check")
    # SQLite ≥ 3.35 удаляет столбец сам; CHECK столбца уходит вместе с ним (без пересоздания
    # таблицы — представления не трогаются).
    op.execute("ALTER TABLE annotations DROP COLUMN entry")
