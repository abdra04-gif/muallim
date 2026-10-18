#!/usr/bin/env python3
"""Stop: изменили одно — обновите связанное (ADR-0039). Механические правила, без догадок.

Сравнивает рабочее дерево с последним коммитом (git): что изменено, добавлено, удалено. Если
сработало правило «изменили X — должно измениться Y», а Y не менялся, агент не может закончить и
получает список. Смысловую сверку (описание поведения, цифры в документах) делает агент
`consistency-auditor`. Повторный Stop (stop_hook_active) пропускается — без вечной петли.
"""

import ast
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _common import ROOT, block, read_event

CODE = ("src/", "migrations/", "analytics/sql/", "curriculum/")
VERSIONED_TEXTS = (
    # (константы в texts.py, версия, которую нужно поднять)
    (r"CONSENT_TEXT", "CONSENT_TEXT_VERSION"),
    (r"PROFILE_\w+", "QUESTIONNAIRE_VERSION"),
)
TEXTS = "src/muallim/presentation/telegram/texts.py"
VERSIONS = "src/muallim/application/use_cases/learners.py"


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=False
    )  # fmt: skip
    return result.stdout if result.returncode == 0 else ""


def changed_files() -> tuple[set[str], set[str]]:
    """(все изменённые пути, новые пути) относительно HEAD, включая неотслеживаемые."""
    changed, added = set(), set()
    for line in git("status", "--porcelain", "-uall").splitlines():
        status, path = line[:2], line[3:].split(" -> ")[-1].strip('"')
        if "__pycache__" in path or path.endswith((".pyc", ".DS_Store")):
            continue  # служебное: не изменение проекта
        changed.add(path)
        if "?" in status or "A" in status:
            added.add(path)
    return changed, added


def head_text(path: str) -> str:
    return git("show", f"HEAD:{path}")


def constants(source: str, pattern: str) -> dict[str, str]:
    """Значения текстовых констант верхнего уровня: NAME = ( … ), NAME = { … } или NAME = "…"."""
    found = {}
    value = r"(\(.*?^\)|\{.*?^\}|\".*?\")$"
    for m in re.finditer(rf"^({pattern}) = {value}", source, re.MULTILINE | re.DOTALL):
        found[m.group(1)] = m.group(2)
    return found


