"""Хуки агента действительно блокируют то, что обещают (ADR-0012, NFR-SEC-01, NFR-TR-04)."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.architecture


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """Копия хуков во временный «проект», чтобы не трогать настоящую фазу и журнал."""
    shutil.copytree(ROOT / ".claude" / "hooks", tmp_path / ".claude" / "hooks")
    (tmp_path / ".agent-phase").write_text("off", encoding="utf-8")
    return tmp_path


def run_hook(
    project: Path, name: str, event: dict[str, object]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 — запускаем свой скрипт текущим интерпретатором
        [sys.executable, str(project / ".claude" / "hooks" / name)],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        check=False,
    )


def guard(project: Path, tool: str, **tool_input: str) -> int:
    return run_hook(project, "guard.py", {"tool_name": tool, "tool_input": tool_input}).returncode


@pytest.mark.parametrize(
    ("tool", "arg", "value"),
    [
        ("Read", "file_path", ".env"),
        ("Read", "file_path", ".env.production"),
        ("Read", "file_path", "data/audio/ab/x.ogg"),
        ("Read", "file_path", "data/dev.sqlite3"),
        ("Grep", "path", "data/exports"),
        ("Bash", "command", "cat .env"),
        ("Bash", "command", "sqlite3 data/dev.sqlite3 'select * from learners'"),
        ("Bash", "command", "echo $BOT_TOKEN"),
        ("Bash", "command", "printenv"),
        ("Bash", "command", "git commit --no-verify -m x"),
        ("Bash", "command", "git push --force origin main"),
        ("Bash", "command", "rm -rf src"),
        ("Bash", "command", "echo impl > .agent-phase"),
        ("Write", "file_path", ".agent-phase"),
    ],
)
def test_guard_blocks(project: Path, tool: str, arg: str, value: str) -> None:
    target = str(project / value) if arg in {"file_path", "path"} else value
    assert guard(project, tool, **{arg: target}) == 2


@pytest.mark.parametrize(
    ("tool", "arg", "value"),
    [
        ("Read", "file_path", ".env.example"),
        ("Read", "file_path", "src/muallim/domain/assessment.py"),
        ("Edit", "file_path", "tests/unit/test_policy.py"),
        ("Bash", "command", "uv run pytest -q"),
        ("Bash", "command", "scripts/phase impl"),
        ("Bash", "command", "git status"),
    ],
)
def test_guard_allows(project: Path, tool: str, arg: str, value: str) -> None:
    target = str(project / value) if arg == "file_path" else value
    assert guard(project, tool, **{arg: target}) == 0


def test_tests_frozen_in_impl_phase(project: Path) -> None:
    (project / ".agent-phase").write_text("impl", encoding="utf-8")
    test_file = str(project / "tests" / "unit" / "test_x.py")
    assert guard(project, "Edit", file_path=test_file) == 2
    assert guard(project, "Bash", command="sed -i '' s/a/b/ tests/unit/test_x.py") == 2
    assert guard(project, "Bash", command="git checkout tests/unit/test_x.py") == 2
    assert guard(project, "Edit", file_path=str(project / "src" / "x.py")) == 0
    assert guard(project, "Read", file_path=test_file) == 0


def test_prompt_logged_with_secrets_redacted(project: Path) -> None:
    token = "1234567890:" + "A" * 35
    prompt = f"почини бота, токен {token}, password=hunter2"
    result = run_hook(project, "log_prompt.py", {"prompt": prompt, "session_id": "abcdef123"})
    assert result.returncode == 0
    (log,) = (project / "docs" / "journal" / "prompts").glob("*.md")
    text = log.read_text(encoding="utf-8")
    assert "почини бота" in text and "abcdef12" in text
    assert token not in text and "hunter2" not in text and "[СКРЫТО]" in text


def test_empty_prompt_not_logged(project: Path) -> None:
    run_hook(project, "log_prompt.py", {"prompt": "  "})
    assert not (project / "docs" / "journal" / "prompts").exists()
