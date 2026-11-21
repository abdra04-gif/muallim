"""Три входа в PostgreSQL (TD-DB-01, ADR-0054): миграции, бот, просмотр.

- ``muallim_owner`` — владелец таблиц, только он меняет схему (миграции);
- ``muallim_app`` — бот и инструменты исследования: читать и писать строки, схему не трогать;
- ``muallim_reader`` — DBeaver и отчёты: только чтение, без Telegram ID.

Запускается, только если задан TEST_POSTGRES_URL (суперпользователь тестовой базы).
"""

import asyncio
import os
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

import asyncpg  # type: ignore[import-untyped]  # у asyncpg нет аннотаций типов
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url

from muallim.domain.assessment import assess
from muallim.domain.attempt import Attempt
from muallim.domain.learner import Learner
from muallim.domain.policy import Verdict
from muallim.infrastructure.db.engine import create_engine, create_session_factory
from muallim.infrastructure.db.repositories.attempts import SqlAttemptRepository
from muallim.infrastructure.db.repositories.events import SqlEventLog
from muallim.infrastructure.db.repositories.learners import SqlLearnerRepository
from tests.fakes import FixedClock

ROOT = Path(__file__).resolve().parents[2]
URL = os.environ.get("TEST_POSTGRES_URL", "")
pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(not URL, reason="TEST_POSTGRES_URL не задан"),
]
PASSWORDS = {
    "owner": "owner-pass", "app": "app-pass", "reader": "reader-pass", "agent": "agent-pass"
}  # fmt: skip
DENIED = (asyncpg.InsufficientPrivilegeError, asyncpg.ReadOnlySQLTransactionError)


def _url(role: str | None = None, *, driver: str = "postgresql+asyncpg") -> str:
    url = make_url(URL).set(drivername=driver)
    if role is not None:
        url = url.set(username=f"muallim_{role}", password=PASSWORDS[role])
    return url.render_as_string(hide_password=False)


def _roles_sql() -> str:
    """scripts/db/roles.sql с подставленными переменными psql (:'имя')."""
    sql = (ROOT / "scripts" / "db" / "roles.sql").read_text(encoding="utf-8")
    for role, password in PASSWORDS.items():
        sql = sql.replace(f":'{role}_password'", "'" + password.replace("'", "''") + "'")
    return sql


async def _run(script: str, role: str | None = None) -> None:
    con = await asyncpg.connect(_url(role, driver="postgresql"))
    try:
        await con.execute(script)
    finally:
        await con.close()


def _alembic(revision: str, *, up: bool, role: str | None = None) -> None:
    cfg = Config(ROOT / "alembic.ini")
    cfg.attributes.update(url=_url(role), configure_logger=False)
    (command.upgrade if up else command.downgrade)(cfg, revision)


@pytest.fixture
def roles() -> Iterator[None]:
    _alembic("head", up=True)  # как сейчас: таблицы созданы суперпользователем
    asyncio.run(_run(_roles_sql()))
    yield
    _alembic("base", up=False)
    asyncio.run(
        _run(
            "DROP TABLE IF EXISTS t_new, alembic_version CASCADE;"
            # по одной роли: общий DROP OWNED спотыкается о права по умолчанию (default ACL)
            "DROP OWNED BY muallim_owner CASCADE;"
            "DROP OWNED BY muallim_app CASCADE;"
            "DROP OWNED BY muallim_reader CASCADE;"
            "DROP OWNED BY muallim_agent CASCADE;"
            "DROP ROLE muallim_owner, muallim_app, muallim_reader, muallim_agent;"
        )
    )


def test_bot_works_as_app(roles: None) -> None:
    async def scenario() -> int:
        engine = create_engine(_url("app"))
        clock = FixedClock()
        async with create_session_factory(engine)() as session:
            people, attempts = SqlLearnerRepository(session), SqlAttemptRepository(session)
            await people.add(
                Learner(UUID(int=1), 7, "L-1", "ru", clock.now(), research_consent=True)
            )
            result = assess("صَ", "سَ")
            await attempts.add(
                Attempt(
                    UUID(int=2), UUID(int=1), "L01-14", "v1", "m", result, Verdict.FAILED,
                    "a" * 64, 900, 10, clock.now(),
                ),
                ("msg",),
            )  # fmt: skip
            await SqlEventLog(session, clock).record(
                "x", UUID(int=1), {"k": 1}
            )  # последовательность
            await session.commit()
            await attempts.forget_audio(UUID(int=1))  # UPDATE и DELETE разметки
            await people.delete(UUID(int=1))  # каскад работает и без прав владельца
            await session.commit()
            count = await attempts.count(UUID(int=1))
        await engine.dispose()
        return count

    assert asyncio.run(scenario()) == 0


@pytest.mark.parametrize(
    "statement",
    [
        "CREATE TABLE x (i int)",
        "DROP TABLE attempts",
        "TRUNCATE annotations",
        "ALTER TABLE attempts ADD COLUMN x int",
        "DROP VIEW v_errors",
        "UPDATE alembic_version SET version_num = '0001'",  # версию схемы меняют только миграции
    ],
)
def test_app_cannot_change_schema(roles: None, statement: str) -> None:
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        asyncio.run(_run(statement, "app"))


