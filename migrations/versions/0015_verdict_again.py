"""Вердикт «прочитай ещё раз» (``again``) — FR-70, ADR-0088.

Проверка «варианты карточки» (MostafaMaroof) отвечает «ещё раз», когда модель не уверена; это
отдельный вердикт, чтобы после дообучения было видно, стал ли бот реже просить повторить. Старые
попытки не меняются. Откат: ``again`` → ``failed`` (до 0015 такого вердикта не было; данные не
теряются, старый бот их читает). Описание полей: docs/data/data-dictionary.md. Перед миграцией
make migrate делает копию БД.

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-19 18:00:00.000000+00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Замороженные значения (тест сверяет с перечислением Verdict в коде).
OLD_VERDICTS = ("excellent", "passed", "failed")
VERDICTS = (*OLD_VERDICTS, "again")
CHECK = "ck_attempts_verdict_values"


def _one_of(column: str, values: Sequence[str]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _swap_verdict_check(values: Sequence[str]) -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":  # PostgreSQL меняет ограничение на месте
        op.drop_constraint(op.f(CHECK), "attempts", type_="check")
        op.create_check_constraint(op.f(CHECK), "attempts", _one_of("verdict", values))
        return
    # SQLite пересоздаёт таблицу attempts, а на неё опираются представления (v_*): снимаем их и
    # ставим обратно тем же текстом, что был в БД.
    saved = bind.exec_driver_sql(
        "SELECT name, sql FROM sqlite_master WHERE type = 'view' ORDER BY name"
    ).all()
    for name, _ in saved:
        op.execute(f'DROP VIEW "{name}"')
    with op.batch_alter_table("attempts") as batch:
        batch.drop_constraint(op.f(CHECK), type_="check")
        batch.create_check_constraint(op.f(CHECK), _one_of("verdict", values))
    for _, sql in saved:
        op.execute(sql)


def upgrade() -> None:
    _swap_verdict_check(VERDICTS)


def downgrade() -> None:
    op.execute("UPDATE attempts SET verdict = 'failed' WHERE verdict = 'again'")
    _swap_verdict_check(OLD_VERDICTS)
