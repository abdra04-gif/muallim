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
    calls: list[tuple[str, ast.Call]] = []
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        calls.extend(
            (f"{path.relative_to(ROOT)}:{node.lineno}", node)
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and _is_log_call(node)
        )
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


def _source(rel: str) -> ast.Module:
    return ast.parse((SRC / rel).read_text(encoding="utf-8"))


def _log_messages(tree: ast.AST) -> list[str]:
    return [
        node.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and _is_log_call(node)
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    ]


def test_log_file_is_outside_learner_data() -> None:
    """ADR-0048: файл логов — в ``logs/``, не в ``data/`` (там голоса), и не попадает в git."""
    from muallim.bootstrap.config import PROJECT_ROOT, Settings  # noqa: PLC0415

    default = Settings.model_fields["log_file"].default
    assert default is not None
    assert default.is_relative_to(PROJECT_ROOT / "logs")
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "logs/" in ignored


def test_bot_start_is_logged_with_versions() -> None:
    """По логу видно, какая версия кода, программы и модели работала (ADR-0048)."""
    messages = " ".join(_log_messages(_source("bootstrap/main.py")))
    for word in ("Запуск", "версия", "программа", "распознавание"):
        assert word in messages, f"в строке запуска нет «{word}»"


def test_every_assessed_attempt_is_logged() -> None:
    """Каждая проверенная попытка — строка лога: ID попытки, псевдоним, карточка, вердикт, время."""
    tree = _source("presentation/telegram/handlers/voice.py")
    voice = next(
        n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "on_voice"
    )
    messages = " ".join(_log_messages(voice))
    assert "Попытка" in messages


def test_unhandled_errors_are_caught_and_logged() -> None:
    """Сбой в обработчике не превращается в молчание: общий перехватчик ``router.errors``."""
    tree = _source("presentation/telegram/errors.py")
    handlers = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef)
        and any(
            isinstance(d, ast.Call) and getattr(d.func, "attr", "") == "errors"
            for d in n.decorator_list
        )
    ]
    assert handlers, "нет обработчика @router.errors()"
    calls = [
        n
        for n in ast.walk(handlers[0])
        if isinstance(n, ast.Call) and getattr(n.func, "attr", "") in {"exception", "error"}
    ]
    assert calls, "перехватчик ошибок ничего не пишет в лог"


def test_docker_bot_logs_to_console_only() -> None:
    """В контейнере ``/app`` принадлежит root, бот не создаст ``/app/logs`` и упадёт (ADR-0048)."""
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    assert compose["services"]["bot"]["environment"].get("LOG_FILE") == ""


def test_log_time_has_time_zone() -> None:
    """Сервер и ученики в разных поясах (TD-FN-16): время в логе — со смещением от UTC."""
    from muallim.bootstrap.logs import DATE_FORMAT  # noqa: PLC0415

    assert "%z" in DATE_FORMAT


def test_whole_bot_crash_is_logged() -> None:
    """Падение бота целиком (не в обработчике) тоже попадает в лог и файл, а не только в stderr."""
    tree = _source("bootstrap/main.py")
    run = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "run")
    assert "critical" in {
        getattr(n.func, "attr", "") for n in ast.walk(run) if isinstance(n, ast.Call)
    }


@pytest.mark.parametrize(
    ("module", "function", "word"),
    [
        ("presentation/telegram/handlers/voice.py", "on_voice", "этап"),
        ("presentation/telegram/handlers/voice.py", "on_voice", "Эталон"),
    ],
)
def test_key_events_are_logged(module: str, function: str, word: str) -> None:
    """Сбой распознавания — с карточкой и этапом; запись эталона учителем — строкой в логе."""
    tree = _source(module)
    func = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef) and n.name == function
    )
    assert word in " ".join(_log_messages(func)), f"{module}::{function}: нет строки «{word}»"


@pytest.mark.parametrize(
    ("module", "function"),
    [
        ("presentation/telegram/handlers/data.py", "cb_consent"),
        ("presentation/telegram/handlers/data.py", "cb_delete"),
        ("presentation/telegram/annotation.py", "_submit"),
    ],
)
def test_research_events_stay_out_of_logs(module: str, function: str) -> None:
    """Согласие, удаление и разметка — только в БД (ADR-0027 п. 4; решил автор 2026-10-18).

    Иначе псевдоним и факт согласия лежат ещё и в файле логов, а после /delete там остаётся след.
    """
    tree = _source(module)
    func = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef) and n.name == function
    )
    calls = [n for n in ast.walk(func) if isinstance(n, ast.Call) and _is_log_call(n)]
    assert not calls, f"{module}::{function}: событие исследования пишется в лог"
