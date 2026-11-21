"""Деление попыток на учёбу и тест (предрегистрация 0.7, ADR-0090, TD-FN-174).

≈ 30 % попыток — в тест: часть определяется при сохранении по хешу номера попытки с солью.
Соль создаётся один раз и лежит в закрытой части (рядом с записями, папка ``holdout``), агенту
её не видно. Голос тестовой попытки бот кладёт в закрытую часть, а не к остальным записям;
читают и удаляют записи из обеих частей (разметка учителей, удаление данных ученика).

Предложенный интерфейс:
- ``muallim.domain.split``: ``Part`` (TRAIN, TEST), ``TEST_SHARE = 0.30``,
  ``part_of(attempt_id: UUID, salt: bytes) -> Part``;
- порт ``SplitSalt`` (``application/ports/storage.py``): ``get() -> bytes``,
  ``fingerprint() -> str``;
- ``FileSplitSalt(path)`` (``infrastructure/audio/holdout.py``): создаёт 32 байта, права 0600;
- ``FileAudioStore.save(audio, part=Part.TRAIN)``: тестовые — в
  ``root.parent / "holdout" / "audio"``;
- ``AssessRecitation(..., split_salt=...)``: без соли — всё в учёбу (как раньше).
"""

import hashlib
import stat
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from muallim.domain.split import TEST_SHARE, Part, part_of
from muallim.infrastructure.audio.file_store import FileAudioStore
from muallim.infrastructure.audio.holdout import FileSplitSalt

SALT = b"s" * 32
OGG = b"OggS fake voice"


# ---------- правило ----------
def test_test_share_is_thirty_percent() -> None:
    assert TEST_SHARE == 0.30  # предрегистрация 0.7, решение автора 2026-11-21


def test_same_attempt_always_lands_in_the_same_part() -> None:
    attempt = uuid4()
    assert {part_of(attempt, SALT) for _ in range(5)} == {part_of(attempt, SALT)}


def test_about_thirty_percent_of_attempts_go_to_test() -> None:
    ids = [UUID(int=k) for k in range(1, 20_001)]
    share = sum(part_of(i, SALT) is Part.TEST for i in ids) / len(ids)
    assert 0.28 < share < 0.32


def test_another_salt_gives_another_split() -> None:
    ids = [UUID(int=k) for k in range(1, 2001)]
    moved = sum(part_of(i, SALT) is not part_of(i, b"t" * 32) for i in ids)
    assert moved > 400  # ≈ 42 % при независимых делениях 30/70


# ---------- соль ----------
def test_salt_is_created_once_and_kept(tmp_path: Path) -> None:
    path = tmp_path / "holdout" / "salt"
    first = FileSplitSalt(path).get()
    assert len(first) == 32
    assert FileSplitSalt(path).get() == first, "соль не меняется между запусками"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_existing_salt_is_never_overwritten(tmp_path: Path) -> None:
    path = tmp_path / "salt"
    path.write_bytes(SALT)
    assert FileSplitSalt(path).get() == SALT


def test_salt_fingerprint_is_sha256_of_salt(tmp_path: Path) -> None:
    path = tmp_path / "salt"
    path.write_bytes(SALT)
    assert FileSplitSalt(path).fingerprint() == hashlib.sha256(SALT).hexdigest()


# ---------- голоса ----------
async def test_test_voice_goes_to_the_closed_part(tmp_path: Path) -> None:
    store = FileAudioStore(tmp_path / "audio")
    sha = await store.save(OGG, part=Part.TEST)
    closed = tmp_path / "holdout" / "audio" / sha[:2] / f"{sha}.ogg"
    assert closed.is_file()
    assert not (tmp_path / "audio" / sha[:2] / f"{sha}.ogg").exists()


async def test_training_voice_stays_with_the_others(tmp_path: Path) -> None:
    store = FileAudioStore(tmp_path / "audio")
    sha = await store.save(OGG)
    assert (tmp_path / "audio" / sha[:2] / f"{sha}.ogg").is_file()
    assert not (tmp_path / "holdout").exists()


async def test_test_voice_is_readable_and_deletable_by_the_bot(tmp_path: Path) -> None:
    """Учителя размечают и тест; удаление данных ученика чистит и закрытую часть."""
    store = FileAudioStore(tmp_path / "audio")
    sha = await store.save(OGG, part=Part.TEST)
    assert await store.read(sha) == OGG
    await store.delete(sha)
    assert await store.read(sha) is None


@pytest.mark.parametrize("part", [Part.TRAIN, Part.TEST])
def test_part_values_are_stable_strings(part: Part) -> None:
    """Значения пойдут в БД и выгрузки — менять их нельзя."""
    assert part.value in {"train", "test"}


# ---------- ревью шага 1 (2026-11-21) ----------
def test_lost_salt_with_test_voices_is_an_error_not_a_new_salt(tmp_path: Path) -> None:
    """Соль пропала, а тестовые голоса есть — новая соль молча перемешала бы части."""
    from muallim.infrastructure.audio.holdout import SaltLostError  # noqa: PLC0415

    voice = tmp_path / "holdout" / "audio" / "ab" / ("ab" + "0" * 62 + ".ogg")
    voice.parent.mkdir(parents=True)
    voice.write_bytes(OGG)
    with pytest.raises(SaltLostError):
        FileSplitSalt(tmp_path / "holdout" / "salt").get()
    assert not (tmp_path / "holdout" / "salt").exists()


