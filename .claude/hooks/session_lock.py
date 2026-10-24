#!/usr/bin/env python3
"""Одна сессия правит основную папку, остальные — в своих копиях (worktree) (ADR-0073).

Метка «чья основная папка» лежит в `.git/claude-main-session.json`: id сессии и время её последнего
действия. Сессия получает метку при первой правке в основной папке, продлевает её каждым действием
и снимает при выходе. Метка без действий дольше STALE_MIN минут считается брошенной.

- SessionStart: папка занята другой сессией → в контекст строка «перейди в копию».
- PreToolUse: правка или git-запись в основной папке, когда метка у другой живой сессии, — блок.
  Чтение не блокируется: вопросы и поиск в основной папке не мешают никому.
- UserPromptSubmit: продлить свою метку. SessionEnd: снять свою метку.

Сбой самого хука действие не блокирует (fail-open): он защищает от гонки, а не от утечки.
"""

import json
import re
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
from _common import MAIN, WORKTREES, block, log_event, read_event, worktree_of

STALE_MIN = 30
LOCK = MAIN / ".git" / "claude-main-session.json"
EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
WRITING_BASH = re.compile(
    r"\bgit\s+(add|commit|push|pull|reset|checkout|switch|stash|merge|rebase|restore|"
    r"cherry-pick|revert|rm|mv|apply|am|tag)\b|\bscripts/phase\b|\bmake\s+(migrate|migration|run)"
)


def load() -> dict[str, Any]:
    try:
        data = json.loads(LOCK.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save(session: str) -> None:
    tmp = LOCK.with_suffix(".tmp")
    tmp.write_text(json.dumps({"session": session, "ts": time.time()}), encoding="utf-8")
    tmp.replace(LOCK)


def minutes_ago(owner: dict[str, Any]) -> float:
    ts = owner.get("ts")
    return (time.time() - ts) / 60 if isinstance(ts, int | float) else float("inf")


def busy_by_other(owner: dict[str, Any], me: str) -> bool:
    return (
        bool(owner.get("session")) and owner.get("session") != me and minutes_ago(owner) < STALE_MIN
    )


def in_main(path: object) -> bool:
    """Путь внутри основной папки, но не в копии."""
    if not isinstance(path, str) or not path:
        return False
    p = Path(path)
    p = (p if p.is_absolute() else MAIN / p).resolve()
    return p.is_relative_to(MAIN) and not p.is_relative_to(WORKTREES)


def writes_main(event: dict[str, Any]) -> bool:
    tool = event.get("tool_name")
    args = event.get("tool_input") or {}
    if tool in EDIT_TOOLS:
        return in_main(args.get("file_path") or args.get("notebook_path"))
    if tool == "Bash":
        return bool(WRITING_BASH.search(str(args.get("command", ""))))
    return False


def main() -> None:
    event = read_event()
    me = str(event.get("session_id") or "")
    name = event.get("hook_event_name")
    if not me or not LOCK.parent.is_dir():
        return
    owner = load()
    mine = owner.get("session") == me

    if name == "SessionEnd":
        if mine:
            LOCK.unlink(missing_ok=True)
        return
    if name == "SessionStart":
        if busy_by_other(owner, me):
            print(
                f"- ⚠ Основная папка занята другой сессией (действие {minutes_ago(owner):.0f} мин "
                "назад). Если задача меняет файлы — первым действием EnterWorktree "
                "(CLAUDE.md → «Параллельные сессии», ADR-0073)."
            )
        return
    if worktree_of(event.get("cwd")):
        if mine:  # сессия ушла в копию — основная папка свободна
            LOCK.unlink(missing_ok=True)
        return
    if name == "UserPromptSubmit":
        if mine:
            save(me)
        return
    # PreToolUse в основной папке
    if not writes_main(event):
        if mine:
            save(me)
        return
    if busy_by_other(owner, me):
        block(
            "Основную папку сейчас правит другая сессия Claude (последнее действие "
            f"{minutes_ago(owner):.0f} мин назад) — правки и коммиты смешаются. Перейди в свою "
            "копию: EnterWorktree (имя — коротко по задаче) и повтори действие там (ADR-0073). "
            f"Та сессия закрыта? Метка снимется сама через {STALE_MIN} мин без действий."
        )
    save(me)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — fail-open: сбой замка не должен останавливать работу
        log_event("error", f"session_lock: {type(exc).__name__}")
