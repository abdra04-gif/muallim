"""FR-56 (ADR-0074): ролики «🎬 Как произносить» — манифест curriculum/video/videos.yaml и файлы.

``VideoLibrary`` повторяет ``SoundLibrary`` (ADR-0068): поиск по тексту карточки и по букве
(ролик-тройка), ``status: bad`` не отдаётся, ``unchecked`` — отдаётся (как у звука), строка без
файла не отдаётся, из имени файла берётся только имя — из папки не выйти. Временная папка с
фальшивым mp4, без сети. Вторая часть — проверка настоящих данных репозитория.
"""

import re
import struct
from pathlib import Path
from typing import Any

import pytest
import yaml

from muallim.domain.curriculum import Curriculum

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
VIDEO_DIR = ROOT / "curriculum" / "video"
SOURCES = ROOT / "docs" / "research" / "sources.md"
MAX_BYTES = 20 * 1024 * 1024
FIELDS = {"text", "file", "seconds", "width", "height", "status", "source", "picture", "origin"}

FAKE_MP4 = b"\x00\x00\x00\x18ftypmp42"


def _manifest(root: Path, rows: str, files: tuple[str, ...]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "videos.yaml").write_text(rows, encoding="utf-8")
    for name in files:
        (root / name).write_bytes(FAKE_MP4 + name.encode())


ROW = "  seconds: 4.29\n  width: 1280\n  height: 720\n  source: SRC-144\n  picture: SRC-148\n"


def _row(text: str, file: str, status: str, letter: str = "") -> str:
    head = f"- text: {text}\n" + (f"  letter: {letter}\n" if letter else "")
    return head + f"  file: {file}\n  status: {status}\n" + ROW


@pytest.fixture
def library(tmp_path: Path) -> Any:
    from muallim.infrastructure.video.library import VideoLibrary  # noqa: PLC0415

    (tmp_path / "secret.mp4").write_bytes(b"secret")  # вне папки роликов
    _manifest(
        tmp_path / "video",
        _row("رَ", "a.mp4", "ok")
        + _row("رِ", "b.mp4", "unchecked")
        + _row("رُ", "c.mp4", "bad")
        + _row("زَ", "missing.mp4", "ok")
        + _row("زِ", "../secret.mp4", "ok")
        + _row("رَ رِ رُ", "t.mp4", "ok", letter="ر")
        + _row("زَ زِ زُ", "z.mp4", "bad", letter="ز"),
        ("a.mp4", "b.mp4", "c.mp4", "t.mp4", "z.mp4"),
    )
    return VideoLibrary.load(tmp_path / "video")


async def test_video_is_found_by_card_text(library: Any) -> None:
    key = library.for_text("رَ")
    assert key is not None
    video = await library.get(key)
    assert video is not None
    assert video.data == FAKE_MP4 + b"a.mp4"
    assert (video.key, video.seconds, video.width, video.height) == (key, 4.29, 1280, 720)


async def test_unchecked_video_is_given_like_unchecked_sound(library: Any) -> None:
    """``SoundLibrary`` отдаёт ``unchecked`` (не прослушано), не отдаёт только ``bad``."""
    key = library.for_text("رِ")
    assert key is not None and await library.get(key) is not None


def test_rejected_video_is_not_given(library: Any) -> None:
    assert library.for_text("رُ") is None  # человек посмотрел и отклонил
    assert library.for_letter("ز") is None  # и тройку тоже


def test_row_without_file_is_not_given(library: Any) -> None:
    assert library.for_text("زَ") is None


def test_file_name_cannot_leave_the_video_folder(library: Any) -> None:
    assert library.for_text("زِ") is None


async def test_letter_triple_is_found_by_letter(library: Any) -> None:
    key = library.for_letter("ر")
    assert key is not None and key == library.for_text("رَ رِ رُ")
    video = await library.get(key)
    assert video is not None and video.data == FAKE_MP4 + b"t.mp4"
    assert library.for_letter("م") is None


@pytest.mark.parametrize("key", ["", "нет", "../secret", "../../secret.mp4", "secret"])
async def test_unknown_or_suspicious_key_gives_nothing(library: Any, key: str) -> None:
    assert await library.get(key) is None


