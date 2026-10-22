"""Выход модели сохраняется числами, а не текстом repr() (ADR-0019, TD-FN-99).

Модель в тестах не нужна: подделки повторяют типы quran_muaalem.muaalem_typing
(Unit, SingleUnit, Sifa, MuaalemOutput), тензор — объект с .tolist(), как у torch.
"""

import json
from dataclasses import dataclass
from typing import Any

from muallim.infrastructure.asr.muaalem import _raw_output


class FakeTensor:
    """Как torch.Tensor: не сериализуется в JSON, но умеет .tolist()."""

    def __init__(self, values: list[Any]) -> None:
        self._values = values

    def tolist(self) -> list[Any]:
        return list(self._values)

    def __repr__(self) -> str:
        return f"tensor({self._values})"


@dataclass
class Unit:
    text: str
    probs: Any
    ids: Any


@dataclass
class SingleUnit:
    text: str
    prob: float
    idx: int


@dataclass
class Sifa:
    phonemes_group: str
    hams_or_jahr: SingleUnit | None
    ghonna: SingleUnit | None


@dataclass
class MuaalemOutput:
    phonemes: Unit
    sifat: list[Sifa]


PROBS = [0.998445307731628, 0.6354]


def _output() -> MuaalemOutput:
    return MuaalemOutput(
        phonemes=Unit("بِس", FakeTensor(PROBS), FakeTensor([2, 34])),
        sifat=[
            Sifa("بِ", SingleUnit("jahr", 0.9986445307731628, 2), None),
            Sifa("س", SingleUnit("hams", 0.999981164932251, 1), SingleUnit("x", 0.5, 1)),
        ],
    )


def test_phoneme_probabilities_are_numbers_with_full_precision() -> None:
    full = _raw_output(_output())["phonemes_full"]
    assert full == {"text": "بِس", "probs": PROBS, "ids": [2, 34]}


def test_sifat_are_a_list_of_dicts_not_a_repr_string() -> None:
    sifat = _raw_output(_output())["sifat_full"]
    assert isinstance(sifat, list)
    assert sifat[0] == {
        "phonemes_group": "بِ",
        "hams_or_jahr": {"text": "jahr", "prob": 0.9986445307731628, "idx": 2},
        "ghonna": None,
    }


def test_whole_output_survives_json_round_trip_without_repr() -> None:
    raw = _raw_output(_output())
    text = json.dumps(raw, ensure_ascii=False)
    assert "tensor(" not in text and "SingleUnit(" not in text
    assert json.loads(text) == raw


def test_phonemes_string_is_kept() -> None:
    assert _raw_output(_output())["phonemes"] == "بِس"


def test_unknown_object_still_saved_as_text_so_nothing_is_lost() -> None:
    @dataclass
    class Odd:
        text: str
        extra: object

    out = MuaalemOutput(phonemes=Odd("بِ", object()), sifat=[])  # type: ignore[arg-type]
    full = _raw_output(out)["phonemes_full"]
    assert full["text"] == "بِ"
    assert isinstance(full["extra"], str)  # неизвестное — строкой, но остальное — структурой
    json.dumps(_raw_output(out), ensure_ascii=False)