def literals(source: str) -> list[str]:
    """Строковые литералы в порядке текста; не разобралось — пусто (значит, не перенос)."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    nodes = [n for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    return [n.value for n in sorted(nodes, key=lambda n: (n.lineno, n.col_offset))]


def moved_verbatim(value: str) -> bool:
    """Новая константа повторяет строки, которые ученик уже видел, в том же порядке.

    Перенос кнопок из keyboards.py в texts.py не меняет того, что видел ученик, — версия текста не
    поднимается. Новые слова или перепутанные пары «код → подпись» — уже другой текст (TD-FN-57).
    """
    wanted = literals(value)
    if not wanted:
        return False
    package = "src/muallim/presentation/telegram/"
    for path in git("ls-tree", "-r", "--name-only", "HEAD", package).splitlines():
        if not path.endswith(".py"):
            continue
        seen = literals(head_text(path))
        if any(seen[i : i + len(wanted)] == wanted for i in range(len(seen) - len(wanted) + 1)):
            return True
    return False


def versioned_text_changed(now: dict[str, str], before: dict[str, str]) -> bool:
    if any(now.get(name) != value for name, value in before.items()):
        return True
    return any(name not in before and not moved_verbatim(value) for name, value in now.items())


def text_versions_problems(changed: set[str]) -> list[str]:
    if TEXTS not in changed:
        return []
    now = (ROOT / TEXTS).read_text(encoding="utf-8")
    before = head_text(TEXTS)
    versions_now = (ROOT / VERSIONS).read_text(encoding="utf-8")
    versions_before = head_text(VERSIONS)
    problems = []
    for pattern, version in VERSIONED_TEXTS:
        text_changed = versioned_text_changed(constants(now, pattern), constants(before, pattern))
        same_version = constants(versions_now, version) == constants(versions_before, version)
        if text_changed and same_version:
            problems.append(
                f"Изменён текст {pattern} в {TEXTS}, а {version} в {VERSIONS} — нет: "
                "поднимите версию (по ней видно, какой текст видел ученик)."
            )
    return problems


def new_requirements_untraced(changed: set[str]) -> list[str]:
    req = "docs/requirements/requirements.md"
    if req not in changed:
        return []
    diff = git("diff", "HEAD", "--", req)
    new_ids = set(re.findall(r"^\+\| ((?:FR|NFR)-[\w-]+) \|", diff, re.MULTILINE))
    matrix = (ROOT / "docs/requirements/traceability.md").read_text(encoding="utf-8")
    missing = sorted(i for i in new_ids if f"| {i} |" not in matrix)
    return (
        [f"Новые требования без строки в traceability.md: {', '.join(missing)}"] if missing else []
    )


WATCHED = ("docs/", "src/", "tests/", "scripts/", "migrations/", ".claude/", "thesis/")
NOISE = ("__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache", ".DS_Store", "thesis/build/")


def ignored_project_files() -> list[str]:
    """Код и документы, которые .gitignore прячет от git — их не будет в репозитории."""
    out = git("ls-files", "-o", "-i", "--exclude-standard", "--", *WATCHED)
    lost = [p for p in out.splitlines() if not any(n in p for n in NOISE)]
    if not lost:
        return []
    shown = ", ".join(lost[:8]) + (" …" if len(lost) > 8 else "")
    return [f"Файлы проекта скрыты .gitignore и не попадут в git: {shown} — поправьте .gitignore."]


Rule = tuple[Callable[[set[str], set[str]], bool], Callable[[set[str]], bool], str]

RULES: tuple[Rule, ...] = (
    (
        lambda c, a: any(p.startswith(CODE) for p in c),
        lambda c: "CHANGELOG.md" in c,
        "Изменён код/программа/SQL/миграции — нет записи в CHANGELOG.md («Не выпущено»).",
    ),
    (
        lambda c, a: "src/muallim/infrastructure/db/tables.py" in c,
        lambda c: (
            "docs/data/data-dictionary.md" in c
            and any(p.startswith("migrations/versions/") for p in c)
        ),
        "Изменена схема БД (tables.py) — нужны миграция и docs/data/data-dictionary.md.",
    ),
    (
        lambda c, a: any(p.startswith("migrations/versions/") and p.endswith(".py") for p in c),
        lambda c: "docs/data/data-dictionary.md" in c,
        "Новая/изменённая миграция — обновите docs/data/data-dictionary.md.",
    ),
    (
        lambda c, a: any(p.startswith("analytics/sql/") for p in a),
        lambda c: "docs/data/reports.md" in c,
        "Новый SQL-отчёт — строка в docs/data/reports.md (какой вопрос и для какой главы).",
    ),
    (
        lambda c, a: any(
            p.startswith((".claude/agents/", ".claude/hooks/", ".claude/commands/")) for p in a
        ),
        lambda c: "docs/process/agent-harness.md" in c,
        "Новый агент/хук/команда — добавьте в docs/process/agent-harness.md.",
    ),
    (
        lambda c, a: any(p.endswith(".mmd") for p in c),
        lambda c: all(
            p[:-4] + ".png" in c and p[:-4] + ".svg" in c for p in c if p.endswith(".mmd")
        ),
        "Изменена схема .mmd, но .png/.svg не перерисованы — make diagrams.",
    ),
)


def main() -> None:
    event = read_event()
    if event.get("stop_hook_active"):
        return
    changed, added = changed_files()
    if not changed:
        return
    problems = [
        msg
        for trigger, satisfied, msg in RULES
        if trigger(changed, added) and not satisfied(changed)
    ]
    problems += text_versions_problems(changed)
    problems += new_requirements_untraced(changed)
    problems += ignored_project_files()
    if problems:
        block(
            "Документация и код разошлись — исправь до завершения (doc_sync, ADR-0039):\n- "
            + "\n- ".join(problems)
            + "\nСмысловую сверку сделает агент consistency-auditor."
        )


if __name__ == "__main__":
    main()
