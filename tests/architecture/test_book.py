"""Книга хранится в проекте, но не в боте (book/README.md, ADR-0022)."""

from pathlib import Path

import pytest

from muallim.bootstrap.main import COMMANDS

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.architecture


def test_book_is_described_with_contents() -> None:
    readme = (ROOT / "book" / "README.md").read_text(encoding="utf-8")
    assert "SHA-256" in readme and "SRC-040" in readme
    assert (ROOT / "book" / "contents.yaml").exists()


def test_bot_code_never_reads_the_book() -> None:
    offenders = [
        p.relative_to(ROOT).as_posix()
        for p in (ROOT / "src").rglob("*.py")
        if "book/" in p.read_text(encoding="utf-8")
    ]
    assert offenders == []


def test_book_scan_stays_out_of_git_and_docker_image() -> None:
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "book/*.pdf" in gitignore
    assert "book" in dockerignore
    assert "COPY book" not in dockerfile


def test_language_switch_is_hidden_while_only_russian() -> None:
    assert "language" not in {c.command for c in COMMANDS}
