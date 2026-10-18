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


@pytest.mark.parametrize(
    "command",
    [
        "docker compose down -v",
        "docker compose down --volumes",
        "docker volume rm muallim_postgres-data",
        "docker volume prune -f",
        "docker system prune --volumes",
        "uv run alembic downgrade base",
        "uv run alembic downgrade -1",
        "make restore d=data/backups/x",
        "docker compose exec postgres psql -c 'DROP TABLE attempts'",
        "psql -c 'truncate annotations'",
        "echo 'DELETE FROM learners;' | make db-shell",
        "rm -r data",
        "rm -r data/backups",
        "find data -delete",
        "uv run muallim-research verify --delete-orphans",
        "docker compose exec -T postgres pg_restore --clean -d muallim",
        "docker compose exec postgres dropdb muallim",
        "uv run alembic -c alembic.ini downgrade base",
        "sh scripts/db/restore.sh data/backups/x",
    ],
)
def test_guard_blocks_destroying_research_data(project: Path, command: str) -> None:
    """Данные пилота невосстановимы: удаление тома, откат миграций, DROP — только человек."""
    assert guard(project, "Bash", command=command) == 2


@pytest.mark.parametrize(
    "command",
    [
        "docker compose up -d postgres",
        "uv run alembic upgrade head",
        "make backup",
        "make migrate",
        "git add scripts/db/restore.sh",  # смотреть и коммитить скрипт можно, запускать — нет
        "git diff scripts/db/restore.sh",
        "uv run muallim-research verify",
    ],
)
def test_guard_allows_safe_database_commands(project: Path, command: str) -> None:
    assert guard(project, "Bash", command=command) == 0


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


def hook_json(project: Path, name: str, event: dict[str, object]) -> dict[str, object]:
    result = run_hook(project, name, event)
    assert result.returncode == 0, result.stderr
    out = result.stdout.strip()
    return json.loads(out)["hookSpecificOutput"] if out else {}


@pytest.mark.parametrize(
    ("tool", "value"),
    [
        ("Write", "curriculum/course.ru.yaml"),
        ("Edit", "src/muallim/presentation/telegram/texts.py"),
        ("MultiEdit", "src/muallim/domain/policy.py"),
        ("Edit", "src/muallim/infrastructure/db/tables.py"),
        ("Write", "migrations/versions/0009_x.py"),
        ("Edit", "pyproject.toml"),
        ("Edit", ".claude/hooks/guard.py"),
        ("Edit", "src/muallim/research/metrics.py"),  # оценщик RQ-1 заморожен (TD-FN-60)
    ],
)
def test_human_zones_ask(project: Path, tool: str, value: str) -> None:
    out = hook_json(
        project,
        "human_zones.py",
        {"tool_name": tool, "tool_input": {"file_path": str(project / value)}},
    )
    assert out["permissionDecision"] == "ask"
    assert "Зона человека" in str(out["permissionDecisionReason"])


def test_human_zones_asks_for_new_dependency(project: Path) -> None:
    out = hook_json(
        project,
        "human_zones.py",
        {"tool_name": "Bash", "tool_input": {"command": "pip install requests"}},
    )
    assert out["permissionDecision"] == "ask"


@pytest.mark.parametrize(
    ("tool", "key", "value"),
    [
        ("Edit", "file_path", "src/muallim/domain/assessment.py"),
        ("Write", "file_path", "docs/thesis/chapters/01-обзор.md"),
        ("Bash", "command", "uv run pytest -q"),
    ],
)
def test_human_zones_silent_elsewhere(project: Path, tool: str, key: str, value: str) -> None:
    target = str(project / value) if key == "file_path" else value
    assert (
        hook_json(project, "human_zones.py", {"tool_name": tool, "tool_input": {key: target}}) == {}
    )


def test_guard_fails_closed(project: Path) -> None:
    result = run_hook(project, "guard.py", {"tool_name": "Read", "tool_input": ["не словарь"]})
    assert result.returncode == 2
    assert "упал" in result.stderr


