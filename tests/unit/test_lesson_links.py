"""FR-67 (ADR-0082, срез 1): ссылки на видеоурок — ``curriculum/lesson_links.yaml``.

Порт ``LessonLinks.for_lesson(lesson_id) -> str | None`` (``application/ports/storage.py``),
адаптер ``YamlLessonLinks.load(path)`` (``infrastructure/curriculum/lesson_links.py``).

Контракт: нет файла, битый YAML, не-строка или ссылка не ``https://`` с хостом — для этого урока
ссылки нет (``None``), кнопки видео нет, бот не падает (иначе Telegram отклонит всю клавиатуру:
``BUTTON_URL_INVALID``). Плохая ссылка урока НЕ подменяется на ``default``. Ссылка урока главнее
``default``; пробелы вокруг ссылки обрезаются; схема ``https`` — в любом регистре, но
значение отдаётся обрезанным.
"""

from pathlib import Path

import pytest

from muallim.application.ports.storage import LessonLinks
from muallim.infrastructure.curriculum.lesson_links import YamlLessonLinks
from tests.conftest import CURRICULUM_DIR

DEFAULT = "https://example.org/channel"
OWN = "https://example.org/watch?v=abc"


def _load(tmp_path: Path, text: str | None) -> LessonLinks:
    path = tmp_path / "lesson_links.yaml"
    if text is not None:
        path.write_text(text, encoding="utf-8")
    return YamlLessonLinks.load(path)


def test_default_link_is_used_for_any_lesson(tmp_path: Path) -> None:
    links = _load(tmp_path, f"default: {DEFAULT}\nlessons: {{}}\n")
    assert links.for_lesson("L004") == DEFAULT and links.for_lesson("L031") == DEFAULT


def test_deep_video_uses_lesson_override(tmp_path: Path) -> None:
    links = _load(tmp_path, f"default: {DEFAULT}\nlessons:\n  L004: {OWN}\n")
    assert links.for_lesson("L004") == OWN
    assert links.for_lesson("L005") == DEFAULT


def test_lesson_link_works_without_default(tmp_path: Path) -> None:
    links = _load(tmp_path, f"lessons:\n  L004: {OWN}\n")
    assert links.for_lesson("L004") == OWN
    assert links.for_lesson("L005") is None


def test_deep_without_links_file_has_no_video_button(tmp_path: Path) -> None:
    assert _load(tmp_path, None).for_lesson("L004") is None


@pytest.mark.parametrize(
    "text", ["default: [unclosed\n  lessons: {", "- just\n- a list\n", "42\n", "", "lessons: 5\n"]
)
def test_broken_links_file_gives_no_link_and_does_not_raise(tmp_path: Path, text: str) -> None:
    assert _load(tmp_path, text).for_lesson("L004") is None


@pytest.mark.parametrize(
    "bad",
    [
        "'http://example.org/'",
        "'javascript:alert(1)'",
        "'ftp://example.org/x'",
        "'example.org'",
        "'tg://resolve?domain=x'",
        "'https://'",
        "'https:///path'",
        "'https://   '",
        "123",
        "[a, b]",
        "{a: b}",
        "''",
    ],
)
def test_deep_rejects_non_https_link(tmp_path: Path, bad: str) -> None:
    """Плохая ссылка урока — ``None`` для этого урока, а не подмена на ``default``."""
    links = _load(tmp_path, f"default: {DEFAULT}\nlessons:\n  L004: {bad}\n")
    assert links.for_lesson("L004") is None
    assert links.for_lesson("L005") == DEFAULT


@pytest.mark.parametrize("bad", ["'http://example.org/'", "'https://'", "123", "[a]", "''"])
def test_bad_default_without_override_gives_none(tmp_path: Path, bad: str) -> None:
    links = _load(tmp_path, f"default: {bad}\n")
    assert links.for_lesson("L004") is None


def test_non_string_default_does_not_break_lesson_links(tmp_path: Path) -> None:
    links = _load(tmp_path, f"default: 123\nlessons:\n  L004: {OWN}\n")
    assert links.for_lesson("L004") == OWN
    assert links.for_lesson("L005") is None


def test_whitespace_around_link_is_trimmed(tmp_path: Path) -> None:
    links = _load(tmp_path, f"default: '  {DEFAULT}  '\nlessons:\n  L004: \"\\t{OWN} \"\n")
    assert links.for_lesson("L004") == OWN and links.for_lesson("L005") == DEFAULT


def test_scheme_case_is_accepted_and_value_is_kept(tmp_path: Path) -> None:
    """``HTTPS://`` — валидная схема (RFC 3986: без учёта регистра); ссылка отдаётся как есть."""
    upper = "HTTPS://example.org/x"
    links = _load(tmp_path, f"lessons:\n  L004: '{upper}'\n")
    assert links.for_lesson("L004") == upper


def test_repository_file_has_https_default() -> None:
    """В репозитории есть ``curriculum/lesson_links.yaml`` с валидным https-default."""
    links = YamlLessonLinks.load(CURRICULUM_DIR / "lesson_links.yaml")
    link = links.for_lesson("L001")
    assert link is not None and link.startswith("https://")
