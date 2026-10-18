"""Хук dep_check: новая библиотека проверяется на PyPI до установки (ADR-0046). Без сети."""

import importlib.util
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.architecture


@pytest.fixture(scope="module")
def hook() -> ModuleType:
    path = ROOT / ".claude" / "hooks" / "dep_check.py"
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location("dep_check", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("uv add structlog", ["structlog"]),
        ("uv add 'httpx>=0.27' Rich_Text", ["httpx", "rich-text"]),
        ("uv add --dev pytest-mock && make check", ["pytest-mock"]),
        ("uv add --group docs mkdocs", ["mkdocs"]),
        ("pip install -r requirements.txt", []),
        ("uv pip install ./local-wheel.whl", []),
        ("uv run pytest -q", []),
        ("echo uv add foo-bar", []),
        ("make check; uv add rich>=13", ["rich"]),
    ],
)
def test_packages_in_command(hook: ModuleType, command: str, expected: list[str]) -> None:
    assert hook.packages_in_command(command) == expected


def test_new_requirements_only_added_lines(hook: ModuleType) -> None:
    old = 'dependencies = [\n    "aiogram~=3.31",\n]'
    new = (
        'dependencies = [\n    "aiogram~=3.31",\n    "structlog>=24",\n    "httpx[http2]>=0.27",\n]'
    )
    assert hook.new_requirements(old, new) == ["httpx", "structlog"]


def test_lookalike_catches_typo_of_known_dependency(hook: ModuleType) -> None:
    known = {"aiogram", "sqlalchemy", "pydantic"}
    assert hook.lookalike("aiogramm", known) == "aiogram"
    assert hook.lookalike("sqlalchemy", known) is None
    assert hook.lookalike("structlog", known) is None


def test_warnings_flag_young_package_without_repo(hook: ModuleType) -> None:
    info = {"summary": "", "project_urls": {"Homepage": "https://example.org"}}
    flags = hook.warnings(info, datetime.now(UTC) - timedelta(days=5), vulns=2)
    assert len(flags) == 4  # нет репозитория, новый, нет описания, уязвимости


def test_warnings_quiet_for_mature_package(hook: ModuleType) -> None:
    info = {"summary": "Fast", "project_urls": {"Source": "https://github.com/a/b"}}
    assert hook.warnings(info, datetime(2015, 1, 1, tzinfo=UTC), vulns=0) == []


def test_quoted_settings_are_not_dependencies(hook: ModuleType) -> None:
    """Коды правил ruff, версия Python, плагины mypy — не пакеты (ложный блок правки настроек)."""
    old = 'select = ["E", "F"]'
    new = 'select = ["E", "F", "PLC0415"]\npython_version = "3.12"\nplugins = ["pydantic.mypy"]'
    assert hook.new_requirements(old, new) == []
    assert hook.new_requirements("", 'requires-python = ">=3.12"') == []
