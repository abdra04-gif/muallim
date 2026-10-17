"""Правила архитектуры (ADR-0002) проверяются автоматически, а не на словах."""

import ast
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "muallim"
pytestmark = pytest.mark.architecture


def test_import_contracts_kept() -> None:
    lint_imports = Path(sys.executable).parent / "lint-imports"
    result = subprocess.run(  # noqa: S603 — фиксированная команда без пользовательского ввода
        [str(lint_imports)], cwd=ROOT, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr


def _modules(layer: str) -> list[Path]:
    return sorted((SRC / layer).rglob("*.py"))


@pytest.mark.parametrize("path", _modules("domain"), ids=lambda p: p.name)
def test_domain_has_no_io(path: Path) -> None:
    """Домен не читает файлы, не ходит в сеть и не спит: только вычисления."""
    banned = {"open", "print", "input"}
    banned_modules = {"os", "pathlib", "socket", "asyncio", "subprocess", "time", "logging"}
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in banned, f"{path.name}: вызов {node.func.id}()"
        if isinstance(node, ast.Import | ast.ImportFrom):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module]
            for name in names:
                assert (name or "").split(".")[0] not in banned_modules, f"{path.name}: {name}"


@pytest.mark.parametrize("path", _modules("presentation"), ids=lambda p: p.name)
def test_handlers_do_not_touch_database(path: Path) -> None:
    """В обработчиках нет SQL: только вызов сценария (thin handlers)."""
    source = path.read_text(encoding="utf-8")
    assert "sqlalchemy" not in source and "session" not in source.lower(), path.name


def test_every_use_case_is_wired_in_di() -> None:
    di = (SRC / "bootstrap" / "di.py").read_text(encoding="utf-8")
    for path in _modules("application/use_cases"):
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            if isinstance(node, ast.ClassDef) and any(
                isinstance(d, ast.Call) and getattr(d.func, "id", "") == "dataclass"
                for d in node.decorator_list
            ):
                is_use_case = any(
                    isinstance(f, ast.AsyncFunctionDef) and f.name == "execute" for f in node.body
                )
                if is_use_case:
                    assert node.name in di, f"{node.name} не зарегистрирован в bootstrap/di.py"
