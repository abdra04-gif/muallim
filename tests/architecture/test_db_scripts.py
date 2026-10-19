"""Резервная копия и восстановление (scripts/db): сбой не выдаётся за успех.

Настоящий docker не нужен: на его место в PATH кладётся скрипт, который пишет, с чем его вызвали,
и по переменной FAIL изображает сбой pg_dump или pg_restore.
"""

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.architecture

FAKE_DOCKER = """#!/bin/sh
echo "$*" >> "$CALLS"
case "$*" in
  *pg_dump*) [ "$FAIL" = dump ] && exit 1; printf 'PGDMP-archive' ;;
  *"pg_restore --list"*) cat > /dev/null; [ "$FAIL" = list ] && exit 1; echo '; toc' ;;
  *pg_restore*) cat > /dev/null; [ "$FAIL" = restore ] && exit 1 ;;
  *pg_roles*) [ "$FAIL" = roles ] && echo 0 || echo 3 ;;
  *psql*) cat > "$CALLS.stdin" ;;
esac
exit 0
"""


@pytest.fixture
def project(tmp_path: Path) -> Path:
    shutil.copytree(ROOT / "scripts" / "db", tmp_path / "scripts" / "db")
    (tmp_path / "data" / "audio" / "ab").mkdir(parents=True)
    (tmp_path / "data" / "audio" / "ab" / "x.ogg").write_bytes(b"voice")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(FAKE_DOCKER, encoding="utf-8")
    docker.chmod(docker.stat().st_mode | stat.S_IEXEC)
    research = bin_dir / "research"  # вместо `uv run muallim-research`: только записывает вызов
    research.write_text('#!/bin/sh\necho "research $*" >> "$CALLS"\n', encoding="utf-8")
    research.chmod(research.stat().st_mode | stat.S_IEXEC)
    (tmp_path / "data" / "erasures").mkdir(parents=True)
    (tmp_path / "data" / "erasures" / "erasures.jsonl").write_text("{}\n", encoding="utf-8")
    return tmp_path


def run(project: Path, script: str, *args: str, fail: str = "") -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "PATH": f"{project / 'bin'}{os.pathsep}{os.environ['PATH']}",
        "CALLS": str(project / "calls.log"),
        "FAIL": fail,
        "MUALLIM_RESEARCH": str(project / "bin" / "research"),
    }
    return subprocess.run(  # noqa: S603 — свой скрипт из репозитория
        ["/bin/sh", str(project / "scripts" / "db" / script), *args],
        cwd=project, env=env, capture_output=True, text=True, check=False, input="",
    )  # fmt: skip


def backups(project: Path) -> list[Path]:
    return sorted((project / "data" / "backups").glob("*"))


def test_backup_writes_dump_audio_and_checksums(project: Path) -> None:
    result = run(project, "backup.sh")
    assert result.returncode == 0, result.stderr
    (copy,) = backups(project)
    assert "Копия:" in result.stdout and copy.name in result.stdout
    assert (copy / "db.dump").read_bytes() == b"PGDMP-archive"
    assert (copy / "audio.tar.gz").stat().st_size > 0
    sums = (copy / "SHA256SUMS").read_text(encoding="utf-8")
    assert "db.dump" in sums and "audio.tar.gz" in sums
    assert "pg_restore --list" in (project / "calls.log").read_text(encoding="utf-8")
    # голоса и псевдонимы: читать может только владелец, как записи в data/audio (0600)
    for path in (copy, *copy.iterdir()):
        assert path.stat().st_mode & 0o077 == 0, path


@pytest.mark.parametrize("fail", ["dump", "list"])
def test_failed_backup_is_reported_as_failure(project: Path, fail: str) -> None:
    """Раньше `make backup` печатал «Копия: …», даже если pg_dump упал."""
    result = run(project, "backup.sh", fail=fail)
    assert result.returncode != 0
    assert "Копия:" not in result.stdout
    assert all(p.name.endswith("-FAILED") for p in backups(project))  # недоделанная — с пометкой


def test_backup_keeps_erasure_log(project: Path) -> None:
    assert run(project, "backup.sh").returncode == 0
    (copy,) = backups(project)
    assert (copy / "erasures.jsonl").read_text(encoding="utf-8") == "{}\n"
    assert "erasures.jsonl" in (copy / "SHA256SUMS").read_text(encoding="utf-8")


def test_db_only_backup_before_migration_skips_recordings(project: Path) -> None:
    """Миграция не трогает записи — копия перед ней только БД: секунды, а не минуты."""
    result = run(project, "backup.sh", "--db-only")
    assert result.returncode == 0, result.stderr
    (copy,) = backups(project)
    assert (copy / "db.dump").exists() and not (copy / "audio.tar.gz").exists()
    assert "audio" not in (copy / "SHA256SUMS").read_text(encoding="utf-8")


def test_restore_reapplies_erasures_after_database(project: Path) -> None:
    """Старая копия не знает о позднейших удалениях — журнал повторяется сразу после неё."""
    assert run(project, "backup.sh").returncode == 0
    (copy,) = backups(project)
    result = run(project, "restore.sh", str(copy), "--yes")
    assert result.returncode == 0, result.stderr
    calls = (project / "calls.log").read_text(encoding="utf-8").splitlines()
    restore_at = next(i for i, c in enumerate(calls) if "--clean" in c)
    reapply_at = next(i for i, c in enumerate(calls) if c == "research reapply-erasures")
    assert reapply_at > restore_at