def test_block_is_logged_without_details(project: Path) -> None:
    assert guard(project, "Bash", command="cat .env") == 2
    (log,) = (project / "docs" / "journal" / "hooks").glob("*.jsonl")
    record = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
    assert record["hook"] == "guard" and record["kind"] == "block"
    assert "cat .env" not in record["reason"]


def test_stub_notice_only_for_stub(project: Path) -> None:
    out = hook_json(
        project, "stub_notice.py", {"tool_name": "Bash", "tool_input": {"command": "make run-stub"}}
    )
    assert "ЗАГЛУШК" in str(out["additionalContext"])
    assert (
        hook_json(
            project, "stub_notice.py", {"tool_name": "Bash", "tool_input": {"command": "make run"}}
        )
        == {}
    )


def test_session_context_reports_phase(project: Path) -> None:
    (project / ".agent-phase").write_text("impl", encoding="utf-8")
    result = run_hook(project, "session_context.py", {})
    assert result.returncode == 0
    assert "TDD-фаза: impl" in result.stdout


# --- ADR-0039: сверка документов (doc_sync) и безопасные коммиты (git_guard) ---
def git(project: Path, *args: str) -> None:
    subprocess.run(  # noqa: S603
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],  # noqa: S607
        cwd=project, check=True, capture_output=True,
    )  # fmt: skip


@pytest.fixture
def repo(project: Path) -> Path:
    """Мини-проект в git: один коммит, дальше тест меняет файлы."""
    files = {
        ".gitignore": "/data/\n.agent-phase\n",
        "CHANGELOG.md": "# log\n",
        "src/muallim/infrastructure/db/tables.py": "x = 1\n",
        "docs/data/data-dictionary.md": "# dict\n",
        "docs/requirements/traceability.md": "| FR-01 | a |\n",
        "src/muallim/presentation/telegram/texts.py": 'CONSENT_TEXT = (\n    "да"\n)\n',
        "src/muallim/application/use_cases/learners.py": 'CONSENT_TEXT_VERSION = "1"\n',
    }
    for name, text in files.items():
        (project / name).parent.mkdir(parents=True, exist_ok=True)
        (project / name).write_text(text, encoding="utf-8")
    git(project, "init", "-q")
    git(project, "add", ".")
    git(project, "commit", "-q", "-m", "base")
    return project


def doc_sync(project: Path) -> subprocess.CompletedProcess[str]:
    return run_hook(project, "doc_sync.py", {})


def test_doc_sync_blocks_schema_change_without_dictionary(repo: Path) -> None:
    (repo / "src/muallim/infrastructure/db/tables.py").write_text("x = 2\n", encoding="utf-8")
    (repo / "CHANGELOG.md").write_text("# log\n- схема\n", encoding="utf-8")
    result = doc_sync(repo)
    assert result.returncode == 2 and "data-dictionary.md" in result.stderr


def test_doc_sync_passes_consistent_change(repo: Path) -> None:
    (repo / "src/muallim/infrastructure/db/tables.py").write_text("x = 2\n", encoding="utf-8")
    (repo / "CHANGELOG.md").write_text("# log\n- схема\n", encoding="utf-8")
    (repo / "docs/data/data-dictionary.md").write_text("# dict\n- x\n", encoding="utf-8")
    (repo / "migrations/versions").mkdir(parents=True)
    (repo / "migrations/versions/0002_x.py").write_text("# m\n", encoding="utf-8")
    assert doc_sync(repo).returncode == 0


def test_doc_sync_finds_files_hidden_by_gitignore(repo: Path) -> None:
    (repo / ".gitignore").write_text("data/\n.agent-phase\n", encoding="utf-8")  # как было
    (repo / "docs/data/reports.md").write_text("# r\n", encoding="utf-8")
    result = doc_sync(repo)
    assert result.returncode == 2 and "docs/data/reports.md" in result.stderr