def test_reader_reads_views_but_not_telegram_ids(roles: None) -> None:
    async def scenario() -> list[tuple[str, str]]:
        con = await asyncpg.connect(_url("reader", driver="postgresql"))
        try:
            await con.fetch("SELECT * FROM v_attempts")
            await con.fetch("SELECT * FROM v_errors")
            await con.fetch("SELECT pseudonym, research_consent FROM learners")
            with pytest.raises(DENIED):
                await con.execute("INSERT INTO annotators (code, created_at) VALUES ('X', now())")
            hidden = await con.fetch(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND column_name LIKE '%telegram%'"
            )
            readable = []
            for row in hidden:
                try:
                    # имена — из information_schema этой же базы, не от пользователя
                    await con.fetch(f'SELECT "{row[1]}" FROM "{row[0]}" LIMIT 1')  # noqa: S608
                    readable.append((row[0], row[1]))
                except asyncpg.InsufficientPrivilegeError:
                    pass
            return readable
        finally:
            await con.close()

    assert asyncio.run(scenario()) == []


def test_owner_migrates_and_new_tables_reach_app_and_reader(roles: None) -> None:
    _alembic("-1", up=False, role="owner")
    _alembic("head", up=True, role="owner")
    asyncio.run(_run("CREATE TABLE t_new (i int)", "owner"))
    asyncio.run(_run("INSERT INTO t_new VALUES (1)", "app"))
    asyncio.run(_run("SELECT * FROM t_new", "reader"))


def test_roles_are_not_superusers_and_script_is_repeatable(roles: None) -> None:
    asyncio.run(_run(_roles_sql()))  # повторный запуск (смена паролей) — без ошибок

    async def flags() -> list[tuple[str, bool, bool]]:
        con = await asyncpg.connect(_url(driver="postgresql"))
        try:
            rows = await con.fetch(
                "SELECT rolname, rolsuper, rolcreaterole FROM pg_roles "
                "WHERE rolname LIKE 'muallim_%' ORDER BY rolname"
            )
            return [(r[0], r[1], r[2]) for r in rows]
        finally:
            await con.close()

    assert asyncio.run(flags()) == [
        ("muallim_agent", False, False),  # вход ИИ-агента (TD-FN-174)
        ("muallim_app", False, False),
        ("muallim_owner", False, False),
        ("muallim_reader", False, False),
    ]


# ---------- вход агента: только учебная часть (TD-FN-174, ADR-0090, шаг 2б) ----------
_SEED = """
INSERT INTO learners (id, telegram_user_id, pseudonym, language, created_at, research_consent,
    blocked_bot)
VALUES ('00000000-0000-0000-0000-000000000001', 7, 'L-1', 'ru', now(), true, false);
INSERT INTO attempts (id, learner_id, item_id, curriculum_version, model_version,
    reference_phonemes, heard_phonemes, score, verdict, processing_ms, created_at, split)
VALUES
 ('00000000-0000-0000-0000-00000000000a', '00000000-0000-0000-0000-000000000001', 'L03-04', 'v',
  'm', 'a', 'a', 100, 'excellent', 1, now(), 'train'),
 ('00000000-0000-0000-0000-00000000000b', '00000000-0000-0000-0000-000000000001', 'L03-04', 'v',
  'm', 'a', 'b', 0, 'failed', 1, now(), 'test');
INSERT INTO detected_errors (attempt_id, ordinal, kind, position, expected, heard, message)
VALUES ('00000000-0000-0000-0000-00000000000a', 0, 'substitution', 0, 'a', 'a', ''),
       ('00000000-0000-0000-0000-00000000000b', 0, 'substitution', 0, 'a', 'b', '');
"""


def test_agent_sees_only_the_training_part(roles: None) -> None:
    """Фильтр строк PostgreSQL: агент пишет обычные запросы, тестовых строк ему не отдают —
    ни в таблицах, ни через представления, ни в связанных таблицах (ошибки, разметка)."""
    asyncio.run(_run(_SEED))

    async def scenario() -> dict[str, list[str]]:
        con = await asyncpg.connect(_url("agent", driver="postgresql"))
        try:
            return {
                "attempts": [r[0] for r in await con.fetch("SELECT split FROM attempts")],
                "errors": [r[0] for r in await con.fetch("SELECT heard FROM detected_errors")],
                "view": [r[0] for r in await con.fetch("SELECT heard_phonemes FROM v_attempts")],
            }
        finally:
            await con.close()

    assert asyncio.run(scenario()) == {"attempts": ["train"], "errors": ["a"], "view": ["a"]}


def test_bot_and_reader_still_see_both_parts(roles: None) -> None:
    asyncio.run(_run(_SEED))

    async def count(role: str) -> int:
        con = await asyncpg.connect(_url(role, driver="postgresql"))
        try:
            return int(await con.fetchval("SELECT count(*) FROM attempts"))
        finally:
            await con.close()

    assert asyncio.run(count("app")) == 2 and asyncio.run(count("reader")) == 2


@pytest.mark.parametrize(
    "statement",
    [
        "INSERT INTO annotators (code, created_at) VALUES ('X', now())",
        "UPDATE attempts SET split = 'train'",
        "DELETE FROM attempts",
        "SELECT telegram_user_id FROM learners",
        "SELECT * FROM learner_names",
        # в журнале действий — оценки и итоги разметки и тестовых попыток
        "SELECT * FROM interaction_events",
    ],
)
def test_agent_reads_only_and_without_personal_ids(roles: None, statement: str) -> None:
    with pytest.raises(DENIED):
        asyncio.run(_run(statement, "agent"))