async def test_key_of_video_rejected_after_reload_gives_nothing(tmp_path: Path) -> None:
    """Человек поставил ``bad``, бот перезапущен: старая кнопка с прежним ключом — пусто."""
    from muallim.infrastructure.video.library import VideoLibrary  # noqa: PLC0415

    root = tmp_path / "video"
    _manifest(root, _row("رَ", "a.mp4", "ok"), ("a.mp4",))
    key = VideoLibrary.load(root).for_text("رَ")
    assert key is not None
    _manifest(root, _row("رَ", "a.mp4", "bad"), ())
    again = VideoLibrary.load(root)
    assert again.for_text("رَ") is None
    assert await again.get(key) is None


def test_missing_manifest_is_an_empty_library(tmp_path: Path) -> None:
    from muallim.infrastructure.video.library import VideoLibrary  # noqa: PLC0415

    empty = VideoLibrary.load(tmp_path / "нет")
    assert empty.for_text("رَ") is None and empty.for_letter("ر") is None


def test_video_library_implements_the_port(library: Any) -> None:
    from muallim.application.ports.storage import ArticulationVideoLibrary  # noqa: PLC0415

    port: ArticulationVideoLibrary = library  # mypy проверяет совместимость с портом
    assert port.for_text("нет") is None


# ---------- настоящие данные: curriculum/video/ ----------
def _rows() -> list[dict[str, Any]]:
    rows = yaml.safe_load((VIDEO_DIR / "videos.yaml").read_text(encoding="utf-8"))
    assert isinstance(rows, list) and rows
    return rows


def _mp4_size(path: Path) -> tuple[int, int]:
    """Ширина и высота видеодорожки из заголовка ``tkhd`` (ISO 14496-12, без ffprobe)."""
    data = path.read_bytes()
    best = (0, 0)
    i = data.find(b"tkhd")
    while i > 0:
        version = data[i + 4]
        off = i + 4 + 4 + (32 if version == 1 else 20) + 8 + 8 + 36
        w, h = struct.unpack(">II", data[off : off + 8])
        best = max(best, (w >> 16, h >> 16))
        i = data.find(b"tkhd", i + 1)
    return best


def _source_keys() -> set[str]:
    return set(re.findall(r"^\| (SRC-\d{3}) \|", SOURCES.read_text(encoding="utf-8"), re.M))


@pytest.mark.parametrize("row", _rows(), ids=lambda r: str(r.get("file")))
def test_every_manifest_row_has_a_720p_file_under_20_mb(row: dict[str, Any]) -> None:
    assert row.keys() >= FIELDS, sorted(FIELDS - row.keys())
    path = VIDEO_DIR / str(row["file"])
    assert Path(str(row["file"])).name == row["file"]  # только имя, без папок
    assert path.is_file(), path
    assert path.stat().st_size <= MAX_BYTES
    assert (row["width"], row["height"]) == (1280, 720)
    assert _mp4_size(path) == (1280, 720)
    assert 0 < float(row["seconds"]) < 60
    assert row["status"] in {"ok", "unchecked", "bad"}


@pytest.mark.parametrize("row", _rows(), ids=lambda r: str(r.get("file")))
def test_every_video_points_to_known_sources(row: dict[str, Any]) -> None:
    keys = _source_keys()
    assert row["source"] in keys and row["source"] == "SRC-144"  # звук ар-Раи
    assert row["picture"] in keys and row["picture"] == "SRC-148"  # рисунок Lynch, CC BY 2.5
    assert (ROOT / str(row["origin"])).is_file(), row["origin"]  # запись, из которой звук


def test_every_video_text_is_a_card_text(curriculum: Curriculum) -> None:
    cards = {i.text for les in curriculum.lessons for i in les.items}
    missing = [r["text"] for r in _rows() if r["text"] not in cards]
    assert not missing, missing


HAMZA_CARRIERS = {"أ": {"أ", "إ"}}  # тройка «أَ إِ أُ»: хамза над алифом и под ним


