"""Отметки учителя: ``annotation_marks.heard_letter`` → ``heard`` (TD-FN-150, FR-63).

С разметкой 3.0 (ADR-0080) в столбце не только буква: у «Огласовка» — гласная или «-» (никакой),
у «Сукун» — гласная, у «Пропуск» и «Лишний звук» — звук. Имя «буква» путало бы того, кто
возьмёт выгрузку для дообучения модели. Значения не меняются. Описание полей:
docs/data/data-dictionary.md. Перед миграцией make migrate делает копию БД.

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-07 14:00:00.000000+00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # RENAME COLUMN — и в PostgreSQL, и в SQLite ≥ 3.25: таблица не пересоздаётся, CHECK,
    # UNIQUE и каскад остаются; представления annotation_marks не читают.
    op.execute("ALTER TABLE annotation_marks RENAME COLUMN heard_letter TO heard")


def downgrade() -> None:
    op.execute("ALTER TABLE annotation_marks RENAME COLUMN heard TO heard_letter")
