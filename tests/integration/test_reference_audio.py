from pathlib import Path

import pytest

from muallim.infrastructure.audio.reference_library import FileReferenceAudio


async def test_reads_existing_file(tmp_path: Path) -> None:
    (tmp_path / "L01-02.ogg").write_bytes(b"voice")
    library = FileReferenceAudio(tmp_path)
    assert library.has("L01-02") and await library.get("L01-02") == b"voice"
    assert not library.has("L01-03") and await library.get("L01-03") is None


@pytest.mark.parametrize("bad", ["../secret", "L01-02/../../x", "", "a" * 40, "L1-01"])
async def test_rejects_suspicious_ids(tmp_path: Path, bad: str) -> None:
    library = FileReferenceAudio(tmp_path)
    assert not library.has(bad) and await library.get(bad) is None


def test_repository_audio_files_belong_to_curriculum(curriculum: object) -> None:
    from muallim.domain.curriculum import Curriculum  # noqa: PLC0415

    assert isinstance(curriculum, Curriculum)
    root = Path(__file__).resolve().parents[2] / "curriculum" / "audio"
    ids = {item.id for lesson in curriculum.lessons for item in lesson.items}
    for path in root.glob("*.ogg"):
        assert path.stem in ids, f"аудио {path.name} не соответствует ни одной карточке"


async def test_teacher_recording_is_saved_and_readable(tmp_path: Path) -> None:
    library = FileReferenceAudio(tmp_path / "audio")
    await library.save("L02-01", b"voice")
    assert library.has("L02-01") and await library.get("L02-01") == b"voice"
    await library.save("L02-01", b"better")  # перезапись — новая версия эталона
    assert await library.get("L02-01") == b"better"


async def test_save_rejects_suspicious_id(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="id"):
        await FileReferenceAudio(tmp_path).save("../x", b"v")


async def test_quran_items_get_recitation_and_teacher_record_wins(tmp_path: Path) -> None:
    from muallim.infrastructure.audio.reference_library import (  # noqa: PLC0415
        CombinedReferenceAudio,
        RecitationCache,
    )

    calls: list[str] = []

    async def fetch(url: str) -> bytes:
        calls.append(url)
        return b"mp3"

    teacher = FileReferenceAudio(tmp_path / "teacher")
    cache = RecitationCache(tmp_path / "cache", fetch, reciter="Husary_Muallim_128kbps")
    library = CombinedReferenceAudio(teacher, cache, {"L200-01": "112:1"})
    assert library.has("L200-01") and not library.has("L200-02")
    assert await library.get("L200-01") == b"mp3"
    assert await library.get("L200-01") == b"mp3"  # второй раз — из кэша
    assert calls == ["https://everyayah.com/data/Husary_Muallim_128kbps/112001.mp3"]
    await library.save("L200-01", b"voice")
    assert await library.get("L200-01") == b"voice"


async def test_recitation_failure_returns_none(tmp_path: Path) -> None:
    from muallim.infrastructure.audio.reference_library import (  # noqa: PLC0415
        CombinedReferenceAudio,
        RecitationCache,
    )

    async def fetch(url: str) -> bytes:
        raise OSError("нет сети")

    cache = RecitationCache(tmp_path / "cache", fetch)
    library = CombinedReferenceAudio(FileReferenceAudio(tmp_path), cache, {"L200-01": "1:1"})
    assert await library.get("L200-01") is None


def _cuts(root: Path, rows: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "cuts.yaml").write_text(rows, encoding="utf-8")
    for name in ("a.ogg", "b.ogg"):
        (root / name).write_bytes(b"OggS" + name.encode())


async def test_husary_cuts_by_card_text_skip_rejected(tmp_path: Path) -> None:
    from muallim.infrastructure.audio.reference_library import HusaryCuts  # noqa: PLC0415

    _cuts(
        tmp_path,
        "- {text: رَ, file: a.ogg, status: unchecked}\n"
        "- {text: رِ, file: b.ogg, status: bad}\n"
        "- {text: رُ, file: ../../secret.ogg, status: ok}\n",
    )
    cuts = HusaryCuts.load(tmp_path)
    assert cuts.has("رَ") and await cuts.get("رَ") == b"OggSa.ogg"
    assert not cuts.has("رِ")  # человек прослушал и отклонил
    assert not cuts.has("رُ")  # путь за пределы папки не принимаем
    assert not HusaryCuts.load(tmp_path / "нет").has("رَ")


async def test_cut_is_the_last_resort_after_teacher_and_ayah(tmp_path: Path) -> None:
    from muallim.infrastructure.audio.reference_library import (  # noqa: PLC0415
        CombinedReferenceAudio,
        HusaryCuts,
        RecitationCache,
    )

    async def fetch(url: str) -> bytes:
        return b"mp3"

    _cuts(tmp_path / "husary", "- {text: رَ, file: a.ogg, status: ok}\n")
    teacher = FileReferenceAudio(tmp_path / "teacher")
    library = CombinedReferenceAudio(
        teacher,
        RecitationCache(tmp_path / "cache", fetch),
        {},
        HusaryCuts.load(tmp_path / "husary"),
        {"L004-02": "رَ", "L004-03": "رِ"},
    )
    assert library.has("L004-02") and not library.has("L004-03")
    assert await library.get("L004-02") == b"OggSa.ogg"
    await teacher.save("L004-02", b"teacher")
    assert await library.get("L004-02") == b"teacher"


def test_repository_cuts_point_to_existing_files() -> None:
    root = Path(__file__).resolve().parents[2] / "curriculum" / "audio" / "husary"
    manifest = root / "cuts.yaml"
    if not manifest.is_file():
        pytest.skip("нарезок пока нет")
    import yaml  # noqa: PLC0415

    for row in yaml.safe_load(manifest.read_text(encoding="utf-8")) or []:
        assert row["status"] in ("unchecked", "ok", "bad"), row["text"]
        assert row["status"] == "bad" or (root / row["file"]).is_file(), row["text"]
        assert row["parts"] and all(":" in p["aya"] for p in row["parts"]), row["text"]