LINE = '{{"at": "2026-10-{day}T12:00:00+00:00", "action": "delete", "learner_id": "{n}"}}\n'


def test_restore_merges_erasure_logs(project: Path) -> None:
    """В текущем журнале — удаления новее копии, в копии — те, что могли пропасть: нужны все."""
    log = project / "data" / "erasures" / "erasures.jsonl"
    log.write_text(LINE.format(day=18, n=1), encoding="utf-8")
    assert run(project, "backup.sh").returncode == 0
    (copy,) = backups(project)
    log.write_text(LINE.format(day=20, n=3), encoding="utf-8")  # журнал пересоздан после копии
    assert run(project, "restore.sh", str(copy), "--yes").returncode == 0
    assert log.read_text(encoding="utf-8") == LINE.format(day=18, n=1) + LINE.format(day=20, n=3)


def test_restore_needs_roles_on_new_server(project: Path) -> None:
    """В дампе владелец таблиц — muallim_owner; без ролей восстановление упадёт посередине."""
    assert run(project, "backup.sh").returncode == 0
    (copy,) = backups(project)
    result = run(project, "restore.sh", str(copy), "--yes", fail="roles")
    assert result.returncode != 0 and "make db-roles" in result.stderr
    assert "--clean" not in (project / "calls.log").read_text(encoding="utf-8")


def test_roles_script_passes_passwords_on_stdin_not_in_arguments(project: Path) -> None:
    """Аргументы команды видны в списке процессов (ps) — пароли туда не попадают."""
    env = project / ".env"
    env.write_text("POSTGRES_USER=admin\nPOSTGRES_DB=muallim\nDATABASE_URL=old\n", encoding="utf-8")
    result = run(project, "roles.sh")
    assert result.returncode == 0, result.stderr
    text = env.read_text(encoding="utf-8")
    app = next(x for x in text.splitlines() if x.startswith("APP_DB_PASSWORD=")).split("=", 1)[1]
    assert f"muallim_app:{app}@" in text and "MIGRATION_DATABASE_URL=" in text
    assert app not in (project / "calls.log").read_text(encoding="utf-8")
    assert "\\set app_password" in (project / "calls.log.stdin").read_text(encoding="utf-8")
    assert env.stat().st_mode & 0o077 == 0


def test_bot_container_gets_no_admin_or_owner_passwords() -> None:
    """Бот входит muallim_app; пароли суперпользователя, владельца и просмотра ему не нужны."""
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    env = compose["services"]["bot"]["environment"]
    for secret in ("POSTGRES_PASSWORD", "MIGRATION_DATABASE_URL", "READER_DB_PASSWORD"):
        assert env.get(secret) == "", secret
    assert "muallim_app" in env["DATABASE_URL"]


def test_restore_brings_back_lost_erasure_log(project: Path) -> None:
    """Новый компьютер: журнала нет — берётся из копии, иначе удаления не повторить."""
    log = project / "data" / "erasures" / "erasures.jsonl"
    log.write_text(LINE.format(day=18, n=1), encoding="utf-8")
    assert run(project, "backup.sh").returncode == 0
    (copy,) = backups(project)
    log.unlink()
    assert run(project, "restore.sh", str(copy), "--yes").returncode == 0
    assert log.read_text(encoding="utf-8") == LINE.format(day=18, n=1)


def test_restore_refuses_damaged_copy(project: Path) -> None:
    assert run(project, "backup.sh").returncode == 0
    (copy,) = backups(project)
    (copy / "db.dump").write_bytes(b"corrupted")
    result = run(project, "restore.sh", str(copy))
    assert result.returncode != 0 and "SHA256" in result.stderr
    calls = (project / "calls.log").read_text(encoding="utf-8")
    assert "--clean" not in calls  # база не тронута


def test_restore_needs_typed_confirmation(project: Path) -> None:
    assert run(project, "backup.sh").returncode == 0
    (copy,) = backups(project)
    result = run(project, "restore.sh", str(copy))  # пустой ввод — не «да»
    assert result.returncode != 0
    assert "--clean" not in (project / "calls.log").read_text(encoding="utf-8")


def test_restore_warns_that_old_copy_brings_back_deleted_learners(project: Path) -> None:
    assert run(project, "backup.sh").returncode == 0
    (copy,) = backups(project)
    result = run(project, "restore.sh", str(copy), "--yes")
    assert "удал" in result.stdout + result.stderr  # учеников, удалённых после копии, удалить снова


def test_restore_is_one_transaction_after_safety_copy(project: Path) -> None:
    assert run(project, "backup.sh").returncode == 0
    (copy,) = backups(project)
    env_yes = run(project, "restore.sh", str(copy), "--yes")
    assert env_yes.returncode == 0, env_yes.stderr
    calls = (project / "calls.log").read_text(encoding="utf-8").splitlines()
    restore = next(c for c in calls if "--clean" in c)
    assert "--single-transaction" in restore  # сбой посередине — база остаётся как была
    assert len(backups(project)) == 2  # перед восстановлением — копия текущего состояния
