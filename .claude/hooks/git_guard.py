#!/usr/bin/env python3
"""PreToolUse (Bash): коммит и push только безопасные и проверенные (ADR-0039).

- `git add -f` запрещён: он обходит .gitignore (данные учеников, секреты, скан книги).
- `git commit`: в подготовленных файлах нет запрещённых путей и секретов (gitleaks).
- `git push`: обычные правки — быстрая проверка (слои, ruff и тесты изменённых файлов);
  важные (код бота, зависимости, миграции, программа) — сначала спросить автора, нужна ли полная
  проверка: `CHECK=full git push` (mypy и все тесты) или `CHECK=quick git push`.
"""

import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _common import ROOT, block, read_event

FORBIDDEN = re.compile(
    r"(^|/)\.env($|\.(?!example$))|^data/|\.(sqlite3?|db|dump|bak)$|^book/.*\.pdf$|^analytics/reports/.*\.md$"
)
ADD_FORCE = re.compile(r"\bgit\s+add\b[^;&|]*\s(-f|--force)\b")
COMMIT = re.compile(r"\bgit\s+commit\b")
# Только сама команда (в начале строки или после ; && | и CHECK=…), не текст в скрипте
PUSH = re.compile(r"(?:^|[;&|]\s*)(?:CHECK=\w+\s+)?git\s+push\b", re.MULTILINE)


def run(*cmd: str, timeout: int = 280) -> tuple[bool, str]:
    result = subprocess.run(
        cmd, cwd=ROOT, capture_output=True, text=True, check=False, timeout=timeout
    )  # fmt: skip
    return result.returncode == 0, (result.stdout + result.stderr)[-2000:]


def staged() -> list[str]:
    _, out = run("git", "diff", "--cached", "--name-only")
    return [line for line in out.splitlines() if line]


def check_commit(command: str) -> None:
    # `git commit -a` добавит изменённые отслеживаемые файлы: проверяем и их
    files = staged()
    if re.search(r"\bgit\s+commit\b[^;&|]*\s-[a-zA-Z]*a", command):
        _, out = run("git", "diff", "--name-only")
        files += out.splitlines()
    bad = sorted({f for f in files if FORBIDDEN.search(f)})
    if bad:
        block(
            "Коммит остановлен: в нём файлы, которым нельзя в git (данные учеников, секреты, "
            "скан, отчёты с псевдонимами): "
            + ", ".join(bad)
            + ". Уберите: git restore --staged <файл>."
        )
    if shutil.which("gitleaks"):
        ok, out = run("gitleaks", "git", "--pre-commit", "--staged", "--redact", "--no-banner", ".")
        if not ok:
            block("Коммит остановлен: gitleaks нашёл похожее на секрет.\n" + out)


IMPORTANT = re.compile(
    r"^(src/|migrations/|curriculum/|pyproject\.toml$|uv\.lock$|\.importlinter$|Dockerfile$)"
)
PYTEST = ("uv", "run", "--quiet", "pytest", "-q", "-x", "--no-header", "-p", "no:cacheprovider")


def pushed_files() -> list[str]:
    """Файлы, которые меняет push: от upstream (или origin/main) до HEAD."""
    for base in ("@{upstream}", "origin/main"):
        ok, out = run("git", "diff", "--name-only", f"{base}...HEAD")
        if ok:
            return [line for line in out.splitlines() if line]
    return []


def quick_checks(files: list[str]) -> list[tuple[str, tuple[str, ...]]]:
    python = [f for f in files if f.endswith(".py") and (ROOT / f).is_file()]
    tests = [f for f in python if f.startswith("tests/") and Path(f).name.startswith("test_")]
    checks: list[tuple[str, tuple[str, ...]]] = [
        ("архитектура", ("uv", "run", "--quiet", "lint-imports"))
    ]
    if python:
        checks.append(("ruff", ("uv", "run", "--quiet", "ruff", "check", *python)))
    if tests:
        checks.append(("тесты изменённых файлов", (*PYTEST, *tests)))
    return checks


def full_checks() -> list[tuple[str, tuple[str, ...]]]:
    return [
        ("архитектура", ("uv", "run", "--quiet", "lint-imports")),
        ("типы", ("uv", "run", "--quiet", "mypy")),
        ("тесты", PYTEST),
    ]


def check_push(command: str) -> None:
    files = pushed_files()
    mode = re.search(r"\bCHECK=(full|quick)\b", command)
    important = sorted(f for f in files if IMPORTANT.search(f))
    if mode is None and important:
        block(
            "Push остановлен: важное изменение ("
            + ", ".join(important[:5])
            + "). Спроси автора, нужна ли полная проверка (mypy и все тесты, несколько минут). "
            "Да → `CHECK=full git push`, нет → `CHECK=quick git push`."
        )
    checks = full_checks() if mode and mode.group(1) == "full" else quick_checks(files)
    problems = []
    for name, cmd in checks:
        ok, out = run(*cmd)
        if not ok:
            problems.append(f"{name}:\n{out}")
    if problems:
        block("Push остановлен: проверки красные — сначала исправить.\n\n" + "\n\n".join(problems))


def main() -> None:
    event = read_event()
    if event.get("tool_name") != "Bash":
        return
    command = str((event.get("tool_input") or {}).get("command", ""))
    if ADD_FORCE.search(command):
        block("`git add -f` запрещён: он обходит .gitignore (данные, секреты, скан книги).")
    if COMMIT.search(command):
        if re.search(r"\bgit\s+add\b", command):
            block(
                "`git add` и `git commit` — отдельными командами: проверка перед коммитом видит "
                "только уже подготовленные файлы."
            )
        check_commit(command)
    if PUSH.search(command):
        check_push(command)


if __name__ == "__main__":
    try:
        main()
    except subprocess.TimeoutExpired:
        block(
            "Проверки перед push не уложились во время — спроси автора, "
            "запустить ли полную проверку (make check)."
        )
