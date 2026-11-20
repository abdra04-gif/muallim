"""Каждая карточка уроков 1–41, которую бот проверяет голосом, переводится в звуки MostafaMaroof
(FR-70 п. 1, ADR-0087 п. 8: «все карточки уроков 1–41 переводятся»; ADR-0088).

Записи фонетизатора бота взяты из `tests/fixtures/maroof_cards.json` (как пересобрать — в
`tests/fixtures/make_maroof_cards.py`): quran-transcript в CI нет, а проверка должна идти всегда.
Что фикстура совпадает с живым фонетизатором — `tests/integration/test_maroof_cards.py`.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from muallim.domain.curriculum import Curriculum

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "maroof_cards.json"
CARDS: list[dict[str, Any]] = json.loads(FIXTURE.read_text(encoding="utf-8"))

# Словарь модели: vocab.json MostafaMaroof/wav2vec2-arabic-phoneme-asr без [PAD], [UNK], «|», «sil».
_SOUNDS = """
$ $$ * ** < << A AA AH D DD E EE H HH I II S SS T TT U UU Z ZZ ^ ^^
a aa b bb d dd f ff g gg h hh i ii j jj k kk l ll m mm n nn p pp q qq r rr
s sh ss t th tt u uu v w ww x xx y yy z zz
"""
MODEL_SOUNDS = frozenset(_SOUNDS.split())

from muallim.infrastructure.asr.maroof_script import to_maroof  # noqa: E402


def test_fixture_covers_every_checkable_card_of_lessons_1_to_41(curriculum: Curriculum) -> None:
    """Программа поменялась, а фикстура нет — пересобрать её (`make_maroof_cards.py`)."""
    expected = {
        (item.id, item.text)
        for lesson in curriculum.lessons
        if 1 <= lesson.number <= 41
        for item in lesson.items
        if item.is_checkable
    }
    assert {(c["id"], c["text"]) for c in CARDS} == expected


def test_every_card_reading_converts_to_model_sounds() -> None:
    broken = []
    for card in CARDS:
        for name in ("wasl", "waqf"):
            try:
                sounds = to_maroof(card[name])
            except ValueError as error:
                broken.append(f"{card['id']} {name}: {error}")
                continue
            unknown = [s for s in sounds if s not in MODEL_SOUNDS]
            if not sounds or unknown:
                broken.append(f"{card['id']} {name}: {sounds} {unknown}")
    assert len(CARDS) > 250
    assert not broken, "\n".join(broken)


@pytest.mark.parametrize(
    ("card_id", "wasl"),
    [
        ("L001-01", ("b", "i", "s", "m", "i")),  # بِسْمِ
    ],
)
def test_book_card_in_model_sounds(card_id: str, wasl: tuple[str, ...]) -> None:
    card = next(c for c in CARDS if c["id"] == card_id)
    assert to_maroof(card["wasl"]) == wasl
