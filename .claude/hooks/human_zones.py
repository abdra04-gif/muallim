#!/usr/bin/env python3
"""PreToolUse: правка «зоны человека» (CLAUDE.md, «Только человек») — только с подтверждения.

Агент не блокируется, а останавливается и спрашивает человека (permissionDecision = ask):
учебный контент, тексты ученику, пороги и методика, параметры чтения, схема БД, зависимости,
сами проверки. Причина видна человеку в запросе подтверждения (ADR-0034).
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _common import ROOT, log_event, read_event

WRITE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}

ZONES: tuple[tuple[str, str], ...] = (
    ("curriculum/", "учебный контент и эталонные записи"),
    ("scripts/book/", "расшифровка книги"),
    ("src/muallim/presentation/telegram/texts.py", "тексты ученику и согласие"),
    ("src/muallim/domain/policy.py", "пороги и методика"),
    ("src/muallim/infrastructure/asr/muaalem.py", "параметры чтения MOSHAF_PARAMS"),
    ("docs/pedagogy/methodology.md", "методика"),
    ("src/muallim/research/metrics.py", "оценщик RQ-1: метрику не правит тот, кого оценивают"),
    ("src/muallim/infrastructure/db/tables.py", "схема БД"),
    ("migrations/versions/", "схема БД"),
    ("pyproject.toml", "зависимости и настройки проверок"),
    ("uv.lock", "зависимости"),
    (".claude/hooks/", "проверки агента"),
    (".claude/settings.json", "проверки и права агента"),
    (".pre-commit-config.yaml", "проверки"),
    (".github/workflows/", "CI"),
)

SHELL_DEPS = re.compile(r"\b(uv\s+(add|remove)|uv\s+pip\s+install|pip3?\s+install|poetry\s+add)\b")


def _rel(path: str) -> str:
    try:
        return Path(path).resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path


def zone_of(rel: str) -> str | None:
    for prefix, what in ZONES:
        if rel == prefix or (prefix.endswith("/") and rel.startswith(prefix)):
            return what
    return None


def ask(reason: str) -> None:
    log_event("ask", reason)
    decision = {
        "hookEventName": "PreToolUse",
        "permissionDecision": "ask",
        "permissionDecisionReason": reason,
    }
    print(json.dumps({"hookSpecificOutput": decision}, ensure_ascii=False))
    sys.exit(0)


def main() -> None:
    event = read_event()
    tool = str(event.get("tool_name", ""))
    args = event.get("tool_input") or {}
    if tool in WRITE_TOOLS:
        rel = _rel(str(args.get("file_path") or args.get("notebook_path") or ""))
        what = zone_of(rel)
        if what:
            ask(f"Зона человека ({what}): {rel}. Подтвердите правку — CLAUDE.md, «Только человек».")
    elif tool == "Bash" and SHELL_DEPS.search(str(args.get("command", ""))):
        ask("Новая зависимость — решение человека (CLAUDE.md). Подтвердите установку.")


if __name__ == "__main__":
    main()
