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

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.architecture

FAKE_DOCKER = """#!/bin/sh
echo "$*" >> "$CALLS"
case "$*" in
  *pg_dump*) [ "$FAIL" = dump ] && exit 1; printf 'PGDMP-archive' ;;
  *"pg_restore --list"*) cat > /dev/null; [ "$FAIL" = list ] && exit 1; echo '; toc' ;;
  *pg_restore*) cat > /dev/null; [ "$FAIL" = restore ] && exit 1 ;;
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
    return tmp_path


def run(project: Path, script: str, *args: str, fail: str = "") -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "PATH": f"{project / 'bin'}{os.pathsep}{os.environ['PATH']}",
        "CALLS": str(project / "calls.log"),
        "FAIL": fail,
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