def test_every_letter_triple_belongs_to_its_letter() -> None:
    triples = [r for r in _rows() if r.get("letter")]
    assert {r["letter"] for r in triples} >= {"أ", "ر", "ز"}  # готово: أ ر ز (FR-56)
    for r in triples:
        letter = r["letter"]
        words = r["text"].split()
        assert len(letter) == 1 and len(words) == 3, r
        allowed = HAMZA_CARRIERS.get(letter, {letter})
        assert all(w[0] in allowed for w in words), r


def test_repository_videos_are_all_reachable_from_the_library() -> None:
    from muallim.infrastructure.video.library import VideoLibrary  # noqa: PLC0415

    library = VideoLibrary.load(VIDEO_DIR)
    for r in _rows():
        if r["status"] == "bad":
            continue
        assert library.for_text(r["text"]) is not None, r["text"]
        if r.get("letter"):
            assert library.for_letter(r["letter"]) == library.for_text(r["text"])


def test_every_video_file_is_in_the_manifest() -> None:
    listed = {r["file"] for r in _rows()}
    stray = sorted(p.name for p in VIDEO_DIR.glob("*.mp4") if p.name not in listed)
    assert not stray, stray


def test_video_button_callbacks_fit_telegram_limit_for_every_card(
    curriculum: Curriculum, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Настоящие ключи роликов: 🎬 на карточках и в шпаргалке ≤ 64 байт; на карточках
    встречается каждый ролик манифеста, кроме ``bad``."""
    from muallim.infrastructure.video.library import VideoLibrary  # noqa: PLC0415
    from muallim.presentation.telegram import callbacks, render, screens  # noqa: PLC0415

    monkeypatch.setattr(render, "available", lambda: False)
    library = VideoLibrary.load(VIDEO_DIR)
    prefix = callbacks.Watch.__prefix__ + ":"
    keys: set[str] = set()
    for les in curriculum.lessons:
        for item in les.items:
            s = screens.card(curriculum, item, True, True, videos=library)
            for row in s.keyboard.inline_keyboard:
                for b in row:
                    data = b.callback_data or ""
                    if data.startswith(prefix):
                        assert len(data.encode()) <= 64, data
                        keys.add(callbacks.Watch.unpack(data).v)
    expected = {library.for_text(r["text"]) for r in _rows() if r["status"] != "bad"}
    assert keys == expected
    sheet = screens.letters_sheet(curriculum, "L031", audio=frozenset(), videos=library)
    for row in sheet.keyboard.inline_keyboard:
        for b in row:
            assert len((b.callback_data or "").encode()) <= 64, b.callback_data


# ---------- общий контракт порта: фейк тестов и настоящий адаптер ----------
def _in_memory(tmp_path: Path) -> Any:
    from tests.fakes import InMemoryVideos  # noqa: PLC0415

    return InMemoryVideos({"رَ": "k-ra", "رَ رِ رُ": "k-ra3"}, {"ر": "k-ra3"})


def _from_files(tmp_path: Path) -> Any:
    from muallim.infrastructure.video.library import VideoLibrary  # noqa: PLC0415

    _manifest(
        tmp_path / "c",
        _row("رَ", "a.mp4", "ok") + _row("رَ رِ رُ", "t.mp4", "ok", letter="ر"),
        ("a.mp4", "t.mp4"),
    )
    return VideoLibrary.load(tmp_path / "c")


@pytest.mark.parametrize("make", [_in_memory, _from_files], ids=["fake", "files"])
async def test_video_library_contract(tmp_path: Path, make: Any) -> None:
    """Фейк ``InMemoryVideos`` ведёт себя как ``VideoLibrary`` — unit-тесты им можно верить."""
    library = make(tmp_path)
    key = library.for_text("رَ")
    assert key is not None
    video = await library.get(key)
    assert video is not None and video.key == key
    assert (video.width, video.height) == (1280, 720) and video.seconds > 0 and video.data
    assert library.for_letter("ر") == library.for_text("رَ رِ رُ") is not None
    assert library.for_letter("ر") != key
    assert library.for_text("مَ") is None and library.for_letter("م") is None
    assert await library.get("нет-такого") is None
