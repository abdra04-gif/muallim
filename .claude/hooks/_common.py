"""Общее для хуков: корень проекта, чтение события, текущая TDD-фаза, журнал срабатываний."""

import json
import sys
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from typing import Any

# Основная папка проекта: хуки всегда запускаются отсюда, даже из сессии в копии (worktree).
MAIN = Path(__file__).resolve().parents[2]
WORKTREES = MAIN / ".claude" / "worktrees"


@cache
def read_event() -> dict[str, Any]:
    """Событие из stdin; читается один раз — его нужны и ROOT, и самому хуку."""
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def worktree_of(cwd: object) -> Path | None:
    """Копия `.claude/worktrees/<имя>`, в которой работает сессия, или None (ADR-0073)."""
    if not isinstance(cwd, str) or not cwd:
        return None
    try:
        rel = Path(cwd).resolve().relative_to(WORKTREES)
    except ValueError:
        return None
    if not rel.parts:
        return None
    tree = WORKTREES / rel.parts[0]
    return tree if (tree / ".git").exists() else None


# Корень, который проверяют хуки: копия сессии, если она в копии, иначе основная папка.
ROOT = worktree_of(read_event().get("cwd")) or MAIN


def log_event(kind: str, reason: str) -> None:
    """Строка в docs/journal/hooks/ГГГГ-ММ.jsonl — данные для Q6.1 (что блокируют проверки).

    Пишется только первая строка причины (до 160 знаков): без команд, вывода тестов и путей
    к данным. Сбой записи не мешает хуку.
    """
    now = datetime.now(UTC)
    record = {
        "ts": now.isoformat(timespec="seconds"),
        "hook": Path(sys.argv[0]).stem,
        "kind": kind,
        "reason": reason.strip().splitlines()[0][:160] if reason.strip() else "",
    }
    try:
        log_dir = ROOT / "docs" / "journal" / "hooks"
        log_dir.mkdir(parents=True, exist_ok=True)
        with (log_dir / f"{now:%Y-%m}.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass


def phase() -> str:
    try:
        return (ROOT / ".agent-phase").read_text(encoding="utf-8").strip() or "off"
    except OSError:
        return "off"


def block(reason: str) -> None:
    """exit 2: действие отменяется, причина уходит агенту."""
    log_event("block", reason)
    print(reason, file=sys.stderr)
    sys.exit(2)
