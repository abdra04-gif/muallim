"""Слабые места архитектуры (docs/architecture/change-scenarios.md), закрытые проверками.

Состояние разговора — в FSM aiogram, а не в словарях модулей: иначе два диспетчера (тесты, режим
--test, второй процесс) делят одно состояние, а замена хранилища требует правки обработчиков.
Обработчики ученика разбиты по темам, чтобы новая функция не растила один файл.
"""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TELEGRAM = ROOT / "src" / "muallim" / "presentation" / "telegram"
pytestmark = pytest.mark.architecture

MUTABLE_CALLS = {"dict", "set", "list", "defaultdict", "OrderedDict", "deque"}
HANDLER_MODULE_MAX_LINES = 250


def _is_mutable(value: ast.expr | None) -> bool:
    if isinstance(value, ast.Dict | ast.Set | ast.List | ast.DictComp | ast.SetComp | ast.ListComp):
        return True
    return (
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Name)
        and value.func.id in MUTABLE_CALLS
    )


def _is_final(node: ast.Assign | ast.AnnAssign) -> bool:
    """Константа — ``Final`` и имя заглавными; ``_cache: Final = {}`` — это состояние."""
    if not isinstance(node, ast.AnnAssign) or not isinstance(node.target, ast.Name):
        return False
    if not node.target.id.lstrip("_").isupper():
        return False
    ann = node.annotation
    target = ann.value if isinstance(ann, ast.Subscript) else ann
    return isinstance(target, ast.Name) and target.id == "Final"


@pytest.mark.parametrize(
    "path", sorted(TELEGRAM.rglob("*.py")), ids=lambda p: str(p.relative_to(TELEGRAM))
)
def test_no_module_level_mutable_state(path: Path) -> None:
    """Изменяемые словари и множества на уровне модуля запрещены; константы — только Final."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    offenders = [
        f"{path.name}:{node.lineno}"
        for node in tree.body
        if isinstance(node, ast.Assign | ast.AnnAssign)
        and _is_mutable(node.value)
        and not _is_final(node)
    ]
    assert not offenders, f"состояние на уровне модуля (перенести в FSM или Display): {offenders}"


def test_learner_handlers_are_split_by_topic() -> None:
    package = TELEGRAM / "handlers"
    assert package.is_dir(), "обработчики ученика — пакет handlers/ с модулями по темам"
    long = {
        p.name: n
        for p in package.glob("*.py")
        if (n := len(p.read_text(encoding="utf-8").splitlines())) > HANDLER_MODULE_MAX_LINES
    }
    assert not long, f"модули обработчиков длиннее {HANDLER_MODULE_MAX_LINES} строк: {long}"


def test_errors_router_is_connected() -> None:
    """Перехватчик сбоев — отдельный роутер в ``routers()``: ловит и ученика, и разметчика."""
    from muallim.bootstrap.main import routers  # noqa: PLC0415

    names = [r.name for r in routers()]
    assert "errors" in names
    assert names.index("annotator") < names.index("learner"), "разметчик раньше ученика"


def test_docker_image_is_built_in_ci() -> None:
    """Поломку образа (как права на /app/logs) видно в CI, а не при развёртывании."""
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "docker build" in ci
    assert "docker run" in ci and "import muallim.bootstrap.main" in ci, "образ надо и запустить"
