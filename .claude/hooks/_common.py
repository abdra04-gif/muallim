"""Общее для хуков: корень проекта, чтение события, текущая TDD-фаза, журнал срабатываний."""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


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


def read_event() -> dict[str, Any]:
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


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