def test_doc_sync_wants_new_consent_version(repo: Path) -> None:
    texts = repo / "src/muallim/presentation/telegram/texts.py"
    texts.write_text('CONSENT_TEXT = (\n    "да, и анкета"\n)\n', encoding="utf-8")
    (repo / "CHANGELOG.md").write_text("# log\n- согласие\n", encoding="utf-8")
    result = doc_sync(repo)
    assert result.returncode == 2 and "CONSENT_TEXT_VERSION" in result.stderr


QUESTIONNAIRE = {
    "src/muallim/presentation/telegram/keyboards.py": (
        'OPTIONS = (("ru", "Русский"), ("kk", "Казахский"))\n'
    ),
    "src/muallim/application/use_cases/learners.py": (
        'CONSENT_TEXT_VERSION = "1"\nQUESTIONNAIRE_VERSION = "1"\n'
    ),
}


def _with_questionnaire(repo: Path) -> Path:
    for name, text in QUESTIONNAIRE.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(text, encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "анкета")
    (repo / "CHANGELOG.md").write_text("# log\n- тексты в texts.py\n", encoding="utf-8")
    return repo / "src/muallim/presentation/telegram/texts.py"


def test_doc_sync_verbatim_move_needs_no_new_version(repo: Path) -> None:
    """Перенос кнопок анкеты в texts.py без правки слов — ученик видит то же (TD-FN-57)."""
    texts = _with_questionnaire(repo)
    moved = '\nPROFILE_LANGUAGES = {\n    "ru": "Русский",\n    "kk": "Казахский",\n}\n'
    texts.write_text(texts.read_text(encoding="utf-8") + moved, encoding="utf-8")
    assert doc_sync(repo).returncode == 0


@pytest.mark.parametrize(
    "edited",
    [
        '\nPROFILE_LANGUAGES = {\n    "ru": "Русский язык",\n    "kk": "Казахский",\n}\n',
        '\nPROFILE_LANGUAGES = {\n    "ru": "Казахский",\n    "kk": "Русский",\n}\n',
    ],
)
def test_doc_sync_edited_questionnaire_needs_new_version(repo: Path, edited: str) -> None:
    """Новые слова или перепутанные ответы — это другая анкета: версию поднять."""
    texts = _with_questionnaire(repo)
    texts.write_text(texts.read_text(encoding="utf-8") + edited, encoding="utf-8")
    result = doc_sync(repo)
    assert result.returncode == 2 and "QUESTIONNAIRE_VERSION" in result.stderr


def test_doc_sync_does_not_loop(repo: Path) -> None:
    (repo / "src/muallim/infrastructure/db/tables.py").write_text("x = 3\n", encoding="utf-8")
    assert run_hook(repo, "doc_sync.py", {"stop_hook_active": True}).returncode == 0


def git_guard(project: Path, command: str) -> subprocess.CompletedProcess[str]:
    return run_hook(
        project, "git_guard.py", {"tool_name": "Bash", "tool_input": {"command": command}}
    )


@pytest.mark.parametrize("command", ["git add -f data/dev.sqlite3", "git add . && git commit -m x"])
def test_git_guard_blocks_unsafe_commands(repo: Path, command: str) -> None:
    assert git_guard(repo, command).returncode == 2


def test_git_guard_blocks_secret_files_in_commit(repo: Path) -> None:
    (repo / ".env").write_text("BOT_TOKEN=x\n", encoding="utf-8")
    git(repo, "add", "-f", ".env")  # как если бы обошли .gitignore руками
    result = git_guard(repo, "git commit -m 'x'")
    assert result.returncode == 2 and ".env" in result.stderr


def test_git_guard_allows_clean_commit(repo: Path) -> None:
    (repo / "CHANGELOG.md").write_text("# log\n- ок\n", encoding="utf-8")
    git(repo, "add", "CHANGELOG.md")
    assert git_guard(repo, "git commit -m 'docs: ок'").returncode == 0