@pytest.mark.parametrize("content", [b"", b"short"], ids=["empty", "cut"])
def test_damaged_salt_is_an_error(tmp_path: Path, content: bytes) -> None:
    from muallim.infrastructure.audio.holdout import SaltLostError  # noqa: PLC0415

    path = tmp_path / "salt"
    path.write_bytes(content)
    with pytest.raises(SaltLostError):
        FileSplitSalt(path).get()


def test_salt_appears_only_whole(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Сбой при создании не оставляет пустой или обрезанный файл соли."""

    def boom(_: int) -> bytes:
        raise OSError("disk")

    monkeypatch.setattr("muallim.infrastructure.audio.holdout.secrets.token_bytes", boom)
    with pytest.raises(OSError):
        FileSplitSalt(tmp_path / "salt").get()
    assert not (tmp_path / "salt").exists()


@pytest.mark.parametrize(
    "first", [Part.TRAIN, Part.TEST], ids=["train_then_test", "test_then_train"]
)
async def test_same_voice_in_both_parts_is_kept_only_in_test(tmp_path: Path, first: Part) -> None:
    """Одни и те же байты в учёбе и тесте — тест побеждает: голос не утекает в учёбу."""
    store = FileAudioStore(tmp_path / "audio")
    second = Part.TEST if first is Part.TRAIN else Part.TRAIN
    sha = await store.save(OGG, part=first)
    await store.save(OGG, part=second)
    assert store.part_on_disk(sha) is Part.TEST
    assert not store.path_for(sha, Part.TRAIN).exists()
    assert await store.read(sha) == OGG


async def test_part_on_disk_tells_where_a_voice_is(tmp_path: Path) -> None:
    store = FileAudioStore(tmp_path / "audio")
    train = await store.save(b"one")
    test = await store.save(b"two", part=Part.TEST)
    assert (store.part_on_disk(train), store.part_on_disk(test)) == (Part.TRAIN, Part.TEST)
    assert store.part_on_disk("f" * 64) is None


async def test_closed_part_folders_are_owner_only(tmp_path: Path) -> None:
    store = FileAudioStore(tmp_path / "audio")
    sha = await store.save(OGG, part=Part.TEST)
    for folder in (
        tmp_path / "holdout",
        tmp_path / "holdout" / "audio",
        store.path_for(sha, Part.TEST).parent,
    ):
        assert stat.S_IMODE(folder.stat().st_mode) == 0o700, folder


async def test_dataset_audio_copy_takes_training_and_counts_test(tmp_path: Path) -> None:
    """Выгрузка для обучения: тестовые попытки не копируются и не падают, а считаются."""
    from muallim.research.dataset import copy_training_audio  # noqa: PLC0415

    store = FileAudioStore(tmp_path / "audio")
    train, test = await store.save(b"one"), await store.save(b"two", part=Part.TEST)
    rows = [
        {"audio_sha256": train, "audio": f"audio/{train}.ogg"},
        {"audio_sha256": test, "audio": f"audio/{test}.ogg"},
    ]
    out = tmp_path / "export"
    (out / "audio").mkdir(parents=True)
    kept, excluded = copy_training_audio(rows, store, out)
    assert [r["audio_sha256"] for r in kept] == [train] and excluded == 1
    assert (out / f"audio/{train}.ogg").is_file() and not (out / f"audio/{test}.ogg").exists()


async def test_dataset_audio_copy_still_fails_on_truly_missing_files(tmp_path: Path) -> None:
    from muallim.research.annotation import AnnotationError  # noqa: PLC0415
    from muallim.research.dataset import copy_training_audio  # noqa: PLC0415

    store = FileAudioStore(tmp_path / "audio")
    rows = [{"audio_sha256": "f" * 64, "audio": "audio/x.ogg"}]
    with pytest.raises(AnnotationError):
        copy_training_audio(rows, store, tmp_path)


# ---------- шаг 2а: часть у попытки и чтения суры; суры делятся так же (автор: «а») ----------
def test_attempt_and_sura_reading_are_training_by_default() -> None:
    from dataclasses import fields  # noqa: PLC0415

    from muallim.domain.attempt import Attempt  # noqa: PLC0415
    from muallim.domain.sura import SuraReading  # noqa: PLC0415

    for model in (Attempt, SuraReading):
        default = {f.name: f.default for f in fields(model)}.get("part")
        assert default is Part.TRAIN, model


# ---------- шаг 3: отпечаток соли в журнал при запуске бота (предрегистрация 0.7) ----------
def test_bot_start_logs_the_salt_fingerprint_not_the_salt(tmp_path: Path) -> None:
    """Отпечаток (SHA-256) — в журнал бота, оттуда в research-log до первого обучения; самой
    соли в журнале нет. Нет соли — бот создаёт её здесь же, до первой попытки."""
    from muallim.bootstrap.main import split_line  # noqa: PLC0415

    salt = FileSplitSalt(tmp_path / "salt")
    line = split_line(salt)
    assert salt.fingerprint() in line and "TD-FN-174" in line
    assert salt.get().hex() not in line
    assert split_line(None) == ""
