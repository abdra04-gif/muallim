"""Настройки: отдельный вход для миграций (ADR-0054)."""

from pydantic import SecretStr

from muallim.bootstrap.config import Settings


def test_migrations_use_owner_url_when_set() -> None:
    s = Settings(
        _env_file=None,
        bot_token=SecretStr("x"),
        database_url=SecretStr("postgresql+asyncpg://app@h/db"),
        migration_database_url=SecretStr("owner-url"),
    )
    assert s.migration_url() == "owner-url"


def test_migrations_fall_back_to_bot_url() -> None:
    s = Settings(_env_file=None, bot_token=SecretStr("x"), database_url=SecretStr("sqlite:///x"))
    assert s.migration_url() == "sqlite:///x"
