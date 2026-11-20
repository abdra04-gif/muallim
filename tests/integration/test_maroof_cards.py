"""Звуки MostafaMaroof из живого фонетизатора бота (FR-70 п. 1, ADR-0087 п. 8; ADR-0088 п. 2).

Фонетизатор (quran-transcript) ставится с моделью (extra ``ml``); без него тесты пропускаются.
Перевод всех карточек уроков 1–41 проверяется всегда по фикстуре —
`tests/unit/test_maroof_book_cards.py`; здесь — что фикстура не отстала от фонетизатора.
"""

import importlib.util
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration
needs_phonetizer = pytest.mark.skipif(
    importlib.util.find_spec("quran_transcript") is None, reason="нет extra ml"
)
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "maroof_cards.json"


def _readings(text: str) -> dict[str, str]:
    """Запись фонетизатора бота: слитно (wasl) и с остановкой (waqf)."""
    from muallim.infrastructure.asr.phonetizer import _references  # noqa: PLC0415

    return dict(_references(text)[1])


@needs_phonetizer
def test_fixture_matches_the_bot_phonetizer() -> None:
    """Расходится — пересобрать фикстуру (`tests/fixtures/make_maroof_cards.py`)."""
    stale = [
        card["id"]
        for card in json.loads(FIXTURE.read_text(encoding="utf-8"))
        if _readings(card["text"]) != {"wasl": card["wasl"], "waqf": card["waqf"]}
    ]
    assert not stale, stale


@needs_phonetizer
@pytest.mark.parametrize(
    ("text", "wasl"),
    [
        ("بُ", ("b", "u")),
        ("رَبَّ", ("r", "a", "bb", "a")),
        ("بَا", ("b", "aa")),
    ],
)
def test_book_card_in_model_sounds(text: str, wasl: tuple[str, ...]) -> None:
    from muallim.infrastructure.asr.maroof_script import to_maroof  # noqa: PLC0415

    assert to_maroof(_readings(text)["wasl"]) == wasl
