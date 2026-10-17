"""Правила логирования (ADR-0027) проверяются автоматически.

В логах — только техника и псевдоним ученика. Никогда: Telegram ID, имя, текст сообщений, голос,
услышанные фонемы, секреты. События для исследования пишутся в ``interaction_events``, не в лог.
"""

import ast
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "muallim"
pytestmark = pytest.mark.architecture

LOG_METHODS = {"debug", "info", "warning", "error", "exception", "critical", "log"}
# Имена, которые нельзя передавать в лог: прямые идентификаторы, содержание, голос, секреты
FORBIDDEN = {
    "telegram_user_id", "from_user", "full_name", "first_name", "last_name", "username",
    "text", "caption", "heard", "phonemes", "audio", "voice", "buf",
    "bot_token", "database_url", "get_secret_value",
}  # fmt: skip


def _is_log_call(node: ast.Call) -> bool:
    func = node.func
    if not isinstance(func, ast.Attribute) or func.attr not in LOG_METHODS:
        return False
    owner = func.value
    if isinstance(owner, ast.Name):
        return owner.id in {"logger", "logging", "log"}
    return isinstance(owner, ast.Call) and getattr(owner.func, "attr", "") == "getLogger"


def _names(node: ast.AST) -> set[str]:
    found: set[str] = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name):
            found.add(sub.id)
        elif isinstance(sub, ast.Attribute):
            found.add(sub.attr)
    return found


def _log_calls() -> list[tuple[str, ast.Call]]:
    calls = []
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _is_log_call(node):
                calls.append((f"{path.relative_to(ROOT)}:{node.lineno}", node))
    return calls


def test_log_calls_are_found() -> None:
    """Защита от тихо сломанного поиска: в коде есть известные вызовы логгера."""
    assert len(_log_calls()) >= 3


@pytest.mark.parametrize(
    ("where", "call"), _log_calls(), ids=lambda x: x if isinstance(x, str) else ""
)
def test_no_personal_data_or_secrets_in_logs(where: str, call: ast.Call) -> None:
    args = [*call.args, *(k.value for k in call.keywords)]
    leaked = set().union(*(_names(a) for a in args)) & FORBIDDEN if args else set()
    assert not leaked, f"{where}: в лог передаётся {sorted(leaked)} (ADR-0027)"


def test_bot_configures_logging_through_one_place() -> None:
    """Фильтры секретов и шума ставит только ``configure_logging``; basicConfig в обход — нельзя."""
    offenders = []
    for path in sorted(SRC.rglob("*.py")):
        if path.name == "logs.py":
            continue
        if "basicConfig" in path.read_text(encoding="utf-8"):
            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, f"logging.basicConfig в обход configure_logging: {offenders}"


def test_docker_logs_are_rotated() -> None:
    """Срок хранения логов ограничен: Docker хранит не больше max-file × max-size на сервис."""
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    for name, service in compose["services"].items():
        options = (service.get("logging") or {}).get("options") or {}
        assert options.get("max-size") and options.get("max-file"), f"{name}: нет ротации логов"
