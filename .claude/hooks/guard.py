#!/usr/bin/env python3
"""PreToolUse: правила, которые агент не может нарушить (ADR-0011, ADR-0012, NFR-SEC-01).

1. Секреты и данные учеников не читаются: .env, data/, дампы БД.
2. Фаза меняется только через scripts/phase.
3. В фазе impl тесты заморожены.
4. Опасные команды git/shell запрещены.
5. Данные пилота не уничтожаются: удаление тома БД, откат миграций, восстановление поверх
   рабочей базы, DROP/TRUNCATE/DELETE через консоль БД — только человек.
Типовые обходы через shell ловятся регулярками; хитрый обход ловят CI и ревью diff.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _common import ROOT, block, phase, read_event

FILE_TOOLS = {"Read", "Edit", "Write", "MultiEdit", "NotebookEdit"}
WRITE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}

SECRET_PATH = re.compile(r"(^|/)\.env(\.[^/]*)?$")
SECRET_PATH_OK = re.compile(r"(^|/)\.env\.example$")
PRIVATE_DIRS = ("data/",)
DB_DUMP = re.compile(r"\.(sqlite3?|db|dump|sql\.gz|bak)$")

SHELL_SECRET = re.compile(
    r"(\.env(?!\.example)\b|(^|[\s/'\"])data/(audio|exports|annotation)|\.sqlite3?\b|progress\.db"
    r"|\bpg_dump\b|\bprintenv\b|(^|\s)env(\s|$)|BOT_TOKEN|DATABASE_URL)"
)
SHELL_DANGER = re.compile(
    r"(--no-verify|git\s+push\s+.*(--force|-f\b)|git\s+reset\s+--hard|rm\s+-[a-z]*r[a-z]*f"
    r"|rm\s+-[a-z]*f[a-z]*r|git\s+clean\s+-[a-z]*f|chmod\s+-R\s+777)"
)
DB_DESTROY = re.compile(
    r"(docker[\s-]+compose\b[^|;&]*\bdown\b[^|;&]*(\s-v\b|\s--volumes\b)"
    r"|docker\s+volume\s+(rm|prune)\b|docker\s+system\s+prune\b[^|;&]*--volumes"
    r"|\balembic\b[^|;&]*\bdowngrade\b|\bmake\s+restore\b|\bpg_restore\b|\bdropdb\b"
    r"|--delete-orphans|\brm\b[^|;&]*(^|\s)\.?/?data\b|\bfind\b[^|;&]*\bdata\b[^|;&]*-delete"
    r"|(^|[;&|]\s*)(sh\s+|bash\s+)?\.?/?scripts/db/restore)",
    re.IGNORECASE,
)
SQL_CLIENT = re.compile(r"\b(psql|db-shell|sqlite3)\b")
SQL_DESTROY = re.compile(
    r"\b(drop\s+(table|database|schema|view|role|owned)|truncate|delete\s+from|alter\s+table)\b",
    re.IGNORECASE,
)
SHELL_WRITES_TESTS = re.compile(
    r"(>>?|\btee\b|\bsed\s+-i|\bperl\s+-[a-z]*i|\bcp\b|\bmv\b|\brm\b|\btouch\b|python3?\s+-c|\bgit\s+(checkout|restore)\b)"
    r".*\btests/"
)


def _rel(path: str) -> str:
    try:
        return Path(path).resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path


def check_file(tool: str, target: str) -> None:
    rel = _rel(target)
    if SECRET_PATH.search(rel) and not SECRET_PATH_OK.search(rel):
        block(f"Запрещено: {rel} содержит секреты. Шаблон настроек — .env.example.")
    if rel.startswith(PRIVATE_DIRS) or DB_DUMP.search(rel):
        block(f"Запрещено: {rel} — данные учеников. Для анализа используйте muallim-research.")
    if tool in WRITE_TOOLS and rel == ".agent-phase":
        block("Фазу меняют только через scripts/phase.")
    if tool in WRITE_TOOLS and phase() == "impl" and rel.startswith("tests/"):
        block("Фаза impl: тесты заморожены. Если тест неверен — остановись и спроси человека.")


def check_shell(command: str) -> None:
    if SHELL_SECRET.search(command):
        block("Запрещено: команда обращается к секретам или данным учеников.")
    if SHELL_DANGER.search(command):
        block("Запрещено: опасная команда (--no-verify, force push, reset --hard, rm -rf...).")
    if DB_DESTROY.search(command) or (SQL_CLIENT.search(command) and SQL_DESTROY.search(command)):
        block(
            "Запрещено: команда может уничтожить данные пилота (том БД, откат миграций, "
            "восстановление, DROP/TRUNCATE/DELETE). Это делает человек — сначала make backup."
        )
    if ".agent-phase" in command and not command.lstrip().startswith("scripts/phase"):
        block("Фазу меняют только через scripts/phase.")
    if phase() == "impl" and SHELL_WRITES_TESTS.search(command):
        block("Фаза impl: тесты заморожены. Если тест неверен — остановись и спроси человека.")


def main() -> None:
    event = read_event()
    tool = str(event.get("tool_name", ""))
    args = event.get("tool_input") or {}
    if tool in FILE_TOOLS:
        check_file(tool, str(args.get("file_path") or args.get("notebook_path") or ""))
    elif tool == "Bash":
        check_shell(str(args.get("command", "")))
    elif tool in {"Grep", "Glob"}:
        target = str(args.get("path", ""))
        if target:
            check_file(tool, target)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        block(f"guard.py упал ({type(exc).__name__}) — действие отменено, сообщи человеку.")
