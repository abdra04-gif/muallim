"""FR-61 (ADR-0077 п. 6): карточка шага «Суры» по слогам через настоящие обработчики и DI.

``navigation.py`` получает ``AyahSyllables`` из Dishka и передаёт
``screens.card(..., syllables=...)``. Чтобы не зависеть от статусов, которые человек ставит в
curriculum/syllables/ayat.yaml, ``SyllableLibrary.load`` читает временный файл (все строки ``ok``)
или отсутствующий файл (прежняя карточка). Окружение — как в test_settings_bot (SQLite, заглушка
распознавания); ``render.ayah`` подменён шпионом, который рисует прежнюю карточку, — пиксели
не проверяются.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml
from aiogram import Dispatcher
from dishka import AsyncContainer

from muallim.domain.curriculum import Curriculum
from muallim.presentation.telegram import render, texts
from muallim.presentation.telegram.callbacks import GoItem
from tests.integration import test_settings_bot as settings_bot
from tests.integration.test_settings_bot import _card_caption, _on_home

app = settings_bot.app  # окружение бота — та же фикстура

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not render.available(), reason="нет libraqm (brew install fribidi)"),
]

FATIHA_BASMALA = "L097-02"  # 1:1 в аль-Фатихе — номер 1
BAQARA_BASMALA = "L098-01"  # басмала перед аль-Бакарой — без номера
NOT_SURA = "L086-05"  # أَحَدٌ (112:1) — урок остановки


@pytest.fixture
def syllables_from(monkeypatch: pytest.MonkeyPatch) -> Callable[[Path], None]:
    """Библиотека бота читает ``path`` вместо curriculum/syllables/ayat.yaml."""
    from muallim.infrastructure.curriculum.syllables import SyllableLibrary  # noqa: PLC0415

    load = SyllableLibrary.load

    def redirect(path: Path) -> None:
        monkeypatch.setattr(SyllableLibrary, "load", staticmethod(lambda _: load(path)))

    return redirect


@pytest.fixture
def all_ok(tmp_path: Path, curriculum: Curriculum, syllables_from: Callable[[Path], None]) -> None:
    """Временный ayat.yaml: все аяты урока L097 и басмала — ``ok``, слово — одна клетка."""
    rows = [
        {"text": t, "status": "ok", "words": [[[w, "звук"]] for w in t.split(" ")]}
        for t in {i.text for i in curriculum.lesson("L097").items if i.quran}
    ]
    path = tmp_path / "syllables" / "ayat.yaml"
    path.parent.mkdir()
    path.write_text(yaml.safe_dump({"ayat": rows}, allow_unicode=True), encoding="utf-8")
    syllables_from(path)


@pytest.fixture
def ayah_calls(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    card = render.card

    def ayah(
        words: Any, number: int | None, position: tuple[int, int], scale: float = 1.0
    ) -> bytes:
        calls.append({"words": words, "number": number, "position": position, "scale": scale})
        text = " ".join("".join(cell.text for cell in word) for word in words)
        return card(text, set(), position, scale)

    monkeypatch.setattr(render, "ayah", ayah)
    return calls


async def test_sura_card_in_bot_is_drawn_by_syllables(
    all_ok: None, app: tuple[Dispatcher, AsyncContainer], ayah_calls: list[dict[str, Any]]
) -> None:
    dp, _ = app
    ali = await _on_home(dp)
    await ali.press(GoItem(item_id=FATIHA_BASMALA))
    [call] = ayah_calls
    assert call["number"] == 1 and call["scale"] == 1.0
    assert texts.CARD_HOW_TO_READ.split("{")[0] in _card_caption(ali)  # спойлер остался


async def test_basmala_before_sura_in_bot_has_no_number(
    all_ok: None, app: tuple[Dispatcher, AsyncContainer], ayah_calls: list[dict[str, Any]]
) -> None:
    dp, _ = app
    ali = await _on_home(dp)
    await ali.press(GoItem(item_id=BAQARA_BASMALA))
    [call] = ayah_calls
    assert call["number"] is None


async def test_card_outside_sura_lessons_is_not_by_syllables(
    all_ok: None, app: tuple[Dispatcher, AsyncContainer], ayah_calls: list[dict[str, Any]]
) -> None:
    dp, _ = app
    ali = await _on_home(dp)
    await ali.press(GoItem(item_id=NOT_SURA))
    assert ayah_calls == []


@pytest.fixture
def card_calls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Тексты, нарисованные прежней ``render.card``."""
    texts_: list[str] = []
    card = render.card

    def spy(text: str, accent: Any, position: tuple[int, int], scale: float = 1.0) -> bytes:
        texts_.append(text)
        return card(text, accent, position, scale)

    monkeypatch.setattr(render, "card", spy)
    return texts_


async def test_without_syllables_file_bot_shows_the_old_card(
    tmp_path: Path,
    syllables_from: Callable[[Path], None],
    app: tuple[Dispatcher, AsyncContainer],
    ayah_calls: list[dict[str, Any]],
    card_calls: list[str],
) -> None:
    syllables_from(tmp_path / "нет" / "ayat.yaml")
    dp, container = app
    ali = await _on_home(dp)
    await ali.press(GoItem(item_id=FATIHA_BASMALA))
    assert ayah_calls == []
    curriculum = await container.get(Curriculum)
    assert curriculum.item(FATIHA_BASMALA).text in card_calls, "карточка — прежняя render.card"
