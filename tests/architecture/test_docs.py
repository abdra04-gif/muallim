"""Документация не расходится с проектом: ADR, трассировка, источники (NFR-TR-01, NFR-TR-02)."""

import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

import pytest

from muallim.domain.curriculum import Curriculum

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
pytestmark = pytest.mark.architecture

ADRS = sorted(p for p in (DOCS / "adr").glob("[0-9][0-9][0-9][0-9]-*.md") if p.name[:4] != "0000")


@pytest.mark.parametrize("adr", ADRS, ids=lambda p: p.name[:4])
def test_adr_has_status_date_and_is_indexed(adr: Path) -> None:
    text = adr.read_text(encoding="utf-8")
    assert re.search(r"\*\*Статус:\*\* \S", text), "нет статуса"
    assert re.search(r"\*\*Дата:\*\* \d{4}-\d{2}-\d{2}", text), "нет даты"
    assert text.startswith(f"# ADR-{adr.name[:4]}:"), "заголовок не совпадает с номером файла"
    assert f"({adr.name})" in (DOCS / "adr" / "README.md").read_text(encoding="utf-8")


def _requirement_ids(done_only: bool) -> set[str]:
    ids = set()
    for line in (
        (DOCS / "requirements" / "requirements.md").read_text(encoding="utf-8").splitlines()
    ):
        m = re.match(r"\| (N?FR-[A-Z-]*\d+) \|", line)
        if m and (not done_only or "✅" in line or "🟡" in line):
            ids.add(m.group(1))
    return ids


def test_every_implemented_requirement_is_traced() -> None:
    matrix = (DOCS / "requirements" / "traceability.md").read_text(encoding="utf-8")
    traced = set(re.findall(r"^\| (N?FR-[A-Z-]*\d+) \|", matrix, flags=re.M))
    missing = _requirement_ids(done_only=True) - traced
    # NFR без отдельного файла реализации допустимы, если проверка описана в requirements.md
    missing = {i for i in missing if i.startswith("FR-")}
    assert not missing, f"нет в traceability.md: {sorted(missing)}"
    assert traced <= _requirement_ids(done_only=False), "в матрице есть несуществующие ID"


def test_traceability_paths_exist() -> None:
    matrix = (DOCS / "requirements" / "traceability.md").read_text(encoding="utf-8")
    paths = re.findall(r"`([\w./-]+(?:\.\w+|/))`", matrix)
    assert paths
    missing = [p for p in paths if not (ROOT / p).exists()]
    assert not missing, f"битые пути в traceability.md: {missing}"


