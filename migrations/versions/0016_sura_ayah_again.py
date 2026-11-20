"""Аят суры на MostafaMaroof: исход «ещё раз» (``again``) и JSON ``model_output`` — FR-70 ч. 7,
ADR-0088 «Суры».

Каждый аят суры решается «вариантами карточки»: исход ``again``, когда модель не уверена; маржи,
победивший вариант, вид ошибки и был ли второй проход — в ``sura_reading_ayahs.model_output``
(у чтений Muaalem — NULL). Старые аяты не меняются. Откат: ``again`` → ``pronunciation`` (прежнее
«не засчитано»: прочитан, но не чисто), столбец удаляется. Описание полей:
docs/data/data-dictionary.md. Перед миграцией make migrate делает копию БД.

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-20 18:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Замороженные значения (тест сверяет с перечислением AyahOutcome в коде).
OLD_AYAH_OUTCOMES = ("clean", "pronunciation", "forgot_part", "skipped", "not_reached")
AYAH_OUTCOMES = (*OLD_AYAH_OUTCOMES, "again")
CHECK = "ck_sura_reading_ayahs_outcome_values"


def _one_of(column: str, values: Sequence[str]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _change(values: Sequence[str], *, add_output: bool) -> None:
    bind = op.get_bind()
    sqlite = bind.dialect.name == "sqlite"
    # SQLite пересоздаёт таблицу; представления (v_*) снимаем и ставим обратно тем же текстом
    saved = (
        bind.exec_driver_sql(
            "SELECT name, sql FROM sqlite_master WHERE type = 'view' ORDER BY name"
        ).all()
        if sqlite
        else []
    )
    for name, _ in saved:
        op.execute(f'DROP VIEW "{name}"')
    with op.batch_alter_table("sura_reading_ayahs") as batch:
        batch.drop_constraint(op.f(CHECK), type_="check")
        batch.create_check_constraint(op.f(CHECK), _one_of("outcome", values))
        if add_output:
            batch.add_column(sa.Column("model_output", sa.JSON(), nullable=True))
        else:
            batch.drop_column("model_output")
    for _, sql in saved:
        op.execute(sql)


def upgrade() -> None:
    _change(AYAH_OUTCOMES, add_output=True)


def downgrade() -> None:
    op.execute("UPDATE sura_reading_ayahs SET outcome = 'pronunciation' WHERE outcome = 'again'")
    _change(OLD_AYAH_OUTCOMES, add_output=False)
