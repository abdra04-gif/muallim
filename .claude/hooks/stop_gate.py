#!/usr/bin/env python3
"""Stop: не даёт агенту закончить, пока код не проходит архитектуру, типы и тесты (петля harness).

Срабатывает, только если в рабочем дереве изменены src/, tests/ или migrations/.
Повторный Stop после блокировки (stop_hook_active) пропускается, чтобы не зациклиться навсегда:
агент получает ошибки ровно один раз за попытку завершиться.
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _common import ROOT, block, read_event

WATCHED = ("src/", "tests/", "migrations/")


def changed_code() -> bool:
    result = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True, check=False
    )
    return any(line[3:].startswith(WATCHED) for line in result.stdout.splitlines())


def run(*cmd: str) -> tuple[bool, str]:
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=False)
    return result.returncode == 0, (result.stdout + result.stderr)[-2500:]


def main() -> None:
    event = read_event()
    if event.get("stop_hook_active") or not changed_code():
        return
    problems = []
    ok, out = run("uv", "run", "--quiet", "lint-imports")
    if not ok:
        problems.append(f"Нарушена архитектура (ADR-0002):\n{out}")
    ok, out = run("uv", "run", "--quiet", "mypy")
    if not ok:
        problems.append(f"Типы не сходятся (mypy --strict):\n{out}")
    ok, out = run(
        "uv", "run", "--quiet", "pytest", "-q", "-x", "--no-header", "-p", "no:cacheprovider"
    )
    if not ok:
        problems.append(f"Тесты не проходят:\n{out}")
    if problems:
        block("Нельзя завершать: исправь и проверь снова.\n\n" + "\n\n".join(problems))


if __name__ == "__main__":
    main()
