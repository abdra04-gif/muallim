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


def _sounds(root: Path, rows: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "sounds.yaml").write_text(rows, encoding="utf-8")
    for name in ("a.ogg", "b.ogg"):
        (root / name).write_bytes(b"OggS" + name.encode())


async def test_sound_library_by_card_text_skips_rejected(tmp_path: Path) -> None:
    from muallim.infrastructure.audio.reference_library import SoundLibrary  # noqa: PLC0415

    _sounds(
        tmp_path,
        "- {text: رَ, file: a.ogg, status: unchecked, source: SRC-144}\n"
        "- {text: رِ, file: b.ogg, status: bad, source: SRC-144}\n"
        "- {text: رُ, file: ../../secret.ogg, status: ok, source: SRC-144}\n",
    )
    sounds = SoundLibrary.load(tmp_path)
    assert sounds.has("رَ") and await sounds.get("رَ") == b"OggSa.ogg"
    assert not sounds.has("رِ")  # человек прослушал и отклонил
    assert not sounds.has("رُ")  # путь за пределы папки не принимаем
    assert not SoundLibrary.load(tmp_path / "нет").has("رَ")


async def test_library_sound_is_the_last_resort_after_teacher_and_ayah(tmp_path: Path) -> None:
    from muallim.infrastructure.audio.reference_library import (  # noqa: PLC0415
        CombinedReferenceAudio,
        RecitationCache,
        SoundLibrary,
    )

    async def fetch(url: str) -> bytes:
        return b"mp3"

    _sounds(tmp_path / "library", "- {text: رَ, file: a.ogg, status: ok, source: SRC-144}\n")
    teacher = FileReferenceAudio(tmp_path / "teacher")
    library = CombinedReferenceAudio(
        teacher,
        RecitationCache(tmp_path / "cache", fetch),
        {},
        SoundLibrary.load(tmp_path / "library"),
        {"L004-02": "رَ", "L004-03": "رِ"},
    )
    assert library.has("L004-02") and not library.has("L004-03")
    assert await library.get("L004-02") == b"OggSa.ogg"
    await teacher.save("L004-02", b"teacher")
    assert await library.get("L004-02") == b"teacher"


async def test_ayat_are_read_by_alafasy_by_default(tmp_path: Path) -> None:
    """Чтец аятов — Мишари Рашид аль-Афаси, муратталь без пауз для повторения (SRC-145)."""
    from muallim.bootstrap.config import Settings  # noqa: PLC0415
    from muallim.infrastructure.audio.reference_library import RecitationCache  # noqa: PLC0415

    calls: list[str] = []

    async def fetch(url: str) -> bytes:
        calls.append(url)
        return b"mp3"

    await RecitationCache(tmp_path, fetch).get("1:2")
    assert calls == ["https://everyayah.com/data/Alafasy_128kbps/001002.mp3"]
    assert Settings.model_fields["reciter"].default == "Alafasy_128kbps"


async def test_recitation_is_trimmed_once_and_cached_trimmed(tmp_path: Path) -> None:
    """Тишина в начале и в конце аята обрезается один раз — при скачивании."""
    from muallim.infrastructure.audio.reference_library import RecitationCache  # noqa: PLC0415

    trims: list[bytes] = []

    async def fetch(url: str) -> bytes:
        return b"  mp3  "

    async def trim(audio: bytes) -> bytes:
        trims.append(audio)
        return audio.strip()

    cache = RecitationCache(tmp_path, fetch, trim=trim)
    assert await cache.get("1:1") == b"mp3"
    assert await cache.get("1:1") == b"mp3"  # второй раз — из кэша, уже обрезанный
    assert trims == [b"  mp3  "]


LIBRARY = Path(__file__).resolve().parents[2] / "curriculum" / "audio" / "library"


def test_repository_sounds_point_to_existing_files_with_source() -> None:
    import yaml  # noqa: PLC0415

    manifest = LIBRARY / "sounds.yaml"
    assert manifest.is_file(), "нет curriculum/audio/library/sounds.yaml"
    for row in yaml.safe_load(manifest.read_text(encoding="utf-8")) or []:
        assert row["status"] in ("unchecked", "ok", "bad"), row["text"]
        assert row["status"] == "bad" or (LIBRARY / row["file"]).is_file(), row["text"]
        assert str(row.get("source", "")).startswith("SRC-"), row["text"]


_LETTER = r"[\u0621-\u064A\u0671]"
_SYLLABLE = rf"{_LETTER}[\u064E-\u0650]"


def test_every_letter_and_syllable_card_has_a_library_sound(curriculum: object) -> None:
    """Буква, слог и тройка слогов звучат готовой записью диктора, а не нарезкой (SRC-144)."""
    import re  # noqa: PLC0415

    from muallim.domain.curriculum import Curriculum  # noqa: PLC0415
    from muallim.infrastructure.audio.reference_library import SoundLibrary  # noqa: PLC0415

    assert isinstance(curriculum, Curriculum)
    pattern = re.compile(rf"(?:{_LETTER}|{_SYLLABLE}(?: {_SYLLABLE}){{2}}|{_SYLLABLE})")
    sounds = SoundLibrary.load(LIBRARY)
    cards = {
        i.text
        for les in curriculum.lessons
        for i in les.items
        if not i.quran and pattern.fullmatch(i.text)
    }
    assert cards, "шаблон не нашёл ни одной карточки-слога"
    missing = sorted(t for t in cards if not sounds.has(t) and t not in {"ٱ", "ة"})
    assert not missing, missing
