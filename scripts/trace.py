"""Статус трассировки и отпечаток версии (make trace) → docs/requirements/verification-status.md.

1. Требования: тесты из `docs/requirements/traceability.md` прогоняются сейчас — какие требования
   проверены зелёными тестами, какие красными, у каких тестов нет.
2. Исследование: сколько вопросов `docs/research/traceability.md` уже считается (✅ / 🟡 / ❌).
3. Отпечаток версии: SHA-256 кода, программы, SQL, миграций и зависимостей. Git-коммитов нет
   (TD-FN-27), поэтому отпечаток — способ доказать, каким кодом получен отчёт (ADR-0036).

Запуск: `make trace` или `uv run python scripts/trace.py [--no-tests]`.
"""

import argparse
import hashlib
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQ_MATRIX = ROOT / "docs" / "requirements" / "traceability.md"
RESEARCH_MATRIX = ROOT / "docs" / "research" / "traceability.md"
OUT = ROOT / "docs" / "requirements" / "verification-status.md"

FINGERPRINT_PARTS: dict[str, tuple[str, ...]] = {
    "код": ("src/**/*.py",),
    "программа (книга)": ("curriculum/*.yaml",),
    "SQL-отчёты": ("analytics/sql/*.sql",),
    "миграции": ("migrations/versions/*.py",),
    "зависимости": ("uv.lock",),
    "предрегистрация": ("docs/research/preregistration.md",),
}

ROW = re.compile(r"^\| ((?:FR|NFR)-[A-Z0-9-]+) \|(.+)$", re.MULTILINE)
TEST_FILE = re.compile(r"tests/[\w/]+\.py")
STATUS = re.compile(r"(✅|🟡|❌)")


def fingerprint(patterns: tuple[str, ...]) -> tuple[str, int]:
    digest = hashlib.sha256()
    files = sorted({p for pattern in patterns for p in ROOT.glob(pattern) if p.is_file()})
    for path in files:
        if "__pycache__" in path.parts:
            continue
        digest.update(path.relative_to(ROOT).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:16], len(files)


def requirement_tests() -> dict[str, list[str]]:
    text = REQ_MATRIX.read_text(encoding="utf-8")
    result: dict[str, list[str]] = {}
    for req, rest in ROW.findall(text):
        cells = rest.split("|")
        tests_cell = cells[1] if len(cells) > 1 else ""
        result[req] = sorted(set(TEST_FILE.findall(tests_cell)))
    return result


def run_tests() -> dict[str, Counter[str]]:
    """Прогон pytest → {файл теста: Counter(passed/failed/skipped)}."""
    with tempfile.TemporaryDirectory() as tmp:
        junit = Path(tmp) / "junit.xml"
        command = ["uv", "run", "--quiet", "pytest", "-q", "-p", "no:cacheprovider"]
        subprocess.run(
            [*command, f"--junitxml={junit}"],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )  # fmt: skip
        if not junit.exists():
            sys.exit("pytest не создал отчёт — запустите `uv run pytest -q` и посмотрите ошибку")
        tree = ET.parse(junit)  # noqa: S314 — свой файл из своего прогона
    by_file: dict[str, Counter[str]] = {}
    for case in tree.iter("testcase"):
        path = case.get("file") or (case.get("classname", "").replace(".", "/") + ".py")
        path = re.sub(r"/[A-Z]\w*\.py$", ".py", path)  # класс теста внутри файла
        outcome = "passed"
        if case.find("failure") is not None or case.find("error") is not None:
            outcome = "failed"
        elif case.find("skipped") is not None:
            outcome = "skipped"
        by_file.setdefault(path, Counter())[outcome] += 1
    return by_file


def requirement_status(files: list[str], results: dict[str, Counter[str]] | None) -> str:
    if not files:
        return "нет автотестов"
    if results is None:
        return "не запускались"
    missing = [f for f in files if f not in results]
    failed = [f for f in files if results.get(f, Counter())["failed"]]
    if failed:
        return "❌ падают: " + ", ".join(f"`{f}`" for f in failed)
    if missing:
        return "⚠️ не найдены в прогоне: " + ", ".join(f"`{f}`" for f in missing)
    return "✅"


def research_summary() -> Counter[str]:
    counts: Counter[str] = Counter()
    for line in RESEARCH_MATRIX.read_text(encoding="utf-8").splitlines():
        if re.match(r"^\| (H\d|—|Q\d)", line):
            cells = [c.strip() for c in line.strip("|").split("|")]
            match = STATUS.search(cells[-2]) if len(cells) >= 2 else None
            counts[match.group(1) if match else "—"] += 1
    return counts


def render(results: dict[str, Counter[str]] | None) -> str:
    now = datetime.now(UTC).isoformat(timespec="seconds")
    lines = [
        "# Статус трассировки (сгенерировано `make trace`, не править руками)",
        "",
        f"Сформирован: {now}. Матрицы: `docs/requirements/traceability.md`, "
        "`docs/research/traceability.md` (ADR-0036).",
        "",
        "## Отпечаток версии",
        "Записывайте в паспорт рисунка или таблицы (`docs/thesis/figures.md`) и рядом с отчётом.",
        "",
        "| Часть | SHA-256 (16 знаков) | Файлов |",
        "|---|---|---|",
    ]
    for name, patterns in FINGERPRINT_PARTS.items():
        digest, count = fingerprint(patterns)
        lines.append(f"| {name} | `{digest}` | {count} |")

    reqs = requirement_tests()
    statuses = {req: requirement_status(files, results) for req, files in reqs.items()}
    ok = sum(1 for s in statuses.values() if s == "✅")
    lines += [
        "",
        "## Требования",
        f"Проверено зелёными тестами: **{ok} из {len(reqs)}**."
        + ("" if results is not None else " Тесты не запускались (`--no-tests`)."),
        "",
        "| ID | Тесты из матрицы | Сейчас |",
        "|---|---|---|",
    ]
    for req, files in reqs.items():
        listed = ", ".join(f"`{f}`" for f in files) or "—"
        lines.append(f"| {req} | {listed} | {statuses[req]} |")

    research = research_summary()
    lines += [
        "",
        "## Исследование",
        f"Строк в матрице: {sum(research.values())} — считается ✅ {research['✅']}, "
        f"частично 🟡 {research['🟡']}, нет ❌ {research['❌']}, "
        f"данных не собираем {research['—']}.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--no-tests", action="store_true", help="не прогонять pytest")
    args = parser.parse_args()
    results = None if args.no_tests else run_tests()
    OUT.write_text(render(results), encoding="utf-8")
    print(f"→ {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
