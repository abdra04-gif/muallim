import hashlib
from pathlib import Path

import pytest

from muallim.infrastructure.audio.file_store import FileAudioStore


async def test_save_is_content_addressed_and_private(tmp_path: Path) -> None:
    store = FileAudioStore(tmp_path)
    sha = await store.save(b"voice")
    assert sha == hashlib.sha256(b"voice").hexdigest()
    path = store.path_for(sha)
    assert path.read_bytes() == b"voice"
    assert oct(path.stat().st_mode & 0o777) == "0o600"
    assert await store.save(b"voice") == sha  # повторное сохранение не ломается


async def test_delete(tmp_path: Path) -> None:
    store = FileAudioStore(tmp_path)
    sha = await store.save(b"voice")
    await store.delete(sha)
    assert not store.path_for(sha).exists()
    await store.delete(sha)  # повторное удаление — не ошибка


@pytest.mark.parametrize("bad", ["../../etc/passwd", "a" * 63, "Z" * 64, "../" + "a" * 61])
def test_path_traversal_rejected(tmp_path: Path, bad: str) -> None:
    with pytest.raises(ValueError):
        FileAudioStore(tmp_path).path_for(bad)