# Документы проекта (без чужих отчётов и журнала запросов — там цитаты, а не ссылки)
_SKIP_DIRS = {
    ".venv",
    ".git",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    "external",
}
_MARKDOWN = sorted(
    p
    for p in ROOT.rglob("*.md")
    if not _SKIP_DIRS & set(p.relative_to(ROOT).parts)
    and "journal/prompts" not in p.relative_to(ROOT).as_posix()
)
_LINK = re.compile(r"\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
# Путь от корня проекта в `…`: однозначный, поэтому проверяется. data/ — вне git, не проверяем
_ROOT_PATH = re.compile(
    r"`((?:src|docs|tests|curriculum|scripts|analytics|migrations|book|\.claude|\.github)/[^`\s]*)`"
)
_PLACEHOLDER = re.compile(r"[<>*{}…]|ГГГГ|NNNN|NN_")


def _without_code_blocks(path: Path) -> str:
    return re.sub(r"```.*?```", "", path.read_text(encoding="utf-8"), flags=re.S)


def test_markdown_links_point_to_existing_files() -> None:
    """[текст](путь) — ссылки, кликабельные на GitHub; при переименовании файла ломаются молча."""
    broken = []
    for doc in _MARKDOWN:
        text = re.sub(r"`[^`\n]*`", "", _without_code_blocks(doc))  # `[…](…)` — пример, не ссылка
        for target in _LINK.findall(text):
            path = unquote(target.split("#")[0])
            if not path or re.match(r"^[a-z]+:", path):  # якорь внутри файла, http:, mailto:
                continue
            if not (doc.parent / path).exists():
                broken.append(f"{doc.relative_to(ROOT)} → {target}")
    assert not broken, "битые ссылки:\n" + "\n".join(broken)


def test_root_paths_in_docs_exist() -> None:
    """`docs/…`, `src/…` и другие пути от корня в тексте документов существуют (TD-FN-28)."""
    broken = []
    for doc in _MARKDOWN:
        for raw in _ROOT_PATH.findall(_without_code_blocks(doc)):
            path = re.sub(r"(::\w+|:\d+|#.*)$", "", raw.rstrip(".,;:)"))
            if _PLACEHOLDER.search(path):
                continue
            if not (ROOT / path).exists():
                broken.append(f"{doc.relative_to(ROOT)} → {raw}")
    assert not broken, "в документах пути на несуществующие файлы:\n" + "\n".join(broken)


def test_source_keys_used_anywhere_are_defined() -> None:
    defined = set(
        re.findall(
            r"^\| (SRC-\d{3}) \|", (DOCS / "research" / "sources.md").read_text("utf-8"), re.M
        )
    )
    used: set[str] = set()
    sources = ("src/**/*.py", "docs/**/*.md", "curriculum/**/*.yaml", "curriculum/**/*.md")
    for path in [p for pattern in sources for p in ROOT.glob(pattern)]:
        used |= set(re.findall(r"SRC-\d{3}", path.read_text(encoding="utf-8")))
    assert used - defined == set(), f"ключи без описания: {sorted(used - defined)}"


def test_bib_has_every_source() -> None:
    sources = (DOCS / "research" / "sources.md").read_text(encoding="utf-8")
    bib = (DOCS / "research" / "sources.bib").read_text(encoding="utf-8")
    for key in re.findall(r"^\| (SRC-\d{3}) \|", sources, re.M):
        assert f"{{{key}," in bib, key


def test_curriculum_sources_are_defined(curriculum: Curriculum) -> None:
    sources = (DOCS / "research" / "sources.md").read_text(encoding="utf-8")
    for lesson in curriculum.lessons:
        for item in lesson.items:
            assert item.source is not None
            assert f"| {item.source.source_id} |" in sources, item.id


def test_every_table_is_in_data_dictionary() -> None:
    from muallim.infrastructure.db.tables import metadata  # noqa: PLC0415

    dictionary = (DOCS / "data" / "data-dictionary.md").read_text(encoding="utf-8")
    for table in metadata.tables.values():
        assert f"`{table.name}`" in dictionary, table.name
        for column in table.columns:
            assert f"`{column.name}`" in dictionary, f"{table.name}.{column.name}"


def test_diagrams_rendered() -> None:
    for source in (DOCS / "architecture" / "diagrams").glob("*.mmd"):
        for ext in (".svg", ".png"):
            image = source.with_suffix(ext)
            assert image.exists(), f"нет {image.name}: запустите make diagrams"
            assert image.stat().st_mtime >= source.stat().st_mtime - 1, (
                f"{image.name} старее исходника: запустите make diagrams"
            )


def test_user_stories_reference_existing_requirements() -> None:
    stories = (DOCS / "requirements" / "user-stories.md").read_text(encoding="utf-8")
    used = set(re.findall(r"\bN?FR-[A-Z-]*\d+\b", stories))
    assert used, "истории без ссылок на требования"
    assert used <= _requirement_ids(done_only=False), sorted(used - _requirement_ids(False))
    summary = set(re.findall(r"^\| (US-[UTI]-\d+) \|", stories, re.M))
    sections = set(re.findall(r"^### (US-[UTI]-\d+)\.", stories, re.M))
    assert summary == sections, f"сводка и разделы расходятся: {sorted(summary ^ sections)}"


def test_traceability_rows_have_honest_status() -> None:
    """Каждая строка матрицы со статусом; без автотеста (— в колонке «Тесты») — не ✅."""
    matrix = (DOCS / "requirements" / "traceability.md").read_text(encoding="utf-8")
    for row in re.findall(r"^\| N?FR-[A-Z-]*\d+ \|.*$", matrix, re.M):
        cells = [c.strip() for c in row.strip("|").split("|")]
        assert len(cells) == 5 and cells[4] in {"✅", "🟡", "❌"}, row[:40]
        if cells[2].startswith("—"):
            assert cells[4] != "✅", f"{cells[0]}: нет автотеста, а статус ✅"


RESEARCH = DOCS / "research" / "traceability.md"
FIGURES = DOCS / "thesis" / "figures.md"


def test_every_gqm_question_is_traced_to_research() -> None:
    gqm = set(
        re.findall(
            r"^\| (Q\d\.\d)",
            (DOCS / "research" / "metrics-gqm.md").read_text(encoding="utf-8"),
            re.M,
        )
    )
    traced = set(re.findall(r"\| (Q\d\.\d) \|", RESEARCH.read_text(encoding="utf-8")))
    assert gqm and not gqm - traced, f"нет в research/traceability.md: {sorted(gqm - traced)}"


def test_research_results_are_registered_figures() -> None:
    used = set(re.findall(r"\b([РТ]-\d{2})\b", RESEARCH.read_text(encoding="utf-8")))
    registered = set(re.findall(r"^\| ([РТ]-\d{2}) \|", FIGURES.read_text(encoding="utf-8"), re.M))
    assert not used - registered, f"нет в thesis/figures.md: {sorted(used - registered)}"


def test_ready_figures_exist() -> None:
    missing = []
    for line in FIGURES.read_text(encoding="utf-8").splitlines():
        if line.startswith("| Р-") and "| ✅" in line:
            missing += [
                p for p in re.findall(r"`(docs/[^`]+\.png)`", line) if not (ROOT / p).exists()
            ]
    assert not missing, missing


def test_trace_script_runs(tmp_path: Path) -> None:
    """Скрипт пишет туда, куда сказано: прогон тестов не портит статус в git (TD-FN-67)."""
    tracked = DOCS / "requirements" / "verification-status.md"
    before = tracked.read_bytes()
    out = tmp_path / "status.md"
    result = subprocess.run(  # noqa: S603
        [sys.executable, str(ROOT / "scripts" / "trace.py"), "--no-tests", "--out", str(out)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert out.is_file() and "Статус трассировки" in out.read_text(encoding="utf-8")
    assert tracked.read_bytes() == before, "тест перезаписал verification-status.md"
